"""Consultas de completude, proveniência e consistência sobre o grafo gravado.

Cada consulta devolve domain.violations.Violation com o rule_id do domínio e o identificador do
grafo como assunto. K3 e K4 puxam as arestas por Cypher e contam componentes com
domain.rules.strongly_connected, porque a imagem Community não traz APOC nem GDS.

O grafo só tem o que passou por domain.persist.to_records. Para comparar com as regras em
Python sobre os mesmos itens, use recorded_output.
"""

from dataclasses import dataclass

from domain.enums import LLM_RELATIONS, Origin, Priority, RelationType, RequirementType
from domain.llm_io import ExtractionOutput
from domain.persist import PersistBatch
from domain.rules import strongly_connected
from domain.violations import Violation
from graph.connection import Graph
from graph.schema import KEY_OF_LABEL

MISSING_FIELDS = (("C1", "priority"), ("C2", "verification_method"), ("C3", "type"))

C4_QUERY = ("MATCH (r:Requirement {type: $nfr}) WHERE NOT EXISTS { (r)-[:MEASURED_BY]->(:QualityAttribute) } "
            "RETURN r.requirement_id AS id ORDER BY id")
P1_QUERY = ("MATCH (r:Requirement) WHERE NOT EXISTS { (r)-[:DERIVED_FROM]->(:SourceDocument) } "
            "RETURN r.requirement_id AS id ORDER BY id")
P2_NODES_QUERY = ("MATCH (n) WHERE n.evidence_chunk_ids IS NOT NULL UNWIND n.evidence_chunk_ids AS c "
                  "WITH n, c WHERE NOT EXISTS { (:SourceChunk {chunk_id: c}) } "
                  "RETURN [k IN $keys WHERE n[k] IS NOT NULL | n[k]][0] AS id, c AS chunk ORDER BY id, chunk")
P2_RELATIONS_QUERY = ("MATCH ()-[r]->() WHERE r.evidence_chunk_ids IS NOT NULL UNWIND r.evidence_chunk_ids AS c "
                      "WITH r, c WHERE NOT EXISTS { (:SourceChunk {chunk_id: c}) } "
                      "RETURN r.relation_id AS id, c AS chunk ORDER BY id, chunk")
P5_QUERY = ("MATCH ()-[r]->() WHERE r.relation_id IS NOT NULL "
            "AND (r.evidence_chunk_ids IS NULL OR size(r.evidence_chunk_ids) = 0) "
            "RETURN r.relation_id AS id, type(r) AS type ORDER BY id")
K1_QUERY = ("MATCH (a:Requirement)-[:CONFLICTS_WITH]-(b:Requirement) "
            "WHERE a.requirement_id < b.requirement_id AND EXISTS { (a)-[:DUPLICATES]-(b) } "
            "RETURN DISTINCT a.requirement_id AS a, b.requirement_id AS b ORDER BY a, b")
K2_QUERY = ("MATCH (n)-[r]->(n) WHERE r.relation_id IS NOT NULL "
            "RETURN r.relation_id AS id, type(r) AS type, [k IN $keys WHERE n[k] IS NOT NULL | n[k]][0] AS node "
            "ORDER BY id")
K5_QUERY = ("MATCH (a:Requirement {priority: $must})-[:DEPENDS_ON]->(b:Requirement {priority: $wont}) "
            "RETURN a.requirement_id AS a, b.requirement_id AS b ORDER BY a, b")
# Chave de cada rótulo, na ordem em que o identificador é escolhido. SourceChunk também tem
# source_id, então chunk_id vem antes.
NODE_KEYS = sorted(set(KEY_OF_LABEL.values()), key=lambda k: (k == "source_id", k))


def missing_field_query(field: str) -> str:
    return f"MATCH (r:Requirement) WHERE r.{field} IS NULL RETURN r.requirement_id AS id ORDER BY id"


def edges_query(relation: RelationType) -> str:
    return (f"MATCH (a:Requirement)-[:{relation.neo4j_type}]->(b:Requirement) "
            "RETURN a.requirement_id AS a, b.requirement_id AS b ORDER BY a, b")


@dataclass(frozen=True)
class GapReport:
    completeness: list[Violation]
    quality_attribute: list[Violation]
    provenance: list[Violation]
    consistency: list[Violation]

    def violations(self) -> list[Violation]:
        return sorted(self.completeness + self.quality_attribute + self.provenance + self.consistency)


def completeness(graph: Graph) -> list[Violation]:
    """C1 a C3, as que entram na razão de completude."""
    return sorted(Violation(rule_id, row["id"], f"{field} ausente")
                  for rule_id, field in MISSING_FIELDS for row in graph.rows(missing_field_query(field)))


def quality_attribute(graph: Graph) -> list[Violation]:
    """C4, contada à parte da razão de completude."""
    return [Violation("C4", row["id"], "não funcional sem atributo de qualidade")
            for row in graph.rows(C4_QUERY, nfr=RequirementType.NON_FUNCTIONAL.value)]


def provenance(graph: Graph) -> list[Violation]:
    found = [Violation("P1", row["id"], "sem derived_from") for row in graph.rows(P1_QUERY)]
    found += [Violation("P2", row["id"], f"{row['chunk']} não existe no grafo")
              for row in graph.rows(P2_NODES_QUERY, keys=NODE_KEYS) + graph.rows(P2_RELATIONS_QUERY)]
    found += [Violation("P5", row["id"], f"{RelationType(row['type'].lower()).value} sem evidência")
              for row in graph.rows(P5_QUERY)]
    return sorted(found)


def cycles(graph: Graph, relation: RelationType, rule_id: str) -> list[Violation]:
    edges = [(row["a"], row["b"]) for row in graph.rows(edges_query(relation)) if row["a"] != row["b"]]
    return [Violation(rule_id, ",".join(members), f"ciclo em {relation.value}")
            for members in strongly_connected(edges)]


def consistency(graph: Graph) -> list[Violation]:
    found = [Violation("K1", f"{row['a']}|{row['b']}", "conflicts_with e duplicates no mesmo par")
             for row in graph.rows(K1_QUERY)]
    found += [Violation("K2", row["id"], f"{row['type'].lower()} de {row['node']} para ele mesmo")
              for row in graph.rows(K2_QUERY, keys=NODE_KEYS)]
    found += cycles(graph, RelationType.DEPENDS_ON, "K3")
    found += cycles(graph, RelationType.REFINES, "K4")
    found += [Violation("K5", f"{row['a']}->{row['b']}", "must depende de wont")
              for row in graph.rows(K5_QUERY, must=Priority.MUST.value, wont=Priority.WONT.value)]
    return sorted(found)


def gap_report(graph: Graph) -> GapReport:
    return GapReport(completeness(graph), quality_attribute(graph), provenance(graph), consistency(graph))


def recorded_output(batch: PersistBatch) -> ExtractionOutput:
    """O lote gravado de volta como ExtractionOutput, com o identificador do grafo como chave.

    domain.rules.check_all sobre esta saída é o lado Python do teste gêmeo: as mesmas regras,
    sobre os mesmos itens que o grafo recebeu. Relações de sistema ficam fora, porque as regras
    não as leem e ExtractionOutput as recusa.
    """
    def evidence(provenance) -> list[dict]:
        return [e.model_dump() for e in provenance.evidence]

    def origin(provenance) -> Origin:
        if provenance.origin is Origin.RESEARCHER_DECISION:
            raise ValueError("decisão do pesquisador não tem forma de candidato do modelo")
        return provenance.origin

    return ExtractionOutput.model_validate({
        "requirements": [
            {"key": r.requirement_id, "statement": r.statement, "type": r.type, "priority": r.priority,
             "verification_method": r.verification_method, "quality_attributes": r.quality_attributes,
             "quantitative_value": r.quantitative_value, "review_flags": r.review_flags,
             "origin": origin(r.provenance), "evidence": evidence(r.provenance)}
            for r in batch.requirements
        ],
        "actors": [{"key": a.actor_id, "name": a.name, "kind": a.kind, "evidence": evidence(a.provenance)}
                   for a in batch.actors],
        "components": [{"key": c.component_id, "name": c.name, "description": c.description,
                        "evidence": evidence(c.provenance)} for c in batch.components],
        "entities": [{"key": e.entity_id, "name": e.name, "entity_type": e.entity_type,
                      "description": e.description, "evidence": evidence(e.provenance)} for e in batch.entities],
        "relations": [{"type": r.type, "source_key": r.source.id, "target_key": r.target.id,
                       "origin": origin(r.provenance), "evidence": evidence(r.provenance)}
                      for r in batch.relations if r.type in LLM_RELATIONS],
    })
