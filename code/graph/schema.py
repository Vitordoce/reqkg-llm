"""Rótulos, chaves, constraints e índices do ReqKG no Neo4j."""

from domain.enums import NodeKind, RelationType
from graph.connection import Graph

LABELS: dict[NodeKind, tuple[str, str]] = {
    NodeKind.SOURCE_DOCUMENT: ("SourceDocument", "source_id"),
    NodeKind.SOURCE_CHUNK: ("SourceChunk", "chunk_id"),
    NodeKind.REQUIREMENT: ("Requirement", "requirement_id"),
    NodeKind.ACTOR: ("Actor", "actor_id"),
    NodeKind.SOFTWARE_COMPONENT: ("SoftwareComponent", "component_id"),
    NodeKind.ENTITY: ("Entity", "entity_id"),
    NodeKind.QUALITY_ATTRIBUTE: ("QualityAttribute", "quality_attribute_id"),
}
KEY_OF_LABEL = dict(LABELS.values())
OWN_LABELS = tuple(sorted(KEY_OF_LABEL))

# Estruturais, gravadas pelo sistema e sem relation_id do contrato.
CONTAINS = "CONTAINS"
SUPPORTS = "SUPPORTS"
CONTRACT_TYPES = tuple(sorted(t.neo4j_type for t in RelationType))
OWN_TYPES = tuple(sorted((*CONTRACT_TYPES, CONTAINS, SUPPORTS)))


def node_constraint_name(label: str, key: str) -> str:
    return f"reqkg_{label.lower()}_{key}_unique"


def relation_constraint_name(neo4j_type: str) -> str:
    return f"reqkg_{neo4j_type.lower()}_relation_id_unique"


INDEXES = (("reqkg_sourcechunk_source_id", "SourceChunk", "source_id"),)


def schema_statements() -> list[str]:
    statements = [
        f"CREATE CONSTRAINT {node_constraint_name(label, key)} IF NOT EXISTS "
        f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE"
        for label, key in sorted(LABELS.values())
    ]
    statements += [
        f"CREATE CONSTRAINT {relation_constraint_name(t)} IF NOT EXISTS "
        f"FOR ()-[r:{t}]-() REQUIRE r.relation_id IS UNIQUE"
        for t in CONTRACT_TYPES
    ]
    statements += [
        f"CREATE INDEX {name} IF NOT EXISTS FOR (n:{label}) ON (n.{prop})" for name, label, prop in INDEXES
    ]
    return statements


def expected_names() -> list[str]:
    names = [node_constraint_name(label, key) for label, key in LABELS.values()]
    names += [relation_constraint_name(t) for t in CONTRACT_TYPES]
    return sorted(names + [name for name, _, _ in INDEXES])


def ensure_schema(graph: Graph) -> None:
    """IF NOT EXISTS torna a chamada idempotente. Esquema é DDL e cada comando roda na própria transação."""
    for statement in schema_statements():
        graph.write(lambda tx, s=statement: tx.run(s).consume())
    graph.write(lambda tx: tx.run("CALL db.awaitIndexes(60)").consume())


def present_schema(graph: Graph) -> list[str]:
    constraints = graph.rows("SHOW CONSTRAINTS YIELD name WHERE name STARTS WITH 'reqkg_' RETURN name")
    indexes = graph.rows("SHOW INDEXES YIELD name, owningConstraint "
                         "WHERE name STARTS WITH 'reqkg_' AND owningConstraint IS NULL RETURN name")
    return sorted(r["name"] for r in constraints + indexes)


def drop_schema(graph: Graph) -> None:
    for name in reversed(expected_names()):
        kind = "INDEX" if name in {n for n, _, _ in INDEXES} else "CONSTRAINT"
        graph.write(lambda tx, n=name, k=kind: tx.run(f"DROP {k} {n} IF EXISTS").consume())


def extension_procedures(graph: Graph) -> list[str]:
    """APOC e GDS. A imagem Community do projeto não traz nenhum dos dois."""
    return [r["name"] for r in graph.rows(
        "SHOW PROCEDURES YIELD name WHERE name STARTS WITH 'apoc.' OR name STARTS WITH 'gds.' RETURN name"
    )]
