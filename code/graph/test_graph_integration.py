"""Testes contra o Neo4j do projeto. Pulam com motivo se ele não estiver no ar ou se a URI for a porta 7687.

Apagam o grafo do projeto a cada teste. Rode make neo4j-up e make neo4j-wait antes.
"""

from pathlib import Path

import pytest

from domain import ids
from domain.enums import NodeKind
from domain.fixtures.build import chunk_paragraphs
from domain.llm_io import ExtractionOutput
from domain.models import SourceChunk, SourceDocument
from domain.persist import to_records
from domain.rules import CorpusIndex, check_all
from domain.serialization import parse
from graph.connection import Graph, GraphUnavailable, Neo4jSettings, UnsafeTarget, refuse_user_instance
from graph.fixture import CONFIDENCE_THRESHOLD, aliased_output, exclusive_database, load_fixture, write_fixture
from graph.properties import GraphWriteError, model_from_props
from graph.queries import gap_report, recorded_output
from graph.schema import LABELS, drop_schema, ensure_schema, expected_names, extension_procedures, present_schema
from graph.state import logical_state
from graph.writer import clear_graph, invalidate_chunks, remove_document, write_batch, write_documents

FIXTURE = load_fixture()
SRC = FIXTURE.document.source_id
TEXT = (Path(__file__).resolve().parents[1] / "domain" / "fixtures" / "corpus" / "entrevista_sintetica.txt").read_text(
    encoding="utf-8")
_, C1, C2, C3 = FIXTURE.chunks


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


@pytest.fixture
def clean(graph):
    clear_graph(graph)
    ensure_schema(graph)
    return graph


def version(text: str) -> tuple[SourceDocument, list[SourceChunk]]:
    document = FIXTURE.document.model_copy(update={"sha256": ids.sha256_text(text), "char_count": len(text)})
    return document, parse(chunk_paragraphs(text, SRC), list[SourceChunk])


def without_chunk(output: ExtractionOutput, chunk_id: str) -> ExtractionOutput:
    """A extração do documento novo, se o parágrafo alterado não render nada."""
    data = output.model_dump(mode="json")
    dropped = set()
    for collection in ("requirements", "actors", "components", "entities"):
        for item in data[collection]:
            item["evidence"] = [e for e in item["evidence"] if e["chunk_id"] != chunk_id]
        dropped |= {item["key"] for item in data[collection] if not item["evidence"]}
        data[collection] = [item for item in data[collection] if item["evidence"]]
    data["relations"] = [r for r in data["relations"] if not {r["source_key"], r["target_key"]} & dropped]
    return ExtractionOutput.model_validate(data)


def ev(chunk: SourceChunk, quote: str, source: str = SRC) -> dict:
    assert quote in chunk.text
    return {"source_id": source, "chunk_id": chunk.chunk_id, "quote": quote}


def test_image_has_no_apoc_nor_gds(graph):
    assert extension_procedures(graph) == []


def test_schema_from_scratch_is_idempotent(clean):
    drop_schema(clean)
    assert present_schema(clean) == []
    ensure_schema(clean)
    ensure_schema(clean)
    assert present_schema(clean) == expected_names()


def test_gate_clean_run_then_second_run_reach_the_same_logical_state(clean):
    write_fixture(clean, FIXTURE)
    first = logical_state(clean)
    print(f"\nprimeira execução: {first}")
    assert first.nodes == {"Actor": 2, "Entity": 1, "QualityAttribute": 2, "Requirement": 6,
                           "SourceChunk": 4, "SourceDocument": 1}
    assert first.relations == {"CONFLICTS_WITH": 1, "CONTAINS": 4, "DEPENDS_ON": 1, "DERIVED_FROM": 6,
                               "DUPLICATES": 1, "MEASURED_BY": 3, "MENTIONS": 1, "REFINES": 2,
                               "REQUESTED_BY": 2, "SUPPORTS": 6}
    ensure_schema(clean)
    write_fixture(clean, FIXTURE)
    second = logical_state(clean)
    print(f"segunda execução:  {second}")
    assert second == first
    clear_graph(clean)
    write_fixture(clean, FIXTURE)
    assert logical_state(clean) == first


@pytest.mark.parametrize("name", sorted(FIXTURE.outputs))
def test_twin_graph_queries_count_what_the_rules_count_on_the_recorded_items(clean, name):
    batch = FIXTURE.batch(name)
    write_documents(clean, [FIXTURE.document], FIXTURE.chunks)
    write_batch(clean, batch)
    graph_side = gap_report(clean).violations()
    python_side = check_all(recorded_output(batch), FIXTURE.corpus)
    print(f"\n{name}: grafo {[(v.rule_id, v.subject) for v in graph_side]}")
    assert graph_side == python_side


def test_alias_divergence_reaches_the_graph(clean):
    output = aliased_output(FIXTURE)
    batch = to_records(output, FIXTURE.corpus, CONFIDENCE_THRESHOLD)
    write_documents(clean, [FIXTURE.document], FIXTURE.chunks)
    write_batch(clean, batch)
    assert check_all(output, FIXTURE.corpus) == []
    assert [v.rule_id for v in gap_report(clean).violations()] == ["K3"]


def test_nodes_read_back_as_contract_models(clean):
    batch = FIXTURE.batch("extraction_output.json")
    write_documents(clean, [FIXTURE.document], FIXTURE.chunks)
    write_batch(clean, batch)
    for kind, models in ((NodeKind.REQUIREMENT, batch.requirements), (NodeKind.ACTOR, batch.actors),
                         (NodeKind.ENTITY, batch.entities)):
        label, key = LABELS[kind]
        stored = clean.rows(f"MATCH (n:{label}) RETURN properties(n) AS p ORDER BY n.{key}")
        assert [model_from_props(kind, r["p"]) for r in stored] == models


def test_batch_without_its_chunks_is_refused_and_nothing_is_written(clean):
    with pytest.raises(GraphWriteError, match="chunks fora do grafo"):
        write_batch(clean, FIXTURE.batch("extraction_output.json"))
    assert logical_state(clean).nodes == {}


def test_new_document_version_needs_invalidation_first(clean):
    write_documents(clean, [FIXTURE.document], FIXTURE.chunks)
    document, chunks = version(TEXT.replace("precisa ser rápida", "abre em dois segundos"))
    with pytest.raises(GraphWriteError, match="rode invalidate_chunks antes"):
        write_documents(clean, [document], chunks)


def test_incremental_update_equals_fresh_load_of_the_new_version(clean):
    clean_output = FIXTURE.outputs["extraction_output.json"]
    document, chunks = version(TEXT.replace("precisa ser rápida", "abre em dois segundos"))
    removed = sorted({c.chunk_id for c in FIXTURE.chunks} - {c.chunk_id for c in chunks})
    assert removed == [C2.chunk_id]
    batch_v2 = to_records(without_chunk(clean_output, C2.chunk_id), CorpusIndex.from_chunks(chunks),
                          CONFIDENCE_THRESHOLD)

    write_documents(clean, [document], chunks)
    write_batch(clean, batch_v2)
    fresh = logical_state(clean)

    clear_graph(clean)
    v1 = FIXTURE.batch("extraction_output.json")
    write_documents(clean, [FIXTURE.document], FIXTURE.chunks)
    write_batch(clean, v1)
    report = invalidate_chunks(clean, SRC, removed)
    by_key = v1.key_to_id
    assert report.removed_chunks == removed
    assert report.deleted_nodes == sorted([by_key["R2"], by_key["R3"], by_key["A2"], by_key["E1"],
                                           "qa-performance"])
    assert report.pruned_nodes == [] and report.deleted_by_primary == []
    write_documents(clean, [document], chunks)
    write_batch(clean, batch_v2)
    assert logical_state(clean) == fresh

    again = invalidate_chunks(clean, SRC, removed)
    assert (again.removed_chunks, again.deleted_nodes, again.deleted_relations) == ([], [], [])
    assert logical_state(clean) == fresh


def two_chunk_output() -> ExtractionOutput:
    both = [ev(C1, "reservar um equipamento por horário"), ev(C3, "cancelar reserva de outra pessoa")]
    return ExtractionOutput.model_validate({
        "requirements": [{"key": "R9", "statement": "O sistema deve registrar reservas e cancelamentos.",
                          "type": "functional", "priority": "must", "verification_method": "test",
                          "evidence": both}],
        "actors": [{"key": "A1", "name": "Coordenadora do laboratório", "kind": "stakeholder",
                    "evidence": [ev(C1, "Coordenadora do laboratório"), ev(C3, "Coordenadora do laboratório")]}],
        "relations": [{"type": "requested_by", "source_key": "R9", "target_key": "A1", "evidence": both}],
    })


def primary_and_secondary() -> tuple[SourceChunk, SourceChunk]:
    first, second = sorted([C1, C3], key=lambda c: c.chunk_id)
    return first, second


def test_secondary_evidence_removed_keeps_the_requirement(clean):
    batch = to_records(two_chunk_output(), FIXTURE.corpus, CONFIDENCE_THRESHOLD)
    requirement = batch.requirements[0]
    primary, secondary = primary_and_secondary()
    write_documents(clean, [FIXTURE.document], FIXTURE.chunks)
    write_batch(clean, batch)

    report = invalidate_chunks(clean, SRC, [secondary.chunk_id])
    assert report.deleted_nodes == [] and report.deleted_by_primary == []
    assert report.pruned_nodes == sorted([requirement.requirement_id, batch.actors[0].actor_id])
    stored = clean.rows("MATCH (r:Requirement) RETURN properties(r) AS p, "
                        "[(c)-[:SUPPORTS]->(r) | c.chunk_id] AS supports, "
                        "[(r)-[:DERIVED_FROM]->(d) | d.source_id] AS derived")
    assert len(stored) == 1
    assert stored[0]["p"]["evidence_chunk_ids"] == [primary.chunk_id]
    assert stored[0]["supports"] == [primary.chunk_id] and stored[0]["derived"] == [SRC]
    relation = clean.rows("MATCH ()-[r:REQUESTED_BY]->() RETURN r.evidence_chunk_ids AS chunks")
    assert relation == [{"chunks": [primary.chunk_id]}]
    assert model_from_props(NodeKind.REQUIREMENT, stored[0]["p"]) == requirement.model_copy(update={
        "provenance": requirement.provenance.model_copy(update={
            "evidence": [e for e in requirement.provenance.evidence if e.chunk_id == primary.chunk_id]})})


def remap_chunk(output: ExtractionOutput, old: str, new: str) -> ExtractionOutput:
    data = output.model_dump(mode="json")
    for collection in ("requirements", "actors", "components", "entities", "relations"):
        for item in data[collection]:
            for evidence in item["evidence"]:
                if evidence["chunk_id"] == old:
                    evidence["chunk_id"] = new
    return ExtractionOutput.model_validate(data)


def test_primary_evidence_removed_deletes_the_requirement_and_reload_matches_fresh(clean):
    """O requisito tinha evidência em dois chunks. O parágrafo da evidência primária muda."""
    v1_output = two_chunk_output()
    primary, secondary = primary_and_secondary()
    document, chunks = version(TEXT.replace(primary.text, primary.text + " Frase nova da versão 2."))
    removed = sorted({c.chunk_id for c in FIXTURE.chunks} - {c.chunk_id for c in chunks})
    assert removed == [primary.chunk_id]
    new_chunk = next(c for c in chunks if c.index == primary.index)
    v2_output = remap_chunk(v1_output, primary.chunk_id, new_chunk.chunk_id)
    batch_v2 = to_records(v2_output, CorpusIndex.from_chunks(chunks), CONFIDENCE_THRESHOLD)

    write_documents(clean, [document], chunks)
    write_batch(clean, batch_v2)
    fresh = logical_state(clean)

    clear_graph(clean)
    batch_v1 = to_records(v1_output, FIXTURE.corpus, CONFIDENCE_THRESHOLD)
    requirement_v1 = batch_v1.requirements[0].requirement_id
    write_documents(clean, [FIXTURE.document], FIXTURE.chunks)
    write_batch(clean, batch_v1)
    report = invalidate_chunks(clean, SRC, removed)
    assert report.deleted_by_primary == [requirement_v1]
    assert requirement_v1 in report.deleted_nodes
    assert report.pruned_nodes == [batch_v1.actors[0].actor_id]
    assert clean.rows("MATCH (r:Requirement) RETURN count(r) AS n") == [{"n": 0}]
    assert clean.rows("MATCH ()-[r:REQUESTED_BY|DERIVED_FROM]->() RETURN count(r) AS n") == [{"n": 0}]

    write_documents(clean, [document], chunks)
    write_batch(clean, batch_v2)
    print(f"\ncarga limpa de v2:  {fresh.digest}\nv1, invalidar, v2: {logical_state(clean).digest}")
    assert batch_v2.requirements[0].requirement_id != requirement_v1
    assert logical_state(clean) == fresh


def test_derived_from_follows_the_documents_that_still_hold_evidence(clean):
    path = "code/graph/fixtures/segundo_documento.txt"
    other_text = "Segundo documento sintético.\n\nO técnico também pede aviso por e-mail quando a calibração vence."
    other_source = ids.source_id(path)
    other_chunks = parse(chunk_paragraphs(other_text, other_source), list[SourceChunk])
    other = SourceDocument(source_id=other_source, path=path, sha256=ids.sha256_text(other_text),
                           kind="meeting_record", char_count=len(other_text))
    output = ExtractionOutput.model_validate({"requirements": [{
        "key": "R7", "statement": "O sistema deve avisar o responsável quando a calibração vencer.",
        "type": "functional", "priority": "should", "verification_method": "test",
        "evidence": [ev(C2, "O sistema deve enviar um aviso ao responsável"),
                     ev(other_chunks[1], "aviso por e-mail", other_source)],
    }]})
    corpus = CorpusIndex.from_chunks([*FIXTURE.chunks, *other_chunks])
    batch = to_records(output, corpus, CONFIDENCE_THRESHOLD)
    write_documents(clean, [FIXTURE.document, other], [*FIXTURE.chunks, *other_chunks])
    write_batch(clean, batch)
    derived = "MATCH (:Requirement)-[:DERIVED_FROM]->(d) RETURN d.source_id AS s ORDER BY s"
    assert [r["s"] for r in clean.rows(derived)] == sorted([SRC, other_source])

    chunk_of = {SRC: C2.chunk_id, other_source: other_chunks[1].chunk_id}
    primary_source, secondary_source = sorted(chunk_of, key=chunk_of.get)
    report = invalidate_chunks(clean, secondary_source, [chunk_of[secondary_source]])
    assert [r["s"] for r in clean.rows(derived)] == [primary_source]
    assert report.deleted_nodes == [] and report.deleted_by_primary == []
    assert len(report.deleted_relations) == 1

    remove_document(clean, secondary_source)
    assert clean.rows("MATCH (d:SourceDocument) RETURN d.source_id AS s") == [{"s": primary_source}]
    assert gap_report(clean).violations() == []


def test_queries_fire_on_a_tampered_graph(clean):
    batch = FIXTURE.batch("extraction_output.json")
    write_documents(clean, [FIXTURE.document], FIXTURE.chunks)
    write_batch(clean, batch)
    assert gap_report(clean).violations() == []
    r1, r2, r4 = (batch.key_to_id[k] for k in ("R1", "R2", "R4"))
    actor = batch.key_to_id["A1"]
    ghost = ids.stable_id("chk", "fantasma")
    clean.write(lambda tx: [tx.run(q, r1=r1, r2=r2, actor=actor, ghost=ghost, c1=C1.chunk_id).consume() for q in (
        "MATCH (:Requirement {requirement_id: $r1})-[d:DERIVED_FROM]->() DELETE d",
        "MATCH (:Requirement {requirement_id: $r1})-[x:REQUESTED_BY]->() SET x.evidence_chunk_ids = []",
        "MATCH (a:Actor {actor_id: $actor}) SET a.evidence_chunk_ids = a.evidence_chunk_ids + $ghost",
        "MATCH (r:Requirement {requirement_id: $r1}) "
        "CREATE (r)-[:DEPENDS_ON {relation_id: 'rel-00000000000000aa', evidence_chunk_ids: [$c1]}]->(r)",
        "MATCH (:Requirement {requirement_id: $r2})-[m:MEASURED_BY]->() DELETE m",
        "MATCH (r:Requirement {requirement_id: $r1}) SET r.priority = 'wont'",
        "MATCH (r:Requirement {requirement_id: $r2}) REMOVE r.verification_method",
    )])
    requested = next(r.relation_id for r in batch.relations if r.type.value == "requested_by" and r.source.id == r1)
    report = gap_report(clean)
    assert [(v.rule_id, v.subject) for v in report.completeness] == [("C2", r2)]
    assert [(v.rule_id, v.subject) for v in report.quality_attribute] == [("C4", r2)]
    assert sorted((v.rule_id, v.subject) for v in report.provenance) == sorted(
        [("P1", r1), ("P2", actor), ("P5", requested)])
    assert sorted((v.rule_id, v.subject) for v in report.consistency) == sorted(
        [("K2", "rel-00000000000000aa"), ("K5", f"{r4}->{r1}")])


def test_clear_graph_refuses_a_database_with_foreign_nodes(clean):
    clean.write(lambda tx: tx.run("CREATE (:DadoDeOutroProjeto {x: 1})").consume())
    try:
        with pytest.raises(GraphWriteError, match="Nada foi apagado"):
            clear_graph(clean)
        assert clean.rows("MATCH (n:DadoDeOutroProjeto) RETURN count(n) AS n") == [{"n": 1}]
    finally:
        clean.write(lambda tx: tx.run("MATCH (n:DadoDeOutroProjeto) DELETE n").consume())
