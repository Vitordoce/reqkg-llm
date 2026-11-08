"""Recuperação local no Neo4j, inspirada no nível baixo do LightRAG.

A semente fica no rank 0. A expansão segue, sem direção, as arestas de TRAVERSED até max_hops
saltos, e o rank de cada nó é a distância mínima em saltos até a semente. CONTAINS e DERIVED_FROM
ficam de fora: elas passam pelo documento, e o documento leva a todos os chunks dele.

Os itens são os nós alcançados e as relações do contrato entre eles. A seleção sob o limite
ordena por (rank, prioridade do tipo, item_id), e a saída volta à ordem (rank, item_id) do contrato.

A vista (View) esconde chunks e fontes. Ela tira do caminho o que uma invalidação desses chunks
tiraria do grafo (graph.writer.invalidate_chunks): evidência fora da vista não conta, nó sem
evidência restante sai, e requisito cuja evidência primária ficou fora da vista sai.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from domain.enums import ContextStrategy, NodeKind, RelationType
from domain.llm_io import ContextItem, RetrievedContext
from domain.models import Evidence, primary_evidence
from graph.connection import Graph
from graph.properties import decode_evidence
from graph.schema import LABELS, SUPPORTS

KIND_OF_LABEL = {label: kind for kind, (label, _) in LABELS.items()}
KEY_OF_KIND = {kind: key for kind, (_, key) in LABELS.items()}

TRAVERSED = tuple(sorted({
    *(t.neo4j_type for t in RelationType if t is not RelationType.DERIVED_FROM),
    SUPPORTS,
}))
# MENTIONS liga o chunk à entidade, e o item da entidade já cita o chunk.
RELATION_ITEMS = tuple(sorted(t.neo4j_type for t in RelationType
                              if t not in (RelationType.DERIVED_FROM, RelationType.MENTIONS)))
RELATION_OF_TYPE = {t.neo4j_type: t for t in RelationType}

KIND_PRIORITY = {
    NodeKind.REQUIREMENT: 0,
    NodeKind.SOURCE_CHUNK: 1,
    "relation": 2,
    NodeKind.ACTOR: 3,
    NodeKind.SOFTWARE_COMPONENT: 4,
    NodeKind.QUALITY_ATTRIBUTE: 5,
    NodeKind.ENTITY: 6,
}
LABEL_CHARS = 160

NEIGHBORS = (
    "UNWIND $frontier AS eid MATCH (n) WHERE elementId(n) = eid "
    "MATCH (n)-[r]-(m) WHERE type(r) IN $types "
    "RETURN eid AS source, elementId(m) AS target, type(r) AS type, r.evidence_json AS evidence_json, "
    "labels(m) AS labels, properties(m) AS props ORDER BY source, target, type"
)
INDUCED = (
    "UNWIND $eids AS eid MATCH (a) WHERE elementId(a) = eid "
    "MATCH (a)-[r]->(b) WHERE elementId(b) IN $eids AND type(r) IN $types "
    "RETURN elementId(a) AS a, elementId(b) AS b, type(r) AS type, r.relation_id AS relation_id, "
    "r.evidence_json AS evidence_json ORDER BY relation_id"
)
SEED_REQUIREMENT = (
    "MATCH (q:Requirement {requirement_id: $id}) "
    f"OPTIONAL MATCH (c:SourceChunk)-[:{SUPPORTS}]->(q) "
    "RETURN elementId(q) AS eid, properties(q) AS props, "
    "collect(CASE WHEN c IS NULL THEN NULL ELSE {eid: elementId(c), props: properties(c)} END) AS chunks"
)
SEED_CHUNKS = "MATCH (c:SourceChunk) WHERE c.chunk_id IN $ids RETURN elementId(c) AS eid, properties(c) AS props"


class RetrievalError(RuntimeError):
    pass


TAINTABLE = (NodeKind.ACTOR, NodeKind.SOFTWARE_COMPONENT, NodeKind.ENTITY)


@dataclass(frozen=True)
class View:
    """excluded_chunks e sources escondem chunks e evidência. tainted_chunks tira inteiro o ator, componente
    ou entidade com qualquer evidência nesses chunks. quality_attributes = False tira os atributos de qualidade
    (e com eles as arestas MEASURED_BY)."""

    excluded_chunks: frozenset[str] = frozenset()
    sources: frozenset[str] | None = None
    tainted_chunks: frozenset[str] = frozenset()
    quality_attributes: bool = True

    def allows(self, source_id: str, chunk_id: str) -> bool:
        return chunk_id not in self.excluded_chunks and (self.sources is None or source_id in self.sources)

    def evidence(self, evidence: list[Evidence]) -> list[Evidence]:
        return [e for e in evidence if self.allows(e.source_id, e.chunk_id)]


@dataclass(frozen=True)
class Node:
    eid: str
    kind: NodeKind
    key: str
    props: Mapping
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class RequirementChunk:
    """Chunk que é ele mesmo um requisito (PROMISE). O item usa item_id e o texto do chunk."""

    item_id: str
    text: str


def node_in_view(eid: str, labels: Sequence[str], props: Mapping, view: View) -> Node | None:
    kind = KIND_OF_LABEL.get(labels[0]) if len(labels) == 1 else None
    if kind is None or kind is NodeKind.SOURCE_DOCUMENT:
        return None
    key = props[KEY_OF_KIND[kind]]
    if kind is NodeKind.SOURCE_CHUNK:
        if not view.allows(props["source_id"], key):
            return None
        return Node(eid, kind, key, props, (Evidence(source_id=props["source_id"], chunk_id=key),))
    if kind is NodeKind.QUALITY_ATTRIBUTE:
        return Node(eid, kind, key, props, ()) if view.quality_attributes else None
    evidence = decode_evidence(props["evidence_json"])
    if kind in TAINTABLE and any(e.chunk_id in view.tainted_chunks for e in evidence):
        return None
    remaining = view.evidence(evidence)
    if not remaining:
        return None
    if kind is NodeKind.REQUIREMENT:
        primary = primary_evidence(evidence)
        if not view.allows(primary.source_id, primary.chunk_id):
            return None
    return Node(eid, kind, key, props, tuple(remaining))


def edge_in_view(evidence_json: str | None, view: View) -> list[Evidence] | None:
    """Evidência da aresta dentro da vista. SUPPORTS não tem evidência e vale pelos dois nós."""
    if evidence_json is None:
        return []
    remaining = view.evidence(decode_evidence(evidence_json))
    return remaining or None


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= LABEL_CHARS else text[:LABEL_CHARS - 1].rstrip() + "…"


def node_text(node: Node) -> str:
    p = node.props
    match node.kind:
        case NodeKind.REQUIREMENT:
            return p["statement"]
        case NodeKind.SOURCE_CHUNK:
            return p["text"]
        case NodeKind.ACTOR:
            return f"{p['name']} ({p['kind']})"
        case NodeKind.SOFTWARE_COMPONENT:
            return f"{p['name']}: {p['description']}" if p.get("description") else p["name"]
        case NodeKind.ENTITY:
            text = f"{p['name']} ({p['entity_type']})"
            return f"{text}: {p['description']}" if p.get("description") else text
        case NodeKind.QUALITY_ATTRIBUTE:
            return p["category"]
    raise RetrievalError(f"nó {node.key} de tipo {node.kind} sem texto")


def select(items: Sequence[ContextItem], limit: int) -> list[ContextItem]:
    """Os limit primeiros por (rank, prioridade do tipo, item_id), devolvidos em (rank, item_id).

    Os itens de rank 0 (a semente, que contém o contexto de LLM-only) entram todos: se não couberem no
    limite, é erro de configuração, não corte.
    """
    seeds = sum(1 for i in items if i.rank == 0)
    if seeds > limit:
        raise RetrievalError(f"{seeds} itens na semente passam de retrieval.max_items = {limit}; o contexto de "
                             "REQKG-grounded deixaria de conter o de LLM-only")
    chosen = sorted(items, key=lambda i: (i.rank, KIND_PRIORITY[i.kind], i.item_id))[:limit]
    return sorted(chosen, key=lambda i: (i.rank, i.item_id))


@dataclass
class _Walk:
    view: View
    rank: dict[str, int] = field(default_factory=dict)
    nodes: dict[str, Node] = field(default_factory=dict)

    def visit(self, node: Node, rank: int) -> bool:
        if node.eid in self.rank:
            return False
        self.rank[node.eid] = rank
        self.nodes[node.eid] = node
        return True


def _seed_requirement(graph: Graph, requirement_id: str, walk: _Walk) -> Node | None:
    found = graph.rows(SEED_REQUIREMENT, id=requirement_id)
    if not found:
        return None
    row = found[0]
    requirement = node_in_view(row["eid"], ["Requirement"], row["props"], walk.view)
    if requirement is None:
        return None
    walk.visit(requirement, 0)
    for chunk in sorted(row["chunks"], key=lambda c: c["props"]["chunk_id"]):
        node = node_in_view(chunk["eid"], ["SourceChunk"], chunk["props"], walk.view)
        if node is not None:
            walk.visit(node, 0)
    return requirement


def _seed_chunks(graph: Graph, chunk_ids: Sequence[str], walk: _Walk) -> None:
    found = {r["props"]["chunk_id"]: r for r in graph.rows(SEED_CHUNKS, ids=sorted(set(chunk_ids)))}
    missing = sorted(set(chunk_ids) - set(found))
    if missing:
        raise RetrievalError(f"chunks da chamada de extração fora do grafo, grave os documentos do caso antes: {missing}")
    for chunk_id in sorted(found):
        node = node_in_view(found[chunk_id]["eid"], ["SourceChunk"], found[chunk_id]["props"], walk.view)
        if node is not None:
            walk.visit(node, 0)


def _expand(graph: Graph, walk: _Walk, max_hops: int) -> None:
    """O atributo de qualidade é folha: entra como item, mas não leva aos outros requisitos da mesma categoria."""
    frontier = sorted(walk.rank)
    for hop in range(1, max_hops + 1):
        if not frontier:
            return
        reached = []
        for row in graph.rows(NEIGHBORS, frontier=frontier, types=list(TRAVERSED)):
            if row["target"] in walk.rank or edge_in_view(row["evidence_json"], walk.view) is None:
                continue
            node = node_in_view(row["target"], row["labels"], row["props"], walk.view)
            if node is not None and walk.visit(node, hop):
                reached.append(node)
        frontier = sorted(n.eid for n in reached if n.kind is not NodeKind.QUALITY_ATTRIBUTE)


def local_context(
    graph: Graph,
    *,
    query: str,
    max_items: int,
    max_hops: int,
    seed_requirement: str | None = None,
    seed_chunks: Sequence[str] = (),
    view: View = View(),
    requirement_chunks: Mapping[str, RequirementChunk] | None = None,
) -> tuple[RetrievedContext, str]:
    """Contexto local e a semente usada ("requirement" se o nó do requisito entrou, senão "chunks").

    Semente, toda no rank 0: o nó do requisito com os chunks que o sustentam, se ele existir na vista,
    e sempre os chunks de seed_chunks. O nó do requisito semente não vira item, porque o alvo já está
    no prompt. Com requirement_chunks, o chunk listado e todo requisito cuja evidência primária está
    nele viram um único item, com o item_id e o texto dados.
    """
    requirement_chunks = requirement_chunks or {}
    walk = _Walk(view)
    target = _seed_requirement(graph, seed_requirement, walk) if seed_requirement else None
    _seed_chunks(graph, seed_chunks, walk)
    _expand(graph, walk, max_hops)

    items: dict[str, ContextItem] = {}
    label: dict[str, str] = {}

    def add(item: ContextItem) -> None:
        if item.item_id not in items or item.rank < items[item.item_id].rank:
            items[item.item_id] = item

    for eid, node in sorted(walk.nodes.items()):
        rank = walk.rank[eid]
        if node.kind is NodeKind.QUALITY_ATTRIBUTE:
            label[eid] = node_text(node)
            continue
        primary = primary_evidence(list(node.evidence))
        alias = requirement_chunks.get(primary.chunk_id) if node.kind in (
            NodeKind.REQUIREMENT, NodeKind.SOURCE_CHUNK) else None
        if alias is not None:
            item = ContextItem(item_id=alias.item_id, kind=NodeKind.REQUIREMENT, rank=rank, text=alias.text,
                               source_id=primary.source_id, chunk_id=primary.chunk_id)
        else:
            item = ContextItem(item_id=node.key, kind=node.kind, rank=rank, text=node_text(node),
                               source_id=primary.source_id, chunk_id=primary.chunk_id)
        label[eid] = _short(item.text)
        if target is None or eid != target.eid:
            add(item)

    quality_evidence: dict[str, list[Evidence]] = {}
    for row in graph.rows(INDUCED, eids=sorted(walk.nodes), types=list(RELATION_ITEMS)):
        evidence = edge_in_view(row["evidence_json"], walk.view)
        if not evidence:
            continue
        relation = RELATION_OF_TYPE[row["type"]]
        a, b = row["a"], row["b"]
        if relation is RelationType.MEASURED_BY:
            quality_evidence.setdefault(b, []).extend(evidence)
        primary = primary_evidence(evidence)
        add(ContextItem(item_id=row["relation_id"], kind="relation", rank=max(walk.rank[a], walk.rank[b]),
                        text=f"{label[a]} --{relation.value}--> {label[b]}",
                        source_id=primary.source_id, chunk_id=primary.chunk_id))

    for eid, evidence in quality_evidence.items():
        node, primary = walk.nodes[eid], primary_evidence(evidence)
        add(ContextItem(item_id=node.key, kind=node.kind, rank=walk.rank[eid], text=node_text(node),
                        source_id=primary.source_id, chunk_id=primary.chunk_id))

    context = RetrievedContext(query=query, strategy=ContextStrategy.GRAPH_LOCAL, limit=max_items,
                               items=select(list(items.values()), max_items))
    return context, "requirement" if target is not None else "chunks"
