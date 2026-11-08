"""Contratos de entrada e saída do modelo, iguais nas condições LLM-only e REQKG-grounded.

A resposta do modelo pode citar fonte ou chunk inexistente. Isso não invalida o JSON: as
regras de proveniência contam o caso. Tipo errado, campo desconhecido ou chave pendurada
invalidam a resposta inteira, e o caso entra como CaseResult inválido.
"""

import re
from typing import TYPE_CHECKING, Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from domain.enums import (
    LLM_RELATIONS,
    RELATION_ENDPOINTS,
    ActorKind,
    Condition,
    ContextStrategy,
    NodeKind,
    Origin,
    Priority,
    PromiseLabel,
    QualityCategory,
    RelationType,
    RequirementType,
    ReviewFlag,
    RunStatus,
    VerificationMethod,
)
from domain.models import ChunkId, ContractModel, NonEmpty, SourceId, sorted_unique
from domain.violations import Violation

if TYPE_CHECKING:
    from domain.rules import CorpusIndex

LocalKey = Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")]
CALL_PREFIX = r"[A-Za-z][A-Za-z0-9]{0,7}"
PromiseId = Annotated[str, StringConstraints(pattern=r"^PROMISE-NFR-\d{4}$")]
ModelOrigin = Literal[Origin.EXTRACTED_FACT, Origin.SYSTEM_INFERENCE]


class CitedEvidence(ContractModel):
    source_id: NonEmpty
    chunk_id: NonEmpty
    quote: Annotated[str, StringConstraints(min_length=1, max_length=1000)] | None = None


class RequirementCandidate(ContractModel):
    key: LocalKey
    statement: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    type: RequirementType | None = None
    priority: Priority | None = None
    verification_method: VerificationMethod | None = None
    quality_attributes: list[QualityCategory] = Field(default_factory=list)
    quantitative_value: NonEmpty | None = None
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: Annotated[str, StringConstraints(min_length=1, max_length=500)] | None = None
    origin: ModelOrigin = Origin.EXTRACTED_FACT
    evidence: list[CitedEvidence] = Field(default_factory=list)

    @field_validator("quality_attributes", "review_flags")
    @classmethod
    def sort_sets(cls, values: list) -> list:
        return sorted_unique(values)


class ActorCandidate(ContractModel):
    key: LocalKey
    name: NonEmpty
    kind: ActorKind
    evidence: list[CitedEvidence] = Field(default_factory=list)


class ComponentCandidate(ContractModel):
    key: LocalKey
    name: NonEmpty
    description: NonEmpty | None = None
    evidence: list[CitedEvidence] = Field(default_factory=list)


class EntityCandidate(ContractModel):
    key: LocalKey
    name: NonEmpty
    entity_type: NonEmpty
    description: NonEmpty | None = None
    evidence: list[CitedEvidence] = Field(default_factory=list)


class RelationCandidate(ContractModel):
    type: RelationType
    source_key: NonEmpty
    target_key: NonEmpty
    origin: ModelOrigin = Origin.EXTRACTED_FACT
    rationale: Annotated[str, StringConstraints(min_length=1, max_length=500)] | None = None
    evidence: list[CitedEvidence] = Field(default_factory=list)

    @field_validator("type")
    @classmethod
    def only_model_relations(cls, value: RelationType) -> RelationType:
        if value not in LLM_RELATIONS:
            raise ValueError(f"{value.value} é derivada pelo sistema, não proposta pelo modelo")
        return value


NODE_COLLECTIONS = (
    ("requirements", NodeKind.REQUIREMENT),
    ("actors", NodeKind.ACTOR),
    ("components", NodeKind.SOFTWARE_COMPONENT),
    ("entities", NodeKind.ENTITY),
)


class ExtractionOutput(ContractModel):
    requirements: list[RequirementCandidate] = Field(default_factory=list)
    actors: list[ActorCandidate] = Field(default_factory=list)
    components: list[ComponentCandidate] = Field(default_factory=list)
    entities: list[EntityCandidate] = Field(default_factory=list)
    relations: list[RelationCandidate] = Field(default_factory=list)

    def key_kinds(self) -> dict[str, NodeKind]:
        return {item.key: kind for name, kind in NODE_COLLECTIONS for item in getattr(self, name)}

    @model_validator(mode="after")
    def check_keys(self) -> Self:
        seen: set[str] = set()
        for collection, _ in NODE_COLLECTIONS:
            for index, item in enumerate(getattr(self, collection)):
                if item.key in seen:
                    raise ValueError(f"{collection}.{index}.key: chave {item.key!r} repetida")
                seen.add(item.key)

        kinds = self.key_kinds()
        for index, relation in enumerate(self.relations):
            source_kind, target_kind = RELATION_ENDPOINTS[relation.type]
            if kinds.get(relation.source_key) is not source_kind:
                raise ValueError(
                    f"relations.{index}.source_key: {relation.source_key!r} não é {source_kind.value}"
                )
            if kinds.get(relation.target_key) is not target_kind:
                raise ValueError(
                    f"relations.{index}.target_key: {relation.target_key!r} não é {target_kind.value}"
                )
        return self


def merge_outputs(parts: list[tuple[str, ExtractionOutput]]) -> ExtractionOutput:
    """Une as respostas das chamadas de um caso. Cada chave ganha o prefixo da chamada.

    Relações entre chaves de chamadas diferentes não existem no MVP.
    """
    merged: dict[str, list] = {name: [] for name, _ in NODE_COLLECTIONS}
    merged["relations"] = []
    prefixes = [prefix for prefix, _ in parts]
    if len(set(prefixes)) != len(prefixes):
        raise ValueError(f"prefixos de chamada repetidos: {prefixes}")
    for prefix, output in parts:
        if not re.fullmatch(CALL_PREFIX, prefix):
            raise ValueError(f"prefixo {prefix!r} precisa ser alfanumérico, começar por letra e ter até 8 caracteres")
        rename = lambda key: f"{prefix}-{key}"  # noqa: E731
        for name, _ in NODE_COLLECTIONS:
            merged[name] += [item.model_copy(update={"key": rename(item.key)}) for item in getattr(output, name)]
        merged["relations"] += [
            r.model_copy(update={"source_key": rename(r.source_key), "target_key": rename(r.target_key)})
            for r in output.relations
        ]
    return ExtractionOutput.model_validate({k: [i.model_dump() for i in v] for k, v in merged.items()})


ContextKind = NodeKind | Literal["relation"]


class ContextItem(ContractModel):
    item_id: NonEmpty
    kind: ContextKind
    rank: int = Field(ge=0)
    text: Annotated[str, StringConstraints(min_length=1)]
    source_id: SourceId
    chunk_id: ChunkId


class RetrievedContext(ContractModel):
    query: NonEmpty
    strategy: ContextStrategy
    limit: int = Field(ge=1)
    items: list[ContextItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_bounded_and_ordered(self) -> Self:
        if len(self.items) > self.limit:
            raise ValueError(f"items: {len(self.items)} itens passam do limite {self.limit}")
        order = [(item.rank, item.item_id) for item in self.items]
        if order != sorted(order):
            raise ValueError("items: ordem tem de ser (rank, item_id) crescente")
        if len(set(item.item_id for item in self.items)) != len(self.items):
            raise ValueError("items: item_id repetido")
        return self

    def chunk_ids(self) -> set[str]:
        return {item.chunk_id for item in self.items}


PRESERVED_FIELDS = ("type", "priority", "verification_method")

FILLED_ONLY_WITH_EVIDENCE = ("priority", "verification_method")

REFINEMENT_RULES = {
    "G1": "A resposta revisada aponta para outro item que não o alvo do refinamento.",
    "G2": "used_context_ids cita item que não estava no contexto recuperado.",
    "G3": "A evidência revisada cita chunk que não estava no contexto nem no candidato original.",
    "G4": "Tipo, prioridade, método de verificação ou evidência existiam e foram perdidos.",
    "G5": "O item do PROMISE avaliado aparece no próprio contexto de classificação, pelo promise_id ou por um "
          "texto idêntico depois de domain.rules.normalize_text.",
    "G6": "Evidência nova (ausente do candidato original) não passa em CorpusIndex.supports no corpus do caso "
          "(chunk de outro documento ou citação que não aparece no chunk), ou prioridade ou método de verificação "
          "nulos no original foram preenchidos sem nenhuma evidência nova que passe.",
}


class RefinementOutput(ContractModel):
    """Resposta da única passagem de refinamento de um candidato, endereçado pela chave."""

    target_key: LocalKey
    revised: RequirementCandidate
    used_context_ids: list[NonEmpty] = Field(default_factory=list)

    def check_against(self, context: RetrievedContext, original: RequirementCandidate,
                      corpus: "CorpusIndex") -> list[Violation]:
        """Violações G que fazem o sistema recusar o refinamento e manter o original.

        corpus: só os chunks do documento do caso, o que o modelo viu na extração.
        """
        subject = self.target_key
        found: list[Violation] = []
        if self.revised.key != self.target_key or original.key != self.target_key:
            found.append(Violation("G1", subject, "chave revisada difere do candidato alvo"))
        known = {item.item_id for item in context.items}
        for item_id in sorted(set(self.used_context_ids) - known):
            found.append(Violation("G2", subject, f"usa {item_id}, fora do contexto recuperado"))
        allowed_chunks = context.chunk_ids() | {e.chunk_id for e in original.evidence}
        for evidence in self.revised.evidence:
            if evidence.chunk_id not in allowed_chunks:
                found.append(Violation("G3", subject, f"cita {evidence.chunk_id}, fora do contexto e do original"))
        for field in PRESERVED_FIELDS:
            if getattr(original, field) is not None and getattr(self.revised, field) is None:
                found.append(Violation("G4", subject, f"{field} existia e foi perdido"))
        if original.evidence and not self.revised.evidence:
            found.append(Violation("G4", subject, "evidence existia e foi perdida"))
        new_evidence = [e for e in self.revised.evidence if e not in original.evidence]
        supported = [e for e in new_evidence if corpus.supports(e)]
        for evidence in new_evidence:
            if evidence not in supported:
                found.append(Violation("G6", subject, f"evidência nova {evidence.source_id}/{evidence.chunk_id} "
                                                      "não passa no corpus do caso"))
        for field in FILLED_ONLY_WITH_EVIDENCE:
            if getattr(original, field) is None and getattr(self.revised, field) is not None and not supported:
                found.append(Violation("G6", subject, f"{field} preenchido sem evidência nova válida"))
        return sorted(found)


class ClassificationOutput(ContractModel):
    """Classificação de um item do PROMISE NFR, na primeira chamada e no refinamento."""

    promise_id: PromiseId
    label: PromiseLabel
    rationale: Annotated[str, StringConstraints(min_length=1, max_length=500)] | None = None
    used_context_ids: list[NonEmpty] = Field(default_factory=list)

    @property
    def is_functional(self) -> bool:
        return self.label is PromiseLabel.F

    def check_against(self, context: RetrievedContext, original: "ClassificationOutput", item_text: str) -> list[Violation]:
        """item_text: o texto do item avaliado, para pegar a cópia com outro promise_id (duplicata do PROMISE)."""
        from domain.rules import normalize_text

        found: list[Violation] = []
        if self.promise_id != original.promise_id:
            found.append(Violation("G1", original.promise_id, "promise_id revisado difere do original"))
        known = {item.item_id for item in context.items}
        for item_id in sorted(set(self.used_context_ids) - known):
            found.append(Violation("G2", original.promise_id, f"usa {item_id}, fora do contexto recuperado"))
        if original.promise_id in known:
            found.append(Violation("G5", original.promise_id, "o item avaliado aparece no próprio contexto"))
        own = normalize_text(item_text)
        for item in context.items:
            if item.item_id != original.promise_id and normalize_text(item.text) == own:
                found.append(Violation("G5", original.promise_id, f"{item.item_id} tem o mesmo texto do item avaliado"))
        return sorted(found)


class ViolationRecord(ContractModel):
    rule_id: NonEmpty
    subject: NonEmpty
    detail: NonEmpty

    @classmethod
    def of(cls, violation: Violation) -> "ViolationRecord":
        return cls(rule_id=violation.rule_id, subject=violation.subject, detail=violation.detail)


Stage = Literal["extraction", "refinement", "classification", "classification_refinement"]
SHARED_STAGES = ("extraction", "classification")
REFINEMENT_STAGES = ("refinement", "classification_refinement")


class CaseResult(ContractModel):
    """Uma chamada registrada. Caso inválido também é registrado e entra nas métricas.

    Extração e classificação são compartilhadas pelas duas condições e não têm condição.
    Refinamento recusado fica com status ok, a resposta proposta e as violações G em violations.
    target_key é a chave do alvo do refinamento (o promise_id na classificação), também quando a
    chamada falhou, e não depende do que o modelo respondeu.
    """

    case_id: NonEmpty
    condition: Condition | None = None
    run_index: int = Field(ge=0)
    stage: Stage
    target_key: LocalKey | None = None
    status: RunStatus
    error: NonEmpty | None = None
    extraction: ExtractionOutput | None = None
    refinements: list[RefinementOutput] = Field(default_factory=list)
    classification: ClassificationOutput | None = None
    violations: list[ViolationRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_condition(self) -> Self:
        if self.stage in SHARED_STAGES and self.condition is not None:
            raise ValueError(f"condition: {self.stage} é compartilhada pelas duas condições e não tem condição")
        if self.stage not in SHARED_STAGES and self.condition is None:
            raise ValueError(f"condition: {self.stage} pertence a uma condição")
        if self.stage in SHARED_STAGES and self.target_key is not None:
            raise ValueError(f"target_key: {self.stage} não tem alvo de refinamento")
        if self.stage in REFINEMENT_STAGES and self.target_key is None:
            raise ValueError(f"target_key: {self.stage} guarda a chave do alvo")
        return self

    @model_validator(mode="after")
    def check_status(self) -> Self:
        has_output = self.extraction is not None or self.classification is not None or bool(self.refinements)
        if self.status is RunStatus.OK and (self.error is not None or not has_output):
            raise ValueError("status: ok exige saída e nenhum erro")
        if self.status is not RunStatus.OK and (self.error is None or has_output):
            raise ValueError("status: caso que falhou guarda o erro e nenhuma saída")
        return self
