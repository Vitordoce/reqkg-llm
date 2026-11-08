"""PROMISE NFR como conjunto de ingestão: um documento por projeto, um requisito por chunk, sem rótulo.

O documento de um projeto é a lista dos textos do projeto, separados por linha em branco, na ordem
de sha256(f"{seed}:{promise_id}"), com seed = evaluation.seed. O arquivo publicado vem ordenado por
rótulo dentro do projeto, e na ordem de promise_id os vizinhos de uma chamada de extração diriam o
rótulo do item. Com chunking.strategy = "paragraph", cada texto vira exatamente um chunk, e o
construtor confere isso. O rótulo nunca é lido do arquivo (decisão do autor de 10 de outubro: o
grafo de B tem só o texto dos outros requisitos do projeto).

O caminho lógico do documento é o do arquivo JSONL seguido de "#project-NN". Ele não existe no
disco: o documento é uma vista sobre o JSONL, e o SHA-256 dos bytes do JSONL vai em set_sha256.
"""

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from domain import ids
from domain.config import ChunkingConfig, ExperimentConfig
from domain.enums import SourceKind
from domain.llm_io import ExtractionOutput, RelationCandidate
from domain.models import SourceChunk, SourceDocument
from domain.persist import PersistBatch, to_records
from domain.rules import CorpusIndex
from domain.rules import normalize_text as normalize_rule_text
from extraction.client import CallLog, LLMClient
from extraction.pipeline import ExtractionRun, extract_case
from graph.connection import Graph
from graph.writer import write_batch, write_documents
from ingestion.chunking import chunk_text, normalize_text
from ingestion.corpus import INGESTION_VERSION, IngestedSet

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMISE_JSONL = REPO_ROOT / "data" / "processed" / "promise" / "promise_nfr.jsonl"
PROMISE_ID = re.compile(r"^PROMISE-NFR-\d{4}$")
PROMISE_KIND = SourceKind.BUSINESS_DOCUMENT


class PromiseError(ValueError):
    pass


@dataclass(frozen=True)
class PromiseItem:
    """Um requisito do PROMISE sem rótulo. O rótulo fica no arquivo e só a avaliação o lê."""

    promise_id: str
    project_id: int
    text: str


@dataclass(frozen=True)
class PromiseProject:
    project_id: int
    ingested: IngestedSet
    promise_ids: tuple[str, ...]

    @property
    def document(self) -> SourceDocument:
        return self.ingested.documents[0]

    @property
    def chunks(self) -> list[SourceChunk]:
        return self.ingested.chunks

    def chunk_of(self, promise_id: str) -> SourceChunk:
        try:
            return self.chunks[self.promise_ids.index(promise_id)]
        except ValueError:
            raise PromiseError(f"{promise_id} não pertence ao projeto {self.project_id}") from None

    def promise_of_chunk(self) -> dict[str, str]:
        return {chunk.chunk_id: promise_id for chunk, promise_id in zip(self.chunks, self.promise_ids)}

    def same_text_chunks(self, promise_id: str) -> frozenset[str]:
        """O chunk do item e os de outros itens com o mesmo texto (domain.rules.normalize_text), como as
        duplicatas do PROMISE. Nenhum deles entra no contexto do item."""
        own = normalize_rule_text(self.chunk_of(promise_id).text)
        return frozenset(c.chunk_id for c in self.chunks if normalize_rule_text(c.text) == own)


def promise_order_key(seed: int, promise_id: str) -> str:
    return hashlib.sha256(f"{seed}:{promise_id}".encode("utf-8")).hexdigest()


def load_promise_items(path: Path = PROMISE_JSONL) -> list[PromiseItem]:
    """Lê promise_id, project_id e text de cada linha. label, label_name e is_functional ficam de fora."""
    items = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            item = PromiseItem(str(data["promise_id"]), int(data["project_id"]), str(data["text"]))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise PromiseError(f"{path}: linha {number}: {error}") from None
        if not PROMISE_ID.fullmatch(item.promise_id):
            raise PromiseError(f"{path}: linha {number}: promise_id {item.promise_id!r} fora do formato PROMISE-NFR-NNNN")
        items.append(item)
    return items


def _logical_path(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        raise PromiseError(f"{path}: o arquivo do PROMISE tem de ficar dentro de {REPO_ROOT}") from None


def build_project(items: Iterable[PromiseItem], project_id: int, *, origin: str, origin_sha256: str,
                  chunking: ChunkingConfig, seed: int) -> PromiseProject:
    """origin é o caminho do JSONL relativo à raiz, origin_sha256 o SHA-256 dos bytes dele, seed a evaluation.seed."""
    if chunking.strategy != "paragraph":
        raise PromiseError("o PROMISE precisa de chunking.strategy = 'paragraph' para ter um requisito por chunk")
    chosen = sorted((i for i in items if i.project_id == project_id),
                    key=lambda i: (promise_order_key(seed, i.promise_id), i.promise_id))
    if not chosen:
        raise PromiseError(f"projeto {project_id} sem requisitos")
    if len({i.promise_id for i in chosen}) != len(chosen):
        raise PromiseError(f"projeto {project_id}: promise_id repetido")
    texts = [normalize_text(i.text) for i in chosen]
    path = ids.canonical_path(f"{origin}#project-{project_id:02d}")
    source = ids.source_id(path)
    text = "\n\n".join(texts)
    chunks = chunk_text(text, source, chunking)
    if [c.text for c in chunks] != texts:
        raise PromiseError(f"projeto {project_id}: os textos não viram um chunk cada "
                           f"({len(chunks)} chunks para {len(texts)} requisitos). Texto vazio, com linha "
                           f"em branco ou maior que chunking.size_chars ({chunking.size_chars})")
    document = SourceDocument(source_id=source, path=path, sha256=ids.sha256_text(text), kind=PROMISE_KIND,
                              title=f"PROMISE NFR, projeto {project_id}", char_count=len(text))
    ingested = IngestedSet(ingestion_version=INGESTION_VERSION, set_path=origin, set_sha256=origin_sha256,
                           chunking=chunking, documents=[document], chunks=chunks)
    return PromiseProject(project_id, ingested, tuple(i.promise_id for i in chosen))


def load_projects(chunking: ChunkingConfig, seed: int, path: Path = PROMISE_JSONL) -> dict[int, PromiseProject]:
    items = load_promise_items(path)
    origin = _logical_path(path)
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return {project: build_project(items, project, origin=origin, origin_sha256=digest, chunking=chunking, seed=seed)
            for project in sorted({i.project_id for i in items})}


def case_id(project: PromiseProject) -> str:
    return f"promise-project-{project.project_id:02d}"


def extract_project(project: PromiseProject, *, run_index: int, config: ExperimentConfig, client: LLMClient,
                    log: CallLog) -> ExtractionRun:
    """Uma extração por projeto, com o mesmo agrupamento de chunks da amostra anotada."""
    return extract_case(case_id=case_id(project), run_index=run_index, chunks=project.chunks, config=config,
                        client=client, log=log)


def split_by_call(output: ExtractionOutput) -> list[tuple[str, ExtractionOutput]]:
    """Desfaz merge_outputs: uma resposta por prefixo de chamada, com as chaves ainda prefixadas."""
    prefix_of = lambda key: key.split("-", 1)[0]  # noqa: E731
    prefixes = sorted({prefix_of(item.key) for name in ("requirements", "actors", "components", "entities")
                       for item in getattr(output, name)}, key=lambda p: (len(p), p))
    parts = []
    for prefix in prefixes:
        keep = lambda item: prefix_of(item.key) == prefix  # noqa: E731
        relations: list[RelationCandidate] = [r for r in output.relations if prefix_of(r.source_key) == prefix]
        parts.append((prefix, ExtractionOutput(
            requirements=[i for i in output.requirements if keep(i)], actors=[i for i in output.actors if keep(i)],
            components=[i for i in output.components if keep(i)], entities=[i for i in output.entities if keep(i)],
            relations=relations)))
    return parts


def write_project_graph(graph: Graph, project: PromiseProject, run: ExtractionRun,
                        confidence_threshold: float) -> list[PersistBatch]:
    """Grava o documento, os chunks e a extração do projeto, um lote por chamada de extração.

    domain.persist.to_records guarda só a evidência da primeira ocorrência de um ator, componente
    ou entidade com o mesmo nome. Gravar cada chamada num lote próprio deixa write_batch unir a
    evidência das chamadas (regra de união entre lotes), e as arestas MENTIONS de todas as
    chamadas chegam ao grafo.
    """
    if run.result.extraction is None:
        raise PromiseError(f"projeto {project.project_id}: extração sem saída ({run.result.status.value}: "
                           f"{run.result.error})")
    corpus = CorpusIndex.from_chunks(project.chunks)
    write_documents(graph, [project.document], project.chunks)
    batches = []
    for _, part in split_by_call(run.result.extraction):
        batch = to_records(part, corpus, confidence_threshold)
        write_batch(graph, batch)
        batches.append(batch)
    return batches
