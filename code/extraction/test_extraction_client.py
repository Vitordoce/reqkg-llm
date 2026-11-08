import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from domain.config import ContractError
from experiments.records import CallRecord
from extraction import prompts
from extraction.client import (
    RUNS_ROOT,
    AnthropicClient,
    CallLog,
    CallTarget,
    ClientConfigError,
    LLMAPIError,
    LLMRequest,
    LLMResponse,
    MissingReplayError,
    ReplayClient,
    default_run_dir,
    invoke,
)
from extraction.fixtures import scenarios

FAKE_KEY = "sk-ant-teste-NAO-E-CHAVE-0123456789"
TARGET = CallTarget("caso-teste", None, 0, "classification", "PROMISE-NFR-9001")


def _model(model_id: str = "claude-modelo-de-teste"):
    return scenarios.config().model.model_copy(update={"provider": "anthropic", "model_id": model_id, "model_digest": "",
                                                        "seed": None, "num_ctx": None})


def _request() -> LLMRequest:
    return LLMRequest(prompts.classification_prompt("PROMISE-NFR-9001", "The system shall do X."), TARGET)


class FakeMessages:
    def __init__(self, error: Exception | None = None):
        self.kwargs = None
        self.error = error

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return SimpleNamespace(
            id="msg_teste", model=kwargs["model"], stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text='{"promise_id": "PROMISE-NFR-9001", "label": "F"}')],
            usage=SimpleNamespace(input_tokens=120, output_tokens=15, cache_creation_input_tokens=None,
                                  cache_read_input_tokens=0),
        )


def test_refuses_empty_model_id_with_clear_message():
    with pytest.raises(ClientConfigError, match=r"model\.model_id está vazio em code/experiments/config/experiment\.toml"):
        AnthropicClient(_model(""), env={"ANTHROPIC_API_KEY": FAKE_KEY})


def test_refuses_empty_key_and_names_both_gaps(tmp_path):
    no_file = tmp_path / ".env"
    with pytest.raises(ClientConfigError, match="ANTHROPIC_API_KEY está vazia no ambiente e ausente de"):
        AnthropicClient(_model(), env={"ANTHROPIC_API_KEY": "  "}, env_file=no_file)
    with pytest.raises(ClientConfigError) as error:
        AnthropicClient(_model(""), env={}, env_file=no_file)
    assert "model.model_id" in str(error.value) and "ANTHROPIC_API_KEY" in str(error.value)


def test_key_comes_from_the_environment_then_from_the_env_file(tmp_path, capsys):
    env_file = tmp_path / ".env"
    env_file.write_text(f"# local\nNEO4J_URI=bolt://localhost:17687\nANTHROPIC_API_KEY='{FAKE_KEY}'\n", encoding="utf-8")
    from_file = AnthropicClient(_model(), env={}, env_file=env_file)
    assert from_file._sdk.api_key == FAKE_KEY
    other = "sk-ant-teste-DO-AMBIENTE-000"
    assert AnthropicClient(_model(), env={"ANTHROPIC_API_KEY": other}, env_file=env_file)._sdk.api_key == other
    assert FAKE_KEY not in json.dumps(from_file.describe())
    env_file.write_text("ANTHROPIC_API_KEY=\n", encoding="utf-8")
    with pytest.raises(ClientConfigError) as error:
        AnthropicClient(_model(), env={}, env_file=env_file)
    assert FAKE_KEY not in str(error.value)
    captured = capsys.readouterr()
    assert FAKE_KEY not in captured.out + captured.err


def test_the_real_config_pins_the_local_model_by_digest():
    model = scenarios.config().model
    assert (model.provider, model.model_id, model.temperature) == ("ollama", "qwen3:14b", 0.0)
    assert len(model.model_digest) == 64 and model.seed is not None and model.num_ctx > model.max_tokens


def test_request_uses_config_and_schema_without_refs(tmp_path):
    messages = FakeMessages()
    model = _model().model_copy(update={"temperature": 0.0, "max_tokens": 1234})
    client = AnthropicClient(model, env={"ANTHROPIC_API_KEY": FAKE_KEY}, sdk=SimpleNamespace(messages=messages))
    response = invoke(client, _request(), CallLog(tmp_path))
    sent = messages.kwargs
    assert sent["model"] == "claude-modelo-de-teste"
    assert sent["max_tokens"] == 1234
    assert sent["extra_body"] == {"temperature": 0.0}
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert "$ref" not in json.dumps(sent["output_config"])
    assert sent["messages"] == [{"role": "user", "content": _request().prompt.user}]
    assert sent["system"] == _request().prompt.system
    assert response.usage["input_tokens"] == 120 and response.response_id == "msg_teste"


def test_log_line_has_the_audit_fields_and_never_the_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    client = AnthropicClient(_model(), sdk=SimpleNamespace(messages=FakeMessages()))
    log = CallLog(tmp_path / "corrida", clock=lambda: "2026-10-10T00:00:00+00:00")
    invoke(client, _request(), log)
    text = log.path.read_text(encoding="utf-8")
    assert FAKE_KEY not in text and "sk-ant" not in text
    [line] = text.splitlines()
    entry = json.loads(line)
    assert entry["prompt_sha256"] == _request().prompt.sha256
    assert entry["prompt_name"] == "classification" and entry["prompt_version"] == 1
    assert entry["prompt_template_sha256"] == prompts.load("classification").sha256
    assert entry["client"]["model_id"] == "claude-modelo-de-teste"
    assert entry["client"]["temperature"] == 0.0 and entry["client"]["max_tokens"] == 4096
    assert entry["client"]["sdk_version"] == anthropic.__version__
    assert entry["usage"] == {"input_tokens": 120, "output_tokens": 15, "cache_creation_input_tokens": None,
                              "cache_read_input_tokens": 0}
    assert json.loads(entry["raw_response"])["label"] == "F"
    assert entry["timestamp"] == "2026-10-10T00:00:00+00:00"
    assert entry["target"] == TARGET.as_dict() and entry["status"] == "returned"
    assert entry["temperature"] == {"value": 0.0, "transport": "extra_body", "sent": True, "accepted": True}
    assert set(entry) == set(CallRecord.model_fields) - {"timing"}, "a Anthropic não devolve tempos"
    assert log.entries() == [CallRecord.model_validate(entry)]


def test_replay_log_says_temperature_was_not_sent(tmp_path):
    log = CallLog(tmp_path)
    prompt = scenarios.SCENARIOS[6].build()
    invoke(ReplayClient.from_fixtures(), LLMRequest(prompt, TARGET), log)
    assert json.loads(log.path.read_text(encoding="utf-8"))["temperature"] == {"sent": False, "accepted": None}


def test_log_refuses_a_line_outside_the_call_record_before_calling(tmp_path):
    chunks = scenarios.entrevista_chunks()[:1]
    without_chunks = LLMRequest(prompts.extraction_prompt(chunks), CallTarget("caso", None, 0, "extraction", "c0"))
    client = AnthropicClient(_model(), env={"ANTHROPIC_API_KEY": FAKE_KEY}, sdk=SimpleNamespace(messages=FakeMessages()))
    with pytest.raises(ValueError, match="meta.chunk_ids"):
        invoke(client, without_chunks, CallLog(tmp_path))
    assert client._sdk.messages.kwargs is None, "a chamada não pode ser feita com um registro inválido"
    log = CallLog(tmp_path)
    invoke(client, _request(), log)
    entry = json.loads(log.path.read_text(encoding="utf-8"))
    for change in ({"status": "api_error"}, {"usage": {"tokens": 1}}, {"target": {**entry["target"], "condition": "LLM-only"}},
                   {"temperature": {"sent": False, "accepted": True}}):
        log.path.write_text(json.dumps({**entry, **change}) + "\n", encoding="utf-8")
        with pytest.raises(ContractError, match="calls.jsonl:1"):
            log.entries()


REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.mark.parametrize("error, accepted", [
    (anthropic.APIConnectionError(request=REQUEST), None),
    (anthropic.BadRequestError("temperature: Extra inputs are not permitted",
                               response=httpx2.Response(400, request=REQUEST), body=None), False),
    (anthropic.BadRequestError("max_tokens: muito grande",
                               response=httpx2.Response(400, request=REQUEST), body=None), None),
])
def test_api_errors_become_llm_api_error_and_are_logged(tmp_path, error, accepted):
    client = AnthropicClient(_model(), env={"ANTHROPIC_API_KEY": FAKE_KEY},
                             sdk=SimpleNamespace(messages=FakeMessages(error)))
    log = CallLog(tmp_path)
    with pytest.raises(LLMAPIError, match=type(error).__name__):
        invoke(client, _request(), log)
    [entry] = log.entries()
    assert entry.status == "api_error" and entry.raw_response is None
    assert entry.temperature.model_dump(exclude_unset=True) == {"value": 0.0, "transport": "extra_body", "sent": True,
                                                                "accepted": accepted}
    assert FAKE_KEY not in log.path.read_text(encoding="utf-8")


def test_replay_missing_response_fails_with_useful_message():
    client = ReplayClient.from_fixtures()
    with pytest.raises(MissingReplayError) as error:
        client.complete(_request())
    message = str(error.value)
    assert "classification v1" in message and _request().prompt.sha256 in message
    assert "build_replays.py" in message


def test_replay_answers_every_recorded_scenario():
    client = ReplayClient.from_fixtures()
    for scenario in scenarios.SCENARIOS:
        prompt = scenario.build()
        assert client.complete(LLMRequest(prompt, TARGET)).text


class RepetitionClient:
    """Responde diferente em cada repetição e falha na API na terceira."""

    def describe(self) -> dict[str, object]:
        return {"provider": "teste", "model_id": "claude-x"}

    def complete(self, request: LLMRequest) -> LLMResponse:
        run_index = request.target.run_index
        if run_index == 2:
            raise LLMAPIError("APIConnectionError: sem rede")
        return LLMResponse(text=f'{{"corrida": {run_index}}}', model="claude-x", stop_reason="end_turn",
                           usage={"input_tokens": 100 + run_index, "output_tokens": 10, "cache_read_input_tokens": 5})


def test_replay_from_calls_log_answers_each_of_three_repetitions_with_its_own_call(tmp_path):
    chunks = scenarios.entrevista_chunks()[:2]

    def request(run_index: int) -> LLMRequest:
        return LLMRequest(prompts.extraction_prompt(chunks), CallTarget("caso", None, run_index, "extraction", "c0"),
                          {"chunk_ids": [c.chunk_id for c in chunks], "chunks_per_call": 6})

    log = CallLog(tmp_path / "corrida")
    for run_index in range(3):
        try:
            invoke(RepetitionClient(), request(run_index), log)
        except LLMAPIError:
            pass
    assert len({e.prompt_sha256 for e in log.entries()}) == 1, "o mesmo prompt nas três repetições"

    replay = ReplayClient.from_calls_log(log.path)
    assert replay.describe()["model_id"] == "claude-x"
    again = CallLog(tmp_path / "refeita")
    for run_index in range(2):
        response = invoke(replay, request(run_index), again)
        assert response.text == f'{{"corrida": {run_index}}}'
        assert response.usage == {"input_tokens": 100 + run_index, "output_tokens": 10, "cache_read_input_tokens": 5}
    with pytest.raises(LLMAPIError, match="sem rede"):
        invoke(replay, request(2), again)
    assert [(e.status, e.usage) for e in again.entries()] == [(e.status, e.usage) for e in log.entries()]
    with pytest.raises(MissingReplayError, match="alvo"):
        replay.complete(request(3))
    log.write(log.entries()[0])
    with pytest.raises(ValueError, match="repetida"):
        ReplayClient.from_calls_log(log.path)


def test_run_dir_is_under_outputs_runs_and_rejects_escape():
    assert default_run_dir("piloto-01") == RUNS_ROOT / "piloto-01"
    for bad in ("../fora", "a/b", ""):
        with pytest.raises(ValueError):
            default_run_dir(bad)
