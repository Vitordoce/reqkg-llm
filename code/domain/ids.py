"""Identificadores estáveis. Mesma entrada, mesmo identificador, em qualquer máquina."""

import hashlib
import re
import unicodedata
from pathlib import PurePosixPath

from domain.enums import NodeKind, QualityCategory, RelationType, SYMMETRIC_RELATIONS

ID_PREFIX: dict[NodeKind, str] = {
    NodeKind.REQUIREMENT: "req",
    NodeKind.ACTOR: "act",
    NodeKind.SOURCE_DOCUMENT: "src",
    NodeKind.SOURCE_CHUNK: "chk",
    NodeKind.QUALITY_ATTRIBUTE: "qa",
    NodeKind.SOFTWARE_COMPONENT: "cmp",
    NodeKind.ENTITY: "ent",
}

HASH_ID = r"[0-9a-f]{16}"
ID_PATTERN: dict[NodeKind, str] = {
    kind: rf"^{prefix}-{HASH_ID}$" for kind, prefix in ID_PREFIX.items()
}
ID_PATTERN[NodeKind.QUALITY_ATTRIBUTE] = (
    r"^qa-(" + "|".join(c.value for c in QualityCategory) + r")$"
)
RELATION_ID_PATTERN = rf"^rel-{HASH_ID}$"

_SEPARATOR = "\x1f"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_name(text: str) -> str:
    folded = unicodedata.normalize("NFC", text).casefold()
    return re.sub(r"\s+", " ", folded).strip()


def stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256(_SEPARATOR.join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:16]}"


def canonical_path(logical_path: str) -> str:
    """Caminho relativo à raiz do repositório, em NFC e com barras normais."""
    text = unicodedata.normalize("NFC", logical_path.replace("\\", "/"))
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"caminho {logical_path!r} tem de ser relativo à raiz do repositório, sem '..'")
    canonical = path.as_posix()
    if canonical in ("", "."):
        raise ValueError("caminho vazio")
    return canonical


def source_id(logical_path: str) -> str:
    """A identidade da fonte é o caminho lógico. O hash do conteúdo marca a versão."""
    return stable_id("src", canonical_path(logical_path))


def chunk_id(source: str, text: str, occurrence: int) -> str:
    """Chunk inalterado mantém o identificador quando outro trecho do documento muda."""
    return stable_id("chk", source, sha256_text(text), str(occurrence))


def requirement_id(source: str, chunk: str, statement: str) -> str:
    """Calculado uma vez, na primeira gravação. O refinamento mantém o identificador."""
    return stable_id("req", source, chunk, normalize_name(statement))


def actor_id(name: str) -> str:
    return stable_id("act", normalize_name(name))


def component_id(name: str) -> str:
    return stable_id("cmp", normalize_name(name))


def entity_id(name: str, entity_type: str) -> str:
    return stable_id("ent", normalize_name(name), normalize_name(entity_type))


def quality_attribute_id(category: QualityCategory) -> str:
    return f"qa-{category.value}"


def relation_id(relation: RelationType, source: str, target: str) -> str:
    if relation in SYMMETRIC_RELATIONS:
        source, target = sorted((source, target))
    return stable_id("rel", relation.value, source, target)
