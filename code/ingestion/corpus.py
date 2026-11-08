"""Ingestão de um conjunto de documentos descrito em TOML.

O arquivo de conjunto lista documentos em tabelas `[[document]]`, com `path` relativo à raiz do
repositório, `kind` (um `SourceKind`) e `title` opcional. A saída é um `IngestedSet`, gravado em
JSON canônico. Nada na saída depende de data, máquina ou ordem de dicionário.
"""

import hashlib
import os
import tomllib
import unicodedata
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from domain import ids
from domain.config import ChunkingConfig, ContractError
from domain.enums import SourceKind
from domain.models import ContractModel, NonEmpty, Sha256, SourceChunk, SourceDocument
from domain.serialization import canonical_json, load_json, parse
from ingestion.chunking import chunk_text, normalize_text

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "data" / "processed" / "ingestion"
EXPERIMENT_CONFIG = REPO_ROOT / "code" / "experiments" / "config" / "experiment.toml"
SUPPORTED_SUFFIXES = (".txt", ".md")
INGESTION_VERSION = "1"


class IngestionError(ValueError):
    pass


class DocumentEntry(ContractModel):
    path: NonEmpty
    kind: SourceKind
    title: NonEmpty | None = None


class SetFile(ContractModel):
    document: list[DocumentEntry] = Field(min_length=1)


class IngestedSet(ContractModel):
    """Documentos em ordem de caminho. Chunks agrupados por documento, em ordem de índice."""

    ingestion_version: Literal["1"]
    set_path: NonEmpty
    set_sha256: Sha256
    chunking: ChunkingConfig
    documents: list[SourceDocument]
    chunks: list[SourceChunk]

    @model_validator(mode="after")
    def check_structure(self) -> Self:
        paths = [d.path for d in self.documents]
        if paths != sorted(set(paths)):
            raise ValueError("documents: caminhos repetidos ou fora de ordem")
        order = {d.source_id: position for position, d in enumerate(self.documents)}
        if len({c.chunk_id for c in self.chunks}) != len(self.chunks):
            raise ValueError("chunks: chunk_id repetido")
        expected: dict[str, int] = {}
        last_document = -1
        for chunk in self.chunks:
            if chunk.source_id not in order:
                raise ValueError(f"chunks: {chunk.chunk_id} aponta para fonte ausente {chunk.source_id}")
            position = order[chunk.source_id]
            if position < last_document or chunk.index != expected.get(chunk.source_id, 0):
                raise ValueError(f"chunks: {chunk.chunk_id} fora da ordem de documento e índice")
            last_document = position
            expected[chunk.source_id] = chunk.index + 1
        return self

    def chunks_of(self, source: str) -> list[SourceChunk]:
        return [c for c in self.chunks if c.source_id == source]


def load_chunking(config_path: Path = EXPERIMENT_CONFIG) -> ChunkingConfig:
    try:
        data = tomllib.loads(Path(config_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise IngestionError(f"{config_path}: arquivo de configuração não encontrado") from None
    except tomllib.TOMLDecodeError as error:
        raise IngestionError(f"{config_path}: TOML inválido: {error}") from None
    if "chunking" not in data:
        raise IngestionError(f"{config_path}: falta a tabela [chunking]")
    try:
        return parse(data["chunking"], ChunkingConfig, f"{config_path} [chunking]")
    except ContractError as error:
        raise IngestionError(str(error)) from None


def _locate(root: Path, canonical: str) -> Path | None:
    for form in ("NFC", "NFD"):
        candidate = root / unicodedata.normalize(form, canonical)
        if candidate.is_file():
            return candidate
    return None


def _read_text(file: Path, origin: str) -> str:
    try:
        return normalize_text(file.read_bytes().decode("utf-8"))
    except UnicodeDecodeError as error:
        raise IngestionError(f"{origin}: não é UTF-8 válido (byte {error.start})") from None


def ingest(set_file: Path, chunking: ChunkingConfig, root: Path = REPO_ROOT) -> IngestedSet:
    root = Path(root).resolve()
    set_file = Path(set_file).resolve()
    try:
        label = set_file.relative_to(root).as_posix()
    except ValueError:
        raise IngestionError(f"{set_file}: o arquivo de conjunto tem de ficar dentro de {root}") from None
    if not set_file.is_file():
        raise IngestionError(f"{label}: arquivo de conjunto não encontrado")
    raw = set_file.read_bytes()
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise IngestionError(f"{label}: TOML inválido: {error}") from None
    try:
        entries = parse(data, SetFile, label).document
    except ContractError as error:
        raise IngestionError(str(error)) from None

    documents: list[tuple[SourceDocument, list[SourceChunk]]] = []
    seen: dict[str, int] = {}
    for position, entry in enumerate(entries):
        field = f"{label}: document.{position}.path"
        try:
            path = ids.canonical_path(entry.path)
        except ValueError as error:
            raise IngestionError(f"{field}: {error}") from None
        if path in seen:
            raise IngestionError(f"{field}: {path!r} repete document.{seen[path]}.path")
        seen[path] = position
        if Path(path).suffix.lower() not in SUPPORTED_SUFFIXES:
            raise IngestionError(f"{field}: {path!r} não é {' nem '.join(SUPPORTED_SUFFIXES)}")
        file = _locate(root, path)
        if file is None:
            raise IngestionError(f"{field}: arquivo {path!r} não existe em {root}")
        text = _read_text(file, f"{field}: {path!r}")
        source = ids.source_id(path)
        chunks = chunk_text(text, source, chunking)
        if not chunks:
            raise IngestionError(f"{field}: {path!r} não tem texto")
        document = SourceDocument(
            source_id=source,
            path=path,
            sha256=ids.sha256_text(text),
            kind=entry.kind,
            title=entry.title,
            char_count=len(text),
        )
        documents.append((document, chunks))

    documents.sort(key=lambda pair: pair[0].path)
    return IngestedSet(
        ingestion_version=INGESTION_VERSION,
        set_path=label,
        set_sha256=hashlib.sha256(raw).hexdigest(),
        chunking=chunking,
        documents=[document for document, _ in documents],
        chunks=[chunk for _, chunks in documents for chunk in chunks],
    )


def default_output(set_file: Path) -> Path:
    return OUTPUT_DIR / f"{Path(set_file).stem}.json"


def check_same_set(previous: IngestedSet, current: IngestedSet, output: Path) -> None:
    """A saída leva o nome do arquivo de conjunto; dois conjuntos com o mesmo nome colidem."""
    if previous.set_path == current.set_path:
        return
    absolute = Path(output).resolve()
    shown = absolute.relative_to(REPO_ROOT).as_posix() if absolute.is_relative_to(REPO_ROOT) else str(output)
    raise IngestionError(
        f"{shown} veio de outro arquivo de conjunto ({previous.set_path}), não de {current.set_path}. "
        "Nada foi gravado. Grave em outro arquivo com --output data/processed/ingestion/<nome>.json, "
        f"ou renomeie {current.set_path}. Se o conjunto mudou de lugar de propósito, apague {shown} "
        "e rode de novo."
    )


def render(ingested: IngestedSet) -> bytes:
    return canonical_json(ingested).encode("utf-8")


def write(ingested: IngestedSet, output: Path) -> bool:
    """Grava só se os bytes mudaram. Devolve True quando gravou."""
    data = render(ingested)
    output = Path(output)
    if output.is_file() and output.read_bytes() == data:
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, output)
    return True


def load(path: Path) -> IngestedSet:
    try:
        return load_json(Path(path), IngestedSet)
    except FileNotFoundError:
        raise IngestionError(f"{path}: arquivo de ingestão não encontrado") from None
    except ContractError as error:
        raise IngestionError(str(error)) from None
