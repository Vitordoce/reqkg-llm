import itertools
import json
import os
import random
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest
from pydantic import ValidationError

from domain import export_schema, ids, models
from domain.config import ContractError, ExperimentConfig, ModelConfig
from domain.enums import PromiseLabel, RelationType
from domain.fixtures import build
from domain.llm_io import (
    CaseResult,
    ClassificationOutput,
    ContextItem,
    ExtractionOutput,
    RefinementOutput,
    RetrievedContext,
    merge_outputs,
)
from domain.persist import to_records
from domain.rules import CorpusIndex, check_all, is_complete, refinement_targets, strongly_connected
from domain.serialization import canonical_json, load_json, load_toml, parse

FIXTURES = Path(__file__).parent / "fixtures"
CODE = Path(__file__).parents[1]
CONFIG = CODE / "experiments" / "config" / "experiment.toml"

MODELS = {
    "SourceDocument": models.SourceDocument,
    "SourceChunk": models.SourceChunk,
    "Requirement": models.Requirement,
    "Actor": models.Actor,
    "Relation": models.Relation,
    "ExtractionOutput": ExtractionOutput,
    "RetrievedContext": RetrievedContext,
    "RefinementOutput": RefinementOutput,
    "ClassificationOutput": ClassificationOutput,
    "CaseResult": CaseResult,
}

VALID = {
    "source_document.json": models.SourceDocument,
    "requirement.json": models.Requirement,
    "actor.json": models.Actor,
    "relation.json": models.Relation,
    "extraction_output.json": ExtractionOutput,
    "extraction_with_violations.json": ExtractionOutput,
    "retrieved_context.json": RetrievedContext,
    "refinement_output.json": RefinementOutput,
    "classification_output.json": ClassificationOutput,
    "case_result_ok.json": CaseResult,
    "case_result_invalid.json": CaseResult,
}

INVALID = json.loads((FIXTURES / "invalid" / "EXPECTED.json").read_text(encoding="utf-8"))


def valid(name: str, model=None):
    return load_json(FIXTURES / "valid" / name, model or VALID[name])


def chunks() -> list[models.SourceChunk]:
    return load_json(FIXTURES / "valid" / "source_chunks.json", list[models.SourceChunk])


def corpus() -> CorpusIndex:
    return CorpusIndex.from_chunks(chunks())


def config() -> ExperimentConfig:
    return load_toml(CONFIG, ExperimentConfig)


def test_fixtures_match_generator():
    assert build.main(["--check"]) == 0


def test_schema_files_match_models():
    assert export_schema.main(["--check"]) == 0


@pytest.mark.parametrize("name", sorted(VALID))
def test_valid_fixture_round_trips(name):
    model = valid(name)
    first = canonical_json(model)
    assert canonical_json(VALID[name].model_validate_json(first)) == first


def test_canonical_json_is_stable_across_hash_seeds():
    script = (
        "from domain.serialization import load_json, canonical_json\n"
        "from domain.llm_io import ExtractionOutput\n"
        "import sys\n"
        "sys.stdout.write(canonical_json(load_json('domain/fixtures/valid/extraction_output.json', ExtractionOutput)))\n"
    )
    outputs = {
        subprocess.run(
            [sys.executable, "-c", script], cwd=CODE, capture_output=True, text=True, check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        ).stdout
        for seed in ("1", "2", "3")
    }
    assert len(outputs) == 1


@pytest.mark.parametrize("name", sorted(INVALID))
def test_invalid_fixture_names_the_field(name):
    spec = INVALID[name]
    data = json.loads((FIXTURES / "invalid" / name).read_text(encoding="utf-8"))
    target = list[MODELS[spec["model"]]] if spec["many"] else MODELS[spec["model"]]
    with pytest.raises(ContractError) as error:
        parse(data, target, name)
    assert spec["expected_loc"] in str(error.value), str(error.value)
    assert name in str(error.value)


def test_clean_extraction_has_no_violations():
    output = valid("extraction_output.json")
    assert check_all(output, corpus()) == []
    assert all(is_complete(r, corpus()) for r in output.requirements)


def test_each_rule_fires_where_expected():
    output = valid("extraction_with_violations.json")
    expected = json.loads((FIXTURES / "valid" / "expected_violations.json").read_text(encoding="utf-8"))
    assert [[v.rule_id, v.subject, v.detail] for v in check_all(output, corpus())] == expected


def test_every_rule_has_a_fixture_case():
    from domain.rules import RULES

    expected = json.loads((FIXTURES / "valid" / "expected_violations.json").read_text(encoding="utf-8"))
    assert {r.rule_id for r in RULES} - {rule_id for rule_id, _, _ in expected} == set()


def test_cycles_counted_per_component_whatever_the_key_names():
    edges = [("a", "b"), ("a", "c"), ("a", "d"), ("c", "a"), ("c", "d"), ("d", "c"), ("x", "y"), ("y", "x")]
    nodes = sorted({n for edge in edges for n in edge})
    rng = random.Random(0)
    counts = set()
    for _ in range(50):
        rename = dict(zip(nodes, rng.sample(nodes, len(nodes))))
        counts.add(len(strongly_connected([(rename[s], rename[t]) for s, t in edges])))
    assert counts == {2}
    assert strongly_connected([("R1", "R2"), ("R1", "R3"), ("R2", "R3"), ("R3", "R1")]) == [("R1", "R2", "R3")]


def test_quote_matches_across_unicode_normalization():
    output = valid("extraction_output.json")
    r3 = output.requirements[2]
    nfd = r3.model_copy(update={"evidence": [
        e.model_copy(update={"quote": unicodedata.normalize("NFD", e.quote)}) for e in r3.evidence
    ]})
    patched = output.model_copy(update={"requirements": [*output.requirements[:2], nfd, *output.requirements[3:]]})
    assert check_all(patched, corpus()) == []


ACCENTED = unicodedata.normalize("NFC", "data/raw/caso/ata_reunião_técnica.txt")


@pytest.mark.parametrize("variant", [
    ACCENTED,
    "./" + ACCENTED,
    ACCENTED.replace("/", "\\"),
    unicodedata.normalize("NFD", ACCENTED),
])
def test_source_id_ignores_path_spelling(variant):
    assert unicodedata.normalize("NFD", ACCENTED) != ACCENTED
    assert ids.source_id(variant) == ids.source_id(ACCENTED)


@pytest.mark.parametrize("bad", ["/abs/arquivo.txt", "../fora.txt", "a/../../b.txt", ""])
def test_source_id_refuses_paths_outside_repository(bad):
    with pytest.raises(ValueError):
        ids.source_id(bad)


def test_persist_clean_extraction():
    batch = to_records(valid("extraction_output.json"), corpus(), confidence_threshold=0.6)
    assert batch.rejected == []
    assert len(batch.requirements) == 5
    by_type = {}
    for relation in batch.relations:
        by_type[relation.type] = by_type.get(relation.type, 0) + 1
    assert by_type == {
        RelationType.REQUESTED_BY: 2,
        RelationType.DEPENDS_ON: 1,
        RelationType.DERIVED_FROM: 5,
        RelationType.MEASURED_BY: 3,
        RelationType.MENTIONS: 1,
    }
    assert canonical_json(batch) == canonical_json(to_records(valid("extraction_output.json"), corpus(), 0.6))


def test_persist_rejects_what_has_no_support():
    batch = to_records(valid("extraction_with_violations.json"), corpus(), confidence_threshold=0.6)
    assert [(r.rule_id, r.subject) for r in batch.rejected] == [
        ("W1", "R2"), ("W1", "R3"), ("W2", "relations.2"), ("W2", "relations.3"), ("W2", "relations.4"),
    ]
    r4 = next(r for r in batch.requirements if r.statement.startswith("Cancelamento"))
    assert r4.provenance.origin.value == "system_inference"
    assert [e.chunk_id for e in r4.provenance.evidence] == [chunks()[3].chunk_id]


def test_derived_from_carries_only_its_own_document_evidence():
    other_text = "Texto de outra fonte sintética."
    other_source = ids.source_id("code/domain/fixtures/corpus/outra_fonte.txt")
    other_chunk = models.SourceChunk(
        chunk_id=ids.chunk_id(other_source, other_text, 0), source_id=other_source, index=0, occurrence=0,
        char_start=0, char_end=len(other_text), text=other_text, sha256=ids.sha256_text(other_text),
    )
    two_sources = CorpusIndex.from_chunks([*chunks(), other_chunk])
    output = valid("extraction_output.json")
    r1 = output.requirements[0]
    extra = r1.evidence[0].model_copy(update={
        "source_id": other_source, "chunk_id": other_chunk.chunk_id, "quote": "outra fonte",
    })
    patched = output.model_copy(update={"requirements": [r1.model_copy(update={"evidence": [*r1.evidence, extra]}), *output.requirements[1:]]})
    batch = to_records(patched, two_sources, 0.6)
    derived = [r for r in batch.relations if r.type is RelationType.DERIVED_FROM and r.target.id == other_source]
    assert len(derived) == 1
    assert {e.source_id for e in derived[0].provenance.evidence} == {other_source}


def test_entity_cited_in_two_calls_keeps_both_evidences():
    c = chunks()

    def call(chunk, quote):
        return ExtractionOutput.model_validate({"entities": [{
            "key": "E1", "name": "reserva", "entity_type": "conceito",
            "evidence": [{"source_id": chunk.source_id, "chunk_id": chunk.chunk_id, "quote": quote}],
        }]})

    merged = merge_outputs([("c1", call(c[1], "reserva dos equipamentos")), ("c2", call(c[3], "cancelar reserva"))])
    batch = to_records(merged, corpus(), 0.6)
    assert len(batch.entities) == 1
    assert {e.chunk_id for e in batch.entities[0].provenance.evidence} == {c[1].chunk_id, c[3].chunk_id}
    assert sum(r.type is RelationType.MENTIONS for r in batch.relations) == 2


def test_persist_marks_low_confidence_for_review():
    output = valid("extraction_output.json")
    shaky = output.requirements[0].model_copy(update={"confidence": 0.2})
    patched = output.model_copy(update={"requirements": [shaky, *output.requirements[1:]]})
    requirement = to_records(patched, corpus(), confidence_threshold=0.6).requirements
    flagged = [r for r in requirement if r.statement == shaky.statement][0]
    assert flagged.status.value == "needs_review"
    assert "low_confidence" in [f.value for f in flagged.review_flags]


def test_persist_accepted_refinement_is_revision_one_with_the_original_id():
    shared = valid("extraction_output.json")
    before = to_records(shared, corpus(), 0.6)
    key = next(r for r in shared.relations if r.type is RelationType.DEPENDS_ON).source_key
    original = next(r for r in shared.requirements if r.key == key)
    revised = original.model_copy(update={"statement": original.statement + " Revisada."})
    final = shared.model_copy(update={"requirements": [revised if r.key == key else r for r in shared.requirements]})

    after = to_records(final, corpus(), 0.6, revisions={key: original.statement})
    assert after.key_to_id == before.key_to_id
    assert {r.relation_id for r in after.relations} == {r.relation_id for r in before.relations}
    by_id = {r.requirement_id: r for r in after.requirements}
    requirement = by_id.pop(before.key_to_id[key])
    assert (requirement.revision, requirement.previous_statement, requirement.statement) == \
        (1, original.statement, revised.statement)
    assert all(r.revision == 0 and r.previous_statement is None for r in by_id.values())
    assert to_records(final, corpus(), 0.6).key_to_id[key] != before.key_to_id[key]

    unchanged = to_records(shared, corpus(), 0.6, revisions={key: original.statement})
    echo = next(r for r in unchanged.requirements if r.requirement_id == before.key_to_id[key])
    assert (echo.revision, echo.previous_statement) == (1, original.statement)
    with pytest.raises(ValueError, match="revisions"):
        to_records(final, corpus(), 0.6, revisions={"X9": original.statement})


def test_merge_prefixes_keys_from_each_call():
    output = valid("extraction_output.json")
    merged = merge_outputs([("c1", output), ("c2", output)])
    assert len(merged.requirements) == 10
    assert merged.relations[0].source_key == "c1-R1"
    with pytest.raises(ValueError, match="repetidos"):
        merge_outputs([("c1", output), ("c1", output)])


def test_refinement_targets_come_from_shared_extraction():
    output = valid("extraction_with_violations.json")
    assert refinement_targets(output, corpus(), 0.6) == ["R2", "R3", "R4", "R5"]
    clean = valid("extraction_output.json")
    assert refinement_targets(clean, corpus(), 0.6) == ["R3"]


def test_refinement_grounding_checks():
    context = valid("retrieved_context.json")
    refinement = valid("refinement_output.json")
    original = valid("extraction_output.json").requirements[0]
    assert refinement.check_against(context, original, corpus()) == []

    leaked = refinement.model_copy(update={"used_context_ids": ["chk-0000000000000000"]})
    assert [v.rule_id for v in leaked.check_against(context, original, corpus())] == ["G2"]

    foreign = original.evidence[0].model_copy(update={"chunk_id": chunks()[2].chunk_id})
    invented = refinement.model_copy(update={"revised": refinement.revised.model_copy(update={"evidence": [foreign]})})
    assert [v.rule_id for v in invented.check_against(context, original, corpus())] == ["G3", "G6"]

    lost = refinement.model_copy(update={"revised": refinement.revised.model_copy(update={"priority": None})})
    assert [v.rule_id for v in lost.check_against(context, original, corpus())] == ["G4"]


def _revise(refinement: RefinementOutput, **fields) -> RefinementOutput:
    return refinement.model_copy(update={"revised": refinement.revised.model_copy(update=fields)})


def test_g6_new_evidence_must_pass_in_the_corpus_of_the_case():
    refinement = valid("refinement_output.json")
    original = valid("extraction_output.json").requirements[0]
    kept = original.evidence[0]
    foreign = ContextItem(item_id="chk-00000000000000aa", kind="source_chunk", rank=2, text="Outro documento.",
                          source_id="src-0000000000000001", chunk_id="chk-00000000000000aa")
    context = valid("retrieved_context.json")
    context = context.model_copy(update={"items": [*context.items, foreign], "limit": 9})

    from_other_document = kept.model_copy(update={"source_id": foreign.source_id, "chunk_id": foreign.chunk_id,
                                                  "quote": "Outro documento."})
    assert [v.rule_id for v in _revise(refinement, evidence=[kept, from_other_document])
            .check_against(context, original, corpus())] == ["G6"], "no contexto de B, mas fora do corpus do caso"

    misquoted = kept.model_copy(update={"quote": "o sistema tem de aceitar reservas sobrepostas"})
    assert [v.rule_id for v in _revise(refinement, evidence=[kept, misquoted])
            .check_against(context, original, corpus())] == ["G6"]

    second_quote = kept.model_copy(update={"quote": "Os técnicos precisam reservar um equipamento por horário"})
    assert _revise(refinement, evidence=[kept, second_quote]).check_against(context, original, corpus()) == []
    case_corpus = CorpusIndex.from_chunks([c for c in chunks() if c.chunk_id != kept.chunk_id])
    assert "G6" in {v.rule_id for v in _revise(refinement, evidence=[kept, second_quote])
                    .check_against(context, original, case_corpus)}, "o corpus é o do caso, não o do banco"


def test_g6_priority_and_method_need_a_new_valid_evidence():
    refinement = valid("refinement_output.json")
    original = valid("extraction_output.json").requirements[0].model_copy(
        update={"priority": None, "verification_method": None})
    context = valid("retrieved_context.json")
    kept = original.evidence[0]

    filled = _revise(refinement, evidence=[kept])
    assert [(v.rule_id, v.detail) for v in filled.check_against(context, original, corpus())] == [
        ("G6", "priority preenchido sem evidência nova válida"),
        ("G6", "verification_method preenchido sem evidência nova válida"),
    ]
    still_null = _revise(refinement, evidence=[kept], priority=None, verification_method=None)
    assert still_null.check_against(context, original, corpus()) == []

    signal = kept.model_copy(update={"quote": "Os técnicos precisam reservar um equipamento por horário"})
    assert _revise(refinement, evidence=[kept, signal]).check_against(context, original, corpus()) == []
    invented_signal = kept.model_copy(update={"quote": "é essencial e será testado"})
    assert [v.rule_id for v in _revise(refinement, evidence=[kept, invented_signal])
            .check_against(context, original, corpus())] == ["G6", "G6", "G6"]


def test_classification_context_cannot_contain_the_item():
    item = valid("classification_output.json")
    context = RetrievedContext(query="classificar", strategy="graph_local", limit=3, items=[
        {"item_id": item.promise_id, "kind": "requirement", "rank": 0, "text": "x",
         "source_id": chunks()[0].source_id, "chunk_id": chunks()[0].chunk_id},
    ])
    assert [v.rule_id for v in item.check_against(context, item, "texto do item")] == ["G5"]
    assert item.is_functional is False


def test_g5_catches_a_copy_of_the_item_under_another_promise_id():
    item = valid("classification_output.json")
    text = "The  system shall\nrefresh the display every 60 seconds."
    copy = {"item_id": "PROMISE-NFR-9999", "kind": "requirement", "rank": 0,
            "text": "the system shall refresh the DISPLAY every 60 seconds.",
            "source_id": chunks()[0].source_id, "chunk_id": chunks()[0].chunk_id}
    other = {**copy, "item_id": "PROMISE-NFR-9998", "text": "The system shall refresh the display hourly."}
    context = RetrievedContext(query="classificar", strategy="source_chunks", limit=3, items=[other, copy])
    assert [(v.rule_id, v.detail) for v in item.check_against(context, item, text)] == [
        ("G5", "PROMISE-NFR-9999 tem o mesmo texto do item avaliado")]
    clean = context.model_copy(update={"items": [ContextItem(**other)]})
    assert item.check_against(clean, item, text) == []


def test_promise_labels_match_the_converter():
    sys.path.insert(0, str(CODE / "benchmarks"))
    import promise

    assert {label.value for label in PromiseLabel} == set(promise.LABEL_NAMES)


def test_experiment_config_loads_but_is_not_runnable_without_choices():
    loaded = config()
    assert loaded.refinement.max_calls == 1
    assert loaded.repetitions.structural_sample == 3
    assert loaded.model.provider == "ollama"
    loaded.ensure_runnable()
    blank = loaded.model_copy(update={
        "model": loaded.model.model_copy(update={"model_id": "", "model_digest": "", "seed": None}),
        "evaluation": loaded.evaluation.model_copy(update={"bertscore_model": ""}),
    })
    with pytest.raises(ContractError, match="model_id.*model_digest.*model.seed.*bertscore_model"):
        blank.ensure_runnable()


def test_model_config_keeps_ollama_fields_out_of_anthropic():
    base = config().model.model_dump()
    with pytest.raises(ValidationError, match="valem só para provider"):
        ModelConfig.model_validate({**base, "provider": "anthropic"})
    anthropic = {**base, "provider": "anthropic", "model_digest": "", "seed": None, "num_ctx": None}
    assert ModelConfig.model_validate(anthropic).provider == "anthropic"
    with pytest.raises(ValidationError, match="valem só para provider"):
        ModelConfig.model_validate({**base, "provider": "openrouter"})
    openrouter = {**base, "provider": "openrouter", "model_digest": "", "num_ctx": None,
                  "base_url": "https://openrouter.ai/api/v1", "model_id": "anthropic/claude-sonnet-4"}
    assert ModelConfig.model_validate(openrouter).provider == "openrouter"
    with pytest.raises(ValidationError, match="num_ctx"):
        ModelConfig.model_validate({**base, "num_ctx": base["max_tokens"]})
    with pytest.raises(ValidationError, match="model_digest"):
        ModelConfig.model_validate({**base, "model_digest": "bdbd181c33f2"})


@pytest.mark.parametrize("path, value, field", [
    (("refinement", "max_calls"), 2, "refinement.max_calls"),
    (("conditions",), ["LLM-only", "LightRAG"], "conditions"),
    (("repetitions", "structural_sample"), 1, "repetitions.structural_sample"),
    (("chunking", "overlap_chars"), 200, "overlap_chars"),
])
def test_config_rejects_out_of_contract_values(path, value, field):
    data = json.loads(config().model_dump_json())
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ContractError, match=field.replace(".", r"\.")):
        parse(data, ExperimentConfig, "experiment.toml")


def test_requirement_keeps_id_through_one_revision():
    requirement = valid("requirement.json")
    revised = requirement.model_copy(update={
        "statement": "O sistema deve impedir reservas sobrepostas do mesmo equipamento.",
        "revision": 1,
        "previous_statement": requirement.statement,
    })
    models.Requirement.model_validate(revised.model_dump())


def test_permutations_of_relation_order_do_not_change_violations():
    output = valid("extraction_with_violations.json")
    baseline = check_all(output, corpus())
    for permutation in itertools.islice(itertools.permutations(output.relations), 0, 40, 7):
        shuffled = output.model_copy(update={"relations": list(permutation)})
        found = check_all(shuffled, corpus())
        assert [(v.rule_id, v.subject) for v in found if v.rule_id[0] != "P" and v.rule_id != "K2"] == [
            (v.rule_id, v.subject) for v in baseline if v.rule_id[0] != "P" and v.rule_id != "K2"
        ]
