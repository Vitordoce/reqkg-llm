"""Clientes do modelo e registro de cada chamada.

OllamaClient chama o modelo local do experimento; AnthropicClient, a API do Claude, que ficou como
opção. real_client escolhe pelo provider da configuração. ReplayClient devolve respostas gravadas: as
dos fixtures, pelo SHA-256 do prompt, ou as de uma corrida, pelo prompt e pelo alvo. Todas seguem o
protocolo LLMClient, e toda chamada passa por invoke, que grava uma linha em <run_dir>/calls.jsonl
validada por experiments.records.CallRecord. A chave de API nunca entra no registro.
"""

import json
import os
import re
import socket
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import anthropic

from domain.config import ContractError, ModelConfig
from domain.enums import Condition
from domain.serialization import parse
from experiments.records import CallMeta, CallRecord, CallTargetRecord
from extraction.prompts import RenderedPrompt
from graph.connection import read_env_file
from extraction.schema import output_schema, schema_sha256

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = REPO_ROOT / "outputs" / "runs"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPLAY_INDEX = FIXTURES / "replay_index.json"
API_KEY_VARIABLE = "ANTHROPIC_API_KEY"
OPENROUTER_API_KEY_VARIABLE = "OPENROUTER_API_KEY"
OPENROUTER_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
ENV_FILE = REPO_ROOT / ".env"
CONFIG_FILE = "code/experiments/config/experiment.toml"


class ClientConfigError(ContractError):
    """Falta algo para montar o cliente: model_id, digest, chave de API ou o servidor do Ollama."""


NOT_SENT = {"sent": False, "accepted": None}


class LLMAPIError(RuntimeError):
    """A API falhou. O caso vira CaseResult com status api_error."""

    def __init__(self, message: str, temperature: Mapping[str, object] = NOT_SENT,
                 recorded: CallRecord | None = None) -> None:
        super().__init__(message)
        self.temperature = dict(temperature)
        self.recorded = recorded


class MissingReplayError(LookupError):
    """Não há resposta gravada para o prompt. É erro de teste ou de fixture, não da API."""


@dataclass(frozen=True)
class CallTarget:
    case_id: str
    condition: Condition | None
    run_index: int
    stage: str
    key: str

    def as_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "condition": self.condition.value if self.condition else None,
            "run_index": self.run_index,
            "stage": self.stage,
            "key": self.key,
        }


@dataclass(frozen=True)
class LLMRequest:
    prompt: RenderedPrompt
    target: CallTarget
    meta: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    stop_reason: str | None = None
    usage: Mapping[str, int | None] = field(default_factory=dict)
    response_id: str | None = None
    temperature: Mapping[str, object] = field(default_factory=lambda: dict(NOT_SENT))
    # Linha de calls.jsonl de uma corrida retomada: invoke a grava como estava, sem nova chamada.
    recorded: CallRecord | None = None
    timing: Mapping[str, float] | None = None


class LLMClient(Protocol):
    def complete(self, request: LLMRequest) -> LLMResponse: ...

    def describe(self) -> dict[str, object]:
        """Modelo e parâmetros, gravados em cada linha do registro."""
        ...


def find_api_key(env: Mapping[str, str] = os.environ, env_file: Path = ENV_FILE,
                 variable: str = API_KEY_VARIABLE) -> str:
    """A chave do ambiente; se vazia, a do .env, lido como graph.connection lê. O valor nunca é impresso."""
    return env.get(variable, "").strip() or read_env_file(Path(env_file)).get(variable, "").strip()


class AnthropicClient:
    """Saída estruturada por output_config.format, com o schema do domínio sem referências.

    O SDK 1.13.0 não tem parâmetro temperature em messages.create. A temperatura da
    configuração vai no corpo da requisição por extra_body. O registro diz se ela foi enviada e
    se a API a aceitou: accepted true quando a API respondeu sem erro com o campo no corpo,
    false quando recusou citando temperature, null quando falhou por outro motivo. Resposta sem
    erro não prova que o valor foi aplicado; o SDK não devolve essa confirmação.
    """

    def __init__(
        self,
        model: ModelConfig,
        *,
        env: Mapping[str, str] = os.environ,
        env_file: Path = ENV_FILE,
        sdk: Any = None,
        max_retries: int = 2,
        timeout_s: float = 600.0,
    ) -> None:
        missing = []
        if not model.model_id.strip():
            missing.append(f"model.model_id está vazio em {CONFIG_FILE} (o autor escolhe a versão do Claude)")
        api_key = find_api_key(env, env_file)
        if not api_key:
            missing.append(f"{API_KEY_VARIABLE} está vazia no ambiente e ausente de {_relative(env_file)} "
                           "(exporte a variável ou ponha a linha no .env)")
        if missing:
            raise ClientConfigError("chamada real recusada: " + "; ".join(missing))
        self.model = model
        self.max_retries = max_retries
        self.timeout_s = timeout_s
        self._sdk = sdk or anthropic.Anthropic(api_key=api_key, max_retries=max_retries, timeout=timeout_s)

    def describe(self) -> dict[str, object]:
        return {
            "provider": "anthropic",
            "sdk_version": anthropic.__version__,
            "model_id": self.model.model_id,
            "temperature": self.model.temperature,
            "temperature_transport": "extra_body",
            "max_tokens": self.model.max_tokens,
            "max_retries": self.max_retries,
            "timeout_s": self.timeout_s,
            "output_format": "output_config.format json_schema",
        }

    def request_kwargs(self, request: LLMRequest) -> dict[str, Any]:
        return {
            "model": self.model.model_id,
            "max_tokens": self.model.max_tokens,
            "system": request.prompt.system,
            "messages": [{"role": "user", "content": request.prompt.user}],
            "output_config": {"format": {"type": "json_schema", "schema": output_schema(request.prompt.output_model)}},
            "extra_body": {"temperature": self.model.temperature},
        }

    def _temperature(self, accepted: bool | None) -> dict[str, object]:
        return {"value": self.model.temperature, "transport": "extra_body", "sent": True, "accepted": accepted}

    def complete(self, request: LLMRequest) -> LLMResponse:
        try:
            message = self._sdk.messages.create(**self.request_kwargs(request))
        except anthropic.APIStatusError as error:
            refused = error.status_code == 400 and "temperature" in str(error.message).lower()
            raise LLMAPIError(f"{type(error).__name__} {error.status_code}: {error.message}",
                              self._temperature(False if refused else None)) from None
        except anthropic.APIError as error:
            raise LLMAPIError(f"{type(error).__name__}: {error.message}", self._temperature(None)) from None
        usage = message.usage
        return LLMResponse(
            text="".join(block.text for block in message.content if block.type == "text"),
            model=message.model,
            stop_reason=message.stop_reason,
            usage={
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_creation_input_tokens": usage.cache_creation_input_tokens,
                "cache_read_input_tokens": usage.cache_read_input_tokens,
            },
            response_id=message.id,
            temperature=self._temperature(True),
        )


OLLAMA_HINT = (f"rode `ollama serve` (ou abra o app do Ollama) e confira model.base_url em {CONFIG_FILE}")


class OllamaUnreachable(ConnectionError):
    """O servidor do Ollama não respondeu: fora do ar, endereço errado ou tempo esgotado."""


class OllamaHTTPError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


Http = Callable[[str, str, Mapping[str, Any] | None, float], dict[str, Any]]


def ollama_http(method: str, url: str, body: Mapping[str, Any] | None, timeout_s: float) -> dict[str, Any]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        text = error.read().decode("utf-8", errors="replace")
        try:
            message = json.loads(text).get("error", text)
        except (json.JSONDecodeError, AttributeError):
            message = text
        raise OllamaHTTPError(error.code, str(message).strip() or error.reason) from None
    except (urllib.error.URLError, ConnectionError, socket.timeout, TimeoutError) as error:
        raise OllamaUnreachable(str(getattr(error, "reason", error))) from None


class OllamaClient:
    """API nativa do Ollama (/api/chat), sem streaming e com o modo de pensamento desligado (think false).

    A saída é restrita pelo campo format, que recebe o mesmo schema sem referências enviado à Anthropic; o
    Ollama o converte numa gramática e o texto devolvido segue o schema. temperature, seed, num_ctx e
    num_predict (max_tokens) vão em options. O registro diz se foram enviados e se o servidor respondeu sem
    erro com eles (accepted); o Ollama não devolve os valores aplicados, e a reprodutibilidade com a mesma
    semente é conferida pelo teste de fumaça. Ao montar, o cliente confere em /api/tags que o modelo está
    instalado com o digest da configuração. O Ollama corta o prompt que não cabe em num_ctx sem dar erro;
    por isso uma resposta que encheu a janela vira api_error.
    """

    def __init__(self, model: ModelConfig, *, http: Http | None = None, timeout_s: float = 1800.0) -> None:
        missing = []
        if not model.model_id.strip():
            missing.append(f"model.model_id está vazio em {CONFIG_FILE} (a tag do modelo no Ollama)")
        if not model.model_digest:
            missing.append(f"model.model_digest está vazio em {CONFIG_FILE} (o digest de `ollama list` ou /api/tags)")
        if model.seed is None or model.num_ctx is None:
            missing.append(f"model.seed e model.num_ctx são obrigatórios em {CONFIG_FILE}")
        if missing:
            raise ClientConfigError("chamada real recusada: " + "; ".join(missing))
        self.model = model
        self.timeout_s = timeout_s
        self._http = http or ollama_http
        try:
            installed = self._http("GET", self._url("/api/tags"), None, 30.0).get("models", [])
            self.server_version = str(self._http("GET", self._url("/api/version"), None, 30.0).get("version", ""))
        except (OllamaUnreachable, OllamaHTTPError) as error:
            raise ClientConfigError(f"chamada real recusada: Ollama não respondeu em {model.base_url} ({error}): "
                                    f"{OLLAMA_HINT}") from None
        digests = {entry.get("name"): entry.get("digest") for entry in installed}
        digest = digests.get(model.model_id, digests.get(f"{model.model_id}:latest"))
        if digest is None:
            raise ClientConfigError(f"chamada real recusada: o modelo {model.model_id} não está no Ollama em "
                                    f"{model.base_url}; rode `ollama pull {model.model_id}`")
        if digest != model.model_digest:
            raise ClientConfigError(
                f"chamada real recusada: o Ollama tem {model.model_id} com o digest {digest}, e {CONFIG_FILE} "
                f"registra {model.model_digest}. Os pesos mudaram: baixe a versão registrada ou registre a troca "
                "de modelo antes de rodar")

    def _url(self, path: str) -> str:
        return self.model.base_url.rstrip("/") + path

    def describe(self) -> dict[str, object]:
        return {
            "provider": "ollama",
            "server_version": self.server_version,
            "base_url": self.model.base_url,
            "model_id": self.model.model_id,
            "model_digest": self.model.model_digest,
            "temperature": self.model.temperature,
            "seed": self.model.seed,
            "num_ctx": self.model.num_ctx,
            "max_tokens": self.model.max_tokens,
            "think": False,
            "timeout_s": self.timeout_s,
            "output_format": "format json_schema",
        }

    def request_body(self, request: LLMRequest) -> dict[str, Any]:
        return {
            "model": self.model.model_id,
            "messages": [{"role": "system", "content": request.prompt.system},
                         {"role": "user", "content": request.prompt.user}],
            "format": output_schema(request.prompt.output_model),
            "stream": False,
            "think": False,
            "options": {"temperature": self.model.temperature, "seed": self.model.seed,
                        "num_ctx": self.model.num_ctx, "num_predict": self.model.max_tokens},
        }

    def _temperature(self, accepted: bool | None) -> dict[str, object]:
        return {"value": self.model.temperature, "transport": "options", "seed": self.model.seed, "sent": True,
                "accepted": accepted}

    def complete(self, request: LLMRequest) -> LLMResponse:
        try:
            data = self._http("POST", self._url("/api/chat"), self.request_body(request), self.timeout_s)
        except OllamaUnreachable as error:
            raise LLMAPIError(f"OllamaUnreachable: {error}. O Ollama não respondeu em {self.model.base_url}: "
                              f"{OLLAMA_HINT}", self._temperature(None)) from None
        except OllamaHTTPError as error:
            refused = error.status == 400 and any(w in error.message.lower() for w in ("temperature", "seed", "option"))
            hint = f"; rode `ollama pull {self.model.model_id}`" if error.status == 404 else ""
            raise LLMAPIError(f"OllamaHTTPError {error.status}: {error.message}{hint}",
                              self._temperature(False if refused else None)) from None
        message = data.get("message") or {}
        if message.get("thinking"):
            raise LLMAPIError("o modelo devolveu raciocínio em message.thinking com think = false: o modo de "
                              "pensamento não foi desligado", self._temperature(True))
        prompt_tokens, output_tokens = data.get("prompt_eval_count"), data.get("eval_count")
        if (prompt_tokens or 0) + (output_tokens or 0) >= self.model.num_ctx:
            raise LLMAPIError(f"janela de contexto cheia: {prompt_tokens} tokens de entrada e {output_tokens} de "
                              f"saída ocupam num_ctx = {self.model.num_ctx}, e o Ollama corta o prompt sem erro. "
                              f"Aumente model.num_ctx em {CONFIG_FILE}", self._temperature(True))
        seconds = {name: (data.get(key) or 0) / 1e9 for name, key in (
            ("total_s", "total_duration"), ("load_s", "load_duration"),
            ("prompt_eval_s", "prompt_eval_duration"), ("eval_s", "eval_duration"))}
        return LLMResponse(
            text=message.get("content", ""),
            model=str(data.get("model") or self.model.model_id),
            stop_reason=data.get("done_reason"),
            usage={"input_tokens": prompt_tokens, "output_tokens": output_tokens},
            temperature=self._temperature(True),
            timing=seconds,
        )


OpenRouterHttp = Callable[[str, Mapping[str, str], Mapping[str, Any], float], dict[str, Any]]


def openrouter_http(url: str, headers: Mapping[str, str], body: Mapping[str, Any], timeout_s: float) -> dict[str, Any]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, method="POST", headers={"Content-Type": "application/json", **headers}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        text = error.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(text)
            err = payload.get("error", payload)
            message = err.get("message", err) if isinstance(err, Mapping) else err
        except (json.JSONDecodeError, AttributeError):
            message = text
        raise OllamaHTTPError(error.code, str(message).strip() or error.reason) from None
    except (urllib.error.URLError, ConnectionError, socket.timeout, TimeoutError) as error:
        raise OllamaUnreachable(str(getattr(error, "reason", error))) from None


class OpenRouterClient:
    """Cliente compatível com OpenRouter / OpenAI (/chat/completions) com response_format json_schema.

    Permite usar qualquer modelo de fronteira ou de pesos abertos (por exemplo anthropic/claude-sonnet-4,
    openai/gpt-4.1, google/gemini-2.5-pro, qwen/qwen3-235b-a22b) mantendo a mesma chave (OPENROUTER_API_KEY)
    e o mesmo contrato JSON Schema sem referências ($ref). A chave nunca entra no registro de chamadas.
    """

    def __init__(
        self,
        model: ModelConfig,
        *,
        env: Mapping[str, str] = os.environ,
        env_file: Path = ENV_FILE,
        http: OpenRouterHttp | None = None,
        timeout_s: float = 600.0,
    ) -> None:
        missing = []
        if not model.model_id.strip():
            missing.append(f"model.model_id está vazio em {CONFIG_FILE} (identificador do modelo no OpenRouter)")
        api_key = find_api_key(env, env_file, OPENROUTER_API_KEY_VARIABLE)
        if not api_key:
            missing.append(f"{OPENROUTER_API_KEY_VARIABLE} está vazia no ambiente e ausente de {_relative(env_file)} "
                           "(exporte a variável ou ponha a linha no .env)")
        if missing:
            raise ClientConfigError("chamada real recusada: " + "; ".join(missing))
        self.model = model
        self.timeout_s = timeout_s
        self._api_key = api_key
        self._http = http or openrouter_http
        base = model.base_url.strip()
        if not base or base == "http://localhost:11434":
            base = OPENROUTER_DEFAULT_BASE_URL
        self.base_url = base.rstrip("/")

    def describe(self) -> dict[str, object]:
        described: dict[str, object] = {
            "provider": "openrouter",
            "base_url": self.base_url,
            "model_id": self.model.model_id,
            "temperature": self.model.temperature,
            "max_tokens": self.model.max_tokens,
            "timeout_s": self.timeout_s,
            "output_format": "response_format json_schema",
        }
        if self.model.seed is not None:
            described["seed"] = self.model.seed
        return described

    def request_body(self, request: LLMRequest) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model.model_id,
            "messages": [
                {"role": "system", "content": request.prompt.system},
                {"role": "user", "content": request.prompt.user},
            ],
            "temperature": self.model.temperature,
            "max_tokens": self.model.max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": request.prompt.output_model.__name__,
                    "strict": True,
                    "schema": output_schema(request.prompt.output_model),
                },
            },
        }
        if self.model.seed is not None:
            body["seed"] = self.model.seed
        return body

    def _temperature(self, accepted: bool | None) -> dict[str, object]:
        info: dict[str, object] = {
            "value": self.model.temperature,
            "transport": "body",
            "sent": True,
            "accepted": accepted,
        }
        if self.model.seed is not None:
            info["seed"] = self.model.seed
        return info

    def complete(self, request: LLMRequest) -> LLMResponse:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = f"{self.base_url}/chat/completions"
        try:
            data = self._http(url, headers, self.request_body(request), self.timeout_s)
        except OllamaUnreachable as error:
            raise LLMAPIError(f"OpenRouterUnreachable: {error}", self._temperature(None)) from None
        except OllamaHTTPError as error:
            refused = error.status == 400 and any(w in error.message.lower() for w in ("temperature", "seed"))
            raise LLMAPIError(f"OpenRouterHTTPError {error.status}: {error.message}",
                              self._temperature(False if refused else None)) from None
        choices = data.get("choices") or []
        if not choices:
            raise LLMAPIError("OpenRouter respondeu sem choices", self._temperature(True))
        choice = choices[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        details = usage.get("prompt_tokens_details") or {}
        return LLMResponse(
            text=str(message.get("content") or ""),
            model=str(data.get("model") or self.model.model_id),
            stop_reason=choice.get("finish_reason"),
            usage={
                "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
                "cache_read_input_tokens": details.get("cached_tokens"),
            },
            response_id=data.get("id"),
            temperature=self._temperature(True),
        )


def real_client(model: ModelConfig) -> LLMClient:
    """O cliente da chamada real, pelo provider da configuração."""
    if model.provider == "ollama":
        return OllamaClient(model)
    if model.provider == "openrouter":
        return OpenRouterClient(model)
    return AnthropicClient(model)


ReplayKey = str | tuple[str, str, str | None, int, str, str]


@dataclass(frozen=True)
class Recorded:
    """Uma resposta gravada. error preenchido: a chamada falhou na API e falha de novo."""

    prompt_name: str
    prompt_version: int
    text: str | None
    stop_reason: str | None = "end_turn"
    usage: Mapping[str, int | None] = field(default_factory=dict)
    error: str | None = None


class ReplayClient:
    """Responde com o que foi gravado, sem chamar a API.

    from_fixtures indexa pelo SHA-256 do prompt e responde a qualquer alvo. from_calls_log refaz uma
    corrida e indexa pelo SHA-256 do prompt e pelo alvo (caso, condição, corrida, etapa, chave): com
    três repetições, a extração de um caso tem o mesmo prompt nas três, e cada uma recebe a própria
    resposta. Chamada que falhou na API falha de novo com o mesmo erro, e o uso de tokens gravado volta
    junto, para que os registros refeitos guardem o custo da corrida original.
    """

    def __init__(self, responses: Mapping[ReplayKey, Recorded], origin: str, *, by_target: bool = False,
                 models: list[str] | None = None, fixtures_dir: Path = FIXTURES) -> None:
        self._responses = dict(responses)
        self.origin = origin
        self.by_target = by_target
        self.models = sorted(models or [])
        self.fixtures_dir = Path(fixtures_dir)

    @classmethod
    def from_fixtures(cls, index_path: Path = REPLAY_INDEX) -> "ReplayClient":
        index = json.loads(index_path.read_text(encoding="utf-8"))
        responses = {}
        for sha, entry in index.items():
            recorded = json.loads((index_path.parent / entry["file"]).read_text(encoding="utf-8"))
            responses[sha] = Recorded(entry["prompt_name"], entry["prompt_version"], response_text(recorded),
                                      entry.get("stop_reason", "end_turn"))
        return cls(responses, origin=_relative(index_path), fixtures_dir=index_path.parent)

    @classmethod
    def from_calls_log(cls, path: Path) -> "ReplayClient":
        """Refaz uma corrida a partir do calls.jsonl dela, chamada a chamada."""
        records = CallLog.read(path)
        responses: dict[ReplayKey, Recorded] = {}
        for number, record in enumerate(records, start=1):
            key = replay_key(record.prompt_sha256, record.target.model_dump(mode="json"))
            if key in responses:
                raise ValueError(f"{path}: linha {number}: chamada repetida para o alvo {record.target.model_dump(mode='json')}")
            responses[key] = Recorded(record.prompt_name, record.prompt_version, record.raw_response, record.stop_reason,
                                      record.usage.model_dump(exclude_unset=True), record.error)
        models = {str(r.client["model_id"]) for r in records if r.client.get("model_id")}
        return cls(responses, origin=_relative(path), by_target=True, models=list(models))

    def source_model(self) -> str:
        """O modelo da corrida original, se for um só. Uma corrida refeita de outra refeita mantém o nome."""
        real = [m for m in self.models if m not in {"replay", "synthetic"}]
        if len(real) == 1:
            return real[0]
        return self.models[0] if len(self.models) == 1 else "replay"

    def describe(self) -> dict[str, object]:
        described: dict[str, object] = {"provider": "replay", "model_id": self.source_model(), "origin": self.origin}
        return {**described, "usage": "gravado"} if self.by_target else described

    def complete(self, request: LLMRequest) -> LLMResponse:
        prompt = request.prompt
        key = replay_key(prompt.sha256, request.target.as_dict()) if self.by_target else prompt.sha256
        entry = self._responses.get(key)
        if entry is None and self.by_target:
            raise MissingReplayError(f"{self.origin}: nenhuma chamada gravada com o prompt {prompt.name} "
                                     f"v{prompt.version} (sha256 {prompt.sha256}) e o alvo {request.target.as_dict()}")
        if entry is None:
            raise MissingReplayError(
                f"nenhuma resposta gravada para o prompt {prompt.name} v{prompt.version} "
                f"(sha256 {prompt.sha256}, alvo {request.target.as_dict()}) em {self.origin}. "
                f"Se o prompt ou a entrada mudou de propósito, grave a resposta em {_relative(self.fixtures_dir / 'responses')}/ "
                f"e rode .venv/bin/python {_relative(self.fixtures_dir / 'build_replays.py')}"
            )
        if (entry.prompt_name, entry.prompt_version) != (prompt.name, prompt.version):
            raise MissingReplayError(
                f"a resposta gravada para {prompt.sha256} é de {entry.prompt_name} v{entry.prompt_version}, "
                f"não de {prompt.name} v{prompt.version}"
            )
        if entry.error is not None:
            raise LLMAPIError(entry.error)
        return LLMResponse(text=entry.text, model="replay", stop_reason=entry.stop_reason, usage=dict(entry.usage))


def replay_key(prompt_sha256: str, target: Mapping[str, Any]) -> ReplayKey:
    return (prompt_sha256, target["case_id"], target["condition"], target["run_index"], target["stage"], target["key"])


def response_text(recorded: Mapping[str, Any]) -> str:
    """raw_text guarda texto exato, inclusive JSON quebrado. response guarda um objeto."""
    if "raw_text" in recorded:
        return recorded["raw_text"]
    return json.dumps(recorded["response"], ensure_ascii=False, sort_keys=True)


def _relative(path: Path) -> str:
    path = Path(path).resolve()
    return path.relative_to(REPO_ROOT).as_posix() if path.is_relative_to(REPO_ROOT) else path.as_posix()


def default_run_dir(run_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", run_id):
        raise ValueError(f"run_id {run_id!r}: use letras, números, ponto, hífen ou sublinhado")
    return RUNS_ROOT / run_id


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class CallLog:
    """Uma linha JSON por chamada, em <run_dir>/calls.jsonl, só acrescentada."""

    def __init__(self, run_dir: Path, clock: Callable[[], str] = _utc_now) -> None:
        self.run_dir = Path(run_dir)
        self.path = self.run_dir / "calls.jsonl"
        self.clock = clock

    def write(self, record: CallRecord) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(record.line())

    def entries(self) -> list[CallRecord]:
        return self.read(self.path) if self.path.exists() else []

    @staticmethod
    def read(path: Path) -> list[CallRecord]:
        records = []
        for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as error:
                raise ContractError(f"{path}:{number}: JSON inválido: {error.msg}") from None
            records.append(parse(data, CallRecord, f"{path}:{number}"))
        return records


def invoke(client: LLMClient, request: LLMRequest, log: CallLog) -> LLMResponse:
    """Chama o modelo uma vez e grava a chamada, com sucesso ou com erro de API, no formato CallRecord."""
    prompt = request.prompt
    target, meta = request.target.as_dict(), dict(request.meta)
    CallRecord.check_request(CallTargetRecord.model_validate(target), CallMeta.model_validate(meta))
    entry: dict[str, Any] = {
        "timestamp": log.clock(),
        "target": target,
        "meta": meta,
        "client": client.describe(),
        "prompt_name": prompt.name,
        "prompt_version": prompt.version,
        "prompt_template_sha256": prompt.template_sha256,
        "prompt_sha256": prompt.sha256,
        "output_model": prompt.output_model.__name__,
        "output_schema_sha256": schema_sha256(prompt.output_model),
        "user_prompt": prompt.user,
    }
    try:
        response = client.complete(request)
    except LLMAPIError as error:
        log.write(error.recorded or CallRecord(**entry, status="api_error", error=str(error), raw_response=None,
                                               model=None, stop_reason=None, usage={}, response_id=None,
                                               temperature=error.temperature))
        raise
    if response.recorded is not None:
        log.write(response.recorded)
        return response
    if response.timing is not None:
        entry["timing"] = dict(response.timing)
    log.write(CallRecord(**entry, status="returned", error=None, raw_response=response.text, model=response.model,
                         stop_reason=response.stop_reason, usage=dict(response.usage),
                         response_id=response.response_id, temperature=dict(response.temperature)))
    return response
