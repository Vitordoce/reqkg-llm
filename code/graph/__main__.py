"""Comandos do grafo. A partir da raiz do repositório:

    PYTHONPATH=code .venv/bin/python -m graph schema    # cria constraints e índices
    PYTHONPATH=code .venv/bin/python -m graph fixture   # apaga o grafo do projeto, grava o fixture duas vezes
    PYTHONPATH=code .venv/bin/python -m graph gaps      # relatório de lacunas do grafo atual
"""

import sys

from graph.connection import Graph, Neo4jSettings
from graph.fixture import exclusive_database, load_fixture, write_fixture
from graph.queries import gap_report
from graph.schema import ensure_schema
from graph.state import logical_state
from graph.writer import clear_graph


def main(argv: list[str]) -> int:
    command = argv[0] if argv else ""
    if command not in ("schema", "fixture", "gaps"):
        print(__doc__)
        return 2
    with Graph(Neo4jSettings.from_env()) as graph:
        ensure_schema(graph)
        if command == "fixture":
            fixture = load_fixture()
            with exclusive_database():
                clear_graph(graph)
                write_fixture(graph, fixture)
                first = logical_state(graph)
                write_fixture(graph, fixture)
                second = logical_state(graph)
            print(f"nós: {first.nodes}\narestas: {first.relations}\nhash: {first.digest}")
            print("segunda carga: mesmo estado lógico" if first == second else f"segunda carga divergiu: {second}")
            if first != second:
                return 1
        if command in ("fixture", "gaps"):
            for violation in gap_report(graph).violations():
                print(f"{violation.rule_id}\t{violation.subject}\t{violation.detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
