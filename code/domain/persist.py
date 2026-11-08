"""Converte a resposta do modelo em registros graváveis no ReqKG.

Só entra o que tem evidência que resolve no corpus. O resto vira Rejection, que o
experimento reporta à parte. As métricas não passam por aqui: elas leem o ExtractionOutput.
"""

from collections.abc import Mapping

from pydantic import Field

from domain import ids
from domain.enums import NodeKind, Origin, RelationType, RequirementStatus, ReviewFlag
from domain.llm_io import CitedEvidence, ExtractionOutput
from domain.models import (
    Actor,
    ContractModel,
    Entity,
    Evidence,
    NodeRef,
    Provenance,
    QualityAttribute,
    Relation,
    Requirement,
    SoftwareComponent,
    primary_evidence,
)
from domain.rules import CorpusIndex

BLOCKING_FLAGS = {ReviewFlag.LOW_CONFIDENCE, ReviewFlag.AMBIGUOUS_TYPE}


class Rejection(ContractModel):
    rule_id: str
    subject: str
    detail: str


class PersistBatch(ContractModel):
    requirements: list[Requirement] = Field(default_factory=list)
    actors: list[Actor] = Field(default_factory=list)
    components: list[SoftwareComponent] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    quality_attributes: list[QualityAttribute] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    rejected: list[Rejection] = Field(default_factory=list)
    key_to_id: dict[str, str] = Field(default_factory=dict)


REJECTION_RULES = {
    "W1": "Item sem nenhuma evidência que resolve no corpus com citação presente no chunk.",
    "W2": "Relação com uma ponta que não foi gravada.",
    "W3": "Relação sem evidência que resolve no corpus.",
    "W4": "Ator com o mesmo nome e tipo diferente de um ator já gravado. Vale o primeiro.",
    "W5": "Relação que liga um nó a ele mesmo depois da resolução de identificadores.",
    "W6": "Requisito com o mesmo identificador de outro já gravado. Vale o primeiro.",
}


def _resolved(evidence: list[CitedEvidence], corpus: CorpusIndex) -> list[Evidence]:
    unique = {
        (e.source_id, e.chunk_id, e.quote): Evidence(source_id=e.source_id, chunk_id=e.chunk_id, quote=e.quote)
        for e in evidence
        if corpus.supports(e)
    }
    return [unique[k] for k in sorted(unique, key=lambda k: (k[1], k[0], k[2] or ""))]


def _origin(declared: Origin, evidence: list[Evidence]) -> Origin:
    """Fato extraído sem citação em toda evidência é gravado como inferência do sistema."""
    if declared is Origin.EXTRACTED_FACT and all(e.quote for e in evidence):
        return Origin.EXTRACTED_FACT
    return Origin.SYSTEM_INFERENCE


def _provenance(declared: Origin, evidence: list[Evidence]) -> Provenance:
    return Provenance(origin=_origin(declared, evidence), evidence=evidence)


def _union(existing: Provenance, evidence: list[Evidence]) -> Provenance:
    """Mesmo nó citado em mais de uma chamada: a evidência é a união das duas."""
    merged = {(e.source_id, e.chunk_id, e.quote): e for e in [*existing.evidence, *evidence]}
    ordered = [merged[k] for k in sorted(merged, key=lambda k: (k[1], k[0], k[2] or ""))]
    return _provenance(existing.origin, ordered)


def to_records(output: ExtractionOutput, corpus: CorpusIndex, confidence_threshold: float,
               revisions: Mapping[str, str] | None = None) -> PersistBatch:
    """revisions: para cada chave com refinamento aceito, a declaração original, da extração.

    Essas chaves viram revisão 1: o identificador sai da evidência primária do refinado e da
    declaração original, que fica em previous_statement. Vale também quando a declaração não mudou.
    """
    revisions = dict(revisions or {})
    unknown = sorted(set(revisions) - {r.key for r in output.requirements})
    if unknown:
        raise ValueError(f"revisions: chaves que não são requisito da saída: {unknown}")
    batch = PersistBatch()
    reject = lambda rule, subject, detail: batch.rejected.append(Rejection(rule_id=rule, subject=subject, detail=detail))  # noqa: E731
    node_kind: dict[str, NodeKind] = {}

    requirements: dict[str, Requirement] = {}
    for candidate in output.requirements:
        evidence = _resolved(candidate.evidence, corpus)
        if not evidence:
            reject("W1", candidate.key, "requisito sem evidência que resolve")
            continue
        primary = primary_evidence(evidence)
        previous = revisions.get(candidate.key)
        requirement_id = ids.requirement_id(primary.source_id, primary.chunk_id,
                                            candidate.statement if previous is None else previous)
        if requirement_id in requirements:
            reject("W6", candidate.key, f"mesmo identificador que outro candidato: {requirement_id}")
            batch.key_to_id[candidate.key] = requirement_id
            continue
        flags = set(candidate.review_flags)
        if candidate.confidence is not None and candidate.confidence < confidence_threshold:
            flags.add(ReviewFlag.LOW_CONFIDENCE)
        status = RequirementStatus.NEEDS_REVIEW if flags & BLOCKING_FLAGS else RequirementStatus.DRAFT
        requirements[requirement_id] = Requirement(
            requirement_id=requirement_id,
            statement=candidate.statement,
            revision=1 if previous is not None else 0,
            previous_statement=previous,
            type=candidate.type,
            priority=candidate.priority,
            verification_method=candidate.verification_method,
            status=status,
            quality_attributes=candidate.quality_attributes,
            quantitative_value=candidate.quantitative_value,
            review_flags=sorted(flags),
            provenance=_provenance(candidate.origin, evidence),
        )
        batch.key_to_id[candidate.key] = requirement_id
        node_kind[requirement_id] = NodeKind.REQUIREMENT

    actors: dict[str, Actor] = {}
    for candidate in output.actors:
        evidence = _resolved(candidate.evidence, corpus)
        if not evidence:
            reject("W1", candidate.key, "ator sem evidência que resolve")
            continue
        actor_id = ids.actor_id(candidate.name)
        batch.key_to_id[candidate.key] = actor_id
        if actor_id in actors:
            if actors[actor_id].kind is not candidate.kind:
                reject("W4", candidate.key, f"{candidate.name!r} já gravado como {actors[actor_id].kind.value}")
            else:
                actors[actor_id] = actors[actor_id].model_copy(
                    update={"provenance": _union(actors[actor_id].provenance, evidence)})
            continue
        actors[actor_id] = Actor(
            actor_id=actor_id, name=candidate.name, kind=candidate.kind,
            provenance=_provenance(Origin.EXTRACTED_FACT, evidence),
        )
        node_kind[actor_id] = NodeKind.ACTOR

    components: dict[str, SoftwareComponent] = {}
    for candidate in output.components:
        evidence = _resolved(candidate.evidence, corpus)
        if not evidence:
            reject("W1", candidate.key, "componente sem evidência que resolve")
            continue
        component_id = ids.component_id(candidate.name)
        batch.key_to_id[candidate.key] = component_id
        if component_id in components:
            components[component_id] = components[component_id].model_copy(
                update={"provenance": _union(components[component_id].provenance, evidence)})
        else:
            components[component_id] = SoftwareComponent(
                component_id=component_id, name=candidate.name, description=candidate.description,
                provenance=_provenance(Origin.EXTRACTED_FACT, evidence),
            )
        node_kind[component_id] = NodeKind.SOFTWARE_COMPONENT

    entities: dict[str, Entity] = {}
    for candidate in output.entities:
        evidence = _resolved(candidate.evidence, corpus)
        if not evidence:
            reject("W1", candidate.key, "entidade sem evidência que resolve")
            continue
        entity_id = ids.entity_id(candidate.name, candidate.entity_type)
        batch.key_to_id[candidate.key] = entity_id
        if entity_id in entities:
            entities[entity_id] = entities[entity_id].model_copy(
                update={"provenance": _union(entities[entity_id].provenance, evidence)})
        else:
            entities[entity_id] = Entity(
                entity_id=entity_id, name=candidate.name, entity_type=candidate.entity_type,
                description=candidate.description, provenance=_provenance(Origin.EXTRACTED_FACT, evidence),
            )
        node_kind[entity_id] = NodeKind.ENTITY

    relations: dict[str, Relation] = {}

    def add(kind: RelationType, source: NodeRef, target: NodeRef, provenance: Provenance) -> None:
        relation_id = ids.relation_id(kind, source.id, target.id)
        relations.setdefault(relation_id, Relation(
            relation_id=relation_id, type=kind, source=source, target=target, provenance=provenance,
        ))

    for index, candidate in enumerate(output.relations):
        subject = f"relations.{index}"
        source_id = batch.key_to_id.get(candidate.source_key)
        target_id = batch.key_to_id.get(candidate.target_key)
        if source_id not in node_kind or target_id not in node_kind:
            reject("W2", subject, f"{candidate.source_key} ou {candidate.target_key} não foi gravado")
            continue
        if source_id == target_id:
            reject("W5", subject, f"{candidate.type.value} liga {source_id} a ele mesmo")
            continue
        evidence = _resolved(candidate.evidence, corpus)
        if not evidence:
            reject("W3", subject, f"{candidate.type.value} sem evidência que resolve")
            continue
        add(candidate.type, NodeRef(kind=node_kind[source_id], id=source_id),
            NodeRef(kind=node_kind[target_id], id=target_id), _provenance(candidate.origin, evidence))

    qualities: set = set()
    for requirement in requirements.values():
        source = NodeRef(kind=NodeKind.REQUIREMENT, id=requirement.requirement_id)
        provenance = requirement.provenance
        for document in sorted({e.source_id for e in provenance.evidence}):
            own = [e for e in provenance.evidence if e.source_id == document]
            add(RelationType.DERIVED_FROM, source, NodeRef(kind=NodeKind.SOURCE_DOCUMENT, id=document),
                Provenance(origin=_origin(provenance.origin, own), evidence=own))
        for category in requirement.quality_attributes:
            qualities.add(category)
            add(RelationType.MEASURED_BY, source,
                NodeRef(kind=NodeKind.QUALITY_ATTRIBUTE, id=ids.quality_attribute_id(category)), provenance)
    for entity in entities.values():
        for evidence in entity.provenance.evidence:
            add(RelationType.MENTIONS, NodeRef(kind=NodeKind.SOURCE_CHUNK, id=evidence.chunk_id),
                NodeRef(kind=NodeKind.ENTITY, id=entity.entity_id),
                Provenance(origin=entity.provenance.origin, evidence=[evidence]))

    batch.requirements = [requirements[k] for k in sorted(requirements)]
    batch.actors = [actors[k] for k in sorted(actors)]
    batch.components = [components[k] for k in sorted(components)]
    batch.entities = [entities[k] for k in sorted(entities)]
    batch.quality_attributes = [QualityAttribute(category=c) for c in sorted(qualities, key=str)]
    batch.relations = [relations[k] for k in sorted(relations)]
    batch.rejected.sort(key=lambda r: (r.rule_id, r.subject))
    return batch
