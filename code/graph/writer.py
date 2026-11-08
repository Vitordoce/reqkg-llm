"""Escrita idempotente do ReqKG no Neo4j e invalidação incremental por chunk.

Tudo é MERGE pelos identificadores do contrato, dentro de uma transação por chamada. Se uma
ponta, um chunk ou um documento faltar, a transação inteira volta e nada fica pela metade.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from neo4j import ManagedTransaction
from pydantic import BaseModel

from domain.enums import RELATION_ENDPOINTS, NodeKind, RelationType
from domain.models import Evidence, Provenance, Relation, SourceChunk, SourceDocument, primary_evidence
from domain.persist import PersistBatch
from graph.connection import Graph, rows
from graph.properties import (
    MODEL_OF_KIND,
    GraphWriteError,
    decode_evidence,
    encode_evidence,
    merge_provenance,
    node_key,
    node_props,
    provenance_from_props,
    relation_endpoints,
    relation_props,
)
from graph.schema import CONTAINS, LABELS, OWN_LABELS, SUPPORTS

PROVENANCE_KINDS = (NodeKind.REQUIREMENT, NodeKind.ACTOR, NodeKind.SOFTWARE_COMPONENT, NodeKind.ENTITY)


def upsert_nodes_query(kind: NodeKind) -> str:
    label, key = LABELS[kind]
    return (f"UNWIND $rows AS row MERGE (n:{label} {{{key}: row.key}}) "
            "SET n = row.props RETURN count(n) AS written")


def existing_nodes_query(kind: NodeKind) -> str:
    label, key = LABELS[kind]
    return (f"MATCH (n:{label}) WHERE n.{key} IN $keys RETURN n.{key} AS key, n.origin AS origin, "
            "n.validation AS validation, n.note AS note, n.evidence_json AS evidence_json")


def upsert_relations_query(relation: RelationType) -> str:
    source_kind, target_kind = RELATION_ENDPOINTS[relation]
    (source_label, source_key), (target_label, target_key) = LABELS[source_kind], LABELS[target_kind]
    return (f"UNWIND $rows AS row MATCH (a:{source_label} {{{source_key}: row.source}}) "
            f"MATCH (b:{target_label} {{{target_key}: row.target}}) "
            f"MERGE (a)-[r:{relation.neo4j_type} {{relation_id: row.props.relation_id}}]->(b) "
            "SET r = row.props RETURN count(r) AS written")


def existing_relations_query(relation: RelationType) -> str:
    return (f"MATCH ()-[r:{relation.neo4j_type}]->() WHERE r.relation_id IN $keys RETURN r.relation_id AS key, "
            "r.origin AS origin, r.validation AS validation, r.note AS note, r.evidence_json AS evidence_json")


CONTAINS_QUERY = (f"UNWIND $rows AS row MATCH (d:SourceDocument {{source_id: row.source}}) "
                  f"MATCH (c:SourceChunk {{chunk_id: row.chunk}}) MERGE (d)-[r:{CONTAINS}]->(c) "
                  "RETURN count(r) AS written")
SUPPORTS_QUERY = (f"UNWIND $rows AS row MATCH (c:SourceChunk {{chunk_id: row.chunk}}) "
                  f"MATCH (q:Requirement {{requirement_id: row.requirement}}) MERGE (c)-[r:{SUPPORTS}]->(q) "
                  "RETURN count(r) AS written")
STALE_CHUNKS_QUERY = (f"MATCH (d:SourceDocument)-[:{CONTAINS}]->(c:SourceChunk) "
                      "WHERE d.source_id IN $sources AND NOT c.chunk_id IN $chunks "
                      "RETURN c.chunk_id AS chunk_id ORDER BY chunk_id")
EVIDENCE_CHECK_QUERY = ("UNWIND $pairs AS p OPTIONAL MATCH (c:SourceChunk {chunk_id: p.chunk_id}) "
                        "RETURN p.chunk_id AS chunk_id, p.source_id AS source_id, c.source_id AS actual")


@dataclass(frozen=True)
class WriteSummary:
    nodes: dict[str, int]
    relations: dict[str, int]


def _revalidate[M: BaseModel](model: M) -> M:
    """Revalida o registro. Um model_construct sem validação não passa daqui."""
    return type(model).model_validate(model.model_dump())


def _write_rows(tx: ManagedTransaction, query: str, rows_: list[dict], what: str) -> int:
    if not rows_:
        return 0
    written = tx.run(query, {"rows": rows_}).single()["written"]
    if written != len(rows_):
        raise GraphWriteError(f"{what}: {len(rows_)} linhas, {written} gravadas. Falta uma ponta no grafo")
    return written


def write_documents(graph: Graph, documents: list[SourceDocument], chunks: list[SourceChunk]) -> WriteSummary:
    """Grava documentos e a lista completa de chunks de cada um, com a aresta CONTAINS.

    Chunk antigo do mesmo documento que não está na lista faz a escrita falhar. Ele tem de sair
    antes por invalidate_chunks, para que o que derivou dele saia junto.
    """
    documents = [_revalidate(d) for d in documents]
    chunks = [_revalidate(c) for c in chunks]
    sources = {d.source_id for d in documents}
    if len(sources) != len(documents):
        raise GraphWriteError("documento repetido na mesma escrita")
    orphans = sorted({c.chunk_id for c in chunks if c.source_id not in sources})
    if orphans:
        raise GraphWriteError(f"chunks sem o documento na mesma escrita: {orphans}")

    def work(tx: ManagedTransaction) -> WriteSummary:
        stale = [r["chunk_id"] for r in rows(tx, STALE_CHUNKS_QUERY, sources=sorted(sources),
                                             chunks=sorted(c.chunk_id for c in chunks))]
        if stale:
            raise GraphWriteError(f"chunks antigos no grafo, rode invalidate_chunks antes: {stale}")
        n_docs = _write_rows(tx, upsert_nodes_query(NodeKind.SOURCE_DOCUMENT),
                             [{"key": d.source_id, "props": node_props(d)} for d in documents], "SourceDocument")
        n_chunks = _write_rows(tx, upsert_nodes_query(NodeKind.SOURCE_CHUNK),
                               [{"key": c.chunk_id, "props": node_props(c)} for c in chunks], "SourceChunk")
        n_contains = _write_rows(tx, CONTAINS_QUERY,
                                 [{"source": c.source_id, "chunk": c.chunk_id} for c in chunks], CONTAINS)
        return WriteSummary({"SourceDocument": n_docs, "SourceChunk": n_chunks}, {CONTAINS: n_contains})

    return graph.write(work)


def _existing(tx: ManagedTransaction, query: str, keys: list[str]) -> dict[str, Provenance]:
    return {r["key"]: provenance_from_props(r) for r in rows(tx, query, keys=keys) if r["evidence_json"]}


def _check_evidence(tx: ManagedTransaction, evidence: Iterable[Evidence]) -> None:
    pairs = sorted({(e.chunk_id, e.source_id) for e in evidence})
    found = rows(tx, EVIDENCE_CHECK_QUERY, pairs=[{"chunk_id": c, "source_id": s} for c, s in pairs])
    missing = sorted(r["chunk_id"] for r in found if r["actual"] is None)
    if missing:
        raise GraphWriteError(f"evidência cita chunks fora do grafo, grave os documentos antes: {missing}")
    foreign = sorted(r["chunk_id"] for r in found if r["actual"] != r["source_id"])
    if foreign:
        raise GraphWriteError(f"evidência cita chunk de outra fonte: {foreign}")


def write_batch(graph: Graph, batch: PersistBatch) -> WriteSummary:
    """Grava os registros de domain.persist.to_records. As recusas do lote não entram no grafo.

    O mesmo nó ou relação vindo de outro lote acumula a evidência (merge_provenance). Os demais
    campos ficam com o valor do lote mais novo.
    """
    batch = _revalidate(batch)
    nodes: dict[NodeKind, list[BaseModel]] = {
        NodeKind.REQUIREMENT: batch.requirements, NodeKind.ACTOR: batch.actors,
        NodeKind.SOFTWARE_COMPONENT: batch.components, NodeKind.ENTITY: batch.entities,
    }
    relations: dict[RelationType, list[Relation]] = defaultdict(list)
    for relation in batch.relations:
        relation_props(relation)
        relations[relation.type].append(relation)

    def work(tx: ManagedTransaction) -> WriteSummary:
        _check_evidence(tx, [e for models in nodes.values() for m in models for e in m.provenance.evidence]
                        + [e for r in batch.relations for e in r.provenance.evidence])
        node_counts: dict[str, int] = {}
        supports = []
        for kind, models in nodes.items():
            merged: dict[str, BaseModel] = {}
            existing = _existing(tx, existing_nodes_query(kind), sorted({node_key(m)[1] for m in models}))
            for model in models:
                key = node_key(model)[1]
                previous = merged[key].provenance if key in merged else existing.get(key)
                update = {"provenance": merge_provenance(previous, model.provenance)}
                merged[key] = MODEL_OF_KIND[kind].model_validate(model.model_copy(update=update).model_dump())
            label = LABELS[kind][0]
            node_counts[label] = _write_rows(tx, upsert_nodes_query(kind),
                                             [{"key": k, "props": node_props(m)} for k, m in sorted(merged.items())],
                                             label)
            if kind is NodeKind.REQUIREMENT:
                supports = sorted({(e.chunk_id, k) for k, m in merged.items() for e in m.provenance.evidence})
        node_counts["QualityAttribute"] = _write_rows(
            tx, upsert_nodes_query(NodeKind.QUALITY_ATTRIBUTE),
            [{"key": node_key(q)[1], "props": node_props(q)} for q in batch.quality_attributes], "QualityAttribute")

        relation_counts: dict[str, int] = {}
        for kind, items in sorted(relations.items()):
            existing = _existing(tx, existing_relations_query(kind), sorted({r.relation_id for r in items}))
            merged_rows: dict[str, dict] = {}
            for relation in items:
                previous = existing.get(relation.relation_id)
                if relation.relation_id in merged_rows:
                    previous = provenance_from_props(merged_rows[relation.relation_id]["props"])
                source, target = relation_endpoints(relation)
                props = relation_props(relation, merge_provenance(previous, relation.provenance))
                merged_rows[relation.relation_id] = {"source": source, "target": target, "props": props}
            relation_counts[kind.neo4j_type] = _write_rows(
                tx, upsert_relations_query(kind), [merged_rows[k] for k in sorted(merged_rows)], kind.neo4j_type)
        relation_counts[SUPPORTS] = _write_rows(
            tx, SUPPORTS_QUERY, [{"chunk": c, "requirement": r} for c, r in supports], SUPPORTS)
        return WriteSummary(node_counts, relation_counts)

    return graph.write(work)


@dataclass
class InvalidationReport:
    source_id: str
    removed_chunks: list[str] = field(default_factory=list)
    deleted_nodes: list[str] = field(default_factory=list)
    pruned_nodes: list[str] = field(default_factory=list)
    deleted_relations: list[str] = field(default_factory=list)
    pruned_relations: list[str] = field(default_factory=list)
    # Requisitos apagados porque o chunk da evidência primária saiu, mesmo com evidência em outro chunk.
    deleted_by_primary: list[str] = field(default_factory=list)


def _prune(tx: ManagedTransaction, match: str, key: str, removed: set[str],
           identity_from_primary: bool = False) -> tuple[list[str], list[dict], list[str]]:
    """Devolve as chaves a apagar, as linhas a atualizar e as chaves apagadas pela evidência primária.

    O identificador do requisito vem do chunk da evidência primária. Sem esse chunk, o requisito
    sai, e a nova extração do parágrafo alterado o grava de novo com o identificador certo.
    """
    found = rows(tx, f"{match} WHERE any(c IN x.evidence_chunk_ids WHERE c IN $removed) "
                     f"RETURN x.{key} AS key, x.evidence_json AS evidence_json ORDER BY key",
                 removed=sorted(removed))
    doomed, updates, by_primary = [], [], []
    for row in found:
        evidence = decode_evidence(row["evidence_json"])
        remaining = [e for e in evidence if e.chunk_id not in removed]
        if remaining and identity_from_primary and primary_evidence(evidence).chunk_id in removed:
            by_primary.append(row["key"])
        if not remaining or row["key"] in by_primary:
            doomed.append(row["key"])
        else:
            updates.append({"key": row["key"], "evidence_json": encode_evidence(remaining),
                            "evidence_chunk_ids": sorted({e.chunk_id for e in remaining})})
    return doomed, updates, by_primary


def _invalidate(tx: ManagedTransaction, source_id: str, removed_chunk_ids: Iterable[str]) -> InvalidationReport:
    removed = set(removed_chunk_ids)
    report = InvalidationReport(source_id=source_id)
    found = rows(tx, "MATCH (c:SourceChunk) WHERE c.chunk_id IN $removed "
                     "RETURN c.chunk_id AS chunk_id, c.source_id AS source_id", removed=sorted(removed))
    foreign = sorted(r["chunk_id"] for r in found if r["source_id"] != source_id)
    if foreign:
        raise GraphWriteError(f"chunks de outra fonte que não {source_id}: {foreign}")
    report.removed_chunks = sorted(r["chunk_id"] for r in found)

    for kind in sorted(RelationType):
        match = f"MATCH ()-[x:{kind.neo4j_type}]->()"
        empty, updates, _ = _prune(tx, match, "relation_id", removed)
        tx.run(f"{match} WHERE x.relation_id IN $keys DELETE x", keys=empty).consume()
        tx.run(f"UNWIND $rows AS row {match} WHERE x.relation_id = row.key "
               "SET x.evidence_json = row.evidence_json, x.evidence_chunk_ids = row.evidence_chunk_ids",
               rows=updates).consume()
        report.deleted_relations += empty
        report.pruned_relations += [u["key"] for u in updates]

    for kind in PROVENANCE_KINDS:
        label, key = LABELS[kind]
        match = f"MATCH (x:{label})"
        empty, updates, by_primary = _prune(tx, match, key, removed, kind is NodeKind.REQUIREMENT)
        detached = rows(tx, f"{match} WHERE x.{key} IN $keys MATCH (x)-[r]-() WHERE r.relation_id IS NOT NULL "
                            "RETURN DISTINCT r.relation_id AS id", keys=empty)
        tx.run(f"{match} WHERE x.{key} IN $keys DETACH DELETE x", keys=empty).consume()
        tx.run(f"UNWIND $rows AS row {match} WHERE x.{key} = row.key "
               "SET x.evidence_json = row.evidence_json, x.evidence_chunk_ids = row.evidence_chunk_ids",
               rows=updates).consume()
        report.deleted_nodes += empty
        report.pruned_nodes += [u["key"] for u in updates]
        report.deleted_relations += [r["id"] for r in detached]
        report.deleted_by_primary += by_primary

    tx.run("MATCH (c:SourceChunk) WHERE c.chunk_id IN $removed DETACH DELETE c", removed=sorted(removed)).consume()
    orphans = rows(tx, "MATCH (q:QualityAttribute) WHERE NOT EXISTS { (q)<-[:MEASURED_BY]-() } "
                       "WITH q, q.quality_attribute_id AS id DELETE q RETURN id")
    report.deleted_nodes += [r["id"] for r in orphans]

    report.deleted_nodes = sorted(set(report.deleted_nodes))
    report.deleted_relations = sorted(set(report.deleted_relations))
    report.pruned_relations = sorted(set(report.pruned_relations) - set(report.deleted_relations))
    report.pruned_nodes = sorted(report.pruned_nodes)
    report.deleted_by_primary = sorted(report.deleted_by_primary)
    return report


def invalidate_chunks(graph: Graph, source_id: str, removed_chunk_ids: Iterable[str]) -> InvalidationReport:
    """Remove os chunks e o que só tinha evidência neles, numa transação.

    Nó ou relação com evidência parcial perde só a evidência dos chunks removidos. Sem evidência
    restante, sai. Requisito cujo chunk da evidência primária saiu é apagado com suas relações,
    mesmo com evidência em outro chunk. DERIVED_FROM leva só a evidência do próprio documento e
    sai pela mesma poda. Atributo de qualidade sem MEASURED_BY sai. Chunk que já não está no
    grafo é ignorado, então repetir a chamada não muda nada.
    """
    return graph.write(lambda tx: _invalidate(tx, source_id, removed_chunk_ids))


def remove_document(graph: Graph, source_id: str) -> InvalidationReport:
    def work(tx: ManagedTransaction) -> InvalidationReport:
        chunk_ids = [r["chunk_id"] for r in rows(tx, "MATCH (c:SourceChunk {source_id: $source}) "
                                                     "RETURN c.chunk_id AS chunk_id", source=source_id)]
        report = _invalidate(tx, source_id, chunk_ids)
        tx.run("MATCH (d:SourceDocument {source_id: $source}) DETACH DELETE d", source=source_id).consume()
        return report

    return graph.write(work)


def clear_graph(graph: Graph) -> None:
    """Apaga o grafo do projeto. Recusa se houver nó com rótulo que não é do ReqKG."""

    def work(tx: ManagedTransaction) -> None:
        foreign = rows(tx, "MATCH (n) WHERE size(labels(n)) = 0 OR any(l IN labels(n) WHERE NOT l IN $own) "
                           "RETURN DISTINCT labels(n) AS labels LIMIT 5", own=list(OWN_LABELS))
        if foreign:
            raise GraphWriteError(f"o banco tem nós que não são do ReqKG {[r['labels'] for r in foreign]}. "
                                  "Nada foi apagado")
        tx.run("MATCH (n) DETACH DELETE n").consume()

    graph.write(work)
