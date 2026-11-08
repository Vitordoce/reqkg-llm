"""Extração de um caso, refinamento de um candidato e classificação de um item do PROMISE.

Toda chamada termina num CaseResult. Resposta que não valida vira invalid_output com o erro do
contrato. Falha da API vira api_error. O refinamento acontece uma vez por alvo: SinglePassGuard
levanta SecondRefinementError antes de uma segunda chamada para o mesmo caso, condição, corrida
e chave, inclusive quando a primeira falhou.
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass

from domain.config import ContractError, ExperimentConfig
from domain.enums import Condition, ContextStrategy, RunStatus
from domain.llm_io import (
    REFINEMENT_STAGES,
    CaseResult,
    ClassificationOutput,
    ContextItem,
    ExtractionOutput,
    RefinementOutput,
    RequirementCandidate,
    RetrievedContext,
    ViolationRecord,
    merge_outputs,
)
from domain.models import SourceChunk
from domain.persist import PersistBatch, to_records
from domain.rules import REFINEMENT_TRIGGERS, CorpusIndex, check_all
from domain.serialization import parse
from domain.violations import Violation
from extraction import prompts
from extraction.client import CallLog, CallTarget, LLMAPIError, LLMClient, LLMRequest, LLMResponse, invoke


class OutputError(ValueError):
    """A resposta do modelo não cumpre o contrato."""


class SecondRefinementError(RuntimeError):
    """Gate do passo 7: uma segunda passagem de refinamento é falha do pipeline."""


class SinglePassGuard:
    """Conta as chamadas de refinamento por alvo e recusa passar de refinement.max_calls.

    from_log reconstrói a contagem a partir do calls.jsonl, então reabrir a mesma corrida em
    outro processo não libera uma segunda passagem.
    """

    def __init__(self, max_calls: int = 1, claimed: Iterable[CallTarget] = ()) -> None:
        self.max_calls = max_calls
        self._calls: dict[CallTarget, int] = {}
        for target in claimed:
            self._calls[target] = self._calls.get(target, 0) + 1

    @classmethod
    def for_config(cls, config: ExperimentConfig, log: CallLog | None = None) -> "SinglePassGuard":
        claimed = []
        for entry in log.entries() if log else []:
            target = entry.target
            if target.stage in REFINEMENT_STAGES:
                claimed.append(CallTarget(target.case_id, target.condition, target.run_index, target.stage, target.key))
        return cls(config.refinement.max_calls, claimed)

    def claim(self, target: CallTarget) -> None:
        if target.stage not in REFINEMENT_STAGES:
            raise ValueError(f"o guarda só conta refinamentos, não {target.stage}")
        used = self._calls.get(target, 0)
        if used >= self.max_calls:
            raise SecondRefinementError(
                f"refinamento recusado: {target.as_dict()} já teve {used} passagem(ns), "
                f"e refinement.max_calls = {self.max_calls}"
            )
        self._calls[target] = used + 1


def parse_output(response: LLMResponse, model: type, origin: str):
    notes = {"max_tokens": "resposta cortada em max_tokens", "refusal": "o modelo recusou responder"}
    note = notes.get(response.stop_reason or "")
    try:
        data = json.loads(response.text)
    except json.JSONDecodeError as error:
        detail = f"{origin}: JSON inválido na linha {error.lineno}, coluna {error.colno}: {error.msg}"
        raise OutputError(f"{detail} ({note})" if note else detail) from None
    try:
        return parse(data, model, origin)
    except ContractError as error:
        raise OutputError(f"{error} ({note})" if note else str(error)) from None


def _result(target: CallTarget, status: RunStatus, **fields) -> CaseResult:
    return CaseResult(case_id=target.case_id, condition=target.condition, run_index=target.run_index,
                      stage=target.stage, target_key=target.key if target.stage in REFINEMENT_STAGES else None,
                      status=status, **fields)


def _failed(target: CallTarget, status: RunStatus, error: str) -> CaseResult:
    return _result(target, status, error=error)


def _ok(target: CallTarget, **output) -> CaseResult:
    return _result(target, RunStatus.OK, **output)


# Extração


def call_prefix(index: int) -> str:
    return f"c{index}"


def group_chunks(chunks: Iterable[SourceChunk], chunks_per_call: int) -> list[list[SourceChunk]]:
    """Grupos de chunks consecutivos, na ordem (source_id, index). A mesma entrada dá os mesmos grupos."""
    if chunks_per_call < 1:
        raise ValueError("chunks_per_call tem de ser pelo menos 1")
    ordered = sorted(chunks, key=lambda c: (c.source_id, c.index, c.chunk_id))
    return [ordered[i:i + chunks_per_call] for i in range(0, len(ordered), chunks_per_call)]


@dataclass(frozen=True)
class ExtractionRun:
    result: CaseResult
    calls: dict[str, tuple[str, ...]]

    def call_of(self, key: str) -> str:
        prefix = key.split("-", 1)[0]
        if prefix not in self.calls:
            raise KeyError(f"{key!r} não começa por um prefixo de chamada desta extração ({sorted(self.calls)})")
        return prefix


def extract_case(
    *,
    case_id: str,
    run_index: int,
    chunks: Iterable[SourceChunk],
    config: ExperimentConfig,
    client: LLMClient,
    log: CallLog,
) -> ExtractionRun:
    """Uma chamada por grupo de extraction.chunks_per_call chunks, unidas com merge_outputs.

    A extração é compartilhada pelas duas condições, então não tem condição. Uma resposta
    inválida invalida o caso inteiro, e as chamadas seguintes não são feitas.
    """
    chunks_per_call = config.extraction.chunks_per_call
    groups = group_chunks(chunks, chunks_per_call)
    calls = {call_prefix(i): tuple(c.chunk_id for c in group) for i, group in enumerate(groups)}
    case = CallTarget(case_id, None, run_index, "extraction", "case")
    parts: list[tuple[str, ExtractionOutput]] = []
    for index, group in enumerate(groups):
        prefix = call_prefix(index)
        target = CallTarget(case_id, None, run_index, "extraction", prefix)
        request = LLMRequest(prompts.extraction_prompt(group), target,
                             {"chunk_ids": list(calls[prefix]), "chunks_per_call": chunks_per_call})
        try:
            response = invoke(client, request, log)
        except LLMAPIError as error:
            return ExtractionRun(_failed(case, RunStatus.API_ERROR, f"{prefix}: {error}"), calls)
        try:
            parts.append((prefix, parse_output(response, ExtractionOutput, f"{case_id}/{prefix}")))
        except OutputError as error:
            return ExtractionRun(_failed(case, RunStatus.INVALID_OUTPUT, str(error)), calls)
    if not parts:
        return ExtractionRun(_failed(case, RunStatus.INVALID_OUTPUT, "caso sem nenhum chunk"), calls)
    try:
        merged = merge_outputs(parts)
    except ValueError as error:
        return ExtractionRun(_failed(case, RunStatus.INVALID_OUTPUT, f"{case_id}: união falhou: {error}"), calls)
    return ExtractionRun(_ok(case, extraction=merged), calls)


def persistable(run: ExtractionRun, corpus: CorpusIndex, confidence_threshold: float) -> PersistBatch:
    """Registros graváveis do caso. Caso inválido não produz nenhum."""
    if run.result.extraction is None:
        return PersistBatch()
    return to_records(run.result.extraction, corpus, confidence_threshold)


# Refinamento


def source_chunks_context(run: ExtractionRun, key: str, chunks: Iterable[SourceChunk]) -> RetrievedContext:
    """Contexto da condição LLM-only: os chunks da chamada de extração em que o candidato nasceu."""
    wanted = run.calls[run.call_of(key)]
    by_id = {c.chunk_id: c for c in chunks}
    items = [
        ContextItem(item_id=chunk_id, kind="source_chunk", rank=rank, text=by_id[chunk_id].text,
                    source_id=by_id[chunk_id].source_id, chunk_id=chunk_id)
        for rank, chunk_id in enumerate(wanted)
    ]
    return RetrievedContext(query=f"refinar {key}", strategy=ContextStrategy.SOURCE_CHUNKS,
                            limit=max(1, len(items)), items=items)


def refinement_reasons(output: ExtractionOutput, corpus: CorpusIndex, key: str, confidence_threshold: float) -> list[str]:
    """Motivos da seleção, iguais nas duas condições porque saem da extração compartilhada."""
    reasons = [f"{v.rule_id}: {v.detail}" for v in check_all(output, corpus)
               if v.subject == key and v.rule_id in REFINEMENT_TRIGGERS]
    candidate = next(r for r in output.requirements if r.key == key)
    reasons += [f"marca de revisão: {flag.value}" for flag in candidate.review_flags]
    if candidate.confidence is not None and candidate.confidence < confidence_threshold:
        reasons.append(f"confiança {candidate.confidence} abaixo do limiar {confidence_threshold}")
    return reasons


@dataclass(frozen=True)
class RefinementResult:
    result: CaseResult
    candidate: RequirementCandidate
    accepted: bool
    violations: tuple[Violation, ...] = ()


def refine_candidate(
    *,
    case_id: str,
    condition: Condition,
    run_index: int,
    candidate: RequirementCandidate,
    context: RetrievedContext,
    reasons: list[str],
    corpus: CorpusIndex,
    client: LLMClient,
    guard: SinglePassGuard,
    log: CallLog,
) -> RefinementResult:
    """Uma passagem. Com violação G, recusa e devolve o candidato original.

    corpus: os chunks do documento do caso, contra os quais G6 confere a evidência nova.
    """
    target = CallTarget(case_id, condition, run_index, "refinement", candidate.key)
    guard.claim(target)
    request = LLMRequest(prompts.refinement_prompt(candidate, context, reasons), target,
                         {"context_item_ids": [i.item_id for i in context.items], "context_strategy": context.strategy.value})
    try:
        response = invoke(client, request, log)
    except LLMAPIError as error:
        return RefinementResult(_failed(target, RunStatus.API_ERROR, str(error)), candidate, False)
    try:
        output = parse_output(response, RefinementOutput, f"{case_id}/{candidate.key}")
    except OutputError as error:
        return RefinementResult(_failed(target, RunStatus.INVALID_OUTPUT, str(error)), candidate, False)
    violations = tuple(output.check_against(context, candidate, corpus))
    result = _ok(target, refinements=[output], violations=[ViolationRecord.of(v) for v in violations])
    if violations:
        return RefinementResult(result, candidate, False, violations)
    return RefinementResult(result, output.revised, True)


def apply_refinements(output: ExtractionOutput, results: Iterable[RefinementResult]) -> ExtractionOutput:
    """Saída final de uma condição: a extração com os refinamentos aceitos no lugar dos candidatos."""
    accepted = {r.candidate.key: r.candidate for r in results if r.accepted}
    requirements = [accepted.get(r.key, r) for r in output.requirements]
    return ExtractionOutput.model_validate({**output.model_dump(), "requirements": [r.model_dump() for r in requirements]})


# Classificação do PROMISE


@dataclass(frozen=True)
class ClassificationItem:
    promise_id: str
    text: str


def empty_context(query: str) -> RetrievedContext:
    """Contexto sem itens, com a estratégia da condição LLM-only."""
    return RetrievedContext(query=query, strategy=ContextStrategy.SOURCE_CHUNKS, limit=1, items=[])


def classify_item(
    *, item: ClassificationItem, run_index: int, client: LLMClient, log: CallLog
) -> CaseResult:
    """A primeira classificação é compartilhada pelas duas condições, então não tem condição."""
    target = CallTarget(item.promise_id, None, run_index, "classification", item.promise_id)
    request = LLMRequest(prompts.classification_prompt(item.promise_id, item.text), target)
    try:
        response = invoke(client, request, log)
    except LLMAPIError as error:
        return _failed(target, RunStatus.API_ERROR, str(error))
    try:
        output = parse_output(response, ClassificationOutput, item.promise_id)
    except OutputError as error:
        return _failed(target, RunStatus.INVALID_OUTPUT, str(error))
    if output.promise_id != item.promise_id:
        return _failed(target, RunStatus.INVALID_OUTPUT,
                       f"{item.promise_id}: a resposta classifica {output.promise_id}, não o item enviado")
    return _ok(target, classification=output)


@dataclass(frozen=True)
class ClassificationRefinementResult:
    result: CaseResult
    classification: ClassificationOutput
    accepted: bool
    violations: tuple[Violation, ...] = ()


def refine_classification(
    *,
    item: ClassificationItem,
    first: ClassificationOutput,
    condition: Condition,
    run_index: int,
    context: RetrievedContext,
    client: LLMClient,
    guard: SinglePassGuard,
    log: CallLog,
) -> ClassificationRefinementResult:
    target = CallTarget(item.promise_id, condition, run_index, "classification_refinement", item.promise_id)
    guard.claim(target)
    request = LLMRequest(prompts.classification_refinement_prompt(item.promise_id, item.text, first, context), target,
                         {"context_item_ids": [i.item_id for i in context.items], "context_strategy": context.strategy.value})
    try:
        response = invoke(client, request, log)
    except LLMAPIError as error:
        return ClassificationRefinementResult(_failed(target, RunStatus.API_ERROR, str(error)), first, False)
    try:
        output = parse_output(response, ClassificationOutput, item.promise_id)
    except OutputError as error:
        return ClassificationRefinementResult(_failed(target, RunStatus.INVALID_OUTPUT, str(error)), first, False)
    violations = tuple(output.check_against(context, first, item.text))
    result = _ok(target, classification=output, violations=[ViolationRecord.of(v) for v in violations])
    if violations:
        return ClassificationRefinementResult(result, first, False, violations)
    return ClassificationRefinementResult(result, output, True)
