"""OllamaClient contra um servidor falso: corpo da requisição, registro, erros e guardas."""

import json

import pytest

from experiments.records import CallRecord
from extraction import client as client_module
from extraction import prompts
from extraction.client import (
    CallLog,
    CallTarget,
    ClientConfigError,
    LLMAPIError,
    LLMRequest,
    OllamaClient,
    OllamaHTTPError,
    OllamaUnreachable,
    invoke,
    real_client,
)
from extraction.fixtures import scenarios
from extraction.schema import output_schema

DIGEST = "ab" * 32
TARGET = CallTarget("caso-teste", None, 0, "classification", "PROMISE-NFR-9001")
ANSWER = '{"promise_id": "PROMISE-NFR-9001", "label": "F", "rationale": null}'


def _model(**update):
    base = {"model_id": "qwen3:14b", "model_digest": DIGEST, "seed": 7, "num_ctx": 8192, "max_tokens": 1024,
            "temperature": 0.0}
    return scenarios.config().model.model_copy(update={**base, **update})


def _request() -> LLMRequest:
    return LLMRequest(prompts.classification_prompt("PROMISE-NFR-9001", "The system shall do X."), TARGET)


class FakeOllama:
    """Responde como o Ollama 0.32: /api/tags, /api/version e /api/chat sem streaming."""

    def __init__(self, *, digest: str = DIGEST, chat: dict | Exception | None = None, down: bool = False):
        self.digest, self.chat, self.down = digest, chat, down
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, method, url, body, timeout):
        self.calls.append((method, url, body))
        if self.down:
            raise OllamaUnreachable("[Errno 61] Connection refused")
        if url.endswith("/api/tags"):
            return {"models": [{"name": "qwen3:14b", "model": "qwen3:14b", "digest": self.digest}]}
        if url.endswith("/api/version"):
            return {"version": "0.32.4"}
        if isinstance(self.chat, Exception):
            raise self.chat
        return self.chat or {
            "model": "qwen3:14b", "message": {"role": "assistant", "content": ANSWER}, "done": True,
            "done_reason": "stop", "total_duration": 2_500_000_000, "load_duration": 100_000_000,
            "prompt_eval_count": 600, "prompt_eval_duration": 1_200_000_000, "eval_count": 25,
            "eval_duration": 1_000_000_000,
        }


def test_refuses_missing_choices_before_touching_the_server():
    server = FakeOllama()
    with pytest.raises(ClientConfigError) as error:
        OllamaClient(_model(model_id="", model_digest="", seed=None), http=server)
    message = str(error.value)
    assert "model.model_id" in message and "model.model_digest" in message and "model.seed" in message
    assert server.calls == []


def test_server_down_says_to_run_ollama_serve():
    with pytest.raises(ClientConfigError, match="rode `ollama serve`"):
        OllamaClient(_model(), http=FakeOllama(down=True))


def test_model_must_be_installed_with_the_registered_digest():
    with pytest.raises(ClientConfigError, match="rode `ollama pull qwen3:8b`"):
        OllamaClient(_model(model_id="qwen3:8b"), http=FakeOllama())
    with pytest.raises(ClientConfigError, match=f"digest {'cd' * 32}.*registra {DIGEST}"):
        OllamaClient(_model(), http=FakeOllama(digest="cd" * 32))


def test_real_client_follows_the_provider(monkeypatch):
    monkeypatch.setattr(client_module, "ollama_http", FakeOllama())
    assert isinstance(real_client(_model()), OllamaClient)
    monkeypatch.setattr(client_module, "AnthropicClient", lambda model: ("anthropic", model.model_id))
    anthropic = _model(provider="anthropic", model_digest="", seed=None, num_ctx=None, model_id="claude-x")
    assert real_client(anthropic) == ("anthropic", "claude-x")
    monkeypatch.setattr(client_module, "OpenRouterClient", lambda model: ("openrouter", model.model_id))
    openrouter = _model(provider="openrouter", model_digest="", num_ctx=None, model_id="anthropic/claude-sonnet-4")
    assert real_client(openrouter) == ("openrouter", "anthropic/claude-sonnet-4")


def test_openrouter_client_sends_json_schema_and_never_logs_the_api_key(tmp_path):
    captured = {}

    def fake_http(url, headers, body, timeout):
        captured["url"] = url
        captured["headers"] = dict(headers)
        captured["body"] = body
        return {
            "id": "gen-123",
            "model": body["model"],
            "choices": [{"message": {"role": "assistant", "content": ANSWER}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 500, "completion_tokens": 20, "prompt_tokens_details": {"cached_tokens": 100}},
        }

    model = _model(provider="openrouter", model_digest="", num_ctx=None,
                   base_url="https://openrouter.ai/api/v1", model_id="anthropic/claude-sonnet-4")
    fake_or_key = "chave-sintetica-openrouter-teste"
    client = client_module.OpenRouterClient(model, env={"OPENROUTER_API_KEY": fake_or_key}, http=fake_http)
    log = CallLog(tmp_path)
    response = invoke(client, _request(), log)
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["headers"] == {"Authorization": f"Bearer {fake_or_key}"}
    assert captured["body"]["response_format"]["type"] == "json_schema"
    assert "$ref" not in json.dumps(captured["body"]["response_format"])
    assert captured["body"]["seed"] == 7 and captured["body"]["temperature"] == 0.0
    assert response.usage == {"input_tokens": 500, "output_tokens": 20, "cache_read_input_tokens": 100}
    assert fake_or_key not in log.path.read_text(encoding="utf-8")


def test_request_is_native_chat_with_schema_format_and_thinking_off(tmp_path):
    server = FakeOllama()
    client = OllamaClient(_model(temperature=0.0, seed=7, num_ctx=8192, max_tokens=1024), http=server)
    invoke(client, _request(), CallLog(tmp_path))
    method, url, body = server.calls[-1]
    assert (method, url) == ("POST", "http://localhost:11434/api/chat")
    assert body["model"] == "qwen3:14b" and body["stream"] is False and body["think"] is False
    assert body["format"] == output_schema(_request().prompt.output_model)
    assert "$ref" not in json.dumps(body["format"]) and "$defs" not in json.dumps(body["format"])
    assert body["options"] == {"temperature": 0.0, "seed": 7, "num_ctx": 8192, "num_predict": 1024}
    assert body["messages"] == [{"role": "system", "content": _request().prompt.system},
                                {"role": "user", "content": _request().prompt.user}]


def test_log_line_records_model_digest_tokens_timing_and_sampling(tmp_path):
    client = OllamaClient(_model(), http=FakeOllama())
    log = CallLog(tmp_path, clock=lambda: "2026-10-14T00:00:00+00:00")
    invoke(client, _request(), log)
    [line] = log.path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(line)
    assert set(entry) == set(CallRecord.model_fields)
    assert entry["client"]["provider"] == "ollama" and entry["client"]["model_digest"] == DIGEST
    assert entry["client"]["server_version"] == "0.32.4" and entry["client"]["think"] is False
    assert entry["usage"] == {"input_tokens": 600, "output_tokens": 25}
    assert entry["timing"] == {"total_s": 2.5, "load_s": 0.1, "prompt_eval_s": 1.2, "eval_s": 1.0}
    assert entry["temperature"] == {"value": 0.0, "transport": "options", "seed": 7, "sent": True, "accepted": True}
    assert entry["model"] == "qwen3:14b" and entry["stop_reason"] == "stop" and entry["raw_response"] == ANSWER
    assert log.entries() == [CallRecord.model_validate(entry)]


@pytest.mark.parametrize("error, accepted, message", [
    (OllamaUnreachable("[Errno 61] Connection refused"), None, "rode `ollama serve`"),
    (OllamaHTTPError(400, "invalid option: seed"), False, "OllamaHTTPError 400"),
    (OllamaHTTPError(404, 'model "qwen3:14b" not found'), None, "rode `ollama pull qwen3:14b`"),
    (OllamaHTTPError(500, "out of memory"), None, "out of memory"),
])
def test_server_errors_become_api_errors_and_are_logged(tmp_path, error, accepted, message):
    client = OllamaClient(_model(), http=FakeOllama(chat=error))
    log = CallLog(tmp_path)
    with pytest.raises(LLMAPIError, match=message):
        invoke(client, _request(), log)
    [entry] = log.entries()
    assert entry.status == "api_error" and entry.raw_response is None and entry.timing is None
    assert entry.temperature.accepted is accepted and entry.temperature.seed == 7


def test_thinking_output_and_a_full_context_window_are_refused(tmp_path):
    base = FakeOllama()(None, "/api/chat", None, 0)
    thinking = {**base, "message": {"role": "assistant", "content": ANSWER, "thinking": "Vou classificar..."}}
    with pytest.raises(LLMAPIError, match="think = false"):
        invoke(OllamaClient(_model(), http=FakeOllama(chat=thinking)), _request(), CallLog(tmp_path / "a"))
    full = {**base, "prompt_eval_count": 8000, "eval_count": 192}
    with pytest.raises(LLMAPIError, match="janela de contexto cheia.*num_ctx = 8192"):
        invoke(OllamaClient(_model(), http=FakeOllama(chat=full)), _request(), CallLog(tmp_path / "b"))
    fits = {**base, "prompt_eval_count": 8000, "eval_count": 191}
    assert invoke(OllamaClient(_model(), http=FakeOllama(chat=fits)), _request(), CallLog(tmp_path / "c")).text == ANSWER
