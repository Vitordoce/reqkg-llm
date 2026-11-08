"""A interface única da recuperação: retrieve_context, chamada pelo experimento nas duas condições.

LLM-only (source_chunks): os chunks da chamada de extração em que o candidato nasceu. Não lê o
Neo4j. No PROMISE, os outros itens da chamada de extração do item, como texto, com item_id igual
ao promise_id (decisão do autor de 11 de outubro).

REQKG-grounded (graph_local): o subgrafo local do Neo4j, até retrieval.max_hops saltos e
retrieval.max_items itens (retrieval.local). Semente: o nó do requisito, se existir, e sempre os
chunks da chamada de extração, para que o contexto de B contenha o de A em todo alvo (decisão do
autor de 11 de outubro). No PROMISE, sem atributos de qualidade e sem ator, componente ou entidade
com evidência no chunk do item.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from domain.config import ExperimentConfig
from domain.enums import CONTEXT_FOR_CONDITION, Condition, ContextStrategy, NodeKind
from domain.llm_io import ContextItem, RetrievedContext
from domain.models import SourceChunk
from extraction.pipeline import group_chunks
from graph.connection import Graph
from retrieval.local import RequirementChunk, RetrievalError, View, local_context
from retrieval.promise import PromiseProject

CALL_KEY = re.compile(r"^c(\d+)-")


@dataclass(frozen=True)
class CandidateTarget:
    """Um candidato da extração de um caso, escolhido por domain.rules.refinement_targets.

    key: a chave unida por merge_outputs, com o prefixo da chamada ("c0-R4").
    case_chunks: os chunks enviados à extração do caso, os mesmos de extraction.pipeline.extract_case.
    requirement_id: o nó do candidato no grafo (PersistBatch.key_to_id), ou None se a gravação o recusou.
    sources: se dado, a recuperação só usa evidência e chunks dessas fontes.
    """

    key: str
    case_chunks: tuple[SourceChunk, ...]
    requirement_id: str | None = None
    sources: frozenset[str] | None = None


@dataclass(frozen=True)
class PromiseTarget:
    """Um item do PROMISE a classificar. O projeto vem de retrieval.promise.build_project."""

    promise_id: str
    project: PromiseProject


Target = CandidateTarget | PromiseTarget


def extraction_call(key: str, chunks: Sequence[SourceChunk], chunks_per_call: int) -> list[SourceChunk]:
    """Os chunks da chamada de extração cujo prefixo está na chave, pelo agrupamento de extract_case."""
    match = CALL_KEY.match(key)
    if match is None:
        raise RetrievalError(f"{key!r} não começa por um prefixo de chamada (c0-, c1-, ...)")
    groups = group_chunks(chunks, chunks_per_call)
    index = int(match.group(1))
    if index >= len(groups):
        raise RetrievalError(f"{key!r}: o caso tem {len(groups)} chamada(s) de extração com "
                             f"chunks_per_call = {chunks_per_call}")
    return groups[index]


def extraction_call_of_chunk(chunk: SourceChunk, chunks: Sequence[SourceChunk], chunks_per_call: int) -> list[SourceChunk]:
    for group in group_chunks(chunks, chunks_per_call):
        if any(c.chunk_id == chunk.chunk_id for c in group):
            return group
    raise RetrievalError(f"{chunk.chunk_id} não está nos chunks do caso")


def source_chunks_context(key: str, chunks: Sequence[SourceChunk], chunks_per_call: int) -> RetrievedContext:
    """Igual a extraction.pipeline.source_chunks_context, sem precisar do ExtractionRun."""
    group = extraction_call(key, chunks, chunks_per_call)
    items = [ContextItem(item_id=c.chunk_id, kind="source_chunk", rank=rank, text=c.text,
                         source_id=c.source_id, chunk_id=c.chunk_id) for rank, c in enumerate(group)]
    return RetrievedContext(query=f"refinar {key}", strategy=ContextStrategy.SOURCE_CHUNKS,
                            limit=max(1, len(items)), items=items)


def _candidate_graph_context(target: CandidateTarget, config: ExperimentConfig, graph: Graph) -> RetrievedContext:
    call = extraction_call(target.key, target.case_chunks, config.extraction.chunks_per_call)
    context, seed = local_context(
        graph, query=f"refinar {target.key}", max_items=config.retrieval.max_items,
        max_hops=config.retrieval.max_hops, seed_requirement=target.requirement_id,
        seed_chunks=[c.chunk_id for c in call], view=View(sources=target.sources))
    chunks = f"chunks da chamada {target.key.split('-', 1)[0]}"
    origin = f"{target.requirement_id} e dos {chunks}" if seed == "requirement" else f"{chunks} (sem nó)"
    return context.model_copy(update={"query": f"refinar {target.key} a partir de {origin}"})


def _promise_call(target: PromiseTarget, config: ExperimentConfig) -> list[SourceChunk]:
    """Os outros chunks da chamada de extração do item, sem o dele nem os de texto igual ao dele."""
    project = target.project
    hidden = project.same_text_chunks(target.promise_id)
    own = project.chunk_of(target.promise_id)
    return [c for c in extraction_call_of_chunk(own, project.chunks, config.extraction.chunks_per_call)
            if c.chunk_id not in hidden]


def _promise_source_context(target: PromiseTarget, config: ExperimentConfig) -> RetrievedContext:
    """Os mesmos itens que a semente de B vira: requisito com o promise_id e o texto do chunk, rank 0."""
    promise_of = target.project.promise_of_chunk()
    items = sorted((ContextItem(item_id=promise_of[c.chunk_id], kind=NodeKind.REQUIREMENT, rank=0, text=c.text,
                                source_id=c.source_id, chunk_id=c.chunk_id) for c in _promise_call(target, config)),
                   key=lambda i: i.item_id)
    return RetrievedContext(query=f"classificar {target.promise_id}", strategy=ContextStrategy.SOURCE_CHUNKS,
                            limit=max(1, len(items)), items=items)


def _promise_graph_context(target: PromiseTarget, config: ExperimentConfig, graph: Graph) -> RetrievedContext:
    """O grafo do projeto sem o item: o chunk do item (e de cópias dele) fica fora da vista, como se tivesse
    sido invalidado. Ator, componente e entidade com evidência nesse chunk saem inteiros, e os atributos de
    qualidade (categorias ISO inferidas, parecidas com os rótulos) não entram.

    Na vista sem o item, ele não tem nó, e a semente são os outros chunks da chamada de extração dele.
    """
    project = target.project
    hidden = project.same_text_chunks(target.promise_id)
    call = _promise_call(target, config)
    query = f"classificar {target.promise_id}"
    if not call:
        return RetrievedContext(query=query, strategy=ContextStrategy.GRAPH_LOCAL,
                                limit=config.retrieval.max_items, items=[])
    by_chunk = {c.chunk_id: c for c in project.chunks}
    aliases = {chunk_id: RequirementChunk(promise_id, by_chunk[chunk_id].text)
               for chunk_id, promise_id in project.promise_of_chunk().items() if chunk_id not in hidden}
    context, _ = local_context(
        graph, query=query, max_items=config.retrieval.max_items, max_hops=config.retrieval.max_hops,
        seed_chunks=[c.chunk_id for c in call],
        view=View(excluded_chunks=hidden, sources=frozenset({project.document.source_id}), tainted_chunks=hidden,
                  quality_attributes=False),
        requirement_chunks=aliases)
    return context


def retrieve_context(
    target: Target,
    condition: Condition,
    config: ExperimentConfig,
    graph: Graph | None = None,
) -> RetrievedContext:
    """Contexto do refinamento de target na condição dada.

    LLM-only nunca lê graph, então o experimento pode passar o mesmo graph nas duas condições.
    REQKG-grounded exige graph com os documentos e a extração do caso já gravados.
    """
    strategy = CONTEXT_FOR_CONDITION[condition]
    if strategy is ContextStrategy.SOURCE_CHUNKS:
        if isinstance(target, PromiseTarget):
            return _promise_source_context(target, config)
        return source_chunks_context(target.key, target.case_chunks, config.extraction.chunks_per_call)
    if graph is None:
        raise RetrievalError(f"{condition.value} precisa do grafo (graph=None)")
    if isinstance(target, PromiseTarget):
        return _promise_graph_context(target, config, graph)
    return _candidate_graph_context(target, config, graph)
