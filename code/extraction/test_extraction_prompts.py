import json
import re

import pytest

from domain.enums import Condition, ContextStrategy, PromiseLabel
from domain.llm_io import ClassificationOutput, ExtractionOutput, RefinementOutput
from extraction import prompts
from extraction.client import REPO_ROOT
from extraction.fixtures import scenarios
from extraction.schema import inline_refs, output_schema

PROMISE_JSONL = REPO_ROOT / "data" / "processed" / "promise" / "promise_nfr.jsonl"


def test_registry_on_disk_matches_prompt_files():
    assert prompts.main(["--check"]) == 0
    registry = json.loads(prompts.REGISTRY_PATH.read_text(encoding="utf-8"))
    assert set(registry) == {"extraction", "refinement", "classification", "classification_refinement"}
    for name, entry in registry.items():
        assert entry["file"].endswith(f"{name}_v{entry['version']}.md")
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])


def test_registry_hash_changes_with_one_byte(tmp_path, monkeypatch):
    copy = tmp_path / "prompts"
    copy.mkdir()
    for file in prompts.PROMPT_FILES.values():
        (copy / file).write_bytes((prompts.PROMPTS_DIR / file).read_bytes())
    before = prompts.load("refinement").sha256
    monkeypatch.setattr(prompts, "PROMPTS_DIR", copy)
    target = copy / prompts.PROMPT_FILES["refinement"]
    target.write_text(target.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert prompts.load("refinement").sha256 != before


def test_superseded_versions_stay_in_the_registry_without_files():
    registry = json.loads(prompts.REGISTRY_PATH.read_text(encoding="utf-8"))
    for name in ("extraction", "refinement"):
        assert registry[name]["version"] == 2
        [old] = registry[name]["superseded"]
        assert old["version"] == 1 and re.fullmatch(r"[0-9a-f]{64}", old["sha256"])
        assert not (prompts.PROMPTS_DIR / f"{name}_v1.md").exists()
    assert registry["classification"]["superseded"] == []


def _rule(system: str, field: str) -> str:
    return next(line for line in system.splitlines() if line.startswith(f"- {field}"))


def priority_signals() -> list[str]:
    rule = _rule(prompts.load("extraction").system, "priority")
    return re.findall(r'"([^"]+)"', rule[rule.index("Sinais:"):])


@pytest.mark.parametrize("name", ["extraction", "refinement"])
def test_modal_verb_alone_never_sustains_priority(name):
    system = prompts.load(name).system
    assert re.search(r'verbo da necessidade sozinho \("deve", "precisa", "tem de", "não pode"', system)
    assert "Um critério mensurável sozinho" in system
    for line in system.splitlines():
        assert not re.search(r'"must"[^.]*"(deve|tem de|não pode|precisa)"', line), line
    if name == "extraction":
        signals = priority_signals()
        assert {"essencial", "obrigatório", "crítico", "prioridade", "seria bom", "pode ficar para depois",
                "não precisamos agora"} <= set(signals)
        assert not {"deve", "tem de", "não pode", "precisa"} & set(signals)


def test_recorded_priorities_are_backed_by_a_quoted_signal():
    """Todo requisito gravável com prioridade cita a frase com o sinal, como manda o protocolo."""
    from domain.llm_io import ExtractionOutput as Output
    from domain.persist import to_records
    from domain.rules import CorpusIndex

    signals = priority_signals()
    cases = [(scenarios.entrevista_extraction(), scenarios.entrevista_chunks()),
             (scenarios.recorded("extracao_ata_inventada", Output), scenarios.ata_chunks())]
    with_priority = 0
    for output, chunks in cases:
        batch = to_records(output, CorpusIndex.from_chunks(chunks), scenarios.config().review.confidence_threshold)
        for requirement in batch.requirements:
            quotes = " ".join(e.quote or "" for e in requirement.provenance.evidence).casefold()
            if requirement.priority is not None:
                with_priority += 1
                assert any(signal.casefold() in quotes for signal in signals), requirement.statement
            assert requirement.verification_method is None, requirement.statement
    assert with_priority == 1


def test_note_above_system_is_not_sent():
    template = prompts.load("extraction")
    assert "escrito em 10 de outubro" not in template.system
    assert template.system.startswith("Você extrai requisitos")


def test_extraction_prompt_shows_ids_and_rules():
    chunks = scenarios.entrevista_chunks()
    prompt = prompts.extraction_prompt(chunks[1:3])
    for chunk in chunks[1:3]:
        assert f'source_id="{chunk.source_id}" chunk_id="{chunk.chunk_id}"' in prompt.user
        assert chunk.text in prompt.user
    assert "$" not in prompt.user
    assert "citação literal" in prompt.system
    assert "Não proponha derived_from, mentions nem measured_by" in prompt.system
    assert "Sem ambiguidade de tipo, rationale fica null" in prompt.system
    assert prompt.output_model is ExtractionOutput


def test_prompt_examples_come_only_from_synthetic_fixture():
    dev_text = (REPO_ROOT / "code/domain/fixtures/corpus/entrevista_sintetica.txt").read_text(encoding="utf-8")
    for name in prompts.PROMPT_FILES:
        system = prompts.load(name).system
        for example in re.findall(r"<trecho [^>]*>\n(.*?)\n</trecho>", system, flags=re.DOTALL):
            assert example in dev_text


def test_no_promise_text_in_prompts_or_fixtures():
    records = [json.loads(line) for line in PROMISE_JSONL.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 625
    texts = [prompts.load(name).system + prompts.load(name).user.template for name in prompts.PROMPT_FILES]
    texts.append((REPO_ROOT / scenarios.ITEMS_PATH).read_text(encoding="utf-8"))
    for record in records:
        for text in texts:
            assert record["text"] not in text, record["promise_id"]
    assert all(int(i[-4:]) > 625 for i in scenarios.classification_items())


def _definitions(name: str) -> str:
    system = prompts.load(name).system
    return system[system.index("Rótulos\n"):system.index("\n\n", system.index("Rótulos\n"))]


def test_classification_is_zero_shot_with_every_label_defined():
    block = _definitions("classification")
    assert block == _definitions("classification_refinement")
    labels = re.findall(r"^- ([A-Z]+), ", block, flags=re.MULTILINE)
    assert labels == [label.value for label in PromiseLabel]
    assert "Não há exemplos" in prompts.load("classification").system


@pytest.mark.parametrize("model", [ExtractionOutput, RefinementOutput, ClassificationOutput])
def test_output_schema_has_no_references(model):
    schema = output_schema(model)
    text = json.dumps(schema)
    assert "$ref" not in text and "$defs" not in text
    assert schema["type"] == "object" and schema["additionalProperties"] is False


def test_inline_refs_refuses_recursive_schema():
    with pytest.raises(ValueError, match="recursivo"):
        inline_refs({"$defs": {"N": {"type": "object", "properties": {"n": {"$ref": "#/$defs/N"}}}},
                     "$ref": "#/$defs/N"})


def test_refinement_prompt_is_the_same_in_both_conditions_except_context():
    candidate, reasons = scenarios.agenda_candidate(), scenarios.agenda_reasons()
    a = prompts.refinement_prompt(candidate, scenarios.agenda_source_context(), reasons)
    b = prompts.refinement_prompt(candidate, scenarios.agenda_graph_context(), reasons)
    assert a.system == b.system and a.template_sha256 == b.template_sha256
    head, tail = "Itens de contexto:\n", "\n\nResponda só"
    strip = lambda text: text[:text.index(head)] + text[text.index(tail):]  # noqa: E731
    assert strip(a.user) == strip(b.user)
    assert a.user != b.user
    for prompt in (a, b):
        for leak in [c.value for c in Condition] + [s.value for s in ContextStrategy] + ["completar ", "refinar "]:
            assert leak not in prompt.system + prompt.user


def test_refinement_prompt_carries_candidate_and_reasons():
    prompt = prompts.refinement_prompt(scenarios.agenda_candidate(), scenarios.agenda_source_context(),
                                       scenarios.agenda_reasons())
    assert "target_key: c1-R2" in prompt.user
    assert "- C1: priority ausente" in prompt.user
    assert "- C2: verification_method ausente" in prompt.user
    assert "- marca de revisão: quantitative_value_pending" in prompt.user
    assert "Nunca preencha priority nem verification_method" in prompt.system


def test_empty_context_is_rendered_explicitly():
    prompt = scenarios.SCENARIOS[8].build()
    assert prompt.name == "classification_refinement"
    assert prompts.NO_CONTEXT in prompt.user
