"""Entradas dos cenários gravados. Os testes e build_replays.py montam os prompts por aqui.

Todo texto é sintético: a entrevista de code/domain/fixtures/corpus/, a ata de corpus/ e as frases
de classification_items.json. O contexto de grafo é escrito à mão no formato RetrievedContext,
porque a recuperação real é de code/retrieval/.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from domain import ids
from domain.config import ExperimentConfig
from domain.enums import ContextStrategy
from domain.fixtures.build import chunk_paragraphs
from domain.llm_io import ClassificationOutput, ContextItem, ExtractionOutput, RetrievedContext, merge_outputs
from domain.models import SourceChunk
from domain.persist import to_records
from domain.rules import CorpusIndex
from domain.serialization import load_json, load_toml, parse
from extraction import prompts
from extraction.client import REPO_ROOT, response_text
from extraction.pipeline import ClassificationItem, call_prefix, empty_context, group_chunks, refinement_reasons

HERE = Path(__file__).resolve().parent
RESPONSES = HERE / "responses"
CONFIG_PATH = REPO_ROOT / "code" / "experiments" / "config" / "experiment.toml"
ENTREVISTA_CHUNKS = REPO_ROOT / "code" / "domain" / "fixtures" / "valid" / "source_chunks.json"
ATA_PATH = "code/extraction/fixtures/corpus/ata_sintetica.txt"
ITEMS_PATH = "code/extraction/fixtures/classification_items.json"

ENTREVISTA_PER_CALL = 2
AGENDA_KEY = "c1-R2"
REFINED_ITEM = "PROMISE-NFR-9002"


def config() -> ExperimentConfig:
    return load_toml(CONFIG_PATH, ExperimentConfig)


def config_with(chunks_per_call: int) -> ExperimentConfig:
    """A configuração congelada com outro agrupamento de chunks, só para os cenários de teste."""
    base = config()
    extraction = base.extraction.model_copy(update={"chunks_per_call": chunks_per_call})
    return base.model_copy(update={"extraction": extraction})


def entrevista_chunks() -> list[SourceChunk]:
    return load_json(ENTREVISTA_CHUNKS, list[SourceChunk])


def ata_chunks() -> list[SourceChunk]:
    text = (REPO_ROOT / ATA_PATH).read_text(encoding="utf-8")
    return parse(chunk_paragraphs(text, ids.source_id(ATA_PATH)), list[SourceChunk], ATA_PATH)


def recorded(name: str, model: type):
    data = json.loads((RESPONSES / f"{name}.json").read_text(encoding="utf-8"))
    return parse(json.loads(response_text(data)), model, name)


def entrevista_extraction() -> ExtractionOutput:
    """A união que extract_case tem de produzir com ENTREVISTA_PER_CALL chunks por chamada."""
    return merge_outputs([
        (call_prefix(0), recorded("extracao_entrevista_c0", ExtractionOutput)),
        (call_prefix(1), recorded("extracao_entrevista_c1", ExtractionOutput)),
    ])


def entrevista_corpus() -> CorpusIndex:
    return CorpusIndex.from_chunks(entrevista_chunks())


def agenda_candidate():
    return next(r for r in entrevista_extraction().requirements if r.key == AGENDA_KEY)


def agenda_reasons() -> list[str]:
    return refinement_reasons(entrevista_extraction(), entrevista_corpus(), AGENDA_KEY,
                              config().review.confidence_threshold)


def agenda_source_context() -> RetrievedContext:
    """Os chunks da chamada c1, como source_chunks_context devolve para a condição LLM-only."""
    group = group_chunks(entrevista_chunks(), ENTREVISTA_PER_CALL)[1]
    items = [ContextItem(item_id=c.chunk_id, kind="source_chunk", rank=rank, text=c.text,
                         source_id=c.source_id, chunk_id=c.chunk_id) for rank, c in enumerate(group)]
    return RetrievedContext(query=f"refinar {AGENDA_KEY}", strategy=ContextStrategy.SOURCE_CHUNKS,
                            limit=len(items), items=items)


def agenda_graph_context() -> RetrievedContext:
    """Subgrafo local escrito à mão: o próprio requisito, o chunk, o ator e um vizinho."""
    output = entrevista_extraction()
    batch = to_records(output, entrevista_corpus(), config().review.confidence_threshold)
    key_to_id = batch.key_to_id
    chunk = next(c for c in entrevista_chunks() if c.chunk_id == agenda_candidate().evidence[0].chunk_id)
    by_key = {r.key: r for r in output.requirements}
    raw = [
        (0, key_to_id[AGENDA_KEY], "requirement", by_key[AGENDA_KEY].statement),
        (1, chunk.chunk_id, "source_chunk", chunk.text),
        (1, key_to_id["c1-A1"], "actor", "Técnico"),
        (2, key_to_id["c1-R1"], "requirement", by_key["c1-R1"].statement),
    ]
    items = [ContextItem(item_id=item_id, kind=kind, rank=rank, text=text,
                         source_id=chunk.source_id, chunk_id=chunk.chunk_id)
             for rank, item_id, kind, text in sorted(raw, key=lambda r: (r[0], r[1]))]
    return RetrievedContext(query=f"completar {key_to_id[AGENDA_KEY]}", strategy=ContextStrategy.GRAPH_LOCAL,
                            limit=config().retrieval.max_items, items=items)


def classification_data() -> dict:
    return json.loads((REPO_ROOT / ITEMS_PATH).read_text(encoding="utf-8"))


def classification_items() -> dict[str, ClassificationItem]:
    return {i["promise_id"]: ClassificationItem(i["promise_id"], i["text"]) for i in classification_data()["items"]}


def project_context(promise_id: str) -> RetrievedContext:
    """Os outros itens do projeto sintético, sem rótulo e sem o item avaliado."""
    source = ids.source_id(ITEMS_PATH)
    items = [ContextItem(item_id=i.promise_id, kind="requirement", rank=0, text=i.text, source_id=source,
                         chunk_id=ids.chunk_id(source, i.text, 0))
             for i in sorted(classification_items().values(), key=lambda i: i.promise_id) if i.promise_id != promise_id]
    return RetrievedContext(query=f"classificar {promise_id}", strategy=ContextStrategy.GRAPH_LOCAL,
                            limit=config().retrieval.max_items, items=items)


def first_classification(promise_id: str) -> ClassificationOutput:
    return recorded(f"classificacao_{promise_id[-4:]}", ClassificationOutput)


@dataclass(frozen=True)
class Scenario:
    name: str
    build: Callable[[], prompts.RenderedPrompt]


def _extraction(chunks: Callable[[], list[SourceChunk]], per_call: int, group: int) -> Callable[[], prompts.RenderedPrompt]:
    return lambda: prompts.extraction_prompt(group_chunks(chunks(), per_call)[group])


def _classification(promise_id: str) -> Callable[[], prompts.RenderedPrompt]:
    return lambda: prompts.classification_prompt(promise_id, classification_items()[promise_id].text)


def _classification_refinement(promise_id: str, context: Callable[[], RetrievedContext]) -> Callable[[], prompts.RenderedPrompt]:
    item = lambda: classification_items()[promise_id]  # noqa: E731
    return lambda: prompts.classification_refinement_prompt(
        promise_id, item().text, first_classification(promise_id), context())


SCENARIOS = (
    Scenario("extracao_entrevista_c0", _extraction(entrevista_chunks, ENTREVISTA_PER_CALL, 0)),
    Scenario("extracao_entrevista_c1", _extraction(entrevista_chunks, ENTREVISTA_PER_CALL, 1)),
    Scenario("extracao_entrevista_invalida", _extraction(entrevista_chunks, 4, 0)),
    Scenario("extracao_ata_inventada", _extraction(ata_chunks, 3, 0)),
    Scenario("refino_agenda_llm_only",
             lambda: prompts.refinement_prompt(agenda_candidate(), agenda_source_context(), agenda_reasons())),
    Scenario("refino_agenda_reqkg_inventado",
             lambda: prompts.refinement_prompt(agenda_candidate(), agenda_graph_context(), agenda_reasons())),
    Scenario("classificacao_9001", _classification("PROMISE-NFR-9001")),
    Scenario("classificacao_9002", _classification(REFINED_ITEM)),
    Scenario("refino_classificacao_9002_llm_only",
             _classification_refinement(REFINED_ITEM, lambda: empty_context(f"classificar {REFINED_ITEM}"))),
    Scenario("refino_classificacao_9002_reqkg",
             _classification_refinement(REFINED_ITEM, lambda: project_context(REFINED_ITEM))),
)
