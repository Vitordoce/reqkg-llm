"""Gates do passo 5 (extração) e do passo 7 (uma passagem de refinamento), com respostas gravadas."""

import json
import random

import pytest

from domain.enums import Condition, ContextStrategy, NodeKind, PromiseLabel, RelationType, RunStatus
from domain.llm_io import CaseResult, ClassificationOutput, ContextItem, RetrievedContext
from domain.rules import CorpusIndex, check_all, refinement_targets
from extraction.client import CallLog, CallTarget, ReplayClient
from extraction.fixtures import build_replays, scenarios
from extraction.fixtures.fakes import CountingClient, FailingClient, StaticClient
from extraction.pipeline import (
    SecondRefinementError,
    SinglePassGuard,
    apply_refinements,
    classify_item,
    empty_context,
    extract_case,
    group_chunks,
    persistable,
    refine_candidate,
    refine_classification,
    source_chunks_context,
)

CONFIG = scenarios.config()
DOMAIN_FIXTURES = scenarios.REPO_ROOT / "code" / "domain" / "fixtures"
THRESHOLD = CONFIG.review.confidence_threshold


@pytest.fixture
def log(tmp_path):
    return CallLog(tmp_path / "corrida")


@pytest.fixture
def replay():
    return ReplayClient.from_fixtures()


def _extract(client, log, chunks=None, per_call=scenarios.ENTREVISTA_PER_CALL, case_id="entrevista"):
    return extract_case(case_id=case_id, run_index=0,
                        chunks=chunks if chunks is not None else scenarios.entrevista_chunks(),
                        config=scenarios.config_with(per_call), client=client, log=log)


def test_replay_index_is_fresh():
    assert build_replays.main(["--check"]) == 0


# Extração


def test_chunks_are_grouped_per_call_in_stable_order():
    chunks = scenarios.entrevista_chunks()
    shuffled = chunks[:]
    random.Random(7).shuffle(shuffled)
    assert group_chunks(shuffled, 2) == [chunks[0:2], chunks[2:4]]
    assert [len(g) for g in group_chunks(chunks, 3)] == [3, 1]
    with pytest.raises(ValueError, match="chunks_per_call"):
        group_chunks(chunks, 0)


def test_extraction_merges_calls_with_prefixed_keys(replay, log):
    run = _extract(replay, log)
    assert run.result.status is RunStatus.OK
    assert run.result.extraction == scenarios.entrevista_extraction()
    assert run.calls == {"c0": ("chk-fb10eaa327ae4290", "chk-9e31855f3c8b8ca8"),
                         "c1": ("chk-f7faa2ea1130ac73", "chk-202c7f98847e276d")}
    keys = [r.key for r in run.result.extraction.requirements]
    assert keys == ["c0-R1", "c0-R2", "c1-R1", "c1-R2", "c1-R3", "c1-R4"]
    entries = log.entries()
    assert [e.target.key for e in entries] == ["c0", "c1"]
    assert entries[1].meta.model_dump(exclude_unset=True) == {"chunk_ids": list(run.calls["c1"]), "chunks_per_call": 2}
    assert run.result.condition is None and all(e.target.condition is None for e in entries)


def test_chunks_per_call_comes_from_the_config(log):
    assert CONFIG.extraction.chunks_per_call == 6
    client = StaticClient(json.dumps({}))
    run = extract_case(case_id="entrevista", run_index=0, chunks=scenarios.entrevista_chunks(),
                       config=CONFIG, client=client, log=log)
    assert run.result.status is RunStatus.OK and len(client.calls) == 1
    assert run.calls == {"c0": tuple(c.chunk_id for c in scenarios.entrevista_chunks())}
    assert log.entries()[0].meta.chunks_per_call == 6


def test_gate5_every_accepted_requirement_points_to_source_and_chunk(replay, log):
    run = _extract(replay, log)
    corpus = scenarios.entrevista_corpus()
    batch = persistable(run, corpus, THRESHOLD)
    assert len(batch.requirements) == 6 and batch.rejected == []
    derived = {(r.source.id, r.target.id) for r in batch.relations if r.type is RelationType.DERIVED_FROM}
    for requirement in batch.requirements:
        assert requirement.provenance.evidence
        for evidence in requirement.provenance.evidence:
            assert corpus.chunk_source[evidence.chunk_id] == evidence.source_id
            assert evidence.quote and evidence.quote.casefold() in corpus.chunk_text[evidence.chunk_id].casefold()
            assert (requirement.requirement_id, evidence.source_id) in derived


def test_gate5_invalid_json_produces_no_record(replay, log):
    run = _extract(replay, log, per_call=4)
    result = run.result
    assert result.status is RunStatus.INVALID_OUTPUT and result.extraction is None
    assert "requirements.0.priority: Input should be 'must'" in result.error
    assert result.error.startswith("entrevista/c0")
    batch = persistable(run, scenarios.entrevista_corpus(), THRESHOLD)
    assert batch.requirements == [] and batch.relations == [] and batch.actors == []
    CaseResult.model_validate(result.model_dump())


def test_dangling_relation_key_is_invalid_output(log):
    dangling = (DOMAIN_FIXTURES / "invalid" / "extraction_dangling_key.json").read_text(encoding="utf-8")
    run = _extract(StaticClient(dangling), log, per_call=4)
    assert run.result.status is RunStatus.INVALID_OUTPUT
    assert "relations.0.target_key: 'A9' não é actor" in run.result.error
    assert persistable(run, scenarios.entrevista_corpus(), THRESHOLD).requirements == []


def test_gate5_invented_evidence_becomes_w_rejection_and_p_violation(replay, log):
    chunks = scenarios.ata_chunks()
    corpus = CorpusIndex.from_chunks(chunks)
    run = _extract(replay, log, chunks=chunks, per_call=3, case_id="ata")
    assert run.result.status is RunStatus.OK
    violations = {(v.rule_id, v.subject) for v in check_all(run.result.extraction, corpus)}
    assert ("P3", "c0-R2") in violations
    assert ("P2", "c0-R3") in violations
    batch = persistable(run, corpus, THRESHOLD)
    rejected = {(r.rule_id, r.subject) for r in batch.rejected}
    assert {("W1", "c0-R2"), ("W1", "c0-R3"), ("W2", "relations.2"), ("W2", "relations.3")} <= rejected
    assert sorted(r.statement for r in batch.requirements) == [
        "O painel de ensaios deve mostrar o estado de cada bancada.",
        "O sistema deveria permitir exportar o relatório diário em PDF.",
    ]
    for requirement in batch.requirements:
        for evidence in requirement.provenance.evidence:
            assert corpus.chunk_source[evidence.chunk_id] == evidence.source_id
    allocated = [r for r in batch.relations if r.type is RelationType.ALLOCATED_TO]
    assert len(allocated) == 1 and allocated[0].target.kind is NodeKind.SOFTWARE_COMPONENT


def test_truncated_text_is_invalid_output_with_reason(log):
    client = StaticClient('{"requirements": [{"key": "R1", "statement": "O sis', stop_reason="max_tokens")
    run = _extract(client, log)
    assert run.result.status is RunStatus.INVALID_OUTPUT
    assert "JSON inválido na linha 1" in run.result.error and "cortada em max_tokens" in run.result.error
    assert len(client.calls) == 1


def test_api_error_is_recorded_and_stops_the_case(log):
    client = FailingClient()
    run = _extract(client, log)
    assert run.result.status is RunStatus.API_ERROR and "sem rede" in run.result.error
    assert len(client.calls) == 1
    assert [e.status for e in log.entries()] == ["api_error"]


# Refinamento


def _refine(client, guard, log, condition=Condition.LLM_ONLY, context=None, run_index=0):
    return refine_candidate(
        case_id="entrevista", condition=condition, run_index=run_index,
        candidate=scenarios.agenda_candidate(),
        context=context or (scenarios.agenda_source_context() if condition is Condition.LLM_ONLY
                            else scenarios.agenda_graph_context()),
        reasons=scenarios.agenda_reasons(), corpus=scenarios.entrevista_corpus(), client=client, guard=guard, log=log,
    )


def test_agenda_is_a_refinement_target_in_both_conditions():
    targets = refinement_targets(scenarios.entrevista_extraction(), scenarios.entrevista_corpus(), THRESHOLD)
    assert scenarios.AGENDA_KEY in targets


def test_llm_only_context_is_the_chunks_of_the_extraction_call(replay, log):
    run = _extract(replay, log)
    assert source_chunks_context(run, scenarios.AGENDA_KEY, scenarios.entrevista_chunks()) == scenarios.agenda_source_context()


def test_accepted_refinement_keeps_unsupported_fields_null(replay, log):
    result = _refine(replay, SinglePassGuard.for_config(CONFIG), log)
    assert result.accepted and result.violations == () and result.result.violations == []
    assert result.result.status is RunStatus.OK and len(result.result.refinements) == 1
    assert result.result.condition is Condition.LLM_ONLY
    revised = result.candidate
    assert revised.statement == "O sistema deve responder rapidamente à consulta da agenda."
    assert revised.priority is None and revised.verification_method is None
    assert "quantitative_value_pending" in revised.review_flags
    assert revised.evidence == scenarios.agenda_candidate().evidence


def test_g_violation_refuses_and_keeps_the_original(replay, log):
    result = _refine(replay, SinglePassGuard.for_config(CONFIG), log, condition=Condition.REQKG_GROUNDED)
    assert not result.accepted
    assert {v.rule_id for v in result.violations} == {"G2", "G3"}
    assert result.candidate == scenarios.agenda_candidate()
    case = result.result
    assert case.status is RunStatus.OK and case.condition is Condition.REQKG_GROUNDED
    assert case.refinements[0].revised.quantitative_value == "2 s"
    assert [(v.rule_id, v.subject) for v in case.violations] == [(v.rule_id, v.subject) for v in result.violations]
    assert CaseResult.model_validate(case.model_dump()) == case


def test_gate7_second_refinement_of_the_same_target_fails(replay, log):
    client = CountingClient(replay)
    guard = SinglePassGuard.for_config(CONFIG)
    _refine(client, guard, log)
    with pytest.raises(SecondRefinementError, match="refinement.max_calls = 1"):
        _refine(client, guard, log)
    assert len(client.calls) == 1
    assert len(log.entries()) == 1


def test_gate7_holds_across_processes_through_the_call_log(replay, log):
    _refine(replay, SinglePassGuard.for_config(CONFIG), log)
    reopened = SinglePassGuard.for_config(CONFIG, log)
    client = CountingClient(replay)
    with pytest.raises(SecondRefinementError):
        _refine(client, reopened, log)
    assert client.calls == []


def test_gate7_failed_first_call_still_counts(log):
    guard = SinglePassGuard.for_config(CONFIG)
    result = _refine(FailingClient(), guard, log)
    assert result.result.status is RunStatus.API_ERROR and result.candidate == scenarios.agenda_candidate()
    assert result.result.target_key == scenarios.agenda_candidate().key, "o erro fica ligado ao alvo"
    with pytest.raises(SecondRefinementError):
        _refine(StaticClient("{}"), guard, log)


def test_gate7_each_condition_and_run_has_its_own_single_pass(replay, log):
    guard = SinglePassGuard.for_config(CONFIG)
    _refine(replay, guard, log, condition=Condition.LLM_ONLY)
    _refine(replay, guard, log, condition=Condition.REQKG_GROUNDED)
    _refine(replay, guard, log, condition=Condition.LLM_ONLY, run_index=1)
    with pytest.raises(SecondRefinementError):
        _refine(replay, guard, log, condition=Condition.REQKG_GROUNDED)


def test_invalid_refinement_output_keeps_the_original(log):
    result = _refine(StaticClient(json.dumps({"target_key": "c1-R2"})), SinglePassGuard.for_config(CONFIG), log)
    assert result.result.status is RunStatus.INVALID_OUTPUT and "revised" in result.result.error
    assert result.candidate == scenarios.agenda_candidate()
    assert result.result.target_key == scenarios.agenda_candidate().key


def test_target_key_comes_from_the_target_not_from_the_answer(log):
    answer = {"target_key": "c0-R1", "revised": {**scenarios.agenda_candidate().model_dump(mode="json"), "key": "c0-R1"}}
    result = _refine(StaticClient(json.dumps(answer)), SinglePassGuard.for_config(CONFIG), log)
    assert "G1" in {v.rule_id for v in result.violations}
    assert result.result.target_key == scenarios.agenda_candidate().key != result.result.refinements[0].target_key


def test_g6_priority_filled_without_new_evidence_is_refused(log):
    candidate = scenarios.agenda_candidate()
    assert candidate.priority is None
    answer = {"target_key": candidate.key, "revised": {**candidate.model_dump(mode="json"), "priority": "must"}}
    result = _refine(StaticClient(json.dumps(answer)), SinglePassGuard.for_config(CONFIG), log)
    assert not result.accepted and [v.rule_id for v in result.violations] == ["G6"]
    assert result.candidate == candidate


def test_final_output_replaces_only_accepted_refinements(replay, log):
    guard = SinglePassGuard.for_config(CONFIG)
    accepted = _refine(replay, guard, log, condition=Condition.LLM_ONLY)
    refused = _refine(replay, guard, log, condition=Condition.REQKG_GROUNDED)
    extraction = scenarios.entrevista_extraction()
    final_a = apply_refinements(extraction, [accepted])
    final_b = apply_refinements(extraction, [refused])
    by_key = lambda output: {r.key: r for r in output.requirements}  # noqa: E731
    assert by_key(final_a)["c1-R2"] == accepted.candidate
    assert final_b == extraction
    assert [r.key for r in final_a.requirements] == [r.key for r in extraction.requirements]


# Classificação do PROMISE


def test_classification_and_refinement_in_both_conditions(replay, log):
    items = scenarios.classification_items()
    first = classify_item(item=items["PROMISE-NFR-9001"], run_index=0, client=replay, log=log)
    assert first.status is RunStatus.OK and first.classification.label is PromiseLabel.F
    assert first.condition is None
    item = items[scenarios.REFINED_ITEM]
    result = classify_item(item=item, run_index=0, client=replay, log=log)
    assert result.classification.label is PromiseLabel.PE
    guard = SinglePassGuard.for_config(CONFIG)
    a = refine_classification(item=item, first=result.classification, condition=Condition.LLM_ONLY, run_index=0,
                              context=empty_context(f"classificar {item.promise_id}"), client=replay, guard=guard, log=log)
    b = refine_classification(item=item, first=result.classification, condition=Condition.REQKG_GROUNDED, run_index=0,
                              context=scenarios.project_context(item.promise_id), client=replay, guard=guard, log=log)
    assert a.accepted and b.accepted
    assert a.classification.label is b.classification.label is PromiseLabel.PE
    assert b.classification.used_context_ids == ["PROMISE-NFR-9001"]
    with pytest.raises(SecondRefinementError):
        refine_classification(item=item, first=result.classification, condition=Condition.LLM_ONLY, run_index=0,
                              context=empty_context("x"), client=replay, guard=guard, log=log)


def test_project_context_never_contains_the_item():
    context = scenarios.project_context(scenarios.REFINED_ITEM)
    assert scenarios.REFINED_ITEM not in {i.item_id for i in context.items}
    assert all("dev_label" not in i.text and i.text for i in context.items)


def test_context_with_the_item_itself_is_refused_g5(log):
    item = scenarios.classification_items()[scenarios.REFINED_ITEM]
    first = ClassificationOutput(promise_id=item.promise_id, label=PromiseLabel.PE)
    leaked = RetrievedContext(query="vazado", strategy=ContextStrategy.GRAPH_LOCAL, limit=5, items=[
        ContextItem(item_id=item.promise_id, kind="requirement", rank=0, text=item.text,
                    source_id="src-0000000000000000", chunk_id="chk-0000000000000000")])
    client = StaticClient(json.dumps({"promise_id": item.promise_id, "label": "US"}))
    result = refine_classification(item=item, first=first, condition=Condition.REQKG_GROUNDED, run_index=0,
                                   context=leaked, client=client, guard=SinglePassGuard.for_config(CONFIG), log=log)
    assert not result.accepted and [v.rule_id for v in result.violations] == ["G5"]
    assert result.classification == first
    assert result.result.status is RunStatus.OK and [v.rule_id for v in result.result.violations] == ["G5"]


def test_classification_of_another_item_is_invalid(log):
    item = scenarios.classification_items()["PROMISE-NFR-9001"]
    client = StaticClient(json.dumps({"promise_id": "PROMISE-NFR-9003", "label": "SE"}))
    result = classify_item(item=item, run_index=0, client=client, log=log)
    assert result.status is RunStatus.INVALID_OUTPUT and "PROMISE-NFR-9003" in result.error


def test_guard_counts_only_refinements():
    with pytest.raises(ValueError, match="só conta refinamentos"):
        SinglePassGuard().claim(CallTarget("c", Condition.LLM_ONLY, 0, "extraction", "c0"))
