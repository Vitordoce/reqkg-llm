"""A instância exportada é o estado lógico de uma carga limpa no Neo4j do projeto.

Pula com motivo se o Neo4j não estiver no ar ou se a URI for a porta 7687. Apaga o grafo do
projeto sob a trava exclusive_database.
"""

from pathlib import Path

import pytest

from domain.enums import Condition
from graph.connection import Graph, GraphUnavailable, Neo4jSettings, UnsafeTarget, refuse_user_instance
from graph.fixture import exclusive_database
from graph.schema import ensure_schema
from graph.state import logical_state
from graph.writer import clear_graph, write_batch, write_documents
from deliverables.inputs import Selection, load
from deliverables.instance import build_instance, case_records

FIXTURES = Path(__file__).resolve().parent / "fixtures"


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
                clear_graph(opened)
        except TimeoutError as error:
            pytest.skip(str(error))


@pytest.mark.parametrize("condition", list(Condition))
def test_clean_load_of_the_instance_reaches_the_exported_state(graph, condition):
    inputs = load(Selection("sintetico-entrevista", condition, 0), FIXTURES / "runs", FIXTURES / "experiment.toml")
    cases = case_records(inputs)
    clear_graph(graph)
    ensure_schema(graph)
    write_documents(graph, inputs.documents, inputs.chunks)
    for case in cases:
        write_batch(graph, case.batch)
    state = logical_state(graph)
    nodes, relations, digest = build_instance(inputs, cases).logical_state()
    assert (state.nodes, state.relations) == (nodes, relations)
    assert state.digest == digest
