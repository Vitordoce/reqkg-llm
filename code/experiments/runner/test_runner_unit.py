"""Executor sem Neo4j: fixtures, dry-run, recusas, diretório da corrida, replay e entradas."""

import dataclasses
import hashlib
import json
import re
import tomllib
from pathlib import Path

import pytest

from domain.enums import Condition
from experiments.records import RunManifest
from experiments.runner import __main__ as cli
from experiments.runner import calibrate
from experiments.runner.clients import UsageMeter, load_replay
from experiments.runner.dry_run import Rate, estimate
from experiments.runner.execute import condition_order
from experiments.runner.fixtures import CONFIG_FILE, PROMISE_FILE, REPLAY_INDEX, RESPONSES, SET_FILE
from experiments.runner.fixtures.build_replays import render_index
from experiments.runner.inputs import InputError, load_promise, load_structural
from experiments.runner.run import make_plan
from experiments.runner.rundir import RunDirectory, RunRefused, build_manifest, preflight, sha256_file
from extraction import prompts
from extraction.client import (
    CallLog, CallTarget, LLMAPIError, LLMRequest, LLMResponse, MissingReplayError, OllamaClient, ReplayClient, invoke,
)
from extraction.client import REPO_ROOT
from domain.config import ExperimentConfig
from domain.serialization import load_toml

CONFIG = load_toml(CONFIG_FILE, ExperimentConfig)
SEED = CONFIG.evaluation.seed


def plan(**kwargs):
    structural = load_structural([SET_FILE], CONFIG.chunking)
    promise = load_promise(CONFIG.chunking, SEED, PROMISE_FILE)
    return make_plan(CONFIG_FILE, structural=structural, promise=promise, **kwargs)


def unrunnable_config(tmp_path: Path) -> Path:
    """A configuração do experimento com o modelo ainda por escolher."""
    text = re.sub(r'^(model_id|model_digest) = ".*"$', r'\1 = ""', CONFIG_FILE.read_text(encoding="utf-8"), flags=re.M)
    path = tmp_path / "experiment.toml"
    path.write_text(text, encoding="utf-8")
    return path


# Fixtures


def test_replay_index_matches_prompts_and_responses():
    assert REPLAY_INDEX.read_text(encoding="utf-8") == render_index(), \
        "rode .venv/bin/python code/experiments/runner/fixtures/build_replays.py"


def test_recorded_responses_are_marked_synthetic():
    for path in sorted(RESPONSES.glob("*.json")):
        assert json.loads(path.read_text(encoding="utf-8"))["synthetic"] is True, path.name


# Dry-run


def test_dry_run_counts_exact_calls_without_touching_anything():
    result = estimate(plan(), targets_per_chunk=1.0)
    rows = {(r["part"], r["stage"], r["condition"]): r for r in result.rows()}
    # 3 corridas x (entrevista 4 chunks -> 1 chamada, ata 11 -> 2, descrição 5 -> 1) com chunks_per_call = 6
    assert rows[("amostra", "extraction", "compartilhada")]["calls"] == 12
    # 20 chunks x 3 corridas x 1 alvo por chunk, em cada condição
    assert rows[("amostra", "refinement (estimado)", "LLM-only")]["calls"] == 60
    assert rows[("amostra", "refinement (estimado)", "REQKG-grounded")]["calls"] == 60
    # PROMISE sintético: projeto 97 com 1 item (1 chamada), projeto 98 com 8 (2 chamadas), 1 corrida
    assert rows[("PROMISE", "extraction", "compartilhada")]["calls"] == 3
    assert rows[("PROMISE", "classification", "compartilhada")]["calls"] == 9
    assert rows[("PROMISE", "classification_refinement", "REQKG-grounded")]["calls"] == 9
    graph, source = (rows[("amostra", "refinement (estimado)", c)]["input_tokens"] for c in ("REQKG-grounded", "LLM-only"))
    assert graph > source > 0
    graph, source = (rows[("PROMISE", "classification_refinement", c)]["input_tokens"] for c in ("REQKG-grounded", "LLM-only"))
    assert graph > source > 0
    assert result.totals()["output_tokens_max"] == result.totals()["calls"] * CONFIG.model.max_tokens


def test_dry_run_cli_writes_nothing(tmp_path, capsys):
    code = cli.main(["--dry-run", "--json", "--ingestion", str(SET_FILE), "--promise", "--promise-file", str(PROMISE_FILE),
                     "--promise-items", "PROMISE-NFR-9003", "--runs-root", str(tmp_path / "runs")])
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert {r["stage"] for r in report["rows"] if r["part"] == "PROMISE"} >= {"classification", "extraction"}
    assert not (tmp_path / "runs").exists()


def test_dry_run_estimates_time_from_a_measured_rate(tmp_path, capsys):
    per_call = {"extraction": 1000.0, "refinement": 300.0, "classification": 30.0, "classification_refinement": 40.0}
    rate = Rate(500.0, 20.0, 0.5, per_call, origin="teste")
    result = estimate(plan(), rate=rate)
    for row in result.rows():
        stage = row["stage"].removesuffix(" (estimado)")
        expected = row["input_tokens"] / 500 + row["calls"] * (per_call[stage] / 20 + 0.5)
        assert row["hours"] == round(expected / 3600, 2)
    assert result.totals()["hours"] == round(sum(r["hours"] for r in result.rows()), 2)
    assert "horas" in result.render() and "taxa de teste" in result.render()

    calibration = tmp_path / "calibracao.json"
    calibration.write_text(json.dumps({"rate": {"prompt_tokens_per_s": 500.0, "output_tokens_per_s": 20.0,
                                                "overhead_s_per_call": 0.5, "chars_per_token": 3.0,
                                                "output_tokens_per_call": per_call}}), encoding="utf-8")
    assert cli.main(["--dry-run", "--json", "--ingestion", str(SET_FILE), "--calibration", str(calibration)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["assumptions"]["chars_per_token"] == 3.0 and report["totals"]["hours"] > 0
    assert cli.main(["--dry-run", "--json", "--ingestion", str(SET_FILE), "--rate", "500,20,0.5,100"]) == 0
    assert json.loads(capsys.readouterr().out)["assumptions"]["rate"]["output_tokens_per_call"]["extraction"] == 100
    assert cli.main(["--dry-run", "--ingestion", str(SET_FILE), "--rate", "500,20"]) == 1
    assert "quatro números" in capsys.readouterr().err
    del per_call["classification"]
    calibration.write_text(json.dumps({"rate": {"prompt_tokens_per_s": 1, "output_tokens_per_s": 1,
                                                "overhead_s_per_call": 0, "output_tokens_per_call": per_call}}))
    assert cli.main(["--dry-run", "--ingestion", str(SET_FILE), "--calibration", str(calibration)]) == 1
    assert "não mediu a saída de classification" in capsys.readouterr().err


def test_calibration_measures_real_ollama_calls_and_feeds_the_dry_run(tmp_path, capsys):
    answers = {"extraction": (2000, 1000, 50.0), "refinement": (1500, 300, 15.0), "classification": (600, 20, 1.0),
               "classification_refinement": (900, 30, 1.5)}

    def server(method, url, body, timeout):
        if url.endswith("/api/tags"):
            return {"models": [{"name": CONFIG.model.model_id, "digest": CONFIG.model.model_digest}]}
        if url.endswith("/api/version"):
            return {"version": "0.32.4"}
        stage = server.stage
        prompt_tokens, output_tokens, eval_s = answers[stage]
        return {"model": CONFIG.model.model_id, "done_reason": "stop",
                "message": {"content": '{"promise_id": "PROMISE-NFR-9001", "label": "F", "rationale": null}'},
                "prompt_eval_count": prompt_tokens, "eval_count": output_tokens,
                "prompt_eval_duration": int(prompt_tokens / 500 * 1e9), "eval_duration": int(eval_s * 1e9),
                "load_duration": int(0.2e9), "total_duration": int((prompt_tokens / 500 + eval_s + 0.5) * 1e9)}

    client = OllamaClient(CONFIG.model, http=server)
    run_dir = tmp_path / "pilot-cal"
    log = CallLog(run_dir)
    prompt = prompts.classification_prompt("PROMISE-NFR-9001", "The system shall do X.")
    for stage in answers:
        server.stage = stage
        shared = stage in ("extraction", "classification")
        meta = ({"chunk_ids": ["chk-1"], "chunks_per_call": 1} if stage == "extraction" else
                {} if shared else {"context_item_ids": [], "context_strategy": "source_chunks"})
        invoke(client, LLMRequest(prompt, CallTarget("caso", None if shared else Condition.LLM_ONLY, 0, stage, "k"),
                                  meta), log)
    manifest = build_manifest(run_id="pilot-cal", model_id=CONFIG.model.model_id, replay=False, runs=1,
                              config_path=CONFIG_FILE, ingestion_sha256=[], freeze=None, command="teste")
    (run_dir / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")

    data = calibrate.calibrate([run_dir])
    rate = data["rate"]
    assert rate["prompt_tokens_per_s"] == pytest.approx(500, rel=1e-3)
    assert rate["output_tokens_per_s"] == pytest.approx(1350 / 67.5, rel=1e-3)
    assert rate["overhead_s_per_call"] == pytest.approx(0.5, abs=0.01)
    assert rate["output_tokens_per_call"] == {s: float(o) for s, (_, o, _) in answers.items()}
    assert data["stages"]["extraction"]["schema_valid"] == 1 and data["model"]["model_digest"] == CONFIG.model.model_digest
    output = tmp_path / "cal.json"
    assert calibrate.main(["pilot-cal", "--runs-root", str(tmp_path), "--output", str(output)]) == 0
    assert Rate.from_calibration(output).output_tokens_per_call["refinement"] == 300

    replayed = manifest.model_copy(update={"replay": True})
    (run_dir / "manifest.json").write_text(replayed.model_dump_json(), encoding="utf-8")
    assert calibrate.main(["pilot-cal", "--runs-root", str(tmp_path), "--output", str(output)]) == 1
    assert "só corridas reais do Ollama" in capsys.readouterr().err


def _plan_with_model(**update):
    config = CONFIG.model_copy(update={"model": CONFIG.model.model_copy(update=update)})
    return dataclasses.replace(plan(), config=config)


def test_dry_run_warns_when_the_largest_call_does_not_fit_the_context():
    result = estimate(plan())
    assert result.context_warning() is None
    assert 0 < result.totals()["max_input_tokens_per_call"] + CONFIG.model.max_tokens < CONFIG.model.num_ctx
    tight = estimate(_plan_with_model(num_ctx=CONFIG.model.max_tokens + 1))
    assert "não cabe em num_ctx" in tight.context_warning() and "não cabe" in tight.render()


def test_dry_run_counts_the_schema_only_where_it_goes_into_the_prompt():
    anthropic = estimate(_plan_with_model(provider="anthropic", model_digest="", seed=None, num_ctx=None))
    assert anthropic.totals()["input_tokens"] > estimate(plan()).totals()["input_tokens"]


# Recusas


def test_real_run_refuses_empty_model_id(tmp_path):
    config = load_toml(unrunnable_config(tmp_path), ExperimentConfig)
    with pytest.raises(RunRefused, match="model.model_id.*model.model_digest"):
        preflight(config, config_path=CONFIG_FILE, real=True, run_id="r1", pilot=False, freeze=None)


def test_real_run_refuses_without_freeze_unless_pilot(tmp_path):
    config = CONFIG
    with pytest.raises(RunRefused, match="congelamento.*--pilot"):
        preflight(config, config_path=CONFIG_FILE, real=True, run_id="r1", pilot=False, freeze=None)
    preflight(config, config_path=CONFIG_FILE, real=True, run_id="pilot-r1", pilot=True, freeze=None)


def test_pilot_is_marked_in_run_id(tmp_path):
    with pytest.raises(RunRefused, match="pilot-"):
        preflight(CONFIG, config_path=CONFIG_FILE, real=False, run_id="r1", pilot=True, freeze=None)
    with pytest.raises(RunRefused, match="reservado"):
        preflight(CONFIG, config_path=CONFIG_FILE, real=False, run_id="pilot-r1", pilot=False, freeze=None)


def test_freeze_manifest_must_match_tree(tmp_path):
    config = CONFIG
    files = {"code/experiments/config/experiment.toml": sha256_file(CONFIG_FILE)}
    manifest = {"format": "reqkg-freeze/1", "date": "2026-10-19", "roots": ["code/experiments/config/experiment.toml"],
                "missing": [], "files": files, "tree_sha256": "0" * 64}
    good = tmp_path / "freeze-ok.json"
    good.write_text(json.dumps(manifest), encoding="utf-8")
    preflight(config, config_path=CONFIG_FILE, real=True, run_id="r1", pilot=False, freeze=good)
    bad = tmp_path / "freeze-bad.json"
    bad.write_text(json.dumps({**manifest, "files": {k: "1" * 64 for k in files}}), encoding="utf-8")
    with pytest.raises(RunRefused, match="alterado: code/experiments/config/experiment.toml"):
        preflight(config, config_path=CONFIG_FILE, real=True, run_id="r1", pilot=False, freeze=bad)


def test_freeze_also_covers_the_config_given_on_the_command_line(tmp_path):
    """R77: a árvore pode bater com o congelamento e a --config apontar para outro arquivo."""
    roots = ["code/experiments/config/experiment.toml"]
    manifest = {"format": "reqkg-freeze/1", "date": "2026-10-19", "roots": roots, "missing": [],
                "files": {roots[0]: sha256_file(CONFIG_FILE)}, "tree_sha256": "0" * 64}
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps(manifest), encoding="utf-8")
    copy = tmp_path / "experiment.toml"
    copy.write_text(CONFIG_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    preflight(CONFIG, config_path=CONFIG_FILE, real=False, run_id="r1", pilot=False, freeze=freeze)
    with pytest.raises(RunRefused, match="fica fora do repositório e não está no congelamento"):
        preflight(CONFIG, config_path=copy, real=False, run_id="r1", pilot=False, freeze=freeze)
    other = REPO_ROOT / "code" / "experiments" / "metrics" / "fixtures" / "experiment.toml"
    with pytest.raises(RunRefused, match="metrics/fixtures/experiment.toml não fica em code/experiments/config/"):
        preflight(CONFIG, config_path=other, real=False, run_id="r1", pilot=False, freeze=freeze)


def test_frozen_config_outside_the_config_folder_is_refused(tmp_path):
    """E2-3: make freeze cobre code/ inteiro, então o TOML de um fixture também está congelado e inalterado."""
    fixture = REPO_ROOT / "code" / "experiments" / "metrics" / "fixtures" / "experiment.toml"
    roots = ["code/experiments/config/experiment.toml", "code/experiments/metrics/fixtures/experiment.toml"]
    manifest = {"format": "reqkg-freeze/1", "date": "2026-10-19", "roots": roots, "missing": [],
                "files": {roots[0]: sha256_file(CONFIG_FILE), roots[1]: sha256_file(fixture)}, "tree_sha256": "0" * 64}
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps(manifest), encoding="utf-8")
    preflight(CONFIG, config_path=CONFIG_FILE, real=False, run_id="r1", pilot=False, freeze=freeze)
    with pytest.raises(RunRefused, match="não fica em code/experiments/config/"):
        preflight(CONFIG, config_path=fixture, real=False, run_id="r1", pilot=False, freeze=freeze)


def test_refusal_and_replay_messages_point_to_the_right_place(tmp_path):
    with pytest.raises(RunRefused) as refused:
        preflight(CONFIG, config_path=CONFIG_FILE, real=False, run_id="r1", pilot=True, freeze=None)
    assert "pilot = true" in str(refused.value) and "não tem campo" not in str(refused.value)
    request = LLMRequest(prompts.classification_prompt("PROMISE-NFR-9999", "texto sem resposta gravada"),
                         CallTarget("PROMISE-NFR-9999", None, 0, "classification", "PROMISE-NFR-9999"))
    with pytest.raises(MissingReplayError) as missing:
        load_replay(REPLAY_INDEX).complete(request)
    assert "code/experiments/runner/fixtures/build_replays.py" in str(missing.value)
    assert "code/experiments/runner/fixtures/responses/" in str(missing.value)
    RunDirectory("r1", tmp_path)
    with pytest.raises(RunRefused, match="--resume"):
        RunDirectory.check_free("r1", tmp_path)


def test_cli_resume_needs_a_partial_run_and_refuses_before_the_graph(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli, "Graph", lambda *a: pytest.fail("o grafo não deve ser aberto"))
    code = cli.main(["r1", "--synthetic", "--resume", "--ingestion", str(SET_FILE), "--runs-root", str(tmp_path)])
    assert code == 1 and "não há corrida interrompida" in capsys.readouterr().err


class _Graph:
    def __init__(self, *args):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _stopped_run(monkeypatch, tmp_path, error: BaseException) -> str:
    monkeypatch.setattr(cli, "Neo4jSettings", type("S", (), {"from_env": staticmethod(lambda: None)}))
    monkeypatch.setattr(cli, "Graph", _Graph)

    def stop(*args, **kwargs):
        raise error

    monkeypatch.setattr(cli, "run", stop)
    return cli.main(["r1", "--synthetic", "--ingestion", str(SET_FILE), "--runs-root", str(tmp_path)])


def test_ctrl_c_message_names_the_reason_and_the_resume(tmp_path, capsys, monkeypatch):
    """E2-9: KeyboardInterrupt() tem texto vazio, e a mensagem saía 'ficou em …: .'."""
    assert _stopped_run(monkeypatch, tmp_path, KeyboardInterrupt()) == 2
    err = capsys.readouterr().err
    assert "interrompida pelo usuário (Ctrl-C)" in err and ": ." not in err
    assert "com --resume para continuar" in err and str(tmp_path / ".partial-r1") in err


def test_missing_recorded_response_does_not_suggest_resume(tmp_path, capsys, monkeypatch):
    """E2-9: a retomada pediria a mesma chamada, e a resposta continuaria faltando."""
    assert _stopped_run(monkeypatch, tmp_path, MissingReplayError("calls.jsonl: nenhuma chamada gravada")) == 2
    err = capsys.readouterr().err
    assert "nenhuma chamada gravada" in err and "--resume não resolve" in err
    assert "com --resume para continuar" not in err


def test_resume_refuses_another_promise_selection():
    """E2-2: --promise-items e --promise-limit não mudam o hash do arquivo do PROMISE, só a seleção."""
    from experiments.runner.rundir import check_resume

    def manifest(**filters):
        chosen = make_plan(CONFIG_FILE, structural=None, promise=load_promise(CONFIG.chunking, SEED, PROMISE_FILE, **filters))
        return build_manifest(run_id="r1", model_id="synthetic", replay=True, runs=1, config_path=CONFIG_FILE,
                              ingestion_sha256=[], promise_sha256=chosen.promise_sha256(),
                              selection_sha256=chosen.selection_sha256(), freeze=None, command="teste")

    started = manifest(items="PROMISE-NFR-9004,PROMISE-NFR-9101")
    assert started.selection_sha256 and json.loads(started.model_dump_json())["selection_sha256"]
    check_resume(started, manifest(items="PROMISE-NFR-9101,PROMISE-NFR-9004"))
    for filters in ({"items": "PROMISE-NFR-9004"}, {}, {"limit": 2}, {"projects": "98"}):
        other = manifest(**filters)
        assert other.promise_sha256 == started.promise_sha256
        with pytest.raises(RunRefused, match="selection_sha256.*--promise-items"):
            check_resume(started, other)
    assert manifest(limit=9).selection_sha256 != manifest().selection_sha256, "o filtro entra mesmo sem mudar os itens"
    legacy = RunManifest.model_validate({**json.loads(started.model_dump_json()), "selection_sha256": None})
    assert "selection_sha256" not in legacy.model_dump_json(), "manifesto antigo mantém os bytes"


def test_documented_pilot_draws_non_functional_items():
    """E2-7: com a semente da configuração, --promise-projects 1 --promise-limit 5 sorteia só itens F."""
    import re

    from retrieval.promise import PROMISE_JSONL

    labels = {}
    for line in PROMISE_JSONL.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        labels[item["promise_id"]] = item["label"]
    documents = [Path(__file__).with_name("README.md"), REPO_ROOT / "instructions" / "ROTEIRO_CORRIDA.md"]
    pilots = [(d.name, m) for d in documents
              for m in re.findall(r"--pilot[^\n`]*?--promise-projects (\S+) --promise-limit (\d+)",
                                  d.read_text(encoding="utf-8").replace("\\\n", " "))]
    assert pilots
    for name, (projects, limit) in pilots:
        drawn = load_promise(CONFIG.chunking, SEED, PROMISE_JSONL, projects=projects, limit=int(limit))
        found = {labels[i.promise_id] for items in drawn.items.values() for i in items}
        assert "F" in found and len(found - {"F"}) >= 2, (name, projects, sorted(found))


def test_stale_prompt_registry_refuses(monkeypatch):
    monkeypatch.setattr(prompts, "render_registry", lambda: "{}\n")
    with pytest.raises(RunRefused, match="REGISTRY.json"):
        preflight(CONFIG, config_path=CONFIG_FILE, real=False, run_id="r1", pilot=False, freeze=None)


def test_runs_override_needs_pilot():
    with pytest.raises(RunRefused, match="--runs só vale com --pilot"):
        plan(runs=1)
    assert plan(runs=1, pilot=True).structural_runs == 1


def test_cli_refuses_before_opening_the_graph(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli, "Graph", lambda *a: pytest.fail("o grafo não deve ser aberto"))
    config = unrunnable_config(tmp_path)
    code = cli.main(["r1", "--real", "--config", str(config), "--ingestion", str(SET_FILE), "--runs-root", str(tmp_path / "runs")])
    assert code == 1
    assert "model.model_id" in capsys.readouterr().err
    assert not (tmp_path / "runs").exists()


# Diretório e manifesto


def test_run_directory_never_overwrites(tmp_path):
    directory = RunDirectory("r1", tmp_path)
    assert directory.staging.name == ".partial-r1"
    with pytest.raises(RunRefused, match="interrompida"):
        RunDirectory("r1", tmp_path)
    final = directory.finalize()
    assert final == tmp_path / "r1" and not directory.staging.exists()
    assert {p.name for p in final.iterdir()} >= {"case_results.jsonl", "finals.jsonl", "classifications.jsonl"}
    with pytest.raises(RunRefused, match="nunca é sobrescrito"):
        RunDirectory("r1", tmp_path)
    with pytest.raises(RunRefused, match="run_id"):
        RunDirectory("../fora", tmp_path)


def test_manifest_hashes_and_packages():
    ingestion = load_structural([SET_FILE], CONFIG.chunking)
    manifest = build_manifest(run_id="r1", model_id="replay", replay=True, runs=3, config_path=CONFIG_FILE,
                              ingestion_sha256=list(ingestion.sha256), freeze=None, command="teste")
    RunManifest.model_validate(manifest.model_dump())
    assert manifest.config_sha256 == hashlib.sha256(CONFIG_FILE.read_bytes()).hexdigest()
    assert manifest.prompts_registry_sha256 == hashlib.sha256(prompts.REGISTRY_PATH.read_bytes()).hexdigest()
    processed = REPO_ROOT / "data" / "processed" / "ingestion" / "fixture.json"
    assert manifest.ingestion_sha256 == [hashlib.sha256(processed.read_bytes()).hexdigest()]
    assert {"python", "pydantic", "anthropic", "neo4j"} <= set(manifest.packages)


# Replay e tokens


def _request(run_index: int, key: str = "c0") -> LLMRequest:
    chunks = list(load_structural([SET_FILE], CONFIG.chunking).cases[0].chunks[:2])
    return LLMRequest(prompts.extraction_prompt(chunks), CallTarget("caso", None, run_index, "extraction", key),
                      {"chunk_ids": [c.chunk_id for c in chunks], "chunks_per_call": 2})


class _Recorded:
    def describe(self) -> dict[str, object]:
        return {"provider": "teste", "model_id": "claude-x"}

    def complete(self, request: LLMRequest) -> LLMResponse:
        run_index = request.target.run_index
        if run_index == 2:
            raise LLMAPIError("APIConnectionError")
        return LLMResponse(text=f"{{\"a\": {run_index}}}", model="claude-x",
                           usage={"input_tokens": 10 + run_index, "output_tokens": 5})


def test_replay_of_a_run_is_keyed_by_target_and_keeps_usage(tmp_path):
    log = CallLog(tmp_path)
    for run_index in range(3):
        try:
            invoke(_Recorded(), _request(run_index), log)
        except LLMAPIError:
            pass
    client = load_replay(log.path)
    assert isinstance(client, ReplayClient) and client.by_target and client.source_model() == "claude-x"
    meter = UsageMeter(client)
    assert meter.complete(_request(0)).text == "{\"a\": 0}"
    assert meter.complete(_request(1)).text == "{\"a\": 1}"
    assert meter.tokens([_request(0).target, _request(1).target]) == (21, 10)
    with pytest.raises(LLMAPIError, match="APIConnectionError"):
        invoke(meter, _request(2), CallLog(tmp_path / "refeita"))
    with pytest.raises(MissingReplayError):
        client.complete(_request(3))
    assert not load_replay(REPLAY_INDEX).by_target


# Entradas


def test_promise_filters():
    items = load_promise(CONFIG.chunking, SEED, PROMISE_FILE, items="PROMISE-NFR-9004,PROMISE-NFR-9101")
    assert [p.project_id for p in items.projects] == [97, 98]
    assert len(items.projects[1].chunks) == 8, "o grafo de B usa o projeto inteiro"
    assert {k: [i.promise_id for i in v] for k, v in items.items.items()} == {97: ["PROMISE-NFR-9101"], 98: ["PROMISE-NFR-9004"]}
    limited = load_promise(CONFIG.chunking, SEED, PROMISE_FILE, projects="98", limit=2)
    assert len(limited.items[98]) == 2 and len(limited.projects[0].chunks) == 8
    for kwargs, message in (({"items": "PROMISE-NFR-0001"}, "não estão"), ({"projects": "5"}, "não estão"),
                            ({"projects": "x"}, "números"), ({"limit": 0}, "pelo menos 1")):
        with pytest.raises(InputError, match=message):
            load_promise(CONFIG.chunking, SEED, PROMISE_FILE, **kwargs)


def test_promise_limit_draws_items_spread_over_the_projects_with_the_seed():
    def drawn(limit: int, seed: int = SEED) -> dict[int, list[str]]:
        chosen = load_promise(CONFIG.chunking, seed, PROMISE_FILE, limit=limit)
        return {project: [i.promise_id for i in items] for project, items in chosen.items.items()}

    assert {p: len(v) for p, v in drawn(2).items()} == {97: 1, 98: 1}, "um item por projeto antes do segundo"
    three = drawn(3)
    assert {p: len(v) for p, v in three.items()} == {97: 1, 98: 2}
    assert three[98] != ["PROMISE-NFR-9001", "PROMISE-NFR-9002"], "não são os primeiros por promise_id"
    assert drawn(3) == three
    assert {tuple(drawn(3, seed)[98]) for seed in range(6)} != {tuple(three[98])}, "o sorteio depende da semente"
    assert sum(len(v) for v in drawn(50).values()) == 9


def test_condition_order_alternates_by_case_and_follows_the_seed():
    cases = [f"PROMISE-NFR-{n:04d}" for n in range(1, 41)]
    orders = {case: condition_order(CONFIG, case) for case in cases}
    assert {orders[c] for c in cases} == {CONFIG.conditions, tuple(reversed(CONFIG.conditions))}
    assert orders == {case: condition_order(CONFIG, case) for case in cases}
    other = CONFIG.model_copy(update={"evaluation": CONFIG.evaluation.model_copy(update={"seed": SEED + 1})})
    assert any(condition_order(other, c) != orders[c] for c in cases)


def test_structural_cases_are_documents_and_sets_do_not_overlap(tmp_path):
    structural = load_structural([SET_FILE], CONFIG.chunking)
    assert [len(c.chunks) for c in structural.cases] == [11, 4, 5]
    assert [c.case_id for c in structural.cases] == sorted(d.source_id for d in structural.documents)
    with pytest.raises(InputError, match="aparece em"):
        load_structural([SET_FILE, SET_FILE], CONFIG.chunking)
    other = CONFIG.chunking.model_copy(update={"size_chars": 900})
    with pytest.raises(InputError, match="Rode a ingestão de novo"):
        load_structural([REPO_ROOT / "data" / "processed" / "ingestion" / "fixture.json"], other)


def test_config_is_the_frozen_one():
    assert tomllib.loads(CONFIG_FILE.read_text(encoding="utf-8"))["extraction"]["chunks_per_call"] == 6
    assert CONFIG.conditions == (Condition.LLM_ONLY, Condition.REQKG_GROUNDED)
