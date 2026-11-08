"""Clientes que o executor põe na frente do modelo: escolha do replay, retomada e medidor de tokens."""

from collections.abc import Mapping
from pathlib import Path

from experiments.records import CallMeta, CallRecord
from extraction.client import (
    CallTarget,
    LLMAPIError,
    LLMClient,
    LLMRequest,
    LLMResponse,
    ReplayClient,
    ReplayKey,
    replay_key,
)


def load_replay(path: Path) -> ReplayClient:
    """calls.jsonl de uma corrida, refeita chamada a chamada pelo alvo, ou um replay_index.json de fixtures."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{path}: arquivo de replay não encontrado")
    if path.suffix == ".jsonl":
        return ReplayClient.from_calls_log(path)
    if path.suffix == ".json":
        return ReplayClient.from_fixtures(path)
    raise ValueError(f"{path}: o replay é um calls.jsonl ou um replay_index.json")


def total_input(usage: Mapping[str, int | None]) -> int:
    """Tokens de entrada, somando os de cache, que a API conta à parte."""
    return sum(usage.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))


class ResumeClient:
    """Retomada: serve do calls.jsonl parcial as chamadas já feitas, pelo prompt e pelo alvo, e chama inner só
    para o que falta. A resposta servida leva a linha original, que invoke grava sem mudar (carimbo de tempo,
    modelo, uso de tokens e temperatura da chamada paga). Chamada que tinha falhado na API falha de novo."""

    def __init__(self, logged: list[CallRecord], inner: LLMClient) -> None:
        self.inner = inner
        self.pending: dict[ReplayKey, CallRecord] = {}
        for record in logged:
            key = replay_key(record.prompt_sha256, record.target.model_dump(mode="json"))
            if key in self.pending and self.pending[key].line() != record.line():
                raise ValueError(f"o registro parcial tem duas chamadas diferentes para o alvo "
                                 f"{record.target.model_dump(mode='json')}")
            self.pending[key] = record
        self.logged = len(self.pending)

    def describe(self) -> dict[str, object]:
        return self.inner.describe()

    def complete(self, request: LLMRequest) -> LLMResponse:
        record = self.pending.pop(replay_key(request.prompt.sha256, request.target.as_dict()), None)
        if record is None:
            return self.inner.complete(request)
        if record.meta.model_dump(exclude_none=True) != CallMeta.model_validate(dict(request.meta)).model_dump(exclude_none=True):
            raise ValueError(f"a retomada pediu {request.target.as_dict()} com outro meta que o registro parcial")
        if record.status == "api_error":
            raise LLMAPIError(record.error, record.temperature.model_dump(exclude_unset=True), recorded=record)
        return LLMResponse(text=record.raw_response, model=record.model or "replay", stop_reason=record.stop_reason,
                           usage=record.usage.model_dump(exclude_unset=True), response_id=record.response_id,
                           temperature=record.temperature.model_dump(exclude_unset=True), recorded=record)


class UsageMeter:
    """Repassa ao cliente e guarda o uso de tokens de cada chamada, pelo alvo."""

    def __init__(self, inner: LLMClient) -> None:
        self.inner = inner
        self.usage: dict[CallTarget, tuple[int, int]] = {}

    def describe(self) -> dict[str, object]:
        return self.inner.describe()

    def complete(self, request: LLMRequest) -> LLMResponse:
        response = self.inner.complete(request)
        self.usage[request.target] = (total_input(response.usage), response.usage.get("output_tokens") or 0)
        return response

    def tokens(self, targets: list[CallTarget]) -> tuple[int, int]:
        spent = [self.usage.get(t, (0, 0)) for t in targets]
        return sum(i for i, _ in spent), sum(o for _, o in spent)
