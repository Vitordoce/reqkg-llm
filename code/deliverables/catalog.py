"""Visão comum dos quatro artefatos: requisitos numerados, atores, evidências e violações.

O número legível (REQ-001) segue a ordem de leitura da primeira evidência que resolve no corpus,
na extração compartilhada. O mesmo candidato tem o mesmo número nas duas condições, e o
refinamento não renumera nada.
"""

import re
from dataclasses import dataclass, field

from domain.enums import RelationType, ReviewFlag
from domain.llm_io import CitedEvidence, ExtractionOutput, RequirementCandidate
from domain.models import Actor, Requirement, SourceChunk, SourceDocument
from domain.persist import BLOCKING_FLAGS, Rejection
from domain.rules import CorpusIndex, check_all
from domain.violations import Violation

from deliverables.inputs import Inputs
from deliverables.instance import CaseRecords, Instance, build_instance, case_records

QUOTE_FOUND = "sim"
QUOTE_MISSING = "não"
NO_QUOTE = "sem citação"
OUTSIDE_CORPUS = "chunk fora do corpus do caso"
NO_EVIDENCE = "sem evidência"
ACTOR_RELATIONS = (RelationType.REQUESTED_BY, RelationType.BENEFITS_ACTOR)
SEPARATORS = {"|": " e ", ",": ", ", "->": " → "}


@dataclass(frozen=True)
class EvidenceView:
    evidence: CitedEvidence
    document: SourceDocument | None
    chunk: SourceChunk | None
    quote_status: str


@dataclass(frozen=True)
class RequirementView:
    label: str
    case_id: str
    candidate: RequirementCandidate
    requirement_id: str | None
    requirement: Requirement | None
    rejection: Rejection | None
    flags: tuple[ReviewFlag, ...]
    refinement: str
    evidence: tuple[EvidenceView, ...]

    @property
    def in_review(self) -> bool:
        return bool(set(self.flags) & BLOCKING_FLAGS)


@dataclass(frozen=True)
class ActorView:
    actor: Actor
    evidence: tuple[EvidenceView, ...]
    requirements: tuple[str, ...]


@dataclass(frozen=True)
class RejectedActor:
    case_id: str
    key: str
    name: str
    kind: str
    rejection: Rejection


@dataclass(frozen=True)
class CaseViolation:
    case_id: str
    violation: Violation
    subject: str


@dataclass
class Catalog:
    inputs: Inputs
    instance: Instance
    requirements: list[RequirementView] = field(default_factory=list)
    actors: list[ActorView] = field(default_factory=list)
    rejected_actors: list[RejectedActor] = field(default_factory=list)
    violations: list[CaseViolation] = field(default_factory=list)
    names: dict[tuple[str, str], str] = field(default_factory=dict)

    def describe(self, case_id: str, subject: str) -> str:
        """Assunto de violação ou recusa com REQ-NNN e nomes no lugar das chaves locais."""
        relation = re.fullmatch(r"relations\.(\d+)", subject)
        if relation:
            final = next(f for f in self.inputs.finals if f.case_id == case_id)
            item = final.output.relations[int(relation.group(1))]
            source, target = self._name(case_id, item.source_key), self._name(case_id, item.target_key)
            return f"relação {item.type.value} de {source} para {target}"
        parts = re.split(r"(\||,|->)", subject)
        return "".join(SEPARATORS.get(p) or self._name(case_id, p) for p in parts if p)

    def _name(self, case_id: str, key: str) -> str:
        return self.names.get((case_id, key), f"`{key}`")


def natural(text: str) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", text)]


def effective_flags(candidate: RequirementCandidate, threshold: float) -> tuple[ReviewFlag, ...]:
    flags = set(candidate.review_flags)
    if candidate.confidence is not None and candidate.confidence < threshold:
        flags.add(ReviewFlag.LOW_CONFIDENCE)
    return tuple(sorted(flags, key=str))


def _evidence_views(evidence: list, inputs: Inputs, corpus: CorpusIndex) -> tuple[EvidenceView, ...]:
    documents = {d.source_id: d for d in inputs.documents}
    chunks = {c.chunk_id: c for c in inputs.chunks}
    views = []
    for item in evidence:
        cited = CitedEvidence(source_id=item.source_id, chunk_id=item.chunk_id, quote=item.quote)
        if not corpus.resolves(cited):
            views.append(EvidenceView(cited, documents.get(cited.source_id), None, OUTSIDE_CORPUS))
            continue
        status = NO_QUOTE if cited.quote is None else QUOTE_FOUND if corpus.quote_found(cited) else QUOTE_MISSING
        views.append(EvidenceView(cited, documents[cited.source_id], chunks[cited.chunk_id], status))
    return tuple(views)


def _reading_position(candidate: RequirementCandidate, inputs: Inputs, corpus: CorpusIndex) -> tuple:
    order = {d.source_id: i for i, d in enumerate(inputs.documents)}
    index = {c.chunk_id: c.index for c in inputs.chunks}
    positions = [(order[e.source_id], index[e.chunk_id]) for e in candidate.evidence if corpus.resolves(e)]
    return (0, *min(positions)) if positions else (1, 0, 0)


def _refinement(key: str, final) -> str:
    if key in final.accepted:
        return "aceito"
    if key in final.refused:
        return "recusado"
    if key in final.failed:
        return "chamada falhou"
    if key in final.targets:
        return "sem resultado registrado"
    return "não selecionado"


def build_catalog(inputs: Inputs) -> Catalog:
    cases = case_records(inputs)
    instance = build_instance(inputs, cases)
    catalog = Catalog(inputs=inputs, instance=instance)
    by_case: dict[str, CaseRecords] = {c.case_id: c for c in cases}
    finals = {f.case_id: f for f in inputs.finals}

    ordered: list[tuple[tuple, str, RequirementCandidate]] = []
    for case_id, record in by_case.items():
        shared = {r.key: r for r in inputs.shared[case_id].requirements}
        for candidate in finals[case_id].output.requirements:
            position = _reading_position(shared[candidate.key], inputs, inputs.case_corpus(case_id))
            ordered.append(((*position, case_id, natural(candidate.key)), case_id, candidate))
    ordered.sort(key=lambda item: item[0])

    label_of_id: dict[str, str] = {}
    width = max(3, len(str(len(ordered))))
    for number, (_, case_id, candidate) in enumerate(ordered, start=1):
        record = by_case[case_id]
        label = f"REQ-{number:0{width}d}"
        requirement_id = record.batch.key_to_id.get(candidate.key)
        created = requirement_id is not None and record.creator.get(requirement_id) == candidate.key
        requirement = instance.requirements.get(requirement_id) if created else None
        rejection = next((r for r in record.batch.rejected if r.subject == candidate.key), None)
        catalog.requirements.append(RequirementView(
            label=label, case_id=case_id, candidate=candidate, requirement_id=requirement_id,
            requirement=requirement, rejection=rejection,
            flags=effective_flags(candidate, inputs.confidence_threshold),
            refinement=_refinement(candidate.key, finals[case_id]),
            evidence=_evidence_views(candidate.evidence, inputs, inputs.case_corpus(case_id)),
        ))
        catalog.names[(case_id, candidate.key)] = label
        if requirement is not None:
            label_of_id[requirement_id] = label

    for case_id, record in by_case.items():
        for actor in finals[case_id].output.actors:
            catalog.names[(case_id, actor.key)] = f"ator {actor.name!r}"
            rejection = next((r for r in record.batch.rejected if r.subject == actor.key), None)
            if rejection is not None:
                catalog.rejected_actors.append(RejectedActor(case_id, actor.key, actor.name, actor.kind.value, rejection))
        for collection, noun in (("components", "componente"), ("entities", "entidade")):
            for item in getattr(finals[case_id].output, collection):
                catalog.names[(case_id, item.key)] = f"{noun} {item.name!r}"

    linked: dict[str, set[str]] = {}
    for relation in instance.relations.values():
        if relation.type in ACTOR_RELATIONS and relation.source.id in label_of_id:
            linked.setdefault(relation.target.id, set()).add(label_of_id[relation.source.id])
    union = CorpusIndex.from_chunks(inputs.chunks)
    catalog.actors = [
        ActorView(actor, _evidence_views(actor.provenance.evidence, inputs, union),
                  tuple(sorted(linked.get(actor_id, ()))))
        for actor_id, actor in sorted(instance.actors.items(), key=lambda kv: (kv[1].name.casefold(), kv[0]))
    ]

    for case_id in by_case:
        for violation in check_all(finals[case_id].output, inputs.case_corpus(case_id)):
            catalog.violations.append(CaseViolation(case_id, violation, catalog.describe(case_id, violation.subject)))
    catalog.violations.sort(key=lambda v: (v.violation.rule_id, natural(v.subject), v.case_id, v.violation.detail))
    return catalog
