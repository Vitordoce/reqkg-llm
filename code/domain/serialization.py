"""Leitura com erro legível e escrita canônica. A mesma entrada gera os mesmos bytes."""

import json
import tomllib
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError

from domain.config import ContractError

M = TypeVar("M", bound=BaseModel)


def canonical_json(model: BaseModel) -> str:
    data = model.model_dump(mode="json")
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"


def describe(error: ValidationError, origin: str) -> str:
    lines = [f"{origin}: {error.error_count()} erro(s) de contrato em {error.title}"]
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"]) or "(raiz)"
        lines.append(f"  {location}: {item['msg']}")
    return "\n".join(lines)


def parse(data: object, model: type[M], origin: str = "<dados>") -> M:
    """Aceita um modelo ou um tipo genérico, como list[SourceChunk]."""
    try:
        return TypeAdapter(model).validate_python(data)
    except ValidationError as error:
        raise ContractError(describe(error, origin)) from None


def load_json(path: Path, model: type[M]) -> M:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ContractError(f"{path}: JSON inválido na linha {error.lineno}: {error.msg}") from None
    return parse(data, model, str(path))


def load_toml(path: Path, model: type[M]) -> M:
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ContractError(f"{path}: TOML inválido: {error}") from None
    return parse(data, model, str(path))
