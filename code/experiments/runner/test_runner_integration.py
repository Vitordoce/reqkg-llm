"""Executor ponta a ponta contra o Neo4j do projeto, em modo sintético e replay.

Pula com motivo se o Neo4j não estiver no ar ou se a URI for a porta 7687. As corridas limpam o
grafo, então o módulo inteiro segura graph.fixture.exclusive_database e chama o executor com
hold_lock=False.

Corridas: S, com o cliente sintético (3 repetições na amostra e o PROMISE sintético); R1 e R2,
replays de S pelo calls.jsonl dela.
"""

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest

from domain import ids
from domain.config import ExperimentConfig
from domain.enums import Condition, ContextStrategy, RunStatus
from domain.llm_io import CaseResult
from domain.persist import to_records
from domain.rules import refinement_targets
from domain.serialization import load_toml
from experiments.records import (
    FILES, CallRecord, ClassificationRecord, ContextRecord, FinalRecord, RejectionRecord, RunManifest,
)
from experiments.runner import execute as execute_module
from experiments.runner.clients import load_replay
from experiments.runner.execute import condition_order
from experiments.runner.fixtures import CONFIG_FILE, DESCRICAO, PROMISE_FILE, REPLAY_INDEX, SET_FILE
from experiments.runner.fixtures.synthetic import SyntheticClient
from experiments.runner.inputs import load_promise, load_structural
from experiments.runner.run import Mode, make_plan, run
from experiments.runner.rundir import RunRefused
from extraction.client import CallLog, CallTarget, MissingReplayError
from extraction.pipeline import SecondRefinementError, SinglePassGuard
from graph.connection import Graph, GraphUnavailable, Neo4jSettings, UnsafeTarget, refuse_user_instance
from graph.fixture import exclusive_database
from retrieval.context import source_chunks_context

CONFIG = load_toml(CONFIG_FILE, ExperimentConfig)
STRUCTURAL = load_structural([SET_FILE], CONFIG.chunking)
PROMISE = load_promise(CONFIG.chunking, CONFIG.evaluation.seed, PROMISE_FILE)
CASES = {c.case_id: c for c in STRUCTURAL.cases}
INVALID_CASE = ids.source_id(DESCRICAO)
MODELS = {"case_results": CaseResult, "contexts": ContextRecord, "finals": FinalRecord,
          "rejections": RejectionRecord, "classifications": ClassificationRecord}
RECORD_FILES = [FILES[k] for k in MODELS]


@pytest.fixture(scope="module")
def graph():
    try:
        settings = Neo4jSettings.from_env()
        refuse_user_instance(settings.uri)
    except GraphUnavailable as error:
        pytest.skip(f"Neo4j não configurado: {error}")
    except UnsafeTarget as error:
        pytest.skip(f"recusado: {error}")
    try:
        opened = Graph(settings)
    except GraphUnavailable as error:
        pytest.skip(f"{error}. Rode make neo4j-up e make neo4j-wait")
    with opened:
        try:
            with exclusive_database():
                yield opened
        except TimeoutError as error:
            pytest.skip(str(error))


def plan(structural=STRUCTURAL, promise=PROMISE):
    return make_plan(CONFIG_FILE, structural=structural, promise=promise)


def start(graph, root: Path, run_id: str, client, mode: Mode, the_plan=None) -> Path:
    return run(the_plan or plan(), run_id=run_id, mode=mode, client=client, graph=graph, command=f"teste {run_id}",
               runs_root=root, hold_lock=False)


@dataclass(frozen=True)
class Runs:
    root: Path
    synthetic: Path
    replay1: Path
    replay2: Path
    retrievals: list[tuple[Condition, bool]]


@pytest.fixture(scope="module")
def runs(graph, tmp_path_factory) -> Runs:
    root = tmp_path_factory.mktemp("runs")
    seen: list[tuple[Condition, bool]] = []
    original = execute_module.retrieve_context

    def spy(target, condition, config, graph=None):
        seen.append((condition, graph is not None))
        return original(target, condition, config, graph)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(execute_module, "retrieve_context", spy)
        synthetic = start(graph, root, "S", SyntheticClient.for_projects(list(PROMISE.projects)), Mode.SYNTHETIC)
    replay1 = start(graph, root, "R1", load_replay(synthetic / "calls.jsonl"), Mode.REPLAY)
    replay2 = start(graph, root, "R2", load_replay(synthetic / "calls.jsonl"), Mode.REPLAY)
    return Runs(root, synthetic, replay1, replay2, seen)


def read(run_dir: Path, kind: str) -> list:
    path = run_dir / FILES[kind]
    return [MODELS[kind].model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines()]


def calls(run_dir: Path) -> list[CallRecord]:
    return CallLog.read(run_dir / "calls.jsonl")


def extraction_of(run_dir: Path, case_id: str, run_index: int) -> CaseResult:
    [found] = [r for r in read(run_dir, "case_results")
               if r.stage == "extraction" and r.case_id == case_id and r.run_index == run_index]
    return found


def ok_finals(run_dir: Path) -> list[FinalRecord]:
    return [f for f in read(run_dir, "finals") if f.status is RunStatus.OK]


def test_every_record_exists_and_validates(runs):
    for run_dir in (runs.synthetic, runs.replay1):
        assert sorted(p.name for p in run_dir.iterdir()) == sorted(FILES.values())
        manifest = RunManifest.model_validate_json((run_dir / "manifest.json").read_text(encoding="utf-8"))
        assert (manifest.model_id, manifest.replay, manifest.runs) == ("synthetic", True, 3)
        assert manifest.ingestion_sha256 == list(STRUCTURAL.sha256)
        assert manifest.promise_sha256 == PROMISE.sha256
        for kind in MODELS:
            records = read(run_dir, kind)
            assert records, f"{kind} vazio"
    finals = read(runs.synthetic, "finals")
    assert Counter((f.run_index, f.condition) for f in finals) == {(r, c): 3 for r in range(3) for c in CONFIG.conditions}
    assert len(read(runs.synthetic, "classifications")) == PROMISE.count() * 2


def test_one_shared_extraction_per_case_and_run(runs):
    extractions = [r for r in read(runs.synthetic, "case_results") if r.stage == "extraction"]
    assert all(r.condition is None for r in extractions)
    expected = {(c, i) for c in CASES for i in range(3)} | {(f"promise-project-{p.project_id:02d}", 0) for p in PROMISE.projects}
    assert Counter((r.case_id, r.run_index) for r in extractions) == Counter(expected)
    extraction_calls = [c.target for c in calls(runs.synthetic) if c.target.stage == "extraction"]
    assert all(t.condition is None for t in extraction_calls)
    assert len(extraction_calls) == 3 * 4 + 3
    for final in ok_finals(runs.synthetic):
        shared = extraction_of(runs.synthetic, final.case_id, final.run_index).extraction
        assert final.output.actors == shared.actors and final.output.relations == shared.relations


def test_targets_are_the_same_in_both_conditions(runs):
    by_case = {}
    for final in ok_finals(runs.synthetic):
        by_case.setdefault((final.case_id, final.run_index), {})[final.condition] = final.targets
    assert len(by_case) == 2 * 3
    for (case_id, run_index), targets in by_case.items():
        shared = extraction_of(runs.synthetic, case_id, run_index).extraction
        expected = refinement_targets(shared, CASES[case_id].corpus, CONFIG.review.confidence_threshold)
        assert targets[Condition.LLM_ONLY] == targets[Condition.REQKG_GROUNDED] == expected
        assert expected


def test_no_candidate_is_refined_twice(runs):
    refinements = [c.target for c in calls(runs.synthetic) if c.target.stage == "refinement"]
    keys = [(t.case_id, t.condition, t.run_index, t.key) for t in refinements]
    assert len(keys) == len(set(keys))
    expected = sum(len(f.targets) for f in ok_finals(runs.synthetic))
    assert len(keys) == expected
    guard = SinglePassGuard.for_config(CONFIG, CallLog(runs.synthetic))
    first = refinements[0]
    with pytest.raises(SecondRefinementError):
        guard.claim(CallTarget(first.case_id, first.condition, first.run_index, "refinement", first.key))


def test_llm_only_never_touches_the_graph(runs):
    assert runs.retrievals and {c for c, _ in runs.retrievals} == set(CONFIG.conditions)
    assert all(not used for c, used in runs.retrievals if c is Condition.LLM_ONLY)
    assert all(used for c, used in runs.retrievals if c is Condition.REQKG_GROUNDED)
    for record in read(runs.synthetic, "contexts"):
        if record.condition is Condition.REQKG_GROUNDED:
            assert record.context.strategy is ContextStrategy.GRAPH_LOCAL
            continue
        assert record.context.strategy is ContextStrategy.SOURCE_CHUNKS
        if record.case_id in CASES:
            expected = source_chunks_context(record.target_key, CASES[record.case_id].chunks,
                                             CONFIG.extraction.chunks_per_call)
            assert record.context == expected


def test_final_output_differs_from_extraction_only_in_accepted_targets(runs):
    results = [r for r in read(runs.synthetic, "case_results") if r.stage == "refinement"]
    by_target = {(r.case_id, r.condition, r.run_index, r.target_key): r for r in results}
    assert len(by_target) == len(results)
    refined = {k: r.refinements[0].revised for k, r in by_target.items() if r.refinements}
    failed = {k for k, r in by_target.items() if r.status is not RunStatus.OK}
    assert failed == {(f.case_id, f.condition, f.run_index, k) for f in ok_finals(runs.synthetic) for k in f.failed}
    assert failed, "nenhum refinamento falhou: a ligação do erro com o alvo ficaria sem teste"
    changed = 0
    for final in ok_finals(runs.synthetic):
        shared = extraction_of(runs.synthetic, final.case_id, final.run_index).extraction
        assert final.output.model_dump(exclude={"requirements"}) == shared.model_dump(exclude={"requirements"})
        assert [r.key for r in final.output.requirements] == [r.key for r in shared.requirements]
        before = {r.key: r for r in shared.requirements}
        for requirement in final.output.requirements:
            if requirement.key in final.accepted:
                assert requirement == refined[(final.case_id, final.condition, final.run_index, requirement.key)]
                changed += requirement != before[requirement.key]
            else:
                assert requirement == before[requirement.key]
    assert changed > 0, "nenhum refinamento aceito mudou um candidato: o teste ficaria vazio"
    refused = [f for f in ok_finals(runs.synthetic) if f.refused]
    assert {v.rule_id for f in refused for v in f.violations} == {"G3", "G4", "G6"}, \
        "o chunk inventado fica fora do contexto (G3) e do corpus do caso (G6)"


def test_invalid_case_is_recorded_as_no_requirement(runs):
    for run_index in range(3):
        result = extraction_of(runs.synthetic, INVALID_CASE, run_index)
        assert result.status is RunStatus.INVALID_OUTPUT and "R9" in result.error
    finals = [f for f in read(runs.synthetic, "finals") if f.case_id == INVALID_CASE]
    assert {(f.condition, f.status) for f in finals} == {(c, RunStatus.INVALID_OUTPUT) for c in CONFIG.conditions}
    assert all(f.output is None and f.targets == [] for f in finals)
    assert not [c for c in read(runs.synthetic, "contexts") if c.case_id == INVALID_CASE]


def test_tokens_are_per_condition(runs):
    usage = {(c.target.case_id, c.target.condition, c.target.run_index, c.target.stage, c.target.key): c.usage
             for c in calls(runs.synthetic)}
    for final in ok_finals(runs.synthetic):
        spent = [usage[(final.case_id, final.condition, final.run_index, "refinement", k)] for k in final.targets]
        assert final.input_tokens == sum(u.input_tokens or 0 for u in spent) > 0
        assert final.output_tokens == sum(u.output_tokens or 0 for u in spent)
    for record in read(runs.synthetic, "classifications"):
        spent = usage[(record.promise_id, record.condition, 0, "classification_refinement", record.promise_id)]
        assert (record.input_tokens, record.output_tokens) == (spent.input_tokens, spent.output_tokens)


def test_same_replay_gives_the_same_bytes(runs):
    for name in RECORD_FILES:
        replayed = (runs.replay1 / name).read_bytes()
        assert replayed == (runs.replay2 / name).read_bytes(), name
        assert replayed == (runs.synthetic / name).read_bytes(), name

    def without_time(run_dir: Path) -> list[dict]:
        return [entry.model_dump(exclude={"timestamp"}) for entry in calls(run_dir)]

    assert without_time(runs.replay1) == without_time(runs.replay2)
    manifests = [json.loads((d / "manifest.json").read_text(encoding="utf-8")) for d in (runs.replay1, runs.replay2)]
    assert {k for k in manifests[0] if manifests[0][k] != manifests[1][k]} == {"run_id", "command"}


def test_promise_item_never_in_its_own_context(runs):
    projects = {p.project_id: p for p in PROMISE.projects}
    records = {(r.promise_id, r.condition): r for r in read(runs.synthetic, "classifications")}
    by_item: dict[str, dict[Condition, ContextRecord]] = {}
    for context in read(runs.synthetic, "contexts"):
        if not context.case_id.startswith("PROMISE-NFR-"):
            continue
        promise_id = context.case_id
        assert int(promise_id[-4:]) >= 9001
        project = projects[records[(promise_id, context.condition)].project_id]
        assert promise_id not in {i.item_id for i in context.context.items}
        assert project.chunk_of(promise_id).chunk_id not in context.context.chunk_ids()
        by_item.setdefault(promise_id, {})[context.condition] = context
    assert any(c[Condition.LLM_ONLY].context.items for c in by_item.values()), "A recebe os outros itens da chamada"
    for contexts in by_item.values():
        a, b = contexts[Condition.LLM_ONLY].context, contexts[Condition.REQKG_GROUNDED].context
        assert a.strategy is ContextStrategy.SOURCE_CHUNKS
        assert all(i in b.items for i in a.items), "B menos A é só a expansão pelo grafo"
    for (promise_id, condition), record in records.items():
        assert record.initial == records[(promise_id, Condition.LLM_ONLY)].initial
    assert not records[("PROMISE-NFR-9006", Condition.REQKG_GROUNDED)].refinement_accepted
    assert [v.rule_id for v in records[("PROMISE-NFR-9006", Condition.REQKG_GROUNDED)].violations] == ["G2"]
    assert records[("PROMISE-NFR-9007", Condition.REQKG_GROUNDED)].final.value == "LF"


def test_promise_refinement_failure_keeps_the_initial_label_and_is_recorded(runs):
    records = {(r.promise_id, r.condition): r for r in read(runs.synthetic, "classifications")}
    broken = records[("PROMISE-NFR-9002", Condition.LLM_ONLY)]
    assert broken.refinement_status is RunStatus.INVALID_OUTPUT
    assert broken.final == broken.initial and not broken.refinement_accepted and broken.violations == []
    assert broken.input_tokens > 0, "a chamada que falhou também custou"
    failed = {key for key, r in records.items() if r.refinement_status is not RunStatus.OK}
    assert failed == {("PROMISE-NFR-9002", Condition.LLM_ONLY)}


def test_condition_order_alternates_and_is_recorded(runs):
    order_of_calls: dict[tuple[str, int], list[Condition]] = {}
    for call in calls(runs.synthetic):
        if call.target.stage in ("refinement", "classification_refinement"):
            seen = order_of_calls.setdefault((call.target.case_id, call.target.run_index), [])
            if call.target.condition not in seen:
                seen.append(call.target.condition)
    recorded: dict[tuple[str, int], dict[int, Condition]] = {}
    for record in [*read(runs.synthetic, "finals"), *read(runs.synthetic, "classifications")]:
        case = (getattr(record, "case_id", None) or record.promise_id, record.run_index)
        assert record.condition_position is not None
        recorded.setdefault(case, {})[record.condition_position] = record.condition
    for case, positions in recorded.items():
        assert sorted(positions) == [0, 1], case
        assert positions[0] == condition_order(CONFIG, case[0])[0]
        if case in order_of_calls:
            assert order_of_calls[case] == [positions[0], positions[1]], case
    firsts = {positions[0] for positions in recorded.values()}
    assert firsts == set(CONFIG.conditions), "A não pode rodar sempre antes de B"


def test_graph_holds_only_the_current_run(graph, runs):
    run_dir = start(graph, runs.root, "R-estrutural", load_replay(runs.synthetic / "calls.jsonl"), Mode.REPLAY,
                    plan(promise=None))
    documents = {r["s"] for r in graph.rows("MATCH (d:SourceDocument) RETURN d.source_id AS s")}
    assert documents == set(STRUCTURAL.sources)
    expected = set()
    for case_id, case in CASES.items():
        result = extraction_of(run_dir, case_id, 2)
        if result.extraction is not None:
            batch = to_records(result.extraction, case.corpus, CONFIG.review.confidence_threshold)
            expected |= {r.requirement_id for r in batch.requirements}
    found = {r["r"] for r in graph.rows("MATCH (q:Requirement) RETURN q.requirement_id AS r")}
    assert found == expected and expected
    revised = graph.rows("MATCH (q:Requirement) WHERE q.revision <> 0 RETURN count(q) AS n")
    assert revised == [{"n": 0}], "o refinamento não é gravado no grafo"


def test_run_id_is_never_overwritten(graph, runs):
    before = (runs.synthetic / "finals.jsonl").read_bytes()
    with pytest.raises(RunRefused, match="nunca é sobrescrito"):
        start(graph, runs.root, "S", load_replay(runs.synthetic / "calls.jsonl"), Mode.REPLAY)
    assert (runs.synthetic / "finals.jsonl").read_bytes() == before


class Interrupted(Exception):
    pass


class Counting:
    """Repassa ao cliente sintético e conta as chamadas; com stop_after, interrompe a corrida nessa chamada."""

    def __init__(self, stop_after: int | None = None) -> None:
        self.inner = SyntheticClient.for_projects(list(PROMISE.projects))
        self.stop_after = stop_after
        self.calls = 0

    def describe(self):
        return self.inner.describe()

    def complete(self, request):
        if self.stop_after is not None and self.calls == self.stop_after:
            raise Interrupted("queda de teste no meio da corrida")
        self.calls += 1
        return self.inner.complete(request)


def test_interrupted_run_resumes_from_the_partial_log(graph, runs, tmp_path):
    """R83: a retomada serve do calls.jsonl parcial o que já foi pago e chama o cliente só para o resto."""
    total = len(calls(runs.synthetic))
    paid = total // 2
    with pytest.raises(Interrupted):
        start(graph, runs.root, "I", Counting(stop_after=paid), Mode.SYNTHETIC)
    partial = runs.root / ".partial-I"
    logged = (partial / "calls.jsonl").read_text(encoding="utf-8")
    assert len(logged.splitlines()) == paid
    with (partial / "calls.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"timestamp": "2026-10-11T00:00:00+00:00", "target": {"case_')

    changed = tmp_path / "experiment.toml"
    changed.write_text(CONFIG_FILE.read_text(encoding="utf-8") + "\n# outra configuração\n", encoding="utf-8")
    other_plan = make_plan(changed, structural=STRUCTURAL, promise=PROMISE)
    with pytest.raises(RunRefused, match="config_sha256"):
        run(other_plan, run_id="I", mode=Mode.SYNTHETIC, client=Counting(), graph=graph, command="teste I --resume",
            runs_root=runs.root, hold_lock=False, resume=True)
    assert (partial / "calls.jsonl").read_text(encoding="utf-8").startswith(logged), "a recusa não mexe na parcial"
    fewer = load_promise(CONFIG.chunking, CONFIG.evaluation.seed, PROMISE_FILE, items="PROMISE-NFR-9004,PROMISE-NFR-9101")
    with pytest.raises(RunRefused, match="selection_sha256"):
        run(make_plan(CONFIG_FILE, structural=STRUCTURAL, promise=fewer), run_id="I", mode=Mode.SYNTHETIC,
            client=Counting(), graph=graph, command="teste I --promise-items ... --resume", runs_root=runs.root,
            hold_lock=False, resume=True)
    assert (partial / "calls.jsonl").read_text(encoding="utf-8").startswith(logged), "a recusa não mexe na parcial"
    with pytest.raises(RunRefused, match="não há corrida interrompida"):
        run(plan(), run_id="nunca-rodou", mode=Mode.SYNTHETIC, client=Counting(), graph=graph, command="teste",
            runs_root=runs.root, hold_lock=False, resume=True)

    rest = Counting()
    final = run(plan(), run_id="I", mode=Mode.SYNTHETIC, client=rest, graph=graph, command="teste I --resume",
                runs_root=runs.root, hold_lock=False, resume=True)
    assert rest.calls == total - paid, "só o que faltava foi chamado"
    assert sorted(p.name for p in final.iterdir()) == sorted(FILES.values())
    for name in RECORD_FILES:
        assert (final / name).read_bytes() == (runs.synthetic / name).read_bytes(), name
    resumed = (final / "calls.jsonl").read_text(encoding="utf-8")
    assert resumed.startswith(logged), "as chamadas pagas ficam como foram gravadas"
    assert [e.model_dump(exclude={"timestamp"}) for e in calls(final)] == \
        [e.model_dump(exclude={"timestamp"}) for e in calls(runs.synthetic)]
    manifest = RunManifest.model_validate_json((final / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.command == "teste I"
    assert [(r.command, r.logged_calls) for r in manifest.resumptions] == [("teste I --resume", paid)]


def test_a_resumption_interrupted_again_resumes_again(graph, runs):
    total = len(calls(runs.synthetic))
    first = total // 3
    with pytest.raises(Interrupted):
        start(graph, runs.root, "J", Counting(stop_after=first), Mode.SYNTHETIC)
    second = Counting(stop_after=first)
    with pytest.raises(Interrupted):
        run(plan(), run_id="J", mode=Mode.SYNTHETIC, client=second, graph=graph, command="teste J --resume 1",
            runs_root=runs.root, hold_lock=False, resume=True)
    third = Counting()
    final = run(plan(), run_id="J", mode=Mode.SYNTHETIC, client=third, graph=graph, command="teste J --resume 2",
                runs_root=runs.root, hold_lock=False, resume=True)
    assert first + second.calls + third.calls == total
    for name in RECORD_FILES:
        assert (final / name).read_bytes() == (runs.synthetic / name).read_bytes(), name
    manifest = RunManifest.model_validate_json((final / "manifest.json").read_text(encoding="utf-8"))
    assert [r.logged_calls for r in manifest.resumptions] == [first, 2 * first]


def test_missing_replay_stops_and_leaves_partial(graph, runs):
    with pytest.raises(MissingReplayError):
        start(graph, runs.root, "incompleta", load_replay(REPLAY_INDEX), Mode.REPLAY, plan(promise=None))
    assert not (runs.root / "incompleta").exists()
    partial = runs.root / ".partial-incompleta"
    assert (partial / "manifest.json").exists() and (partial / "case_results.jsonl").exists()
    with pytest.raises(RunRefused, match="interrompida"):
        start(graph, runs.root, "incompleta", load_replay(runs.synthetic / "calls.jsonl"), Mode.REPLAY)
