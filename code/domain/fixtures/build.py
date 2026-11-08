"""Gera os fixtures do contrato a partir do texto sintético.

Uso, a partir da raiz do repositório:
    .venv/bin/python code/domain/fixtures/build.py          # reescreve
    .venv/bin/python code/domain/fixtures/build.py --check  # falha se o disco divergir
"""

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1]))

from domain import ids  # noqa: E402
from domain.enums import NodeKind, RelationType  # noqa: E402

CORPUS_PATH = "code/domain/fixtures/corpus/entrevista_sintetica.txt"
DELETE = "__DELETE__"


def chunk_paragraphs(text: str, source: str) -> list[dict]:
    chunks, cursor, seen = [], 0, {}
    for index, paragraph in enumerate(p for p in text.split("\n\n") if p.strip()):
        paragraph = paragraph.strip("\n")
        start = text.index(paragraph, cursor)
        cursor = start + len(paragraph)
        occurrence = seen.get(paragraph, 0)
        seen[paragraph] = occurrence + 1
        chunks.append(
            {
                "chunk_id": ids.chunk_id(source, paragraph, occurrence),
                "source_id": source,
                "index": index,
                "occurrence": occurrence,
                "char_start": start,
                "char_end": cursor,
                "text": paragraph,
                "sha256": ids.sha256_text(paragraph),
            }
        )
    return chunks


def evidence(source: str, chunk: dict, quote: str) -> dict:
    assert quote in chunk["text"], quote
    return {"source_id": source, "chunk_id": chunk["chunk_id"], "quote": quote}


def build() -> dict[str, object]:
    text = (ROOT / "corpus" / "entrevista_sintetica.txt").read_text(encoding="utf-8")
    src = ids.source_id(CORPUS_PATH)
    chunks = chunk_paragraphs(text, src)
    _, c1, c2, c3 = chunks

    document = {
        "source_id": src,
        "path": CORPUS_PATH,
        "sha256": ids.sha256_text(text),
        "kind": "interview",
        "title": "Entrevista sintética de desenvolvimento",
        "char_count": len(text),
    }

    no_overlap = evidence(src, c1, "o sistema tem de impedir duas reservas no mesmo horário")
    statement = "O sistema deve impedir duas reservas do mesmo equipamento no mesmo horário."
    req_id = ids.requirement_id(src, c1["chunk_id"], statement)
    requirement = {
        "requirement_id": req_id,
        "statement": statement,
        "type": "functional",
        "priority": "must",
        "verification_method": "test",
        "status": "draft",
        "quality_attributes": [],
        "quantitative_value": None,
        "review_flags": [],
        "provenance": {"origin": "extracted_fact", "evidence": [no_overlap], "validation": "unvalidated", "note": None},
    }

    coordinator = "Coordenadora do laboratório"
    actor = {
        "actor_id": ids.actor_id(coordinator),
        "name": coordinator,
        "kind": "stakeholder",
        "provenance": {
            "origin": "extracted_fact",
            "evidence": [evidence(src, c1, coordinator)],
            "validation": "unvalidated",
            "note": None,
        },
    }

    relation = {
        "relation_id": ids.relation_id(RelationType.REQUESTED_BY, req_id, actor["actor_id"]),
        "type": "requested_by",
        "source": {"kind": NodeKind.REQUIREMENT.value, "id": req_id},
        "target": {"kind": NodeKind.ACTOR.value, "id": actor["actor_id"]},
        "provenance": {
            "origin": "extracted_fact",
            "evidence": [no_overlap],
            "validation": "unvalidated",
            "note": None,
        },
    }

    alert = evidence(src, c2, "O sistema deve enviar um aviso ao responsável em até cinco minutos")
    fast = evidence(src, c2, "A consulta da agenda precisa ser rápida")
    cancel = evidence(src, c3, "só a coordenação pode cancelar reserva de outra pessoa")
    retention = evidence(src, c3, "Os dados de uso ficam guardados por dois anos para auditoria")

    clean = {
        "requirements": [
            {"key": "R1", "statement": statement, "type": "functional", "priority": "must",
             "verification_method": "test", "evidence": [no_overlap]},
            {"key": "R2", "statement": "O sistema deve avisar o responsável em até cinco minutos após o vencimento da calibração.",
             "type": "non_functional", "priority": "should", "verification_method": "test",
             "quality_attributes": ["performance"], "quantitative_value": "5 min", "evidence": [alert]},
            {"key": "R3", "statement": "A consulta da agenda deve ter tempo de resposta adequado.",
             "type": "non_functional", "priority": "could", "verification_method": "test",
             "quality_attributes": ["performance"], "review_flags": ["quantitative_value_pending"], "evidence": [fast]},
            {"key": "R4", "statement": "Somente a coordenação pode cancelar reservas de outros usuários.",
             "type": "functional", "priority": "must", "verification_method": "demonstration",
             "quality_attributes": ["security"], "evidence": [cancel]},
            {"key": "R5", "statement": "O sistema deve reter os dados de uso por dois anos.",
             "type": "constraint", "priority": "should", "verification_method": "inspection", "evidence": [retention]},
        ],
        "actors": [
            {"key": "A1", "name": coordinator, "kind": "stakeholder", "evidence": [evidence(src, c1, coordinator)]},
            {"key": "A2", "name": "Técnico", "kind": "user_role", "evidence": [evidence(src, c2, "Técnico")]},
        ],
        "components": [],
        "entities": [
            {"key": "E1", "name": "calibração", "entity_type": "evento", "evidence": [evidence(src, c2, "sai de calibração")]},
        ],
        "relations": [
            {"type": "requested_by", "source_key": "R1", "target_key": "A1", "evidence": [no_overlap]},
            {"type": "requested_by", "source_key": "R2", "target_key": "A2", "evidence": [alert]},
            {"type": "depends_on", "source_key": "R4", "target_key": "R1", "origin": "system_inference",
             "rationale": "Cancelar pressupõe a existência da reserva.", "evidence": [cancel]},
        ],
    }

    ghost_chunk = ids.stable_id("chk", "inexistente")
    violations = {
        "requirements": [
            {"key": "R1", "statement": statement, "type": "functional", "priority": "must",
             "verification_method": "test", "evidence": [no_overlap]},
            {"key": "R2", "statement": "A agenda deve ser rápida.", "type": "non_functional",
             "evidence": [{"source_id": src, "chunk_id": c2["chunk_id"], "quote": "a agenda abre em um segundo"}]},
            {"key": "R3", "statement": "O sistema deve ter login único.", "verification_method": "test", "priority": "wont",
             "type": "functional", "evidence": []},
            {"key": "R4", "statement": "Cancelamento restrito à coordenação.", "type": "functional", "priority": "must",
             "verification_method": "demonstration",
             "evidence": [{"source_id": src, "chunk_id": ghost_chunk, "quote": "só a coordenação"},
                          {"source_id": src, "chunk_id": c3["chunk_id"]}]},
            {"key": "R5", "statement": "O sistema deve reter os dados de uso por dois anos.", "priority": "should",
             "verification_method": "inspection", "evidence": [retention]},
        ],
        "actors": [],
        "components": [],
        "entities": [],
        "relations": [
            {"type": "conflicts_with", "source_key": "R1", "target_key": "R4", "evidence": [cancel]},
            {"type": "duplicates", "source_key": "R4", "target_key": "R1", "evidence": [cancel]},
            {"type": "depends_on", "source_key": "R1", "target_key": "R3", "evidence": []},
            {"type": "depends_on", "source_key": "R3", "target_key": "R1", "evidence": [no_overlap]},
            {"type": "refines", "source_key": "R2", "target_key": "R2", "evidence": [fast]},
            {"type": "refines", "source_key": "R5", "target_key": "R1", "evidence": [retention]},
            {"type": "refines", "source_key": "R1", "target_key": "R5", "evidence": [no_overlap]},
        ],
    }
    expected_violations = [
        ["C1", "R2", "priority ausente"],
        ["C2", "R2", "verification_method ausente"],
        ["C3", "R5", "type ausente"],
        ["C4", "R2", "não funcional sem atributo de qualidade"],
        ["K1", "R1|R4", "conflicts_with e duplicates no mesmo par"],
        ["K2", "relations.4", "refines de R2 para ele mesmo"],
        ["K3", "R1,R3", "ciclo em depends_on"],
        ["K4", "R1,R5", "ciclo em refines"],
        ["K5", "R1->R3", "must depende de wont"],
        ["P1", "R3", "sem evidência"],
        ["P2", "R4", f"{src}/{ghost_chunk} não existe no corpus"],
        ["P3", "R2", f"citação não aparece em {c2['chunk_id']}"],
        ["P4", "R4", "fato extraído sem citação"],
        ["P5", "relations.2", "depends_on sem evidência"],
    ]

    context = {
        "query": f"completar {req_id}",
        "strategy": "graph_local",
        "limit": 5,
        "items": [
            {"item_id": req_id, "kind": "requirement", "rank": 0, "text": statement,
             "source_id": src, "chunk_id": c1["chunk_id"]},
            {"item_id": actor["actor_id"], "kind": "actor", "rank": 1, "text": coordinator,
             "source_id": src, "chunk_id": c1["chunk_id"]},
            {"item_id": c1["chunk_id"], "kind": "source_chunk", "rank": 1, "text": c1["text"],
             "source_id": src, "chunk_id": c1["chunk_id"]},
        ],
    }

    refinement = {
        "target_key": "R1",
        "revised": clean["requirements"][0],
        "used_context_ids": [req_id, c1["chunk_id"]],
    }

    classification = {
        "promise_id": "PROMISE-NFR-0001",
        "label": "PE",
        "rationale": "Declara tempo máximo de resposta.",
        "used_context_ids": [],
    }

    case_ok = {
        "case_id": "fixture-entrevista",
        "run_index": 0,
        "stage": "extraction",
        "status": "ok",
        "extraction": clean,
    }
    case_invalid = {
        "case_id": "fixture-entrevista",
        "run_index": 1,
        "stage": "extraction",
        "status": "invalid_output",
        "error": "relations.0.target_key: 'A9' não é actor",
    }

    valid = {
        "source_document.json": document,
        "source_chunks.json": chunks,
        "requirement.json": requirement,
        "actor.json": actor,
        "relation.json": relation,
        "extraction_output.json": clean,
        "extraction_with_violations.json": violations,
        "expected_violations.json": expected_violations,
        "retrieved_context.json": context,
        "refinement_output.json": refinement,
        "classification_output.json": classification,
        "case_result_ok.json": case_ok,
        "case_result_invalid.json": case_invalid,
    }

    mutations = [
        ("requirement_without_evidence", "requirement.json", "Requirement", [("provenance.evidence", [])], "provenance"),
        ("requirement_priority_not_moscow", "requirement.json", "Requirement", [("priority", "high")], "priority"),
        ("requirement_unknown_field", "requirement.json", "Requirement", [("owner", "ninguém")], "owner"),
        ("requirement_low_confidence_not_in_review", "requirement.json", "Requirement",
         [("review_flags", ["low_confidence"])], "status"),
        ("fact_without_quote", "requirement.json", "Requirement", [("provenance.evidence.0.quote", None)], "evidence.quote"),
        ("decision_without_note", "requirement.json", "Requirement",
         [("provenance.origin", "researcher_decision"), ("provenance.evidence", [])], "note"),
        ("relation_without_evidence", "relation.json", "Relation", [("provenance.evidence", [])], "provenance"),
        ("relation_wrong_target", "relation.json", "Relation",
         [("target", {"kind": "requirement", "id": req_id})], "target"),
        ("chunk_hash_mismatch", "source_chunks.json", "SourceChunk", [("0.sha256", "0" * 64)], "sha256"),
        ("document_id_not_from_path", "source_document.json", "SourceDocument", [("path", "outro/caminho.txt")], "source_id"),
        ("extraction_dangling_key", "extraction_output.json", "ExtractionOutput",
         [("relations.0.target_key", "A9")], "relations.0.target_key"),
        ("extraction_derived_from_by_model", "extraction_output.json", "ExtractionOutput",
         [("relations.0.type", "derived_from")], "relations.0.type"),
        ("extraction_duplicate_key", "extraction_output.json", "ExtractionOutput",
         [("actors.0.key", "R1")], "actors.0.key"),
        ("context_unordered", "retrieved_context.json", "RetrievedContext", [("items.0.rank", 2)], "items"),
        ("context_item_without_chunk", "retrieved_context.json", "RetrievedContext",
         [("items.0.chunk_id", DELETE)], "items.0.chunk_id"),
        ("context_over_limit", "retrieved_context.json", "RetrievedContext", [("limit", 2)], "items"),
        ("document_path_not_canonical", "source_document.json", "SourceDocument",
         [("path", "./" + CORPUS_PATH)], "path"),
        ("requirement_id_not_from_evidence", "requirement.json", "Requirement",
         [("requirement_id", "req-0000000000000000")], "requirement_id"),
        ("requirement_revision_without_previous", "requirement.json", "Requirement",
         [("revision", 1)], "previous_statement"),
        ("requirement_second_revision", "requirement.json", "Requirement",
         [("revision", 2), ("previous_statement", statement)], "revision"),
        ("requirement_decision_without_evidence", "requirement.json", "Requirement",
         [("provenance.origin", "researcher_decision"), ("provenance.note", "decisão de teste"),
          ("provenance.evidence", [])], "requisito gravado precisa de source_id"),
        ("relation_decision_without_evidence", "relation.json", "Relation",
         [("provenance.origin", "researcher_decision"), ("provenance.note", "decisão de teste"),
          ("provenance.evidence", [])], "relação sem source_id"),
        ("extraction_measured_by_by_model", "extraction_output.json", "ExtractionOutput",
         [("relations.0.type", "measured_by")], "relations.0.type"),
        ("context_without_strategy", "retrieved_context.json", "RetrievedContext",
         [("strategy", DELETE)], "strategy"),
        ("classification_unknown_label", "classification_output.json", "ClassificationOutput",
         [("label", "availability")], "label"),
        ("case_ok_without_output", "case_result_ok.json", "CaseResult", [("extraction", DELETE)], "status"),
        ("case_extraction_with_condition", "case_result_ok.json", "CaseResult",
         [("condition", "LLM-only")], "condition"),
        ("case_refinement_without_condition", "case_result_ok.json", "CaseResult",
         [("stage", "refinement"), ("target_key", "R1")], "condition"),
        ("case_refinement_without_target", "case_result_ok.json", "CaseResult",
         [("stage", "refinement"), ("condition", "LLM-only")], "target_key"),
        ("case_extraction_with_target", "case_result_ok.json", "CaseResult",
         [("target_key", "R1")], "target_key"),
        ("case_failed_with_output", "case_result_invalid.json", "CaseResult",
         [("classification", classification)], "status"),
    ]

    invalid, manifest = {}, {}
    for name, base, model, patches, loc in mutations:
        data = copy.deepcopy(valid[base])
        for path, value in patches:
            apply_patch(data, path, value)
        invalid[f"{name}.json"] = data
        manifest[f"{name}.json"] = {"model": model, "many": base == "source_chunks.json", "expected_loc": loc}

    return {
        **{f"valid/{k}": v for k, v in valid.items()},
        **{f"invalid/{k}": v for k, v in invalid.items()},
        "invalid/EXPECTED.json": manifest,
    }


def apply_patch(data: object, path: str, value: object) -> None:
    *parents, last = path.split(".")
    for part in parents:
        data = data[int(part)] if isinstance(data, list) else data[part]
    if isinstance(data, list):
        data[int(last)] = value
    elif value == DELETE:
        del data[last]
    else:
        data[last] = value


def render(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for relative, value in build().items():
        target = ROOT / relative
        content = render(value)
        if check:
            if not target.exists() or target.read_text(encoding="utf-8") != content:
                stale.append(relative)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    if stale:
        print("fixtures desatualizados, rode build.py:", *stale, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
