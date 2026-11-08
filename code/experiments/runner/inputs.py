"""Entradas de uma corrida: casos da amostra estruturada e itens do PROMISE.

Um caso é um documento de um conjunto de ingestão. Os chunks do caso são os chunks do documento,
e o corpus contra o qual as regras e a gravação conferem a evidência é esse mesmo conjunto de
chunks: o modelo só viu esses trechos na extração do caso.
"""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from domain.config import ChunkingConfig
from domain.models import SourceChunk, SourceDocument
from domain.rules import CorpusIndex
from ingestion.corpus import IngestedSet, ingest, render
from ingestion.corpus import load as load_ingested
from retrieval.promise import (
    PROMISE_JSONL,
    PromiseItem,
    PromiseProject,
    load_projects,
    load_promise_items,
    promise_order_key,
)


class InputError(ValueError):
    pass


@dataclass(frozen=True)
class Case:
    document: SourceDocument
    chunks: tuple[SourceChunk, ...]

    @property
    def case_id(self) -> str:
        return self.document.source_id

    @property
    def corpus(self) -> CorpusIndex:
        return CorpusIndex.from_chunks(self.chunks)


@dataclass(frozen=True)
class StructuralInput:
    sets: tuple[IngestedSet, ...]
    sha256: tuple[str, ...]

    @property
    def documents(self) -> list[SourceDocument]:
        return [d for s in self.sets for d in s.documents]

    @property
    def chunks(self) -> list[SourceChunk]:
        return [c for s in self.sets for c in s.chunks]

    @property
    def sources(self) -> frozenset[str]:
        return frozenset(d.source_id for d in self.documents)

    @property
    def cases(self) -> list[Case]:
        cases = [Case(d, tuple(s.chunks_of(d.source_id))) for s in self.sets for d in s.documents]
        return sorted(cases, key=lambda c: c.case_id)


def load_structural(paths: list[Path], chunking: ChunkingConfig) -> StructuralInput:
    """Arquivo de conjunto (.toml, ingerido agora) ou saída da ingestão (.json, conferida contra a configuração)."""
    sets, hashes, seen = [], [], {}
    for path in paths:
        path = Path(path)
        if path.suffix == ".toml":
            ingested = ingest(path, chunking)
        elif path.suffix == ".json":
            ingested = load_ingested(path)
            if ingested.chunking != chunking:
                raise InputError(f"{path}: ingerido com {ingested.chunking.model_dump()}, e a configuração pede "
                                 f"{chunking.model_dump()}. Rode a ingestão de novo")
        else:
            raise InputError(f"{path}: conjunto de ingestão é .toml ou .json")
        for document in ingested.documents:
            if document.source_id in seen:
                raise InputError(f"{document.path} aparece em {seen[document.source_id]} e em {path}")
            seen[document.source_id] = path
        sets.append(ingested)
        hashes.append(hashlib.sha256(render(ingested)).hexdigest())
    return StructuralInput(tuple(sets), tuple(hashes))


@dataclass(frozen=True)
class PromiseInput:
    """Projetos inteiros (o grafo de B usa todos os requisitos do projeto) e os itens escolhidos.

    filters: --promise-projects, --promise-items e --promise-limit normalizados, que entram na seleção."""

    path: Path
    sha256: str
    projects: tuple[PromiseProject, ...]
    items: dict[int, tuple[PromiseItem, ...]]
    filters: dict[str, object] = field(default_factory=dict)

    def count(self) -> int:
        return sum(len(v) for v in self.items.values())

    def selection(self) -> dict[str, object]:
        return {"filters": self.filters,
                "items": {str(p): [i.promise_id for i in v] for p, v in sorted(self.items.items())}}


def _ids(text: str | None) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()] if text else []


def sample_spread(items: list[PromiseItem], limit: int, seed: int) -> list[PromiseItem]:
    """limit itens sorteados com a semente, um projeto por vez: cada projeto (em ordem de sha256(seed:project-NN))
    entrega o próximo item na ordem de promise_order_key antes de algum projeto entregar mais um."""
    queues: dict[int, list[PromiseItem]] = {}
    for item in sorted(items, key=lambda i: promise_order_key(seed, i.promise_id)):
        queues.setdefault(item.project_id, []).append(item)
    order = sorted(queues, key=lambda p: promise_order_key(seed, f"project-{p:02d}"))
    chosen: list[PromiseItem] = []
    for depth in range(max(len(q) for q in queues.values())):
        for project in order:
            if depth < len(queues[project]) and len(chosen) < limit:
                chosen.append(queues[project][depth])
    return chosen


def load_promise(chunking: ChunkingConfig, seed: int, path: Path = PROMISE_JSONL, *, projects: str | None = None,
                 items: str | None = None, limit: int | None = None) -> PromiseInput:
    """projects e items são listas separadas por vírgula. limit sorteia, com a semente, no máximo limit itens
    no total, espalhados pelos projetos que passaram no filtro (sample_spread)."""
    path = Path(path)
    if not path.is_file():
        raise InputError(f"{path}: arquivo do PROMISE não encontrado")
    every = load_promise_items(path)
    by_id = {i.promise_id: i for i in every}
    wanted_items = _ids(items)
    unknown = sorted(set(wanted_items) - set(by_id))
    if unknown:
        raise InputError(f"--promise-items: {unknown} não estão em {path}")
    try:
        wanted_projects = {int(p) for p in _ids(projects)}
    except ValueError:
        raise InputError(f"--promise-projects: {projects!r} não é uma lista de números") from None
    unknown_projects = sorted(wanted_projects - {i.project_id for i in every})
    if unknown_projects:
        raise InputError(f"--promise-projects: {unknown_projects} não estão em {path}")
    if limit is not None and limit < 1:
        raise InputError("--promise-limit tem de ser pelo menos 1")

    chosen = [i for i in every if (not wanted_items or i.promise_id in wanted_items)
              and (not wanted_projects or i.project_id in wanted_projects)]
    if not chosen:
        raise InputError("o filtro do PROMISE não deixou nenhum item")
    if limit is not None:
        chosen = sample_spread(chosen, limit, seed)
    selected: dict[int, list[PromiseItem]] = {}
    for item in sorted(chosen, key=lambda i: i.promise_id):
        selected.setdefault(item.project_id, []).append(item)
    built = load_projects(chunking, seed, path)
    return PromiseInput(
        path=path,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        projects=tuple(built[p] for p in sorted(selected)),
        items={p: tuple(v) for p, v in sorted(selected.items())},
        filters={"projects": sorted(wanted_projects), "items": sorted(set(wanted_items)), "limit": limit},
    )
