"""Métricas sobre os registros sintéticos de fixtures/. Cada valor esperado foi calculado à mão.

Corrida fixture-run, por corrida e condição (A = LLM-only, B = REQKG-grounded):

- a01 gera 4 requisitos (c0-R1, c1-R1, c1-R2, c2-R1), todos alvos de refinamento.
- a02 gera 5 (c0-R1, c1-R1 a c1-R4), alvos c1-R1, c1-R2 e c1-R3. Na corrida 2 a extração de a02 é inválida.
- K: a01 tem um ciclo depends_on (K3); a02 tem K1 (conflito e duplicata no mesmo par) e K2 (laço).
- Uma chamada de refinamento custa 100/20 tokens em A e 300/30 em B. Na corrida 1, o refinamento de
  a02 c1-R2 em A falha na API: custa zero e mantém o candidato.
- Cada chamada de extração custa 1000/200, com 100 dos 1000 tokens de entrada vindos do cache.
- Evidência de outro documento, só em B: a02 c1-R3 passa a citar só o chunk 4 de a01 (as três corridas
  em que a02 é válido), e a01 c1-R2 acrescenta o chunk 3 de a02 à evidência original (corridas 0 e 2).
  No corpus do caso as duas são P2: a02 c1-R3 fica incompleto, sem proveniência e não corrigido; a01
  c1-R2 não cobre a referência a01-R03. Com a união dos documentos, B teria 8, 8 e 3 completos,
  corrigidos 6, 7 e 3, e cobertura 1 nas três corridas.
- Violação P nova: em A, corridas 0 e 1, a01 c1-R1 ganha método e atributo e uma evidência sem citação.
  Sai de C2, C3 e C4 (3) para C2 e P4 (2); com P4 nova, não conta como corrigido. Sem essa regra, A
  teria 4 corrigidos nas corridas 0 e 1.
"""

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from domain.config import ContractError, ExperimentConfig
from domain.enums import Condition
from domain.serialization import load_toml
from experiments.annotation import validate_sample
from experiments.metrics import bertscore, pairing
from experiments.metrics.__main__ import main
from experiments.metrics.loading import _read_calls, load_corpus, load_run
from experiments.metrics.promise import INVALID, task_scores
from experiments.metrics.structural import aggregate, context_sizes, is_corrected, shared, structural

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
CONFIG = FIXTURES / "experiment.toml"
CHUNKING = load_toml(CONFIG, ExperimentConfig).chunking
INGESTION = FIXTURES / "ingestion.json"
SET_FILE = FIXTURES / "conjunto.toml"
REFERENCE = FIXTURES / "amostra"
LABELS = FIXTURES / "promise_labels.jsonl"
A, B = Condition.LLM_ONLY, Condition.REQKG_GROUNDED
TINY_MODEL = "hf-internal-testing/tiny-random-BertModel"


@pytest.fixture
def runs(tmp_path: Path) -> Path:
    shutil.copytree(FIXTURES / "runs", tmp_path / "runs")
    return tmp_path / "runs"


def cli(runs: Path, run_id: str, *args: str, config: Path = CONFIG) -> int:
    return main([run_id, "--runs-root", str(runs), "--config", str(config), *args])


def inputs(*extra: str) -> list[str]:
    return ["--ingestion", str(INGESTION), "--reference", str(REFERENCE), *extra]


def _load_decisions():
    spec = importlib.util.spec_from_file_location("fixture_decisions", FIXTURES / "decisions.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DECISIONS = _load_decisions()


def fill_sheets(runs: Path, decisions: dict[str, str] | None = None) -> None:
    for i in range(3):
        DECISIONS.fill(pairing.sheet_path(runs / "fixture-run", i), decisions or DECISIONS.DECISIONS)


def lock_all(runs: Path) -> None:
    for i in range(3):
        assert cli(runs, "fixture-run", "lock", "--run-index", str(i), *inputs()) == 0


def read_csv(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_fixtures_are_current():
    result = subprocess.run([sys.executable, str(FIXTURES / "build.py"), "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_readme_commands_run_in_zsh():
    """E2-9: M="..."; $M falha em zsh, que não divide a variável em palavras."""
    import re

    blocks = "\n".join(re.findall(r"```sh\n(.*?)```", (HERE / "README.md").read_text(encoding="utf-8"), flags=re.S))
    assert "$M" not in blocks and 'M="' not in blocks
    [definition] = [line for line in blocks.splitlines() if line.startswith("M() {")]
    shell = shutil.which("zsh") or shutil.which("bash")
    if shell is None:
        pytest.skip("sem zsh nem bash")
    done = subprocess.run([shell, "-c", f"{definition}\nM --help"], cwd=HERE.parents[2], capture_output=True,
                          text=True, env={"PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin"})
    assert done.returncode == 0, done.stderr
    assert "{sheet,lock,compute}" in done.stdout


def test_reference_fixture_is_valid():
    assert validate_sample(REFERENCE).errors == []


# Métricas por regra

# (corrida, condição): gerados, completos, C4, sem proveniência, violações K, corrigidos, inválidos,
# tokens de refinamento (entrada, saída), alvos, aceitos, recusados, com falha, evidências de outro documento.
EXPECTED_STRUCTURAL = {
    (0, A): (9, 5, 0, 1, 3, 3, 0, (700, 140), 7, 6, 1, 0, 0),
    (0, B): (9, 7, 0, 2, 3, 5, 0, (2100, 210), 7, 7, 0, 0, 2),
    (1, A): (9, 5, 0, 1, 3, 3, 0, (600, 120), 7, 6, 0, 1, 0),
    (1, B): (9, 7, 0, 1, 3, 6, 0, (2100, 210), 7, 7, 0, 0, 1),
    (2, A): (4, 2, 1, 1, 1, 2, 1, (400, 80), 4, 3, 1, 0, 0),
    (2, B): (4, 3, 0, 1, 1, 3, 1, (1200, 120), 4, 4, 0, 0, 1),
}


@pytest.fixture(scope="module")
def fixture_run():
    run = load_run(FIXTURES / "runs" / "fixture-run")
    return run, load_corpus([INGESTION], run.manifest, CHUNKING)


def test_structural_counts_per_run_and_condition(fixture_run):
    run, corpus = fixture_run
    found = {
        (r.run_index, r.condition): (r.generated, r.complete, r.c4, r.unsupported, r.k_violations, r.corrected,
                                     r.invalid_cases, (r.refinement.input_tokens, r.refinement.output_tokens),
                                     r.targets, r.accepted, r.refused, r.failed, r.foreign_evidence)
        for r in structural(run, corpus)
    }
    assert found == EXPECTED_STRUCTURAL


def test_evidence_from_another_document_is_p2_in_the_case_corpus(fixture_run):
    run, corpus = fixture_run
    final = run.final("a02", 0, B).output
    c1_r3 = next(r for r in final.requirements if r.key == "c1-R3")
    [evidence] = c1_r3.evidence
    assert corpus.index.resolves(evidence) and corpus.index.quote_found(evidence)
    assert not corpus.case("a02").resolves(evidence)
    assert corpus.case("a01").resolves(evidence)


def test_corrected_needs_fewer_cp_and_no_new_p():
    c2, c3, c4 = ("C2", "priority ausente"), ("C3", "verification_method ausente"), ("C4", "não funcional sem atributo")
    p4 = ("P4", "fato extraído sem citação")
    p2_a, p2_b = ("P2", "src-a/chk-a não existe no corpus"), ("P2", "src-b/chk-b não existe no corpus")
    assert is_corrected([c2, c3, c4], [c2])
    assert not is_corrected([c2, c3, c4], [c2, p4])  # 3 para 2, mas P4 é nova
    assert not is_corrected([p2_a], [p2_b])  # mesma contagem e P2 nova em outro chunk
    assert is_corrected([c2, p4], [p4])  # P4 já estava na extração


def test_structural_ratios(fixture_run):
    run, corpus = fixture_run
    metrics = {(r.run_index, r.condition): r.metrics() for r in structural(run, corpus)}
    assert metrics[(0, A)]["completeness_ratio"] == pytest.approx(5 / 9)
    assert metrics[(0, B)]["completeness_ratio"] == pytest.approx(7 / 9)
    assert metrics[(2, B)]["completeness_ratio"] == pytest.approx(3 / 4)
    assert metrics[(2, A)]["c4_rate"] == pytest.approx(1 / 4)
    assert metrics[(0, A)]["c4_rate"] == 0
    assert metrics[(0, B)]["foreign_evidence"] == 2
    assert metrics[(0, B)]["unsupported_claim_rate"] == pytest.approx(2 / 9)
    assert metrics[(1, B)]["unsupported_claim_rate"] == pytest.approx(1 / 9)
    assert metrics[(2, A)]["unsupported_claim_rate"] == pytest.approx(1 / 4)
    assert metrics[(0, A)]["rule_violation_rate"] == pytest.approx(3 / 9)
    assert metrics[(2, B)]["rule_violation_rate"] == pytest.approx(1 / 4)
    assert metrics[(0, A)]["tokens_per_corrected"] == pytest.approx(840 / 3)
    assert metrics[(0, A)]["input_tokens_per_corrected"] == pytest.approx(700 / 3)
    assert metrics[(0, B)]["tokens_per_corrected"] == pytest.approx(2310 / 5)
    assert metrics[(1, A)]["tokens_per_corrected"] == pytest.approx(720 / 3)
    assert metrics[(1, B)]["output_tokens_per_corrected"] == pytest.approx(210 / 6)
    assert metrics[(2, B)]["tokens_per_corrected"] == pytest.approx(1320 / 3)


def test_aggregate_mean_sd_and_values(fixture_run):
    run, corpus = fixture_run
    rows = [(m, r.condition.value, r.run_index, v) for r in structural(run, corpus) for m, v in r.metrics().items()]
    by_key = {(a.metric, a.condition): a for a in aggregate(rows)}
    completeness_a = by_key[("completeness_ratio", A.value)]
    assert completeness_a.values == pytest.approx((5 / 9, 5 / 9, 1 / 2))
    assert completeness_a.mean == pytest.approx(29 / 54)
    assert completeness_a.sd == pytest.approx((1 / 972) ** 0.5)
    unsupported_b = by_key[("unsupported_claim_rate", B.value)]
    assert unsupported_b.mean == pytest.approx(7 / 36)
    assert unsupported_b.sd == pytest.approx(7 ** 0.5 / 36)
    tokens_b = by_key[("tokens_per_corrected", B.value)]
    assert tokens_b.values == pytest.approx((462, 385, 440))
    assert tokens_b.mean == pytest.approx(429)
    assert tokens_b.sd == pytest.approx(1573 ** 0.5)
    invalid = by_key[("invalid_cases", A.value)]
    assert (invalid.mean, invalid.sd) == pytest.approx((1 / 3, 3 ** -0.5))


def test_undefined_run_is_left_out_of_mean():
    [only] = aggregate([("m", "A", 0, 0.5), ("m", "A", 1, None), ("m", "A", 2, 1.0)])
    assert only.values == (0.5, None, 1.0)
    assert (len(only.defined), only.mean, only.sd) == (2, 0.75, pytest.approx(0.125 ** 0.5))


def shared_table(run) -> dict:
    def cell(u):
        return (u.calls, u.input_tokens, u.output_tokens)

    return {s.run_index: (cell(s.sample_extraction), cell(s.promise_extraction), cell(s.classification),
                          dict(s.rejections)) for s in shared(run)}


def test_shared_extraction_cost_and_rejections(fixture_run):
    run, _ = fixture_run
    assert shared_table(run) == {
        0: ((5, 5000, 1000), (0, 0, 0), (0, 0, 0), {"W1": 4, "W5": 1}),
        1: ((5, 5000, 1000), (0, 0, 0), (0, 0, 0), {"W1": 4, "W5": 1}),
        2: ((5, 5000, 1000), (0, 0, 0), (0, 0, 0), {"W1": 3}),
    }


# Corrida com amostra e PROMISE: as chamadas de fixture-promise somadas às de fixture-run. Extração da amostra:
# 5 chamadas de 1000/200 por corrida. Projetos 901 e 902 do PROMISE: 5 itens cada, em chamadas de 2, 2 e 1, ou
# seja 6 chamadas de 800/150 (4800/900), só na corrida 0. Primeira classificação: 10 chamadas de 120/10.
def test_shared_cost_separates_sample_promise_projects_and_classification(fixture_run):
    run = load_run(FIXTURES / "runs" / "fixture-run")
    _read_calls(FIXTURES / "runs" / "fixture-promise" / "calls.jsonl", run)
    assert shared_table(run) == {
        0: ((5, 5000, 1000), (6, 4800, 900), (10, 1200, 100), {"W1": 4, "W5": 1}),
        1: ((5, 5000, 1000), (0, 0, 0), (0, 0, 0), {"W1": 4, "W5": 1}),
        2: ((5, 5000, 1000), (0, 0, 0), (0, 0, 0), {"W1": 3}),
    }


def test_shared_cost_of_a_promise_only_run(runs):
    pytest.importorskip("sklearn")
    assert cli(runs, "fixture-promise", "compute", "--promise-labels", str(LABELS)) == 0
    metrics = runs / "fixture-promise" / "metrics"
    [row] = read_csv(metrics / "shared_by_run.csv")
    assert [row[k] for k in ("extraction_calls", "extraction_input_tokens", "promise_extraction_calls",
                             "promise_extraction_input_tokens", "promise_extraction_output_tokens",
                             "classification_calls", "classification_input_tokens",
                             "classification_output_tokens")] == ["0", "0", "6", "4800", "900", "10", "1200", "100"]
    summary = (metrics / "summary.md").read_text(encoding="utf-8")
    assert "| 0 | 0 / 0/0 | 6 / 4800/900 | 10 / 1200/100 |" in summary


# Ingestão a partir do arquivo de conjunto


def test_set_file_is_ingested_in_memory_and_matches_the_manifest(fixture_run, runs):
    run, from_json = fixture_run
    output = HERE.parents[2] / "data" / "processed" / "ingestion" / "conjunto.json"
    existed = output.exists()
    from_toml = load_corpus([SET_FILE], run.manifest, CHUNKING)
    assert output.exists() == existed
    assert from_toml.index == from_json.index
    [(path, digest, how)] = from_toml.files
    assert digest == run.manifest.ingestion_sha256[0] == hashlib.sha256(INGESTION.read_bytes()).hexdigest()
    assert path == "code/experiments/metrics/fixtures/conjunto.toml" and "ingerido em memória" in how
    assert cli(runs, "fixture-run", "compute", "--ingestion", str(SET_FILE), "--skip-bertscore") == 0
    summary = (runs / "fixture-run" / "metrics" / "summary.md").read_text(encoding="utf-8")
    assert f"`code/experiments/metrics/fixtures/conjunto.toml`, ingerido em memória" in summary


def test_set_file_ingested_with_other_chunking_is_refused(fixture_run):
    run, _ = fixture_run
    other = CHUNKING.model_copy(update={"size_chars": 40})
    with pytest.raises(ContractError, match="ingestion_sha256 da corrida"):
        load_corpus([SET_FILE], run.manifest, other)


# Tamanho do contexto. Cada chunk da chamada tem 100 caracteres; B soma 4 itens de 50 ao alvo gravado
# no grafo e 1 ao recusado na gravação (a01 c1-R2, a01 c2-R1 e a02 c1-R3). Chamadas: a01 c0 e c1 com
# 2 chunks, c2 com 1; a02 c0 e c1 com 2.
# (corrida, condição, estrato): alvos, itens (média, mediana, máx.), caracteres (média, mediana, máx.).
EXPECTED_CONTEXT = {
    (0, A, "all"): (7, (13 / 7, 2, 2), (1300 / 7, 200, 200)),
    (0, A, "written"): (4, (2, 2, 2), (200, 200, 200)),
    (0, A, "rejected_w"): (3, (5 / 3, 2, 2), (500 / 3, 200, 200)),
    (0, B, "all"): (7, (32 / 7, 6, 6), (2250 / 7, 400, 400)),
    (0, B, "written"): (4, (6, 6, 6), (400, 400, 400)),
    (0, B, "rejected_w"): (3, (8 / 3, 3, 3), (650 / 3, 250, 250)),
    (2, A, "rejected_w"): (2, (3 / 2, 3 / 2, 2), (150, 150, 200)),
    (2, B, "all"): (4, (17 / 4, 9 / 2, 6), (300, 325, 400)),
    (2, B, "rejected_w"): (2, (5 / 2, 5 / 2, 3), (200, 200, 250)),
}


def test_context_size_per_target_and_stratum(fixture_run):
    run, _ = fixture_run
    found = {(s.run_index, s.condition, s.stratum): (s.items.n, s.items.mean, s.items.median, s.items.max,
                                                      s.chars.mean, s.chars.median, s.chars.max)
             for s in context_sizes(run)}
    for key, (n, items, chars) in EXPECTED_CONTEXT.items():
        assert found[key] == pytest.approx((n, *items, *chars)), key
    assert found[(1, B, "all")] == found[(0, B, "all")]
    assert all(s.without_context == 0 for s in context_sizes(run))


# Pareamento


@pytest.fixture(scope="module")
def references(fixture_run):
    run, corpus = fixture_run
    reference = validate_sample(REFERENCE).reference
    return pairing.references_by_case(reference, corpus, run.case_ids())


def test_candidates_come_from_the_extraction_call_chunks(fixture_run, references):
    run, corpus = fixture_run
    found = {(g.case_id, g.condition, g.key): g.candidates for g in pairing.generated(run, corpus, references, 0)}
    assert found[("a01", A, "c0-R1")] == ("a01-R01",)
    assert found[("a01", B, "c1-R1")] == ("a01-R02", "a01-R03")
    assert found[("a01", A, "c2-R1")] == ()
    assert found[("a02", A, "c0-R1")] == ()
    assert found[("a02", B, "c1-R4")] == ("a02-R01", "a02-R02")


def test_sheet_merges_equal_statements_and_hides_the_condition(fixture_run, references):
    run, corpus = fixture_run
    rows = {i: pairing.sheet_rows(pairing.generated(run, corpus, references, i), 20261010, i) for i in range(3)}
    assert [len(rows[i]) for i in range(3)] == [8, 8, 4]
    by_statement = {row.statement: row for row in rows[0]}
    export = by_statement["O sistema deve exportar relatório em planilha."]
    assert export.members == (("a02", A.value, "c1-R2"), ("a02", B.value, "c1-R2"))
    assert by_statement["A tela de cadastro deve abrir rápido."].members == (("a01", A.value, "c1-R1"),)
    assert by_statement["A tela de cadastro deve abrir rapidamente no tablet."].members == (("a01", B.value, "c1-R1"),)
    again = pairing.sheet_rows(pairing.generated(run, corpus, references, 0), 20261010, 0)
    assert again == rows[0]
    assert {r.code for r in rows[0]} != {r.code for r in rows[1]}
    text = pairing.render_sheet("fixture-run", 0, rows[0], validate_sample(REFERENCE).reference)
    for leak in ("LLM-only", "REQKG", "c1-R", "c0-R", "condition", "priority"):
        assert leak not in text


# (corrida, condição): gerados, pareados, gerados sem par, sem candidata, decisão nenhum, duplicata,
# referências sem par, cobertos, cobertos / pareados, cobertos / referências. Cinco referências por corrida,
# inclusive na corrida 2, em que a02 é inválido. B não cobre a01-R03 nas corridas 0 e 2: a evidência que
# contém a citação é de a02.
EXPECTED_PAIRING = {
    (0, A): (9, 5, 4, 2, 1, 1, 0, 5, 1.0, 1.0),
    (0, B): (9, 5, 4, 2, 1, 1, 0, 4, 4 / 5, 4 / 5),
    (1, A): (9, 5, 4, 2, 1, 1, 0, 5, 1.0, 1.0),
    (1, B): (9, 5, 4, 2, 1, 1, 0, 5, 1.0, 1.0),
    (2, A): (4, 3, 1, 1, 0, 0, 2, 3, 1.0, 3 / 5),
    (2, B): (4, 3, 1, 1, 0, 0, 2, 2, 2 / 3, 2 / 5),
}


def pairing_table(runs: Path) -> dict:
    return {
        (int(r["run_index"]), Condition(r["condition"])): (
            int(r["generated"]), int(r["paired"]), int(r["generated_unpaired"]), int(r["unpaired_no_candidates"]),
            int(r["unpaired_decided_none"]), int(r["unpaired_duplicate"]), int(r["references_unpaired"]),
            int(r["covered"]), pytest.approx(float(r["provenance_coverage"]), abs=1e-6),
            pytest.approx(float(r["provenance_coverage_of_references"]), abs=1e-6),
        )
        for r in read_csv(runs / "fixture-run" / "metrics" / "pairing_by_run.csv")
    }


def test_blind_pairing_end_to_end(runs, capsys):
    run_dir = runs / "fixture-run"
    assert cli(runs, "fixture-run", "sheet", *inputs()) == 0
    shutil.rmtree(pairing.pairing_dir(run_dir) / "key")  # sem registro, compute não abre a chave
    assert cli(runs, "fixture-run", "compute", *inputs("--skip-bertscore")) == 0
    assert "pareamento pendente nas corridas [0, 1, 2]" in capsys.readouterr().out
    assert not (run_dir / "metrics" / "pairing_by_run.csv").exists()

    assert cli(runs, "fixture-run", "sheet", *inputs("--force")) == 0
    fill_sheets(runs)
    lock_all(runs)
    lock = json.loads(pairing.lock_path(run_dir, 0).read_text(encoding="utf-8"))
    assert lock["sheet_sha256"] == hashlib.sha256(pairing.sheet_path(run_dir, 0).read_bytes()).hexdigest()
    assert (lock["items"], lock["decided_none"]) == (8, 1)
    assert cli(runs, "fixture-run", "compute", *inputs("--skip-bertscore")) == 0
    assert pairing_table(runs) == EXPECTED_PAIRING

    pairs = read_csv(run_dir / "metrics" / "pairs.csv")
    outcome = {(p["run_index"], p["condition"], p["case"], p["key"]): (p["outcome"], p["reference"]) for p in pairs}
    assert outcome[("0", A.value, "a02", "c1-R1")] == ("paired", "a02-R01")
    assert outcome[("0", A.value, "a02", "c1-R3")] == ("duplicate", "")
    assert outcome[("2", B.value, "a01", "c1-R2")] == ("paired", "a01-R03")

    summary = (run_dir / "metrics" / "summary.md").read_text(encoding="utf-8")
    assert "PYTHONPATH=code .venv/bin/python -m experiments.metrics fixture-run" in summary
    assert "compute --ingestion code/experiments/metrics/fixtures/ingestion.json" in summary
    assert lock["sheet_sha256"] in summary
    assert "BERTScore não calculado: --skip-bertscore" in summary
    assert "`provenance_coverage_of_references` = covered / R" in summary
    assert "| 0 | REQKG-grounded | rejected_w | 3 | 2.6667 / 3.0000 / 3.0000 | 216.6667 / 250.0000 / 250.0000 |" in summary

    context = {(r["run_index"], r["condition"], r["stratum"]): r
               for r in read_csv(run_dir / "metrics" / "context_by_run.csv")}
    assert context[("2", B.value, "all")]["chars_median"] == "325.000000"
    stats = {(r["metric"], r["condition"]): r for r in read_csv(run_dir / "metrics" / "summary.csv")}
    assert float(stats[("context_items_mean", B.value)]["mean"]) == pytest.approx((32 / 7 * 2 + 17 / 4) / 3)
    assert float(stats[("provenance_coverage_of_references", B.value)]["mean"]) == pytest.approx((4 / 5 + 1 + 2 / 5) / 3)
    assert stats[("foreign_evidence", B.value)]["values"] == "2.000000;1.000000;1.000000"


def test_sheet_is_not_rewritten_and_lock_validates_decisions(runs, capsys):
    run_dir = runs / "fixture-run"
    assert cli(runs, "fixture-run", "sheet", *inputs()) == 0
    assert cli(runs, "fixture-run", "sheet", *inputs()) == 1
    assert "a planilha já existe" in capsys.readouterr().err
    assert cli(runs, "fixture-run", "lock", "--run-index", "0", *inputs()) == 1
    assert "decision vazio" in capsys.readouterr().err

    fill_sheets(runs, {statement: "a01-R03" for statement in DECISIONS.DECISIONS})
    assert cli(runs, "fixture-run", "lock", "--run-index", "0", *inputs()) == 1
    assert "não é 'nenhum' nem uma das candidatas" in capsys.readouterr().err
    assert not pairing.lock_path(run_dir, 0).exists()


def test_registered_decisions_do_not_change(runs, capsys):
    run_dir = runs / "fixture-run"
    assert cli(runs, "fixture-run", "sheet", *inputs()) == 0
    fill_sheets(runs)
    lock_all(runs)
    assert cli(runs, "fixture-run", "lock", "--run-index", "0", *inputs()) == 0  # mesmo arquivo: idempotente
    sheet = pairing.sheet_path(run_dir, 0)
    sheet.write_text(sheet.read_text(encoding="utf-8").replace('"nenhum"', '"a02-R02"'), encoding="utf-8")
    capsys.readouterr()
    assert cli(runs, "fixture-run", "lock", "--run-index", "0", *inputs()) == 1
    assert "Decisão registrada não muda" in capsys.readouterr().err
    assert cli(runs, "fixture-run", "compute", *inputs("--skip-bertscore")) == 1
    assert "difere do registrado" in capsys.readouterr().err
    assert cli(runs, "fixture-run", "sheet", *inputs("--force")) == 1
    assert "já foram registradas" in capsys.readouterr().err


def test_correction_after_lock_is_applied_and_listed(runs):
    run_dir = runs / "fixture-run"
    assert cli(runs, "fixture-run", "sheet", *inputs()) == 0
    fill_sheets(runs)
    lock_all(runs)
    import tomllib

    items = tomllib.loads(pairing.sheet_path(run_dir, 0).read_text(encoding="utf-8"))["item"]
    code = next(i["code"] for i in items if i["statement"] == "O sistema deve guardar os registros de semeadura por dois anos.")
    pairing.corrections_path(run_dir, 0).write_text(
        f'[[correction]]\ncode = "{code}"\ndecision = "nenhum"\ndate = "2026-10-20"\nreason = "erro de leitura"\n',
        encoding="utf-8",
    )
    assert cli(runs, "fixture-run", "compute", *inputs("--skip-bertscore")) == 0
    table = pairing_table(runs)
    assert table[(0, A)][:7] == (9, 5, 4, 2, 2, 0, 0)
    assert table[(1, A)][:7] == (9, 5, 4, 2, 1, 1, 0)
    summary = (run_dir / "metrics" / "summary.md").read_text(encoding="utf-8")
    assert f"Correção {code} em 2026-10-20: nenhum (erro de leitura)" in summary


# Conferências de entrada


def test_config_must_be_the_one_of_the_run(runs, tmp_path, capsys):
    other = tmp_path / "outra.toml"
    other.write_text(CONFIG.read_text(encoding="utf-8").replace("seed = 20261010", "seed = 1"), encoding="utf-8")
    assert cli(runs, "fixture-run", "compute", *inputs("--skip-bertscore"), config=other) == 1
    assert "difere do config_sha256 da corrida" in capsys.readouterr().err


def test_reference_artifact_must_have_the_text_of_the_ingested_document(runs, tmp_path, capsys):
    """E2-6: o nome a01 pareia o artefato com o documento; o texto tem de ser o mesmo."""
    reference = tmp_path / "amostra"
    shutil.copytree(REFERENCE, reference)
    artifact = reference / "a01.txt"
    artifact.write_text(artifact.read_text(encoding="utf-8").rstrip("\n") + "\n\nParágrafo acrescentado depois.\n",
                        encoding="utf-8")
    assert validate_sample(reference).errors == []
    for command in (["sheet"], ["compute", "--skip-bertscore"]):
        assert cli(runs, "fixture-run", command[0], "--ingestion", str(INGESTION), "--reference", str(reference),
                   *command[1:]) == 1
        err = capsys.readouterr().err
        assert "mesmo nome e textos diferentes: a01.txt" in err
        assert "code/experiments/metrics/fixtures/amostra/a01.txt" in err and "a02" not in err
    crlf = tmp_path / "crlf"
    shutil.copytree(REFERENCE, crlf)
    original = (REFERENCE / "a01.txt").read_bytes()
    (crlf / "a01.txt").write_bytes(original.replace(b"\n", b"\r\n"))
    assert cli(runs, "fixture-run", "sheet", "--ingestion", str(INGESTION), "--reference", str(crlf)) == 0, \
        "o texto é comparado depois da normalização da ingestão"


def test_ingestion_must_be_the_one_of_the_run(runs, capsys):
    other = HERE.parents[2] / "data" / "processed" / "ingestion" / "fixture.json"
    assert cli(runs, "fixture-run", "compute", "--ingestion", str(other), "--skip-bertscore") == 1
    assert "ingestion_sha256 da corrida" in capsys.readouterr().err


# BERTScore


def test_bertscore_is_refused_with_empty_model(runs, capsys):
    with pytest.raises(bertscore.BertScoreUnavailable, match="evaluation.bertscore_model está vazio"):
        bertscore.resolve("")
    assert cli(runs, "fixture-run", "sheet", *inputs()) == 0
    fill_sheets(runs)
    lock_all(runs)
    capsys.readouterr()
    assert cli(runs, "fixture-run", "compute", *inputs()) == 1
    err = capsys.readouterr().err
    assert "evaluation.bertscore_model está vazio" in err and "--skip-bertscore" in err


def test_bertscore_with_small_test_model(runs, tmp_path):
    pytest.importorskip("bert_score")
    try:
        bertscore.resolve(TINY_MODEL, "main", 2)
    except bertscore.BertScoreUnavailable as error:
        pytest.skip(f"modelo de teste indisponível: {error}")
    config = tmp_path / "experiment_bertscore.toml"
    config.write_text(CONFIG.read_text(encoding="utf-8").replace('bertscore_model = ""', f'bertscore_model = "{TINY_MODEL}"'),
                      encoding="utf-8")
    manifest = runs / "fixture-run" / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["config_sha256"] = hashlib.sha256(config.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(data), encoding="utf-8")
    assert cli(runs, "fixture-run", "sheet", *inputs(), config=config) == 0
    fill_sheets(runs)
    for i in range(3):
        assert cli(runs, "fixture-run", "lock", "--run-index", str(i), *inputs(), config=config) == 0
    assert cli(runs, "fixture-run", "compute", *inputs("--bertscore-num-layers", "2"), config=config) == 0

    metrics = runs / "fixture-run" / "metrics"
    pairs = [p for p in read_csv(metrics / "pairs.csv") if p["outcome"] == "paired"]
    identical = [p for p in pairs if p["statement"] == p["reference_statement"]]
    assert {(p["condition"], p["case"], p["key"]) for p in identical if p["run_index"] == "0"} == {
        (B.value, "a01", "c1-R1"), (A.value, "a02", "c1-R1"), (B.value, "a02", "c1-R1"), (A.value, "a02", "c1-R2"),
    }
    assert all(float(p["bertscore_f1"]) == pytest.approx(1.0, abs=1e-5) for p in identical)
    for row in read_csv(metrics / "pairing_by_run.csv"):
        mine = [float(p["bertscore_f1"]) for p in pairs if (p["run_index"], p["condition"]) == (row["run_index"], row["condition"])]
        assert float(row["bertscore_f1"]) == pytest.approx(sum(mine) / len(mine), abs=1e-6)
    summary = (metrics / "summary.md").read_text(encoding="utf-8")
    revision = summary.split("revision ", 1)[1].split(",", 1)[0]
    assert len(revision) == 40 and all(c in "0123456789abcdef" for c in revision)
    assert f"model {TINY_MODEL}" in summary and "num_layers 2" in summary


# PROMISE

# (classificação, tarefa): precisão macro, revocação macro, F1 macro, itens, inválidas.
# O refinamento de 9008 em A falha na API e mantém o rótulo inicial O. Em A, F é predito para 9001, 9002,
# 9003 e 9005 (3 acertos em 3 F) e NF para os outros 6, todos NF: F com P 3/4, R 1, F1 6/7; NF com P 1,
# R 6/7, F1 12/13. Na categoria, A erra 9005 (F) e prediz O para 9008 (US), como a inicial.
EXPECTED_PROMISE = {
    ("initial", "binary"): (2 / 3 / 2 + 6 / 7 / 2, 2 / 3 / 2 + 6 / 7 / 2, 32 / 42, 10, 0),
    ("initial", "category"): (3.5 / 4, 3 / 4, 3 / 4, 7, 0),
    (A.value, "binary"): (7 / 8, 13 / 14, 81 / 91, 10, 0),
    (A.value, "category"): (3.5 / 4, 3 / 4, 3 / 4, 7, 0),
    (B.value, "binary"): (15 / 16, 5 / 6, 13 / 15, 10, 0),
    (B.value, "category"): (1.0, 1.0, 1.0, 7, 0),
}


def test_promise_classification_metrics(runs):
    pytest.importorskip("sklearn")
    assert cli(runs, "fixture-promise", "compute", "--promise-labels", str(LABELS)) == 0
    metrics = runs / "fixture-promise" / "metrics"
    macro = {
        (r["variant"], r["task"]): (float(r["macro_precision"]), float(r["macro_recall"]), float(r["macro_f1"]),
                                    int(r["items"]), int(r["invalid"]))
        for r in read_csv(metrics / "promise_macro.csv")
    }
    assert macro == {k: pytest.approx(v, abs=1e-6) for k, v in EXPECTED_PROMISE.items()}
    labels = {(r["variant"], r["task"], r["label"]): r for r in read_csv(metrics / "promise_by_label.csv")}
    po = labels[("initial", "category", "PO")]
    assert (po["support"], po["f1"], po["in_macro"]) == ("1", "1.000000", "0")
    assert "um único item" in po["note"]
    assert labels[("initial", "category", "A")]["in_macro"] == "0"
    assert labels[("initial", "category", "A")]["precision"] == ""
    o = labels[("initial", "category", "O")]
    assert (o["support"], o["predicted"], o["precision"], o["recall"]) == ("1", "2", "0.500000", "1.000000")
    nf = labels[(A.value, "binary", "NF")]
    assert (nf["precision"], nf["recall"], nf["f1"]) == ("1.000000", "0.857143", "0.923077")
    summary = (metrics / "summary.md").read_text(encoding="utf-8")
    assert "PO fora da média macro" in summary
    assert "--promise-labels code/experiments/metrics/fixtures/promise_labels.jsonl" in summary
    assert ("Refinamentos com falha (refinement_status diferente de ok: resposta inválida ou erro de API), que mantêm "
            "o rótulo inicial: corrida 0, LLM-only: 1 (api_error 1); corrida 0, REQKG-grounded: 1 "
            "(invalid_output 1).") in summary
    # Recusas: 9006 em A (G2) e 9004 em B (G1), com o rótulo inicial em final. Os outros 16 refinamentos válidos
    # foram aceitos, inclusive os que repetem o rótulo inicial.
    assert ("Refinamentos recusados por regra G (refinement_status ok e refinement_accepted falso), que mantêm o "
            "rótulo inicial: corrida 0, LLM-only: 1 (G2 1); corrida 0, REQKG-grounded: 1 (G1 1).") in summary
    stats = {(r["metric"], r["condition"]): r for r in read_csv(metrics / "summary.csv")}
    assert stats[("promise_refinement_failures", A.value)]["values"] == "1.000000"
    assert stats[("promise_refinement_refusals", B.value)]["values"] == "1.000000"


# Concordância de rótulo com os requisitos do PROMISE no contexto (fixtures/build.py, PROMISE_CONTEXT).
# Projeto 901: F, F, F, SE, SE; projeto 902: PE, US, US, PO, O. Fração dos demais itens do projeto com o
# mesmo rótulo: F 2/4, SE 1/4, US 1/4, PE, PO e O 0.
# A: 8 itens com 1 vizinho; concordam 9001 e 9002 (F com F). Esperada: (3 * 2/4 + 3 * 1/4) / 8 = 9/32.
# B: 16 vizinhos em 9 itens; concordam 2 (9001), 2 (9002), 2 (9003), 1 (9004), 1 (9005), 1 (9007), 1 (9008).
# Esperada: (7 * 2/4 + 7 * 1/4) / 16 = 21/64. Maioria única igual ao rótulo: 9001, 9002, 9003, 9005.
EXPECTED_AGREEMENT = {
    A.value: (8, 8, 2, 1 / 4, 9 / 32, 2, 2 / 8),
    B.value: (9, 16, 10, 10 / 16, 21 / 64, 4, 4 / 9),
}


def test_promise_context_label_agreement(runs):
    pytest.importorskip("sklearn")
    assert cli(runs, "fixture-promise", "compute", "--promise-labels", str(LABELS)) == 0
    rows = read_csv(runs / "fixture-promise" / "metrics" / "promise_context_agreement.csv")
    found = {r["condition"]: (int(r["items_with_promise_context"]), int(r["context_items"]), int(r["agreeing"]),
                              float(r["agreement"]), float(r["expected_agreement"]), int(r["majority_matches"]),
                              float(r["majority_rate"])) for r in rows}
    assert found == {k: pytest.approx(v, abs=1e-6) for k, v in EXPECTED_AGREEMENT.items()}


def test_refinement_failure_must_keep_the_initial_label(runs, capsys):
    path = runs / "fixture-promise" / "classifications.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        record = json.loads(line)
        if record["promise_id"] == "PROMISE-NFR-9008" and record["condition"] == A.value:
            lines[i] = json.dumps({**record, "final": "US"})
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert cli(runs, "fixture-promise", "compute", "--promise-labels", str(LABELS)) == 1
    assert "refinamento que falhou mantém o rótulo inicial" in capsys.readouterr().err


def test_invalid_prediction_misses_the_item_and_predicts_no_label():
    gold = {"PROMISE-NFR-9001": "F", "PROMISE-NFR-9004": "SE"}
    binary, category = task_scores(0, "initial", gold, {"PROMISE-NFR-9001": INVALID, "PROMISE-NFR-9004": "SE"})
    f = next(ls for ls in binary.labels if ls.label == "F")
    assert (binary.invalid, f.support, f.predicted, f.recall) == (1, 1, 0, 0.0)
    assert (category.items, category.invalid, category.macro_f1) == (1, 0, 1.0)
