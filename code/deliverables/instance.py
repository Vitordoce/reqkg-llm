"""Instância parcial do ReqKG: os registros que uma carga limpa da saída final gravaria no Neo4j.

Cada caso passa por domain.persist.to_records sobre a saída final da condição, com o corpus do
caso, como no executor. Os lotes são
unidos em ordem de case_id pela mesma regra de write_batch (graph.properties.merge_provenance).
O resultado sai no formato de graph.state.logical_state, com o mesmo SHA-256.
"""

import hashlib
from collections import Counter
from dataclasses import dataclass

from pydantic import BaseModel

from domain.enums import NodeKind, QualityCategory
from domain.llm_io import ExtractionOutput
from domain.models import (
    Actor, Entity, QualityAttribute, Relation, Requirement, SoftwareComponent, SourceChunk, SourceDocument,
)
from domain.persist import PersistBatch, Rejection, to_records
from graph.properties import MODEL_OF_KIND, merge_provenance, node_key, node_props, relation_endpoints, relation_props
from graph.schema import CONTAINS, LABELS, SUPPORTS
from graph.state import canonical

from deliverables.inputs import DeliverableError, Inputs

PROVENANCE_KINDS = (NodeKind.REQUIREMENT, NodeKind.ACTOR, NodeKind.SOFTWARE_COMPONENT, NodeKind.ENTITY)
BATCH_FIELD = {NodeKind.REQUIREMENT: "requirements", NodeKind.ACTOR: "actors",
               NodeKind.SOFTWARE_COMPONENT: "components", NodeKind.ENTITY: "entities"}


@dataclass(frozen=True)
class CaseRecords:
    case_id: str
    batch: PersistBatch
    creator: dict[str, str]  # requirement_id -> chave do candidato que gerou o requisito


def _creators(output: ExtractionOutput, batch: PersistBatch) -> dict[str, str]:
    recorded = {r.requirement_id for r in batch.requirements}
    creators: dict[str, str] = {}
    for candidate in output.requirements:
        requirement_id = batch.key_to_id.get(candidate.key)
        if requirement_id in recorded:
            creators.setdefault(requirement_id, candidate.key)
    return creators


def case_records(inputs: Inputs) -> list[CaseRecords]:
    """O refinado aceito entra como revisão 1, pela regra de domain.persist.to_records."""
    records = []
    for final in inputs.finals:
        if final.output is None:
            continue
        original = {r.key: r.statement for r in inputs.shared[final.case_id].requirements}
        batch = to_records(final.output, inputs.case_corpus(final.case_id), inputs.confidence_threshold,
                           revisions={key: original[key] for key in final.accepted})
        records.append(CaseRecords(final.case_id, batch, _creators(final.output, batch)))
    return records


@dataclass(frozen=True)
class Instance:
    documents: list[SourceDocument]
    chunks: list[SourceChunk]
    requirements: dict[str, Requirement]
    actors: dict[str, Actor]
    components: dict[str, SoftwareComponent]
    entities: dict[str, Entity]
    quality_attributes: list[QualityAttribute]
    relations: dict[str, Relation]
    rejected: list[tuple[str, Rejection]]

    def node_rows(self) -> list[tuple[str, str, dict]]:
        models: list[BaseModel] = [*self.documents, *self.chunks, *self.requirements.values(), *self.actors.values(),
                                   *self.components.values(), *self.entities.values(), *self.quality_attributes]
        rows = []
        for model in models:
            kind, key = node_key(model)
            rows.append((LABELS[kind][0], key, node_props(model)))
        return sorted(rows, key=lambda r: (r[0], r[1]))

    def relation_rows(self) -> list[tuple[str, tuple[str, str], tuple[str, str], dict]]:
        rows = [(CONTAINS, ("SourceDocument", c.source_id), ("SourceChunk", c.chunk_id), {}) for c in self.chunks]
        supports = {(e.chunk_id, r.requirement_id) for r in self.requirements.values() for e in r.provenance.evidence}
        rows += [(SUPPORTS, ("SourceChunk", c), ("Requirement", r), {}) for c, r in supports]
        for relation in self.relations.values():
            source, target = relation_endpoints(relation)
            rows.append((relation.type.neo4j_type, (LABELS[relation.source.kind][0], source),
                         (LABELS[relation.target.kind][0], target), relation_props(relation)))
        return sorted(rows, key=lambda r: (r[0], r[1], r[2]))

    def logical_state(self) -> tuple[dict[str, int], dict[str, int], str]:
        """Contagens e SHA-256 como graph.state.logical_state calcula sobre o Neo4j."""
        nodes = sorted(([[label], props] for label, _, props in self.node_rows()), key=canonical)
        relations = sorted(([kind, list(a), list(b), props] for kind, a, b, props in self.relation_rows()),
                           key=canonical)
        digest = hashlib.sha256(canonical({"nodes": nodes, "relations": relations}).encode("utf-8")).hexdigest()
        node_counts = Counter(label for (label,), _ in nodes)
        relation_counts = Counter(r[0] for r in relations)
        return dict(sorted(node_counts.items())), dict(sorted(relation_counts.items())), digest


def build_instance(inputs: Inputs, cases: list[CaseRecords]) -> Instance:
    store: dict[NodeKind, dict[str, BaseModel]] = {kind: {} for kind in PROVENANCE_KINDS}
    relations: dict[str, Relation] = {}
    qualities: set[QualityCategory] = set()
    rejected: list[tuple[str, Rejection]] = []
    for case in cases:
        for kind in PROVENANCE_KINDS:
            for model in getattr(case.batch, BATCH_FIELD[kind]):
                key = node_key(model)[1]
                previous = store[kind].get(key)
                merged = merge_provenance(previous.provenance if previous else None, model.provenance)
                store[kind][key] = MODEL_OF_KIND[kind].model_validate(
                    model.model_copy(update={"provenance": merged}).model_dump())
        for relation in case.batch.relations:
            previous = relations.get(relation.relation_id)
            merged = merge_provenance(previous.provenance if previous else None, relation.provenance)
            relations[relation.relation_id] = relation.model_copy(update={"provenance": merged})
        qualities |= {q.category for q in case.batch.quality_attributes}
        rejected += [(case.case_id, r) for r in case.batch.rejected]
    cited = {e.source_id for kind in PROVENANCE_KINDS for m in store[kind].values() for e in m.provenance.evidence}
    if cited - {d.source_id for d in inputs.documents}:
        raise DeliverableError(f"evidência gravada cita fontes fora da ingestão: {sorted(cited - {d.source_id for d in inputs.documents})}")
    sort = lambda d: dict(sorted(d.items()))  # noqa: E731
    return Instance(
        documents=inputs.documents, chunks=inputs.chunks,
        requirements=sort(store[NodeKind.REQUIREMENT]), actors=sort(store[NodeKind.ACTOR]),
        components=sort(store[NodeKind.SOFTWARE_COMPONENT]), entities=sort(store[NodeKind.ENTITY]),
        quality_attributes=[QualityAttribute(category=c) for c in sorted(qualities)],
        relations=sort(relations), rejected=rejected,
    )
