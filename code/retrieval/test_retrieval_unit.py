"""Testes sem Neo4j: source_chunks, seleção e ordem, vista, e o construtor do PROMISE."""

import hashlib
import itertools
import json
from collections import Counter
from pathlib import Path

import pytest

from domain.config import ChunkingConfig, ExperimentConfig
from domain.enums import Condition, ContextStrategy, NodeKind, PromiseLabel, RunStatus, SourceKind
from domain.llm_io import CaseResult, ClassificationOutput, ContextItem, ExtractionOutput, RetrievedContext
from domain.models import Evidence
from domain.serialization import canonical_json, load_toml
from extraction.client import CallLog
from extraction.pipeline import ExtractionRun, group_chunks
from extraction.pipeline import source_chunks_context as extraction_source_chunks
from graph.fixture import load_fixture
from graph.properties import encode_evidence
from retrieval import CandidateTarget, PromiseTarget, RetrievalError, retrieve_context
from retrieval.context import source_chunks_context
from retrieval.fixtures import PROMISE_JSONL, SyntheticExtractionClient
from retrieval.local import View, node_in_view, select
from retrieval.promise import (
    PromiseError,
    PromiseItem,
    build_project,
    extract_project,
    load_projects,
    load_promise_items,
    promise_order_key,
    split_by_call,
)

ROOT = Path(__file__).resolve().parents[2]
CONFIG = load_toml(ROOT / "code" / "experiments" / "config" / "experiment.toml", ExperimentConfig)
FIXTURE = load_fixture()
CHUNKS = tuple(FIXTURE.chunks)
ORIGIN = "code/retrieval/fixtures/promise_sintetico.jsonl"
ORIGIN_SHA = hashlib.sha256(PROMISE_JSONL.read_bytes()).hexdigest()


def config(chunks_per_call: int | None = None, max_items: int | None = None) -> ExperimentConfig:
    extraction = CONFIG.extraction.model_copy(update={"chunks_per_call": chunks_per_call or CONFIG.extraction.chunks_per_call})
    retrieval = CONFIG.retrieval.model_copy(update={"max_items": max_items or CONFIG.retrieval.max_items})
    return CONFIG.model_copy(update={"extraction": extraction, "retrieval": retrieval})


SEED = CONFIG.evaluation.seed


def project(project_id: int = 98, chunking: ChunkingConfig = CONFIG.chunking, items=None):
    return build_project(items or load_promise_items(PROMISE_JSONL), project_id, origin=ORIGIN,
                         origin_sha256=ORIGIN_SHA, chunking=chunking, seed=SEED)


class Untouchable:
    def __getattr__(self, name):
        raise AssertionError(f"LLM-only leu o grafo ({name})")


# source_chunks


def test_source_chunks_is_the_extraction_call_of_the_candidate():
    context = retrieve_context(CandidateTarget("c1-R2", CHUNKS), Condition.LLM_ONLY, config(chunks_per_call=2),
                               graph=Untouchable())
    second_call = group_chunks(CHUNKS, 2)[1]
    assert context.strategy is ContextStrategy.SOURCE_CHUNKS
    assert [(i.rank, i.item_id) for i in context.items] == [(r, c.chunk_id) for r, c in enumerate(second_call)]
    assert all(i.kind == NodeKind.SOURCE_CHUNK and i.chunk_id == i.item_id for i in context.items)
    assert [i.text for i in context.items] == [c.text for c in second_call]


def test_source_chunks_matches_the_extraction_package():
    calls = {f"c{i}": tuple(c.chunk_id for c in g) for i, g in enumerate(group_chunks(CHUNKS, 2))}
    run = ExtractionRun(CaseResult(case_id="caso", run_index=0, stage="extraction", status=RunStatus.OK,
                                   extraction=ExtractionOutput()), calls)
    for key in ("c0-R1", "c1-R4"):
        assert source_chunks_context(key, CHUNKS, 2) == extraction_source_chunks(run, key, CHUNKS)


def test_source_chunks_ignores_the_order_the_chunks_arrive_in():
    shuffled = tuple(reversed(CHUNKS))
    assert source_chunks_context("c0-R1", shuffled, 3) == source_chunks_context("c0-R1", CHUNKS, 3)


@pytest.mark.parametrize("key", ["R2", "x0-R2", "c9-R2"])
def test_source_chunks_refuses_a_key_without_a_valid_call(key):
    with pytest.raises(RetrievalError):
        source_chunks_context(key, CHUNKS, 2)


def test_llm_only_promise_context_is_the_rest_of_the_extraction_call_and_never_reads_the_graph():
    built = project()
    three = config(chunks_per_call=3)
    for x in built.promise_ids:
        context = retrieve_context(PromiseTarget(x, built), Condition.LLM_ONLY, three, graph=Untouchable())
        call = next(g for g in group_chunks(built.chunks, 3) if built.chunk_of(x) in g)
        others = [c for c in call if c.chunk_id != built.chunk_of(x).chunk_id]
        assert context.strategy is ContextStrategy.SOURCE_CHUNKS
        assert sorted((i.item_id, i.text, i.chunk_id) for i in context.items) == sorted(
            (built.promise_of_chunk()[c.chunk_id], c.text, c.chunk_id) for c in others)
        assert all(i.kind == NodeKind.REQUIREMENT and i.rank == 0 for i in context.items)
        assert x not in {i.item_id for i in context.items}
    alone = retrieve_context(PromiseTarget("PROMISE-NFR-9101", project(97)), Condition.LLM_ONLY, CONFIG,
                             graph=Untouchable())
    assert alone.items == [] and alone.limit == 1


def test_promise_context_leaves_out_copies_of_the_item_in_both_conditions():
    items = load_promise_items(PROMISE_JSONL)
    original = next(i for i in items if i.promise_id == "PROMISE-NFR-9001")
    copy = PromiseItem("PROMISE-NFR-9009", 98, "  the system shall ALLOW a technician to book an instrument for a time slot.")
    built = project(items=[*items, copy])
    assert built.same_text_chunks(original.promise_id) == built.same_text_chunks(copy.promise_id)
    assert len(built.same_text_chunks(original.promise_id)) == 2
    one_call = config(chunks_per_call=20)
    for x in (original.promise_id, copy.promise_id):
        context = retrieve_context(PromiseTarget(x, built), Condition.LLM_ONLY, one_call, graph=Untouchable())
        assert {i.item_id for i in context.items} == set(built.promise_ids) - {original.promise_id, copy.promise_id}
        first = ClassificationOutput(promise_id=x, label=PromiseLabel.F)
        assert first.check_against(context, first, original.text) == []


def test_grounded_condition_needs_the_graph():
    with pytest.raises(RetrievalError, match="precisa do grafo"):
        retrieve_context(CandidateTarget("c0-R1", CHUNKS), Condition.REQKG_GROUNDED, CONFIG)


# seleção e ordem


def item(item_id: str, kind, rank: int) -> ContextItem:
    chunk = CHUNKS[1]
    return ContextItem(item_id=item_id, kind=kind, rank=rank, text="t", source_id=chunk.source_id,
                       chunk_id=chunk.chunk_id)


def test_select_keeps_lower_ranks_then_kind_priority_and_returns_contract_order():
    items = [
        item("ent-b", NodeKind.ENTITY, 1), item("act-a", NodeKind.ACTOR, 1), item("req-z", NodeKind.REQUIREMENT, 1),
        item("chk-x", NodeKind.SOURCE_CHUNK, 0), item("rel-q", "relation", 1), item("req-a", NodeKind.REQUIREMENT, 2),
    ]
    chosen = select(items, 4)
    assert [i.item_id for i in chosen] == ["chk-x", "act-a", "rel-q", "req-z"]
    RetrievedContext(query="q", strategy=ContextStrategy.GRAPH_LOCAL, limit=4, items=chosen)
    assert select(list(reversed(items)), 4) == chosen


def test_select_never_passes_the_limit():
    items = [item(f"chk-{n:02d}", NodeKind.SOURCE_CHUNK, n % 3 + 1) for n in range(50)]
    assert len(select(items, 7)) == 7


def test_select_keeps_every_seed_item_or_refuses():
    seeds = [item(f"chk-{n:02d}", NodeKind.SOURCE_CHUNK, 0) for n in range(5)]
    near = [item(f"req-{n:02d}", NodeKind.REQUIREMENT, 1) for n in range(5)]
    assert {i.item_id for i in seeds} <= {i.item_id for i in select([*near, *seeds], 5)}
    with pytest.raises(RetrievalError, match="semente"):
        select([*near, *seeds], 4)


# vista


def requirement_props(evidence: list[Evidence]) -> dict:
    return {"requirement_id": "req-0000000000000001", "statement": "s", "evidence_json": encode_evidence(evidence)}


def test_view_drops_a_requirement_whose_primary_evidence_is_hidden():
    first, second = sorted(CHUNKS[1:3], key=lambda c: c.chunk_id)
    evidence = [Evidence(source_id=c.source_id, chunk_id=c.chunk_id, quote="q") for c in (first, second)]
    props = requirement_props(evidence)
    assert node_in_view("e", ["Requirement"], props, View(excluded_chunks=frozenset({first.chunk_id}))) is None
    kept = node_in_view("e", ["Requirement"], props, View(excluded_chunks=frozenset({second.chunk_id})))
    assert [e.chunk_id for e in kept.evidence] == [first.chunk_id]


def test_view_drops_chunks_and_evidence_of_other_sources():
    chunk = CHUNKS[1]
    props = chunk.model_dump(mode="json")
    assert node_in_view("e", ["SourceChunk"], props, View(sources=frozenset({"src-0000000000000000"}))) is None
    assert node_in_view("e", ["SourceChunk"], props, View(sources=frozenset({chunk.source_id}))) is not None
    assert node_in_view("e", ["SourceDocument"], {"source_id": chunk.source_id}, View()) is None


# PROMISE


def test_promise_builder_makes_one_business_document_per_project_and_one_chunk_per_requirement():
    items = load_promise_items(PROMISE_JSONL)
    built = project()
    assert len(built.ingested.documents) == 1
    assert built.document.kind is SourceKind.BUSINESS_DOCUMENT
    assert built.document.path == f"{ORIGIN}#project-98"
    mine = sorted((i for i in items if i.project_id == 98), key=lambda i: promise_order_key(SEED, i.promise_id))
    assert built.promise_ids == tuple(i.promise_id for i in mine)
    assert [c.text for c in built.chunks] == [i.text for i in mine]
    assert built.chunk_of("PROMISE-NFR-9003").text == next(i.text for i in mine if i.promise_id == "PROMISE-NFR-9003")
    assert project(97).promise_ids == ("PROMISE-NFR-9101",)
    assert project(97).document.source_id != built.document.source_id


def test_promise_builder_never_reads_the_label():
    assert set(vars(load_promise_items(PROMISE_JSONL)[0])) == {"promise_id", "project_id", "text"}
    dumped = canonical_json(project().ingested)
    labels = {json.loads(line)["label_name"] for line in PROMISE_JSONL.read_text(encoding="utf-8").splitlines()}
    assert '"label' not in dumped and not any(name in dumped for name in labels)


def test_promise_builder_is_deterministic():
    assert canonical_json(project().ingested) == canonical_json(project().ingested)


def test_promise_builder_order_comes_from_the_seed_not_from_the_promise_id():
    items = load_promise_items(PROMISE_JSONL)
    built = project()
    assert list(built.promise_ids) != sorted(built.promise_ids)
    other = build_project(items, 98, origin=ORIGIN, origin_sha256=ORIGIN_SHA, chunking=CONFIG.chunking, seed=SEED + 1)
    assert other.promise_ids != built.promise_ids and sorted(other.promise_ids) == sorted(built.promise_ids)


REAL_PROMISE = ROOT / "data" / "processed" / "promise" / "promise_nfr.jsonl"


@pytest.mark.skipif(not REAL_PROMISE.is_file(), reason="data/processed/promise/promise_nfr.jsonl ausente")
def test_real_promise_calls_carry_no_more_label_agreement_than_chance():
    """Só lê os rótulos do arquivo real para medir; nenhum texto do PROMISE sai daqui.

    No arquivo publicado, os itens vêm agrupados por rótulo dentro do projeto. Sem o embaralhamento,
    os vizinhos de chamada concordam no rótulo em 64% dos pares, contra 26% esperados ao acaso.
    """
    labels = {json.loads(line)["promise_id"]: json.loads(line)["label"]
              for line in REAL_PROMISE.read_text(encoding="utf-8").splitlines() if line.strip()}
    per_call = CONFIG.extraction.chunks_per_call
    same = pairs = expected_same = expected_pairs = 0
    for built in load_projects(CONFIG.chunking, SEED, REAL_PROMISE).values():
        promise_of = built.promise_of_chunk()
        for call in group_chunks(built.chunks, per_call):
            ids_in_call = [promise_of[c.chunk_id] for c in call]
            for a, b in itertools.permutations(ids_in_call, 2):
                pairs += 1
                same += labels[a] == labels[b]
        counts = Counter(labels[i] for i in built.promise_ids)
        n = len(built.promise_ids)
        expected_same += sum(k * (k - 1) for k in counts.values())
        expected_pairs += n * (n - 1)
    observed, chance = same / pairs, expected_same / expected_pairs
    assert abs(observed - chance) < 0.04, f"concordância {observed:.3f} contra {chance:.3f} ao acaso"


def test_promise_builder_refuses_what_would_not_be_one_requirement_per_chunk():
    with pytest.raises(PromiseError, match="paragraph"):
        project(chunking=ChunkingConfig(strategy="window", size_chars=1500, overlap_chars=0))
    with pytest.raises(PromiseError, match="um chunk cada"):
        project(chunking=ChunkingConfig(strategy="paragraph", size_chars=40, overlap_chars=0))
    with pytest.raises(PromiseError, match="sem requisitos"):
        project(5)


def test_split_by_call_gives_back_each_extraction_call(tmp_path):
    built = project()
    run = extract_project(built, run_index=0, config=config(chunks_per_call=3),
                          client=SyntheticExtractionClient(built), log=CallLog(tmp_path))
    parts = split_by_call(run.result.extraction)
    assert [p for p, _ in parts] == ["c0", "c1", "c2"]
    merged = run.result.extraction
    for name in ("requirements", "actors", "entities", "relations"):
        assert sum(len(getattr(o, name)) for _, o in parts) == len(getattr(merged, name))
    for prefix, part in parts:
        assert all(r.key.startswith(f"{prefix}-") for r in part.requirements)
        assert {e.chunk_id for r in part.requirements for e in r.evidence} <= set(run.calls[prefix])
