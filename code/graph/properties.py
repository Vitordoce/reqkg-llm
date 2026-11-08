"""Conversão entre os registros do contrato e as propriedades dos nós e arestas.

Neo4j não guarda lista de mapas. A evidência vai como JSON canônico em evidence_json, e os
chunk_id citados vão em evidence_chunk_ids, que as consultas e a invalidação usam.
"""

import json

from pydantic import BaseModel

from domain.enums import SYMMETRIC_RELATIONS, NodeKind, Origin
from domain.models import (
    Actor,
    Entity,
    Evidence,
    Provenance,
    QualityAttribute,
    Relation,
    Requirement,
    SoftwareComponent,
    SourceChunk,
    SourceDocument,
)
from graph.schema import LABELS

MODEL_OF_KIND: dict[NodeKind, type[BaseModel]] = {
    NodeKind.SOURCE_DOCUMENT: SourceDocument,
    NodeKind.SOURCE_CHUNK: SourceChunk,
    NodeKind.REQUIREMENT: Requirement,
    NodeKind.ACTOR: Actor,
    NodeKind.SOFTWARE_COMPONENT: SoftwareComponent,
    NodeKind.ENTITY: Entity,
    NodeKind.QUALITY_ATTRIBUTE: QualityAttribute,
}
KIND_OF_MODEL = {model: kind for kind, model in MODEL_OF_KIND.items()}
PROVENANCE_FIELDS = ("origin", "validation", "note", "evidence_json", "evidence_chunk_ids")


class GraphWriteError(RuntimeError):
    pass


def _evidence_key(e: Evidence) -> tuple[str, str, str]:
    return (e.chunk_id, e.source_id, e.quote or "")


def unique_evidence(evidence: list[Evidence]) -> list[Evidence]:
    return [e for _, e in sorted({_evidence_key(e): e for e in evidence}.items())]


def encode_evidence(evidence: list[Evidence]) -> str:
    data = [e.model_dump(mode="json") for e in unique_evidence(evidence)]
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def decode_evidence(text: str) -> list[Evidence]:
    return [Evidence.model_validate(item) for item in json.loads(text)]


def provenance_props(provenance: Provenance) -> dict:
    evidence = unique_evidence(provenance.evidence)
    return {
        "origin": provenance.origin.value,
        "validation": provenance.validation.value,
        "note": provenance.note,
        "evidence_json": encode_evidence(evidence),
        "evidence_chunk_ids": sorted({e.chunk_id for e in evidence}),
    }


def provenance_from_props(props: dict) -> Provenance:
    return Provenance(
        origin=props["origin"], validation=props["validation"], note=props.get("note"),
        evidence=decode_evidence(props["evidence_json"]),
    )


def merge_provenance(existing: Provenance | None, new: Provenance) -> Provenance:
    """O mesmo nó gravado por dois lotes acumula a evidência dos dois.

    Fato extraído só continua fato se os dois lados forem fato. Decisão do pesquisador não é
    sobrescrita por uma extração. No resto, validação e nota vêm do lote mais novo.
    """
    if existing is None:
        return new
    evidence = unique_evidence([*existing.evidence, *new.evidence])
    if Origin.RESEARCHER_DECISION in (existing.origin, new.origin):
        decided = new if new.origin is Origin.RESEARCHER_DECISION else existing
        return Provenance(origin=Origin.RESEARCHER_DECISION, evidence=evidence,
                          validation=decided.validation, note=decided.note)
    both_facts = existing.origin is new.origin is Origin.EXTRACTED_FACT
    return Provenance(origin=Origin.EXTRACTED_FACT if both_facts else Origin.SYSTEM_INFERENCE,
                      evidence=evidence, validation=new.validation, note=new.note)


def node_key(model: BaseModel) -> tuple[NodeKind, str]:
    kind = KIND_OF_MODEL[type(model)]
    if kind is NodeKind.QUALITY_ATTRIBUTE:
        return kind, model.quality_attribute_id
    return kind, getattr(model, LABELS[kind][1])


def node_props(model: BaseModel) -> dict:
    """Propriedade nula não existe no Neo4j, então não entra no mapa."""
    data = model.model_dump(mode="json", exclude={"provenance"})
    kind, key = node_key(model)
    data[LABELS[kind][1]] = key
    if "provenance" in type(model).model_fields:
        data |= provenance_props(model.provenance)
    return {k: v for k, v in sorted(data.items()) if v is not None}


def model_from_props(kind: NodeKind, props: dict) -> BaseModel:
    if kind is NodeKind.QUALITY_ATTRIBUTE:
        return QualityAttribute(category=props["category"])
    model = MODEL_OF_KIND[kind]
    data = {k: v for k, v in props.items() if k in model.model_fields and k != "provenance"}
    if "provenance" in model.model_fields:
        data["provenance"] = provenance_from_props(props)
    return model.model_validate(data)


def relation_endpoints(relation: Relation) -> tuple[str, str]:
    """Em relação simétrica a aresta vai sempre do menor para o maior identificador."""
    source, target = relation.source.id, relation.target.id
    if relation.type in SYMMETRIC_RELATIONS:
        source, target = sorted((source, target))
    return source, target


def relation_props(relation: Relation, provenance: Provenance | None = None) -> dict:
    provenance = provenance or relation.provenance
    if not provenance.evidence or any(not e.source_id or not e.chunk_id for e in provenance.evidence):
        raise GraphWriteError(f"{relation.relation_id}: relação sem source_id e chunk_id não é gravada")
    props = {"relation_id": relation.relation_id, **provenance_props(provenance)}
    return {k: v for k, v in sorted(props.items()) if v is not None}
