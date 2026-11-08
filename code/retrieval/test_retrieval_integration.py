"""Recuperação contra o Neo4j do projeto, com o fixture do domínio e um projeto PROMISE sintético.

Pulam com motivo se o Neo4j não estiver no ar ou se a URI for a porta 7687. Apagam o grafo do
projeto, por isso seguram graph.fixture.exclusive_database. Rode com -s para ver os contextos.
"""

import hashlib
from dataclasses import dataclass

import pytest

from domain.config import ExperimentConfig
from domain.enums import Condition, ContextStrategy, NodeKind, PromiseLabel
from domain.llm_io import ClassificationOutput, ContextItem, RetrievedContext
from extraction.client import CallLog
from graph.connection import Graph, GraphUnavailable, Neo4jSettings, UnsafeTarget, refuse_user_instance
from graph.fixture import exclusive_database, write_fixture
from graph.schema import ensure_schema
from graph.writer import clear_graph
from graph.properties import decode_evidence
from retrieval import CandidateTarget, PromiseTarget, RetrievalError, retrieve_context
from retrieval.fixtures import PROMISE_JSONL, SyntheticExtractionClient
from retrieval.local import KEY_OF_KIND, TAINTABLE, select
from retrieval.promise import PromiseProject, build_project, extract_project, load_promise_items, write_project_graph
from retrieval.test_retrieval_unit import CHUNKS, CONFIG, FIXTURE, ORIGIN, ORIGIN_SHA, config

SRC = FIXTURE.document.source_id
INTRO, C1, C2, C3 = (c.chunk_id for c in CHUNKS)
KEY_TO_ID = FIXTURE.batch("extraction_output.json").key_to_id
FORBIDDEN_WORDS = ("REQKG", "LLM-only", "graph_local", "source_chunks", "grafo", "condição", "condition")


@pytest.fixture(scope="module")
def graph():
    try:
        settings = Neo4jSettings.from_env()
        refuse_user_instance(settings.uri)
    except GraphUnavailable as error:
        pytest.skip(f"Neo4j não configurado: {error}")
    except UnsafeTarget as error:
        pytest.skip(f"recusado: {error}")
    try:
        opened = Graph(settings)
    except GraphUnavailable as error:
        pytest.skip(f"{error}. Rode make neo4j-up e make neo4j-wait")
    with opened:
        try:
            with exclusive_database():
                yield opened
        except TimeoutError as error:
            pytest.skip(str(error))


@dataclass(frozen=True)
class Loaded:
    graph: Graph
    project: PromiseProject
    promise_config: ExperimentConfig


def load(graph: Graph, tmp_path_factory) -> PromiseProject:
    clear_graph(graph)
    ensure_schema(graph)
    write_fixture(graph, FIXTURE)
    project = build_project(load_promise_items(PROMISE_JSONL), 98, origin=ORIGIN, origin_sha256=ORIGIN_SHA,
                            chunking=CONFIG.chunking, seed=CONFIG.evaluation.seed)
    run = extract_project(project, run_index=0, config=config(chunks_per_call=3),
                          client=SyntheticExtractionClient(project), log=CallLog(tmp_path_factory.mktemp("calls")))
    write_project_graph(graph, project, run, CONFIG.review.confidence_threshold)
    return project


@pytest.fixture(scope="module")
def loaded(graph, tmp_path_factory):
    return Loaded(graph, load(graph, tmp_path_factory), config(chunks_per_call=3))


def show(title: str, context: RetrievedContext) -> None:
    print(f"\n--- {title}: {context.query} ({len(context.items)}/{context.limit} itens)")
    for i in context.items:
        print(f"  {i.rank} {i.kind:<18} {i.item_id:<22} {i.chunk_id}  {' '.join(i.text.split())[:80]}")


def assert_traceable(graph: Graph, context: RetrievedContext) -> None:
    RetrievedContext.model_validate(context.model_dump())
    for i in context.items:
        found = graph.rows("MATCH (c:SourceChunk {chunk_id: $c}) RETURN c.source_id AS source", c=i.chunk_id)
        assert found == [{"source": i.source_id}], f"{i.item_id}: proveniência {i.source_id}/{i.chunk_id} fora do grafo"
        assert not any(word.casefold() in i.text.casefold() for word in FORBIDDEN_WORDS), i.text


def graph_size(graph: Graph) -> int:
    nodes = graph.rows("MATCH (n) WHERE NOT n:SourceDocument RETURN count(n) AS n")[0]["n"]
    relations = graph.rows("MATCH ()-[r]->() WHERE r.relation_id IS NOT NULL RETURN count(r) AS n")[0]["n"]
    return nodes + relations


def candidate(key: str, requirement_id: str | None, sources=frozenset({SRC})) -> CandidateTarget:
    return CandidateTarget(key, CHUNKS, requirement_id, sources)


def ranks(context: RetrievedContext) -> dict[str, int]:
    return {i.item_id: i.rank for i in context.items}


# candidato da extração


TWO_PER_CALL = config(chunks_per_call=2)


def test_requirement_seed_is_the_node_and_the_chunks_of_the_extraction_call(loaded):
    """Com dois chunks por chamada, R4 (sustentado por C3) nasce na chamada c1 = [C2, C3]."""
    r4, r1 = KEY_TO_ID["R4"], KEY_TO_ID["R1"]
    context = retrieve_context(candidate("c1-R4", r4), Condition.REQKG_GROUNDED, TWO_PER_CALL, loaded.graph)
    show("semente por requisito e chamada (R4)", context)
    assert_traceable(loaded.graph, context)
    assert context.strategy is ContextStrategy.GRAPH_LOCAL and context.limit == CONFIG.retrieval.max_items
    assert f"a partir de {r4} e dos chunks da chamada c1" in context.query
    got = ranks(context)
    assert r4 not in got, "o alvo não aparece no próprio contexto"
    assert sorted(i.item_id for i in context.items if i.rank == 0) == sorted([C2, C3])
    assert got[r1] == 1 and got["qa-security"] == 1
    assert any(i.kind == "relation" and "depends_on" in i.text and i.rank == 1 for i in context.items)
    assert got[C1] == 2, "o chunk que sustenta o vizinho R1 fica a dois saltos"
    assert INTRO not in got


def test_chunk_seed_when_the_candidate_has_no_node(loaded):
    context = retrieve_context(candidate("c1-R9", None), Condition.REQKG_GROUNDED, TWO_PER_CALL, loaded.graph)
    show("semente por chunks (c1, sem nó)", context)
    assert_traceable(loaded.graph, context)
    assert "a partir de chunks da chamada c1" in context.query
    assert sorted(i.item_id for i in context.items if i.rank == 0) == sorted([C2, C3])
    assert any(i.kind == NodeKind.ENTITY and i.rank == 1 for i in context.items), "entidade mencionada no chunk"
    assert INTRO not in ranks(context)
    absent = candidate("c1-R9", "req-0000000000000000")
    assert retrieve_context(absent, Condition.REQKG_GROUNDED, TWO_PER_CALL, loaded.graph).items == context.items


def test_grounded_context_contains_the_llm_only_context_for_every_target(loaded):
    r4 = KEY_TO_ID["R4"]
    checked = 0
    for per_call in (1, 2, 3, 6):
        cfg = config(chunks_per_call=per_call)
        for call in range(-(-len(CHUNKS) // per_call)):
            for requirement_id in (r4, None):
                target = candidate(f"c{call}-R4", requirement_id)
                a = retrieve_context(target, Condition.LLM_ONLY, cfg)
                b = retrieve_context(target, Condition.REQKG_GROUNDED, cfg, loaded.graph)
                seen = {(i.item_id, i.text, i.source_id, i.chunk_id): i.rank for i in b.items}
                assert all(seen.get((i.item_id, i.text, i.source_id, i.chunk_id)) == 0 for i in a.items), \
                    (per_call, call, requirement_id)
                checked += 1
    assert checked == 2 * (4 + 2 + 2 + 1)


def test_limit_is_respected_and_keeps_the_seed_and_the_closest_items(loaded):
    target = candidate("c1-R4", KEY_TO_ID["R4"])
    full = retrieve_context(target, Condition.REQKG_GROUNDED, TWO_PER_CALL, loaded.graph)
    small_config = config(chunks_per_call=2, max_items=4)
    small = retrieve_context(target, Condition.REQKG_GROUNDED, small_config, loaded.graph)
    show("limite 4", small)
    assert small.limit == 4 and len(small.items) == 4 < len(full.items)
    assert small.items == select(full.items, 4)
    assert {C2, C3} <= set(ranks(small))
    with pytest.raises(RetrievalError, match="semente"):
        retrieve_context(candidate("c0-R4", KEY_TO_ID["R4"]), Condition.REQKG_GROUNDED, config(max_items=3),
                         loaded.graph)


def test_order_is_deterministic_between_calls_and_after_reloading_the_graph(loaded, tmp_path_factory):
    targets = [(candidate("c0-R4", KEY_TO_ID["R4"]), CONFIG), (candidate("c1-R9", None), TWO_PER_CALL),
               (PromiseTarget("PROMISE-NFR-9005", loaded.project), loaded.promise_config)]
    first = [retrieve_context(t, Condition.REQKG_GROUNDED, c, loaded.graph) for t, c in targets]
    second = [retrieve_context(t, Condition.REQKG_GROUNDED, c, loaded.graph) for t, c in targets]
    load(loaded.graph, tmp_path_factory)
    third = [retrieve_context(t, Condition.REQKG_GROUNDED, c, loaded.graph) for t, c in targets]
    assert first == second == third


def test_context_is_not_the_whole_graph(loaded):
    total = graph_size(loaded.graph)
    for target in (candidate("c1-R4", KEY_TO_ID["R4"]), candidate("c1-R9", None)):
        context = retrieve_context(target, Condition.REQKG_GROUNDED, TWO_PER_CALL, loaded.graph)
        assert len(context.items) < total
        assert INTRO not in ranks(context)
        assert all(i.source_id == SRC for i in context.items)


def test_quality_attribute_is_a_leaf_and_does_not_bring_other_requirements(loaded):
    """Sem sources, qa-security ligaria R4 aos requisitos de segurança do projeto PROMISE (9004 e 9006)."""
    context = retrieve_context(candidate("c1-R4", KEY_TO_ID["R4"], sources=None), Condition.REQKG_GROUNDED,
                               TWO_PER_CALL, loaded.graph)
    show("sem sources: atributo de qualidade como folha", context)
    assert_traceable(loaded.graph, context)
    assert ranks(context)["qa-security"] == 1, "o atributo continua aparecendo como item"
    promise_source = loaded.project.document.source_id
    assert not [i for i in context.items if i.kind == NodeKind.REQUIREMENT and i.source_id == promise_source]


# PROMISE


def classification(promise_id: str) -> ClassificationOutput:
    return ClassificationOutput(promise_id=promise_id, label=PromiseLabel.F)


def test_promise_context_leaves_out_the_item_and_names_requirements_by_promise_id(loaded):
    """Com a semente da configuração e três chunks por chamada, as chamadas são [9007, 9004, 9008],
    [9001, 9003, 9002] e [9005, 9006]."""
    x = "PROMISE-NFR-9005"
    project = loaded.project
    context = retrieve_context(PromiseTarget(x, project), Condition.REQKG_GROUNDED, loaded.promise_config, loaded.graph)
    show(f"PROMISE sem {x}", context)
    assert_traceable(loaded.graph, context)
    got = ranks(context)
    own_chunk = project.chunk_of(x).chunk_id
    assert x not in got and own_chunk not in context.chunk_ids()
    promise_of = project.promise_of_chunk()
    for i in context.items:
        assert i.source_id == project.document.source_id
        if i.kind == NodeKind.REQUIREMENT:
            assert i.item_id == promise_of[i.chunk_id]
        assert i.kind != NodeKind.SOURCE_CHUNK, "chunk do PROMISE é requisito e usa o promise_id"
    assert [i.item_id for i in context.items if i.rank == 0] == ["PROMISE-NFR-9006"]
    assert got["act-53298cc228995fed"] == 2, "o coordenador, ator de 9006"

    item_text = project.chunk_of(x).text
    assert classification(x).check_against(context, classification(x), item_text) == []
    chunk = project.chunk_of(x)
    leaked = RetrievedContext(query=context.query, strategy=context.strategy, limit=context.limit + 1,
                              items=sorted([*context.items, ContextItem(
                                  item_id=x, kind=NodeKind.REQUIREMENT, rank=0, text=chunk.text,
                                  source_id=chunk.source_id, chunk_id=chunk.chunk_id)],
                                  key=lambda i: (i.rank, i.item_id)))
    assert {v.rule_id for v in classification(x).check_against(leaked, classification(x), item_text)} == {"G5"}


def test_promise_grounded_context_has_no_quality_attribute_and_no_node_from_the_item(loaded):
    """audit log (entidade de 9005 e 9006) e instrument (de 9001, 9007 e 9008) teriam evidência no chunk
    do item; security e usability são categorias inferidas pelo modelo, parecidas com os rótulos."""
    project = loaded.project
    without_9005 = retrieve_context(PromiseTarget("PROMISE-NFR-9005", project), Condition.REQKG_GROUNDED,
                                    loaded.promise_config, loaded.graph)
    without_9007 = retrieve_context(PromiseTarget("PROMISE-NFR-9007", project), Condition.REQKG_GROUNDED,
                                    loaded.promise_config, loaded.graph)
    assert not [i for i in without_9005.items if i.kind == NodeKind.ENTITY and i.text.startswith("audit log")]
    assert not [i for i in without_9007.items if i.kind == NodeKind.ENTITY and i.text.startswith("instrument")]
    for x in project.promise_ids:
        context = retrieve_context(PromiseTarget(x, project), Condition.REQKG_GROUNDED, loaded.promise_config,
                                   loaded.graph)
        assert not [i for i in context.items if i.kind == NodeKind.QUALITY_ATTRIBUTE], x
        assert not [i for i in context.items if i.kind == "relation" and "--measured_by-->" in i.text], x
        own = project.chunk_of(x).chunk_id
        for i in context.items:
            if i.kind in TAINTABLE:
                [row] = loaded.graph.rows(f"MATCH (n {{{KEY_OF_KIND[i.kind]}: $id}}) RETURN n.evidence_json AS e",
                                          id=i.item_id)
                assert own not in {e.chunk_id for e in decode_evidence(row["e"])}, (x, i.item_id)


def test_promise_item_never_appears_in_its_own_context_and_b_contains_a(loaded):
    project = loaded.project
    for x in project.promise_ids:
        context = retrieve_context(PromiseTarget(x, project), Condition.REQKG_GROUNDED, loaded.promise_config,
                                   loaded.graph)
        assert_traceable(loaded.graph, context)
        assert x not in ranks(context) and project.chunk_of(x).chunk_id not in context.chunk_ids()
        assert classification(x).check_against(context, classification(x), project.chunk_of(x).text) == []
        source = retrieve_context(PromiseTarget(x, project), Condition.LLM_ONLY, loaded.promise_config)
        assert source.items and all(i in context.items for i in source.items), x


def test_promise_context_stays_in_the_project_even_with_a_shared_entity(loaded):
    """calibração existe no fixture do domínio e no projeto PROMISE, com o mesmo entity_id."""
    project = loaded.project
    context = retrieve_context(PromiseTarget("PROMISE-NFR-9007", project), Condition.REQKG_GROUNDED,
                               loaded.promise_config, loaded.graph)
    show("PROMISE sem 9007 (entidade compartilhada)", context)
    shared = [i for i in context.items if i.kind == NodeKind.ENTITY and i.text.startswith("calibração")]
    assert shared and shared[0].chunk_id == project.chunk_of("PROMISE-NFR-9008").chunk_id
    assert all(i.source_id == project.document.source_id for i in context.items)
    assert len(context.items) < graph_size(loaded.graph)


def test_promise_llm_only_is_the_rest_of_the_call(loaded):
    context = retrieve_context(PromiseTarget("PROMISE-NFR-9005", loaded.project), Condition.LLM_ONLY,
                               loaded.promise_config, loaded.graph)
    assert [(i.item_id, i.kind, i.rank) for i in context.items] == [("PROMISE-NFR-9006", NodeKind.REQUIREMENT, 0)]
    assert context.strategy is ContextStrategy.SOURCE_CHUNKS
