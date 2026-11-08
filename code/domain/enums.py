from enum import StrEnum


class RequirementType(StrEnum):
    FUNCTIONAL = "functional"
    NON_FUNCTIONAL = "non_functional"
    CONSTRAINT = "constraint"


class Priority(StrEnum):
    MUST = "must"
    SHOULD = "should"
    COULD = "could"
    WONT = "wont"


class VerificationMethod(StrEnum):
    INSPECTION = "inspection"
    ANALYSIS = "analysis"
    DEMONSTRATION = "demonstration"
    TEST = "test"


class RequirementStatus(StrEnum):
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewFlag(StrEnum):
    LOW_CONFIDENCE = "low_confidence"
    AMBIGUOUS_TYPE = "ambiguous_type"
    QUANTITATIVE_VALUE_PENDING = "quantitative_value_pending"


class QualityCategory(StrEnum):
    """Seis características da ISO/IEC 25010 fixadas no TG-1, com os nomes da edição de 2011.

    Security é proteção de informação e acesso. Safety, criada em 2023, não faz parte do conjunto.
    """

    PERFORMANCE = "performance"
    SECURITY = "security"
    USABILITY = "usability"
    RELIABILITY = "reliability"
    MAINTAINABILITY = "maintainability"
    PORTABILITY = "portability"


ISO_25010_2023_NAME: dict[QualityCategory, str] = {
    QualityCategory.PERFORMANCE: "performance efficiency",
    QualityCategory.SECURITY: "security",
    QualityCategory.USABILITY: "interaction capability",
    QualityCategory.RELIABILITY: "reliability",
    QualityCategory.MAINTAINABILITY: "maintainability",
    QualityCategory.PORTABILITY: "flexibility",
}


class Origin(StrEnum):
    EXTRACTED_FACT = "extracted_fact"
    SYSTEM_INFERENCE = "system_inference"
    RESEARCHER_DECISION = "researcher_decision"


class ValidationState(StrEnum):
    UNVALIDATED = "unvalidated"
    VALIDATED = "validated"
    REJECTED = "rejected"


class SourceKind(StrEnum):
    INTERVIEW = "interview"
    USER_STORY = "user_story"
    BUSINESS_DOCUMENT = "business_document"
    MEETING_RECORD = "meeting_record"
    EXISTING_SYSTEM_DESCRIPTION = "existing_system_description"


class ActorKind(StrEnum):
    STAKEHOLDER = "stakeholder"
    EXTERNAL_SYSTEM = "external_system"
    USER_ROLE = "user_role"


class NodeKind(StrEnum):
    REQUIREMENT = "requirement"
    ACTOR = "actor"
    SOURCE_DOCUMENT = "source_document"
    SOURCE_CHUNK = "source_chunk"
    QUALITY_ATTRIBUTE = "quality_attribute"
    SOFTWARE_COMPONENT = "software_component"
    ENTITY = "entity"


class RelationType(StrEnum):
    DEPENDS_ON = "depends_on"
    CONFLICTS_WITH = "conflicts_with"
    REFINES = "refines"
    DUPLICATES = "duplicates"
    REQUESTED_BY = "requested_by"
    BENEFITS_ACTOR = "benefits_actor"
    DERIVED_FROM = "derived_from"
    MEASURED_BY = "measured_by"
    ALLOCATED_TO = "allocated_to"
    MENTIONS = "mentions"
    RELATED_TO = "related_to"

    @property
    def neo4j_type(self) -> str:
        return self.value.upper()


RELATION_ENDPOINTS: dict[RelationType, tuple[NodeKind, NodeKind]] = {
    RelationType.DEPENDS_ON: (NodeKind.REQUIREMENT, NodeKind.REQUIREMENT),
    RelationType.CONFLICTS_WITH: (NodeKind.REQUIREMENT, NodeKind.REQUIREMENT),
    RelationType.REFINES: (NodeKind.REQUIREMENT, NodeKind.REQUIREMENT),
    RelationType.DUPLICATES: (NodeKind.REQUIREMENT, NodeKind.REQUIREMENT),
    RelationType.REQUESTED_BY: (NodeKind.REQUIREMENT, NodeKind.ACTOR),
    RelationType.BENEFITS_ACTOR: (NodeKind.REQUIREMENT, NodeKind.ACTOR),
    RelationType.DERIVED_FROM: (NodeKind.REQUIREMENT, NodeKind.SOURCE_DOCUMENT),
    RelationType.MEASURED_BY: (NodeKind.REQUIREMENT, NodeKind.QUALITY_ATTRIBUTE),
    RelationType.ALLOCATED_TO: (NodeKind.REQUIREMENT, NodeKind.SOFTWARE_COMPONENT),
    RelationType.MENTIONS: (NodeKind.SOURCE_CHUNK, NodeKind.ENTITY),
    RelationType.RELATED_TO: (NodeKind.ENTITY, NodeKind.ENTITY),
}

SYMMETRIC_RELATIONS = frozenset({RelationType.CONFLICTS_WITH, RelationType.DUPLICATES})

# derived_from e mentions saem da evidência gravada pelo sistema, e measured_by sai de
# quality_attributes. O modelo nunca propõe essas três.
SYSTEM_RELATIONS = frozenset({RelationType.DERIVED_FROM, RelationType.MENTIONS, RelationType.MEASURED_BY})
LLM_RELATIONS = frozenset(RelationType) - SYSTEM_RELATIONS


class PromiseLabel(StrEnum):
    """Rótulos do PROMISE NFR, usados sem correspondência com a ISO/IEC 25010."""

    F = "F"
    A = "A"
    FT = "FT"
    L = "L"
    LF = "LF"
    MN = "MN"
    O = "O"  # noqa: E741
    PE = "PE"
    PO = "PO"
    SC = "SC"
    SE = "SE"
    US = "US"


class RunStatus(StrEnum):
    OK = "ok"
    INVALID_OUTPUT = "invalid_output"
    API_ERROR = "api_error"


class ContextStrategy(StrEnum):
    SOURCE_CHUNKS = "source_chunks"
    GRAPH_LOCAL = "graph_local"


class Condition(StrEnum):
    LLM_ONLY = "LLM-only"
    REQKG_GROUNDED = "REQKG-grounded"


# As duas condições refinam os mesmos candidatos uma vez. Só a origem do contexto muda.
CONTEXT_FOR_CONDITION: dict[Condition, ContextStrategy] = {
    Condition.LLM_ONLY: ContextStrategy.SOURCE_CHUNKS,
    Condition.REQKG_GROUNDED: ContextStrategy.GRAPH_LOCAL,
}
