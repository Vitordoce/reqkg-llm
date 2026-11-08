"""Configuração de experimento. O tipo já impede uma segunda passagem de refinamento."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from domain.enums import Condition
from domain.models import ContractModel
from domain.rules import RULES_VERSION

CONDITIONS = (Condition.LLM_ONLY, Condition.REQKG_GROUNDED)


class ContractError(ValueError):
    pass


class MetricName(StrEnum):
    PRECISION = "precision"
    RECALL = "recall"
    F1 = "f1"
    BERTSCORE_F1 = "bertscore_f1"
    COMPLETENESS_RATIO = "completeness_ratio"
    PROVENANCE_COVERAGE = "provenance_coverage"
    UNSUPPORTED_CLAIM_RATE = "unsupported_claim_rate"
    RULE_VIOLATION_RATE = "rule_violation_rate"


class ModelConfig(ContractModel):
    """ollama: modelo de pesos abertos local, identificado pela tag e pelo digest dos pesos (o de /api/tags),
    com temperatura, semente e janela de contexto fixas. openrouter: API unificada compatível com OpenAI
    (OpenRouter ou qualquer endpoint /chat/completions), que permite selecionar modelos de fronteira ou de
    pesos abertos pela mesma chave e pelo mesmo formato de saída JSON Schema. anthropic: a API nativa do
    Claude, do TG-1."""

    provider: Literal["ollama", "openrouter", "anthropic"]
    model_id: str = ""
    model_digest: str = Field(default="", pattern=r"^([0-9a-f]{64})?$")
    base_url: str = "http://localhost:11434"
    temperature: float = Field(ge=0.0, le=1.0)
    seed: int | None = Field(default=None, ge=0)
    num_ctx: int | None = Field(default=None, gt=0)
    max_tokens: int = Field(gt=0)

    @model_validator(mode="after")
    def check_provider_fields(self) -> Self:
        if self.provider == "anthropic":
            given = [name for name in ("model_digest", "seed", "num_ctx") if getattr(self, name)]
            if given:
                raise ValueError(f"{given[0]}: {', '.join(given)} valem só para provider = \"ollama\"")
        elif self.provider == "openrouter":
            given = [name for name in ("model_digest", "num_ctx") if getattr(self, name)]
            if given:
                raise ValueError(f"{given[0]}: {', '.join(given)} valem só para provider = \"ollama\"")
        elif self.num_ctx is not None and self.num_ctx <= self.max_tokens:
            raise ValueError("num_ctx: a janela de contexto tem de caber o prompt e os max_tokens da resposta")
        return self


class ChunkingConfig(ContractModel):
    """paragraph faz de cada parágrafo um chunk, e size_chars é o teto para dividir parágrafo longo.
    Um parágrafo alterado só invalida os próprios chunks. window corta em janelas fixas, e uma
    inserção no início troca todos os chunks."""

    strategy: Literal["paragraph", "window"]
    size_chars: int = Field(gt=0)
    overlap_chars: int = Field(ge=0)

    @model_validator(mode="after")
    def check_overlap(self) -> Self:
        if self.overlap_chars >= self.size_chars:
            raise ValueError("overlap_chars: sobreposição tem de ser menor que size_chars")
        if self.strategy == "paragraph" and self.overlap_chars:
            raise ValueError("overlap_chars: a estratégia paragraph não usa sobreposição")
        return self


class ExtractionConfig(ContractModel):
    """Quantos chunks vão em cada chamada de extração. Igual nas duas condições."""

    chunks_per_call: int = Field(ge=1)


class RetrievalConfig(ContractModel):
    mode: Literal["local"]
    max_items: int = Field(ge=1)
    max_hops: int = Field(ge=1, le=2)


class RefinementConfig(ContractModel):
    max_calls: Literal[1]


class ReviewConfig(ContractModel):
    confidence_threshold: float = Field(ge=0.0, le=1.0)


class EvaluationConfig(ContractModel):
    bertscore_model: str = ""
    bertscore_revision: str = ""
    bertscore_num_layers: int | None = Field(default=None, ge=1)
    seed: int = Field(ge=0)


class RepetitionConfig(ContractModel):
    structural_sample: int = Field(ge=3)
    promise: int = Field(ge=1)


class ExperimentConfig(ContractModel):
    schema_version: Literal["2"]
    rules_version: str
    conditions: tuple[Condition, Condition]
    model: ModelConfig
    chunking: ChunkingConfig
    extraction: ExtractionConfig
    retrieval: RetrievalConfig
    refinement: RefinementConfig
    review: ReviewConfig
    evaluation: EvaluationConfig
    repetitions: RepetitionConfig
    metrics: list[MetricName]

    @model_validator(mode="after")
    def check_conditions(self) -> Self:
        if self.conditions != CONDITIONS:
            raise ValueError(f"conditions: o experimento tem exatamente {[c.value for c in CONDITIONS]}")
        return self

    def ensure_runnable(self) -> None:
        missing = []
        if self.model.provider == "ollama":
            if not self.model.model_id:
                missing.append("model.model_id (tag do modelo no Ollama)")
            if not self.model.model_digest:
                missing.append("model.model_digest (digest dos pesos, o de ollama list ou /api/tags)")
            if self.model.seed is None:
                missing.append("model.seed")
            if self.model.num_ctx is None:
                missing.append("model.num_ctx")
        elif self.model.provider == "openrouter":
            if not self.model.model_id:
                missing.append("model.model_id (identificador do modelo no OpenRouter, ex.: anthropic/claude-sonnet-4)")
        elif not self.model.model_id:
            missing.append("model.model_id (versão do Claude)")
        if not self.evaluation.bertscore_model:
            missing.append("evaluation.bertscore_model")
        if not self.evaluation.bertscore_revision:
            missing.append("evaluation.bertscore_revision (commit do modelo no Hugging Face)")
        if missing:
            raise ContractError(f"escolha e registre antes de rodar o experimento: {', '.join(missing)}")
        if self.rules_version != RULES_VERSION:
            raise ContractError(
                f"rules_version {self.rules_version!r} difere das regras em código ({RULES_VERSION!r})"
            )
