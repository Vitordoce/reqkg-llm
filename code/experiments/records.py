"""Registros de uma corrida. O executor grava, métricas e artefatos do estudo de caso leem.

Uma corrida fica em `outputs/runs/<run_id>/`, um arquivo JSONL por tipo de registro, uma linha
por registro em JSON canônico (`domain.serialization.canonical_json`):

    manifest.json           RunManifest
    calls.jsonl             CallRecord, gravado por extraction.client.invoke, uma linha por chamada
    case_results.jsonl      CaseResult de todas as etapas, inclusive inválidas
    contexts.jsonl          ContextRecord, um por candidato refinado e condição
    finals.jsonl            FinalRecord, a saída final medida de cada caso, corrida e condição
    rejections.jsonl        RejectionRecord, recusas na gravação do grafo
    classifications.jsonl   ClassificationRecord, um por item do PROMISE, corrida e condição
"""

import json
from typing import Annotated, Any, Literal, Self

from pydantic import (
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StringConstraints,
    model_serializer,
    model_validator,
)

from domain.enums import Condition, ContextStrategy, PromiseLabel, RunStatus
from domain.llm_io import SHARED_STAGES, ExtractionOutput, PromiseId, RetrievedContext, Stage, ViolationRecord
from domain.models import ContractModel, NonEmpty, Sha256
from domain.persist import Rejection

RunId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")]
# 0: a condição rodou primeiro no caso (ou item do PROMISE); 1: rodou depois. O executor sempre preenche;
# None só em registros escritos à mão, como os fixtures de outros pacotes.
ConditionPosition = Annotated[int, Field(ge=0, le=1)] | None

FILES = {
    "manifest": "manifest.json",
    "calls": "calls.jsonl",
    "case_results": "case_results.jsonl",
    "contexts": "contexts.jsonl",
    "finals": "finals.jsonl",
    "rejections": "rejections.jsonl",
    "classifications": "classifications.jsonl",
}


class CallTargetRecord(ContractModel):
    """Alvo da chamada (extraction.client.CallTarget). key é o prefixo da chamada na extração (c0, c1, ...),
    a chave do candidato no refinamento e o promise_id na classificação."""

    case_id: NonEmpty
    condition: Condition | None
    run_index: int = Field(ge=0)
    stage: Stage
    key: NonEmpty

    @model_validator(mode="after")
    def check_condition(self) -> Self:
        if (self.stage in SHARED_STAGES) != (self.condition is None):
            raise ValueError(f"condition: nula nas etapas compartilhadas e obrigatória nas outras, não em {self.stage}")
        return self


class CallMeta(ContractModel):
    """Extração: chunks enviados na chamada e chunks_per_call. Refinamento: itens e estratégia do contexto."""

    chunk_ids: list[NonEmpty] | None = None
    chunks_per_call: int | None = Field(default=None, ge=1)
    context_item_ids: list[NonEmpty] | None = None
    context_strategy: ContextStrategy | None = None


class TokenUsage(ContractModel):
    """Uso devolvido pela API. Vazio em erro de API. O cliente sintético só preenche entrada e saída."""

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cache_creation_input_tokens: int | None = Field(default=None, ge=0)
    cache_read_input_tokens: int | None = Field(default=None, ge=0)


class CallTemperature(ContractModel):
    """sent falso: replay ou sintético, nada foi enviado. accepted segue code/extraction/README.md.
    seed: a semente enviada junto da temperatura (Ollama); a mesma regra de accepted vale para as duas."""

    sent: bool
    accepted: bool | None
    value: float | None = None
    transport: NonEmpty | None = None
    seed: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def check_sent(self) -> Self:
        if self.sent != (self.value is not None) or self.sent != (self.transport is not None):
            raise ValueError("value: value e transport existem só quando a temperatura foi enviada")
        if not self.sent and (self.accepted is not None or self.seed is not None):
            raise ValueError("accepted: temperatura não enviada não foi aceita nem recusada")
        return self


class CallTiming(ContractModel):
    """Tempos devolvidos pelo Ollama, em segundos. prompt_eval_s conta só os tokens de entrada fora do cache."""

    total_s: float = Field(ge=0)
    load_s: float = Field(ge=0)
    prompt_eval_s: float = Field(ge=0)
    eval_s: float = Field(ge=0)


class CallRecord(ContractModel):
    """Uma linha de calls.jsonl: uma chamada ao modelo, respondida ou com erro de API. A chave de API nunca entra.

    user_prompt e raw_response ficam exatos, sem tirar espaços, porque a resposta bruta pode ser JSON quebrado.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    timestamp: NonEmpty
    target: CallTargetRecord
    meta: CallMeta
    client: dict[str, Any]
    prompt_name: NonEmpty
    prompt_version: int = Field(ge=1)
    prompt_template_sha256: Sha256
    prompt_sha256: Sha256
    output_model: NonEmpty
    output_schema_sha256: Sha256
    user_prompt: str
    status: Literal["returned", "api_error"]
    error: str | None
    raw_response: str | None
    model: str | None
    stop_reason: str | None
    usage: TokenUsage
    response_id: str | None
    temperature: CallTemperature
    # Só nas chamadas que o servidor cronometra (Ollama); ausente da linha nas outras.
    timing: CallTiming | None = None

    @model_validator(mode="after")
    def check(self) -> Self:
        if self.status == "returned" and (self.error is not None or self.raw_response is None):
            raise ValueError("status: returned guarda raw_response e nenhum erro")
        spent = any(v is not None for v in self.usage.model_dump().values())
        if self.status == "api_error" and (not self.error or self.raw_response is not None or spent):
            raise ValueError("status: api_error guarda o erro, sem raw_response e sem usage")
        self.check_request(self.target, self.meta)
        return self

    @staticmethod
    def check_request(target: CallTargetRecord, meta: CallMeta) -> None:
        """A parte da linha que existe antes da chamada. invoke confere antes de gastar a chamada."""
        if target.stage == "extraction" and not meta.chunk_ids:
            raise ValueError("meta.chunk_ids: obrigatório na extração, é a lista de chunks enviados na chamada")
        if target.stage not in SHARED_STAGES and (meta.context_item_ids is None or meta.context_strategy is None):
            raise ValueError(f"meta.context_item_ids: {target.stage} guarda os itens e a estratégia do contexto")

    def line(self) -> str:
        """Linha de calls.jsonl: só os campos dados (meta, usage e temperatura variam), chaves em ordem."""
        return json.dumps(self.model_dump(mode="json", exclude_unset=True), ensure_ascii=False, sort_keys=True) + "\n"


class Resumption(ContractModel):
    """Uma retomada de corrida interrompida (--resume). logged_calls: chamadas já gravadas no calls.jsonl parcial
    quando a retomada começou, servidas do registro sem nova chamada à API."""

    command: NonEmpty
    logged_calls: int = Field(ge=0)


class RunManifest(ContractModel):
    """Corrida piloto dispensa o congelamento e não entra no relatório como resultado.

    resumptions só aparece no JSON de uma corrida retomada, uma entrada por retomada; command continua sendo o
    comando que abriu a corrida.

    selection_sha256: SHA-256 da seleção efetiva (casos da amostra, filtros do PROMISE e itens escolhidos), que
    os hashes dos arquivos de entrada não distinguem; a retomada confere. Ausente do JSON quando None, como nos
    manifestos anteriores a 11 de outubro de 2026.
    """

    run_id: RunId
    model_id: str
    replay: bool
    pilot: bool = False
    runs: int = Field(ge=1)
    config_sha256: Sha256
    ingestion_sha256: list[Sha256] = Field(default_factory=list)
    promise_sha256: Sha256 | None = None
    selection_sha256: Sha256 | None = None
    prompts_registry_sha256: Sha256
    freeze_manifest_sha256: Sha256 | None = None
    packages: dict[str, str] = Field(default_factory=dict)
    command: NonEmpty
    resumptions: list[Resumption] = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def omit_empty_fields(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        if not self.resumptions:
            data.pop("resumptions", None)
        if self.selection_sha256 is None:
            data.pop("selection_sha256", None)
        return data


class ContextRecord(ContractModel):
    case_id: NonEmpty
    run_index: int = Field(ge=0)
    condition: Condition
    target_key: NonEmpty
    context: RetrievedContext


class FinalRecord(ContractModel):
    """Extração compartilhada com os refinamentos aceitos no lugar dos candidatos.

    targets: chaves escolhidas por refinement_targets. accepted: refinamento aceito e aplicado.
    refused: refinamento com violação G, candidato original mantido. failed: chamada inválida ou erro
    de API, candidato original mantido. violations: as violações G dos refinamentos recusados.
    """

    case_id: NonEmpty
    run_index: int = Field(ge=0)
    condition: Condition
    status: RunStatus
    output: ExtractionOutput | None = None
    targets: list[NonEmpty] = Field(default_factory=list)
    accepted: list[NonEmpty] = Field(default_factory=list)
    refused: list[NonEmpty] = Field(default_factory=list)
    failed: list[NonEmpty] = Field(default_factory=list)
    violations: list[ViolationRecord] = Field(default_factory=list)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    condition_position: ConditionPosition = None

    @model_validator(mode="after")
    def check(self) -> Self:
        if (self.status is RunStatus.OK) != (self.output is not None):
            raise ValueError("output: obrigatório com status ok e proibido nos demais")
        groups = [set(self.accepted), set(self.refused), set(self.failed)]
        if any(a & b for i, a in enumerate(groups) for b in groups[i + 1:]):
            raise ValueError("accepted: uma chave fica em um só grupo (aceita, recusada ou com falha)")
        if not set().union(*groups) <= set(self.targets):
            raise ValueError("targets: aceitos, recusados e falhos têm de estar entre os alvos")
        return self


class RejectionRecord(ContractModel):
    case_id: NonEmpty
    run_index: int = Field(ge=0)
    rejection: Rejection


class ClassificationRecord(ContractModel):
    promise_id: PromiseId
    project_id: int = Field(ge=0)
    run_index: int = Field(ge=0)
    condition: Condition
    status: RunStatus
    initial: PromiseLabel | None = None
    final: PromiseLabel | None = None
    refinement_accepted: bool = False
    # Falha do refinamento (resposta inválida ou erro de API) mantém o rótulo inicial em final.
    refinement_status: RunStatus = RunStatus.OK
    violations: list[ViolationRecord] = Field(default_factory=list)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    condition_position: ConditionPosition = None

    @model_validator(mode="after")
    def check(self) -> Self:
        if self.status is RunStatus.OK and self.final is None:
            raise ValueError("final: obrigatório com status ok")
        if self.refinement_status is not RunStatus.OK:
            if self.status is not RunStatus.OK:
                raise ValueError("refinement_status: sem primeira classificação válida não houve refinamento")
            if self.final != self.initial or self.refinement_accepted or self.violations:
                raise ValueError("final: refinamento que falhou mantém o rótulo inicial, sem aceite nem violação")
        return self
