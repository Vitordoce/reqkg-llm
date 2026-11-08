"""Registros que podem ser gravados no ReqKG. Nada entra no Neo4j sem passar por aqui."""

import re
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from domain import ids
from domain.enums import (
    RELATION_ENDPOINTS,
    ActorKind,
    NodeKind,
    Origin,
    Priority,
    QualityCategory,
    RelationType,
    RequirementStatus,
    RequirementType,
    ReviewFlag,
    SourceKind,
    ValidationState,
    VerificationMethod,
)

SourceId = Annotated[str, StringConstraints(pattern=ids.ID_PATTERN[NodeKind.SOURCE_DOCUMENT])]
ChunkId = Annotated[str, StringConstraints(pattern=ids.ID_PATTERN[NodeKind.SOURCE_CHUNK])]
RequirementId = Annotated[str, StringConstraints(pattern=ids.ID_PATTERN[NodeKind.REQUIREMENT])]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
NonEmpty = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, use_enum_values=False)


def sorted_unique(values: list) -> list:
    return sorted(set(values), key=str)


class Evidence(ContractModel):
    source_id: SourceId
    chunk_id: ChunkId
    quote: Annotated[str, StringConstraints(min_length=1, max_length=1000)] | None = None


class Provenance(ContractModel):
    origin: Origin
    evidence: list[Evidence] = Field(default_factory=list)
    validation: ValidationState = ValidationState.UNVALIDATED
    note: NonEmpty | None = None

    @model_validator(mode="after")
    def check_support(self) -> Self:
        if self.origin is Origin.RESEARCHER_DECISION:
            if self.note is None:
                raise ValueError("note: decisão do pesquisador precisa de justificativa escrita")
            return self
        if not self.evidence:
            raise ValueError(
                f"evidence: {self.origin.value} precisa de ao menos uma evidência com source_id e chunk_id"
            )
        if self.origin is Origin.EXTRACTED_FACT and any(e.quote is None for e in self.evidence):
            raise ValueError("evidence.quote: fato extraído precisa citar o trecho da fonte")
        return self


class SourceDocument(ContractModel):
    source_id: SourceId
    path: NonEmpty
    sha256: Sha256
    kind: SourceKind
    title: NonEmpty | None = None
    char_count: int = Field(ge=0)

    @model_validator(mode="after")
    def check_id(self) -> Self:
        canonical = ids.canonical_path(self.path)
        if self.path != canonical:
            raise ValueError(f"path: use a forma canônica {canonical!r}")
        expected = ids.source_id(self.path)
        if self.source_id != expected:
            raise ValueError(f"source_id: esperado {expected} para o caminho {self.path!r}")
        return self


class SourceChunk(ContractModel):
    chunk_id: ChunkId
    source_id: SourceId
    index: int = Field(ge=0)
    occurrence: int = Field(ge=0)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    text: Annotated[str, StringConstraints(min_length=1)]
    sha256: Sha256

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    @model_validator(mode="after")
    def check_consistency(self) -> Self:
        if self.char_end - self.char_start != len(self.text):
            raise ValueError("char_end: char_end - char_start difere do tamanho de text")
        if self.sha256 != ids.sha256_text(self.text):
            raise ValueError("sha256: hash não corresponde a text")
        expected = ids.chunk_id(self.source_id, self.text, self.occurrence)
        if self.chunk_id != expected:
            raise ValueError(f"chunk_id: esperado {expected}")
        return self


def primary_evidence(evidence: list[Evidence]) -> Evidence:
    """A evidência que entra no identificador do requisito: a de menor chunk_id."""
    return min(evidence, key=lambda e: (e.chunk_id, e.source_id))


class Requirement(ContractModel):
    requirement_id: RequirementId
    statement: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    revision: Literal[0, 1] = 0
    previous_statement: Annotated[str, StringConstraints(min_length=1, max_length=2000)] | None = None
    type: RequirementType | None = None
    priority: Priority | None = None
    verification_method: VerificationMethod | None = None
    status: RequirementStatus = RequirementStatus.DRAFT
    quality_attributes: list[QualityCategory] = Field(default_factory=list)
    quantitative_value: NonEmpty | None = None
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    provenance: Provenance

    @field_validator("quality_attributes", "review_flags")
    @classmethod
    def sort_sets(cls, values: list) -> list:
        return sorted_unique(values)

    @model_validator(mode="after")
    def check_traceable(self) -> Self:
        if not self.provenance.evidence:
            raise ValueError("provenance.evidence: requisito gravado precisa de source_id e chunk_id")
        if (self.revision == 1) != (self.previous_statement is not None):
            raise ValueError("previous_statement: obrigatório na revisão 1 e proibido na revisão 0")
        statement = self.previous_statement or self.statement
        primary = primary_evidence(self.provenance.evidence)
        expected = ids.requirement_id(primary.source_id, primary.chunk_id, statement)
        if self.requirement_id != expected:
            raise ValueError(f"requirement_id: esperado {expected}, calculado da evidência primária e da declaração original")
        blocking = {ReviewFlag.LOW_CONFIDENCE, ReviewFlag.AMBIGUOUS_TYPE}
        if blocking & set(self.review_flags) and self.status not in (
            RequirementStatus.NEEDS_REVIEW,
            RequirementStatus.REJECTED,
        ):
            raise ValueError("status: requisito com baixa confiança ou tipo ambíguo fica em needs_review")
        return self


class Actor(ContractModel):
    actor_id: Annotated[str, StringConstraints(pattern=ids.ID_PATTERN[NodeKind.ACTOR])]
    name: NonEmpty
    kind: ActorKind
    provenance: Provenance

    @model_validator(mode="after")
    def check_id(self) -> Self:
        if self.actor_id != ids.actor_id(self.name):
            raise ValueError(f"actor_id: esperado {ids.actor_id(self.name)}")
        return self


class SoftwareComponent(ContractModel):
    component_id: Annotated[str, StringConstraints(pattern=ids.ID_PATTERN[NodeKind.SOFTWARE_COMPONENT])]
    name: NonEmpty
    description: NonEmpty | None = None
    provenance: Provenance

    @model_validator(mode="after")
    def check_id(self) -> Self:
        if self.component_id != ids.component_id(self.name):
            raise ValueError(f"component_id: esperado {ids.component_id(self.name)}")
        return self


class Entity(ContractModel):
    """Conceito extraído que ainda não tem classe ReqKG. Interno, nunca contrato público."""

    entity_id: Annotated[str, StringConstraints(pattern=ids.ID_PATTERN[NodeKind.ENTITY])]
    name: NonEmpty
    entity_type: NonEmpty
    description: NonEmpty | None = None
    provenance: Provenance

    @model_validator(mode="after")
    def check_id(self) -> Self:
        expected = ids.entity_id(self.name, self.entity_type)
        if self.entity_id != expected:
            raise ValueError(f"entity_id: esperado {expected}")
        return self


class QualityAttribute(ContractModel):
    category: QualityCategory

    @property
    def quality_attribute_id(self) -> str:
        return ids.quality_attribute_id(self.category)


class NodeRef(ContractModel):
    kind: NodeKind
    id: NonEmpty

    @model_validator(mode="after")
    def check_pattern(self) -> Self:
        if not re.match(ids.ID_PATTERN[self.kind], self.id):
            raise ValueError(f"id: {self.id!r} não é identificador de {self.kind.value}")
        return self


class Relation(ContractModel):
    relation_id: Annotated[str, StringConstraints(pattern=ids.RELATION_ID_PATTERN)]
    type: RelationType
    source: NodeRef
    target: NodeRef
    provenance: Provenance

    @model_validator(mode="after")
    def check_relation(self) -> Self:
        expected_source, expected_target = RELATION_ENDPOINTS[self.type]
        if self.source.kind is not expected_source:
            raise ValueError(f"source: {self.type.value} parte de {expected_source.value}")
        if self.target.kind is not expected_target:
            raise ValueError(f"target: {self.type.value} chega em {expected_target.value}")
        if self.source.id == self.target.id:
            raise ValueError("target: relação de um nó com ele mesmo não é gravada")
        if not self.provenance.evidence:
            raise ValueError("provenance.evidence: relação sem source_id e chunk_id é rejeitada")
        expected = ids.relation_id(self.type, self.source.id, self.target.id)
        if self.relation_id != expected:
            raise ValueError(f"relation_id: esperado {expected}")
        return self
