"""Testes sem Neo4j: recusa da porta, Cypher gerado, conversão de propriedades e o lado Python do gêmeo."""

import json
import re

import pytest
from pydantic import ValidationError

from domain.enums import RELATION_ENDPOINTS, NodeKind, Origin, RelationType, ValidationState
from domain.models import Evidence, Provenance, Relation
from domain.persist import PersistBatch, to_records
from domain.rules import check_all
from graph import connection
from graph.connection import Graph, GraphUnavailable, Neo4jSettings, UnsafeTarget, refuse_user_instance
from graph.fixture import aliased_output, load_fixture
from graph.properties import (
    GraphWriteError,
    merge_provenance,
    model_from_props,
    node_key,
    node_props,
    relation_endpoints,
    relation_props,
)
from graph.queries import recorded_output
from graph.schema import CONTRACT_TYPES, LABELS, expected_names, schema_statements
from graph.writer import upsert_nodes_query, upsert_relations_query, write_batch

FIXTURE = load_fixture()
SRC = FIXTURE.document.source_id
C1, C2, C3 = (c.chunk_id for c in FIXTURE.chunks[1:])


@pytest.mark.parametrize("uri", ["bolt://localhost:7687", "neo4j://127.0.0.1:7687", "bolt://localhost",
                                 "neo4j://example.org"])
def test_port_7687_is_refused(uri):
    with pytest.raises(UnsafeTarget, match="7687"):
        refuse_user_instance(uri)


def test_project_port_is_accepted():
    refuse_user_instance("bolt://localhost:17687")


def test_graph_refuses_before_opening_a_driver(monkeypatch):
    def no_driver(*args, **kwargs):
        raise AssertionError("o driver não pode ser criado para a porta 7687")

    monkeypatch.setattr(connection.GraphDatabase, "driver", no_driver)
    with pytest.raises(UnsafeTarget):
        Graph(Neo4jSettings("bolt://localhost:7687", "neo4j", "senha-qualquer"))


def test_settings_read_env_file_and_environment_wins(tmp_path, monkeypatch):
    for name in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "NEO4J_DATABASE"):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text("# comentário\nNEO4J_URI=bolt://localhost:17687\nNEO4J_USER=neo4j\nNEO4J_PASSWORD='s3nha'\n")
    assert Neo4jSettings.from_env(env) == Neo4jSettings("bolt://localhost:17687", "neo4j", "s3nha")
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:27687")
    assert Neo4jSettings.from_env(env).uri == "bolt://localhost:27687"
    with pytest.raises(GraphUnavailable, match="NEO4J_PASSWORD"):
        Neo4jSettings.from_env(tmp_path / "ausente")


def test_schema_has_one_unique_constraint_per_label_and_relation_type():
    statements = schema_statements()
    assert all("IF NOT EXISTS" in s for s in statements)
    for label, key in LABELS.values():
        assert sum(f"(n:{label}) REQUIRE n.{key} IS UNIQUE" in s for s in statements) == 1
    assert {t.neo4j_type for t in RelationType} == set(CONTRACT_TYPES)
    for neo4j_type in CONTRACT_TYPES:
        assert sum(f"[r:{neo4j_type}]-() REQUIRE r.relation_id IS UNIQUE" in s for s in statements) == 1
    names = [re.search(r"(CONSTRAINT|INDEX) (\S+)", s).group(2) for s in statements]
    assert sorted(names) == expected_names() and len(set(names)) == len(names)


@pytest.mark.parametrize("relation", list(RelationType))
def test_relation_query_uses_the_contract_endpoints(relation):
    source, target = RELATION_ENDPOINTS[relation]
    query = upsert_relations_query(relation)
    assert f"(a:{LABELS[source][0]} {{{LABELS[source][1]}: row.source}})" in query
    assert f"(b:{LABELS[target][0]} {{{LABELS[target][1]}: row.target}})" in query
    assert f"[r:{relation.neo4j_type} {{relation_id: row.props.relation_id}}]" in query


def test_node_query_merges_on_the_contract_key():
    assert "MERGE (n:Requirement {requirement_id: row.key}) SET n = row.props" in upsert_nodes_query(NodeKind.REQUIREMENT)


def all_nodes(batch: PersistBatch) -> list:
    return [*batch.requirements, *batch.actors, *batch.entities, *batch.quality_attributes]


def test_node_properties_round_trip_without_nulls():
    batch = FIXTURE.batch("extraction_output.json")
    for model in [FIXTURE.document, *FIXTURE.chunks, *all_nodes(batch)]:
        props = node_props(model)
        assert None not in props.values()
        kind, key = node_key(model)
        assert props[LABELS[kind][1]] == key
        assert model_from_props(kind, props) == model


def test_evidence_is_canonical_json_with_chunk_index():
    evidence = [Evidence(source_id=SRC, chunk_id=C3, quote="b"), Evidence(source_id=SRC, chunk_id=C1, quote="a"),
                Evidence(source_id=SRC, chunk_id=C1, quote="a")]
    props = node_props(FIXTURE.batch("extraction_output.json").requirements[0].model_copy(
        update={"provenance": Provenance(origin=Origin.EXTRACTED_FACT, evidence=evidence)}))
    decoded = json.loads(props["evidence_json"])
    assert [e["chunk_id"] for e in decoded] == sorted([C1, C3])
    assert props["evidence_chunk_ids"] == sorted({C1, C3})
    assert props["evidence_json"] == json.dumps(decoded, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def bypassed_relation() -> Relation:
    good = FIXTURE.batch("extraction_output.json").relations[0]
    empty = Provenance.model_construct(origin=Origin.SYSTEM_INFERENCE, evidence=[],
                                       validation=ValidationState.UNVALIDATED, note=None)
    return good.model_copy(update={"provenance": empty})


def test_relation_without_evidence_is_refused_even_if_constructed_unvalidated():
    with pytest.raises(GraphWriteError, match="sem source_id e chunk_id"):
        relation_props(bypassed_relation())


def test_writer_revalidates_the_batch_before_touching_the_graph():
    class NoGraph:
        def write(self, work):
            raise AssertionError("o grafo não pode ser tocado")

    batch = FIXTURE.batch("extraction_output.json")
    tampered = batch.model_copy(update={"relations": [bypassed_relation(), *batch.relations[1:]]})
    with pytest.raises(ValidationError, match="evidence"):
        write_batch(NoGraph(), tampered)


def test_symmetric_relation_is_written_from_smaller_to_larger_id():
    batch = FIXTURE.batch("extraction_with_violations.json")
    for relation in batch.relations:
        source, target = relation_endpoints(relation)
        if relation.type in (RelationType.CONFLICTS_WITH, RelationType.DUPLICATES):
            assert source < target
        else:
            assert (source, target) == (relation.source.id, relation.target.id)


def provenance(origin: Origin, *chunks: str, quote: str | None = "x", note: str | None = None) -> Provenance:
    return Provenance(origin=origin, note=note,
                      evidence=[Evidence(source_id=SRC, chunk_id=c, quote=quote) for c in chunks])


def test_merge_accumulates_evidence_and_weakens_origin():
    merged = merge_provenance(provenance(Origin.EXTRACTED_FACT, C1), provenance(Origin.EXTRACTED_FACT, C1, C3))
    assert merged.origin is Origin.EXTRACTED_FACT
    assert [e.chunk_id for e in merged.evidence] == sorted([C1, C3])
    mixed = merge_provenance(provenance(Origin.EXTRACTED_FACT, C1), provenance(Origin.SYSTEM_INFERENCE, C2, quote=None))
    assert mixed.origin is Origin.SYSTEM_INFERENCE and len(mixed.evidence) == 2
    decided = merge_provenance(provenance(Origin.RESEARCHER_DECISION, C1, note="decidido"),
                               provenance(Origin.EXTRACTED_FACT, C2))
    assert decided.origin is Origin.RESEARCHER_DECISION and decided.note == "decidido"
    assert merge_provenance(None, provenance(Origin.EXTRACTED_FACT, C1)) == provenance(Origin.EXTRACTED_FACT, C1)


def test_recorded_output_uses_graph_ids_and_drops_system_relations():
    batch = FIXTURE.batch("extraction_output.json")
    recorded = recorded_output(batch)
    assert [r.key for r in recorded.requirements] == [r.requirement_id for r in batch.requirements]
    assert len(recorded.relations) == 3
    assert check_all(recorded, FIXTURE.corpus) == []


def involved(subject: str) -> set[str]:
    return set(re.split(r"\||,|->", subject))


def to_graph_subject(rule_id: str, subject: str, key_to_id: dict[str, str]) -> str:
    if rule_id == "K1":
        return "|".join(sorted(key_to_id[k] for k in subject.split("|")))
    if rule_id in ("K3", "K4"):
        return ",".join(sorted(key_to_id[k] for k in subject.split(",")))
    if rule_id == "K5":
        return "->".join(key_to_id[k] for k in subject.split("->"))
    return key_to_id[subject]


def test_divergence_by_design_is_only_what_persist_filtered():
    """Toda violação das regras sobre a resposta inteira está no lado gravado ou tem um motivo de filtro."""
    output = FIXTURE.outputs["extraction_with_violations.json"]
    batch = FIXTURE.batch("extraction_with_violations.json")
    rejected = {r.subject for r in batch.rejected}
    recorded = {(v.rule_id, v.subject) for v in check_all(recorded_output(batch), FIXTURE.corpus)}
    kept, lost = set(), {}
    for v in check_all(output, FIXTURE.corpus):
        if involved(v.subject) & rejected:
            lost[(v.rule_id, v.subject)] = "recusado por to_records"
        elif v.rule_id in ("P2", "P3", "P4"):
            lost[(v.rule_id, v.subject)] = "evidência filtrada ou origem rebaixada por to_records"
        else:
            kept.add((v.rule_id, to_graph_subject(v.rule_id, v.subject, batch.key_to_id)))
    assert kept == recorded
    assert sorted(lost) == [("C1", "R2"), ("C2", "R2"), ("C4", "R2"), ("K2", "relations.4"), ("K3", "R1,R3"),
                            ("K5", "R1->R3"), ("P1", "R3"), ("P2", "R4"), ("P3", "R2"), ("P4", "R4"),
                            ("P5", "relations.2")]


def test_alias_divergence_graph_sees_a_cycle_the_keys_hide():
    output = aliased_output(FIXTURE)
    batch = to_records(output, FIXTURE.corpus, 0.6)
    assert [r.rule_id for r in batch.rejected] == ["W6"]
    assert [v.rule_id for v in check_all(output, FIXTURE.corpus)] == []
    assert [v.rule_id for v in check_all(recorded_output(batch), FIXTURE.corpus)] == ["K3"]
