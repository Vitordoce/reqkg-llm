"""Clientes falsos para os testes de borda que as respostas gravadas não cobrem."""

from dataclasses import dataclass, field

from extraction.client import LLMAPIError, LLMRequest, LLMResponse


@dataclass
class StaticClient:
    """Devolve sempre o mesmo texto e conta as chamadas."""

    text: str
    stop_reason: str = "end_turn"
    calls: list[LLMRequest] = field(default_factory=list)

    def describe(self) -> dict[str, object]:
        return {"provider": "static", "model_id": "static"}

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(text=self.text, model="static", stop_reason=self.stop_reason)


@dataclass
class FailingClient:
    message: str = "APIConnectionError: sem rede"
    calls: list[LLMRequest] = field(default_factory=list)

    def describe(self) -> dict[str, object]:
        return {"provider": "failing", "model_id": "failing"}

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        raise LLMAPIError(self.message)


@dataclass
class CountingClient:
    """Repassa ao cliente real e conta as chamadas."""

    inner: object
    calls: list[LLMRequest] = field(default_factory=list)

    def describe(self) -> dict[str, object]:
        return self.inner.describe()

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        return self.inner.complete(request)
