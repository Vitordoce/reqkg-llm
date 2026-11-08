"""O laço do experimento: amostra estruturada e PROMISE, com as duas condições sobre a mesma extração.

Amostra estruturada, para cada corrida:
1. Limpa o grafo e grava todos os documentos e chunks dos conjuntos de ingestão. O grafo de B só
   tem a corrida atual.
2. Para cada caso (um documento), uma extração compartilhada, sem condição. Resposta válida vira
   lote por to_records, com as recusas W registradas, e é gravada no grafo.
3. Com todos os casos gravados, para cada caso: alvos por refinement_targets, uma vez. Para cada
   condição, um contexto e uma passagem de refinamento por alvo. LLM-only recebe graph=None. O
   refinamento não é gravado no grafo, então todo contexto de B vê o mesmo estado (a extração da
   corrida) e a ordem dos alvos não muda nada.
4. Saída final por condição: a extração com os refinamentos aceitos no lugar dos candidatos.
   Caso com extração inválida gera um FinalRecord sem saída em cada condição.

PROMISE, para cada corrida e projeto: extração do projeto inteiro (compartilhada), grafo limpo com
só esse projeto, classificação compartilhada de cada item escolhido e uma passagem de refinamento
por condição. A vê os outros itens da chamada de extração; B vê esses itens e o grafo do projeto
sem o item.

Ordem das condições: em cada caso (documento da amostra ou item do PROMISE), condition_order
decide pela paridade de sha256(seed:case_id) qual condição roda primeiro, e a posição vai em
condition_position do FinalRecord e do ClassificationRecord.

Tokens nos registros: só as chamadas da própria condição (refinamentos). Extração e primeira
classificação são compartilhadas e ficam em calls.jsonl, com condition nula.
"""

import hashlib
from contextlib import nullcontext
from dataclasses import dataclass

from domain.config import ExperimentConfig
from domain.enums import Condition, RunStatus
from domain.llm_io import ViolationRecord
from domain.persist import PersistBatch, to_records
from domain.rules import refinement_targets
from experiments.records import ClassificationRecord, ContextRecord, FinalRecord, RejectionRecord
from experiments.runner.clients import UsageMeter
from experiments.runner.inputs import Case, PromiseInput, StructuralInput
from experiments.runner.rundir import RunDirectory
from extraction.client import CallTarget
from extraction.pipeline import (
    ClassificationItem,
    ExtractionRun,
    RefinementResult,
    SinglePassGuard,
    apply_refinements,
    classify_item,
    extract_case,
    refine_candidate,
    refine_classification,
    refinement_reasons,
)
from graph.connection import Graph
from graph.fixture import exclusive_database
from graph.schema import ensure_schema
from graph.writer import clear_graph, write_batch, write_documents
from retrieval import CandidateTarget, PromiseTarget, retrieve_context
from retrieval.promise import extract_project, write_project_graph

GRAPH_CONDITIONS = frozenset({Condition.REQKG_GROUNDED})


@dataclass
class Session:
    config: ExperimentConfig
    client: UsageMeter
    run: RunDirectory
    guard: SinglePassGuard
    graph: Graph

    def graph_for(self, condition: Condition) -> Graph | None:
        return self.graph if condition in GRAPH_CONDITIONS else None


def reset_graph(graph: Graph) -> None:
    clear_graph(graph)
    ensure_schema(graph)


def condition_order(config: ExperimentConfig, case_id: str) -> tuple[Condition, ...]:
    """As condições da configuração, invertidas quando sha256(seed:case_id) é ímpar."""
    digest = hashlib.sha256(f"{config.evaluation.seed}:{case_id}".encode("utf-8")).hexdigest()
    return tuple(reversed(config.conditions)) if int(digest, 16) % 2 else tuple(config.conditions)


# Amostra estruturada


def _extract(session: Session, case: Case, run_index: int) -> tuple[ExtractionRun, PersistBatch | None]:
    run = extract_case(case_id=case.case_id, run_index=run_index, chunks=case.chunks, config=session.config,
                       client=session.client, log=session.run.log)
    session.run.append("case_results", run.result)
    if run.result.extraction is None:
        return run, None
    batch = to_records(run.result.extraction, case.corpus, session.config.review.confidence_threshold)
    for rejection in batch.rejected:
        session.run.append("rejections", RejectionRecord(case_id=case.case_id, run_index=run_index, rejection=rejection))
    write_batch(session.graph, batch)
    return run, batch


def _refine_condition(session: Session, case: Case, run_index: int, condition: Condition, position: int,
                      extraction: ExtractionRun, batch: PersistBatch, targets: list[str],
                      sources: frozenset[str]) -> FinalRecord:
    output = extraction.result.extraction
    threshold = session.config.review.confidence_threshold
    by_key = {r.key: r for r in output.requirements}
    results: list[RefinementResult] = []
    for key in targets:
        target = CandidateTarget(key=key, case_chunks=case.chunks, requirement_id=batch.key_to_id.get(key),
                                 sources=sources)
        context = retrieve_context(target, condition, session.config, session.graph_for(condition))
        session.run.append("contexts", ContextRecord(case_id=case.case_id, run_index=run_index, condition=condition,
                                                     target_key=key, context=context))
        result = refine_candidate(case_id=case.case_id, condition=condition, run_index=run_index,
                                  candidate=by_key[key], context=context,
                                  reasons=refinement_reasons(output, case.corpus, key, threshold), corpus=case.corpus,
                                  client=session.client, guard=session.guard, log=session.run.log)
        session.run.append("case_results", result.result)
        results.append(result)
    calls = [CallTarget(case.case_id, condition, run_index, "refinement", key) for key in targets]
    input_tokens, output_tokens = session.client.tokens(calls)
    refused = [r for r in results if r.result.status is RunStatus.OK and not r.accepted]
    return FinalRecord(
        case_id=case.case_id, run_index=run_index, condition=condition, status=RunStatus.OK,
        output=apply_refinements(output, results), targets=targets,
        accepted=[r.candidate.key for r in results if r.accepted],
        refused=[r.candidate.key for r in refused],
        failed=[r.candidate.key for r in results if r.result.status is not RunStatus.OK],
        violations=[ViolationRecord.of(v) for r in refused for v in r.violations],
        input_tokens=input_tokens, output_tokens=output_tokens, condition_position=position,
    )


def run_structural(session: Session, structural: StructuralInput, runs: int) -> None:
    config = session.config
    for run_index in range(runs):
        reset_graph(session.graph)
        write_documents(session.graph, structural.documents, structural.chunks)
        extracted = [(case, *_extract(session, case, run_index)) for case in structural.cases]
        for case, extraction, batch in extracted:
            order = condition_order(config, case.case_id)
            if batch is None:
                for position, condition in enumerate(order):
                    session.run.append("finals", FinalRecord(case_id=case.case_id, run_index=run_index,
                                                             condition=condition, status=extraction.result.status,
                                                             condition_position=position))
                continue
            targets = refinement_targets(extraction.result.extraction, case.corpus, config.review.confidence_threshold)
            for position, condition in enumerate(order):
                final = _refine_condition(session, case, run_index, condition, position, extraction, batch, targets,
                                          structural.sources)
                session.run.append("finals", final)


# PROMISE


def _write_project(session: Session, project, extraction: ExtractionRun, run_index: int) -> None:
    reset_graph(session.graph)
    if extraction.result.extraction is None:
        write_documents(session.graph, [project.document], project.chunks)
        return
    case_id = extraction.result.case_id
    for batch in write_project_graph(session.graph, project, extraction, session.config.review.confidence_threshold):
        for rejection in batch.rejected:
            session.run.append("rejections", RejectionRecord(case_id=case_id, run_index=run_index, rejection=rejection))


def _classify(session: Session, project, item, run_index: int) -> None:
    classification_item = ClassificationItem(item.promise_id, item.text)
    first = classify_item(item=classification_item, run_index=run_index, client=session.client, log=session.run.log)
    session.run.append("case_results", first)
    common = {"promise_id": item.promise_id, "project_id": item.project_id, "run_index": run_index}
    for position, condition in enumerate(condition_order(session.config, item.promise_id)):
        if first.classification is None:
            session.run.append("classifications", ClassificationRecord(**common, condition=condition,
                                                                       status=first.status,
                                                                       condition_position=position))
            continue
        context = retrieve_context(PromiseTarget(item.promise_id, project), condition, session.config,
                                   session.graph_for(condition))
        session.run.append("contexts", ContextRecord(case_id=item.promise_id, run_index=run_index, condition=condition,
                                                     target_key=item.promise_id, context=context))
        refined = refine_classification(item=classification_item, first=first.classification, condition=condition,
                                        run_index=run_index, context=context, client=session.client,
                                        guard=session.guard, log=session.run.log)
        session.run.append("case_results", refined.result)
        input_tokens, output_tokens = session.client.tokens(
            [CallTarget(item.promise_id, condition, run_index, "classification_refinement", item.promise_id)])
        session.run.append("classifications", ClassificationRecord(
            **common, condition=condition, status=RunStatus.OK, initial=first.classification.label,
            final=refined.classification.label, refinement_accepted=refined.accepted,
            refinement_status=refined.result.status,
            violations=[ViolationRecord.of(v) for v in refined.violations],
            input_tokens=input_tokens, output_tokens=output_tokens, condition_position=position,
        ))


def run_promise(session: Session, promise: PromiseInput, runs: int) -> None:
    for run_index in range(runs):
        for project in promise.projects:
            extraction = extract_project(project, run_index=run_index, config=session.config, client=session.client,
                                         log=session.run.log)
            session.run.append("case_results", extraction.result)
            _write_project(session, project, extraction, run_index)
            for item in promise.items[project.project_id]:
                _classify(session, project, item, run_index)


def execute(session: Session, *, structural: StructuralInput | None, structural_runs: int,
            promise: PromiseInput | None, promise_runs: int, hold_lock: bool = True) -> None:
    """Segura graph.fixture.exclusive_database durante toda a corrida, porque ela limpa e grava o banco."""
    with exclusive_database() if hold_lock else nullcontext():
        if structural is not None:
            run_structural(session, structural, structural_runs)
        if promise is not None:
            run_promise(session, promise, promise_runs)
