"""Estado lógico do grafo: contagem por rótulo e tipo e um hash canônico das propriedades.

Dois grafos com o mesmo estado lógico têm os mesmos nós, arestas e propriedades, qualquer que
seja o identificador interno do Neo4j.
"""

import hashlib
import json
from dataclasses import dataclass

from graph.connection import Graph
from graph.schema import KEY_OF_LABEL

NODES_QUERY = "MATCH (n) RETURN labels(n) AS labels, properties(n) AS props"
RELATIONS_QUERY = ("MATCH (a)-[r]->(b) RETURN type(r) AS type, labels(a) AS a_labels, properties(a) AS a, "
                   "labels(b) AS b_labels, properties(b) AS b, properties(r) AS props")


@dataclass(frozen=True)
class LogicalState:
    nodes: dict[str, int]
    relations: dict[str, int]
    digest: str


def node_identity(labels: list[str], props: dict) -> list:
    label = sorted(labels)[0]
    return [label, props.get(KEY_OF_LABEL.get(label, ""))]


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def logical_state(graph: Graph) -> LogicalState:
    nodes = [[sorted(r["labels"]), r["props"]] for r in graph.rows(NODES_QUERY)]
    relations = [
        [r["type"], node_identity(r["a_labels"], r["a"]), node_identity(r["b_labels"], r["b"]), r["props"]]
        for r in graph.rows(RELATIONS_QUERY)
    ]
    nodes.sort(key=canonical)
    relations.sort(key=canonical)
    node_counts: dict[str, int] = {}
    for labels, _ in nodes:
        for label in labels:
            node_counts[label] = node_counts.get(label, 0) + 1
    relation_counts: dict[str, int] = {}
    for relation in relations:
        relation_counts[relation[0]] = relation_counts.get(relation[0], 0) + 1
    digest = hashlib.sha256(canonical({"nodes": nodes, "relations": relations}).encode("utf-8")).hexdigest()
    return LogicalState(dict(sorted(node_counts.items())), dict(sorted(relation_counts.items())), digest)
