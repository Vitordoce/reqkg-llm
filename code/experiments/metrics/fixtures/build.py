"""Gera os registros sintéticos dos testes de métricas. Não editar a saída à mão.

A partir da raiz do repositório:

    .venv/bin/python code/experiments/metrics/fixtures/build.py          # grava
    .venv/bin/python code/experiments/metrics/fixtures/build.py --check  # confere sem gravar

Saída: ingestion.json (ingestão de amostra/a01.txt e a02.txt) e duas corridas em runs/:

- fixture-run: três corridas da amostra, casos a01 e a02, duas condições. Na corrida 1 um refinamento
  de LLM-only falha na API; na corrida 2 a extração de a02 é inválida. Os valores esperados de cada
  métrica estão escritos em test_metrics.py. Alguns refinamentos aceitos aqui seriam recusados pela
  regra G6 do executor (evidência de outro documento); eles existem para provar que as métricas medem
  certo um registro assim:
  - REQKG-grounded cita um chunk do outro documento: a01 c1-R2 (corridas 0 e 2, além da evidência
    original) e a02 c1-R3 (no lugar da evidência original). No corpus do caso, as duas viram P2.
  - LLM-only, corridas 0 e 1, preenche método e atributo de a01 c1-R1 e acrescenta uma evidência sem
    citação: tira C3 e C4 e ganha P4, então o alvo não conta como corrigido.
  - contexts.jsonl: textos de tamanho fixo (100 caracteres por chunk da chamada, 50 por item a mais
    de REQKG-grounded: 4 para alvo gravado no grafo, 1 para alvo recusado na gravação).
- fixture-promise: uma corrida de classificação com os itens sintéticos PROMISE-NFR-9001 a 9010, um
  refinamento com erro de API em LLM-only e um com resposta inválida em REQKG-grounded, uma recusa por
  regra G em cada condição, os contextos e o calls.jsonl (extração dos dois projetos em 3 chamadas cada,
  primeira classificação e refinamento da classificação).
"""

import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))

from domain.config import ExperimentConfig  # noqa: E402
from domain.enums import Condition, ContextStrategy, RunStatus  # noqa: E402
from domain.llm_io import CaseResult, ExtractionOutput, ViolationRecord  # noqa: E402
from domain.rules import CorpusIndex, refinement_targets  # noqa: E402
from domain.serialization import canonical_json, load_toml  # noqa: E402
from experiments.records import (  # noqa: E402
    CallRecord, ClassificationRecord, ContextRecord, FinalRecord, RejectionRecord, RunManifest,
)
from ingestion.corpus import ingest, render  # noqa: E402

CONFIG = HERE / "experiment.toml"
SET_FILE = HERE / "conjunto.toml"
INGESTION = HERE / "ingestion.json"
RUNS = HERE / "runs"
STRUCTURAL_RUN = "fixture-run"
PROMISE_RUN = "fixture-promise"
RUN_COUNT = 3
SYNTHETIC_SHA = "0" * 64
A, B = Condition.LLM_ONLY, Condition.REQKG_GROUNDED
# Consumo sintético de cada chamada. A extração põe 100 dos 1000 tokens de entrada no cache.
EXTRACTION_USAGE = {"input_tokens": 900, "cache_read_input_tokens": 100, "output_tokens": 200}
REFINEMENT_USAGE = {A: (100, 20), B: (300, 30)}
CHUNK_ITEM_CHARS, GRAPH_ITEM_CHARS = 100, 50
GRAPH_ITEMS_WRITTEN, GRAPH_ITEMS_REJECTED = 4, 1


class Text:
    def __init__(self, ingested, stem: str) -> None:
        document = next(d for d in ingested.documents if Path(d.path).stem == stem)
        self.source_id = document.source_id
        self.chunks = ingested.chunks_of(document.source_id)

    def chunk(self, index: int) -> str:
        return self.chunks[index].chunk_id

    def ev(self, index: int, quote: str, source_id: str | None = None) -> dict:
        return {"source_id": source_id or self.source_id, "chunk_id": self.chunk(index), "quote": quote}


def req(key, statement, type_, priority, verification, evidence, quality=()) -> dict:
    return {"key": key, "statement": statement, "type": type_, "priority": priority,
            "verification_method": verification, "quality_attributes": list(quality), "evidence": evidence}


def replace(output: dict, **changes: dict) -> dict:
    """Saída final: a extração com os requisitos alterados pelos refinamentos aceitos."""
    requirements = []
    for r in output["requirements"]:
        update = changes.get(r["key"].replace("-", "_"), {})
        requirements.append({**r, **update})
    return {**output, "requirements": requirements}


def extraction_a01(t: Text) -> dict:
    return {
        "requirements": [
            req("c0-R1", "O sistema deve cadastrar cada bandeja com a data de semeadura.", "functional", "must", None,
                [t.ev(1, "toda bandeja semeada precisa ser cadastrada")]),
            req("c1-R1", "A tela de cadastro deve abrir rápido.", "non_functional", None, None,
                [t.ev(2, "a tela de cadastro tem de abrir rápido")]),
            req("c1-R2", "O sistema deve emitir alerta de umidade.", "functional", "should", "test",
                [t.ev(2, "alerta de umidade instantâneo")]),
            req("c2-R1", "O sistema deve funcionar sem internet.", "functional", "could", "demonstration", []),
        ],
        "actors": [{"key": "c0-A1", "name": "Gerente da estufa", "kind": "stakeholder",
                    "evidence": [{"source_id": t.source_id, "chunk_id": "chunk-inexistente", "quote": "Gerente"}]}],
        "relations": [
            {"type": "depends_on", "source_key": "c1-R1", "target_key": "c1-R2",
             "evidence": [t.ev(2, "a tela de cadastro tem de abrir rápido no tablet")]},
            {"type": "depends_on", "source_key": "c1-R2", "target_key": "c1-R1",
             "evidence": [t.ev(2, "a tela de cadastro tem de abrir rápido no tablet")]},
        ],
    }


def extraction_a02(t: Text, other_source: str) -> dict:
    return {
        "requirements": [
            req("c0-R1", "O sistema deve registrar os participantes da reunião.", "functional", "could", "inspection",
                [t.ev(1, "Participantes: gerente, técnica e auditor")]),
            req("c1-R1", "Os registros de semeadura devem ser guardados por dois anos.", "constraint", None, "inspection",
                [t.ev(2, "registros de semeadura devem ser guardados por dois anos")]),
            req("c1-R2", "O sistema deve exportar relatório em planilha.", "functional", "wont", None,
                [t.ev(3, "exportar relatório em planilha")]),
            req("c1-R3", "O sistema deve guardar os registros de semeadura por dois anos.", "constraint", "must",
                "inspection", [t.ev(2, "guardados por dois anos", source_id=other_source)]),
            req("c1-R4", "O sistema deve notificar o auditor sobre cada decisão.", "functional", "could", "inspection",
                [t.ev(2, "Decisão:")]),
        ],
        "relations": [
            {"type": "duplicates", "source_key": "c1-R1", "target_key": "c1-R3",
             "evidence": [t.ev(2, "guardados por dois anos")]},
            {"type": "conflicts_with", "source_key": "c1-R1", "target_key": "c1-R3",
             "evidence": [t.ev(2, "guardados por dois anos")]},
            {"type": "depends_on", "source_key": "c0-R1", "target_key": "c0-R1",
             "evidence": [t.ev(1, "texto que não existe na ata")]},
        ],
    }


def finals_a01(t: Text, other: Text, run_index: int) -> dict:
    extraction = extraction_a01(t)
    fixed_alert = {"evidence": [t.ev(3, "quero um alerta quando a umidade passar do limite")]}
    a_changes = {
        "c0_R1": {"verification_method": "inspection"},
        "c1_R2": fixed_alert,
        "c2_R1": {"rationale": "o contexto não traz a fonte"},
    }
    a_refused = ["c1-R1"]
    if run_index != 2:
        a_changes["c1_R1"] = {"verification_method": "test", "quality_attributes": ["performance"],
                              "evidence": [t.ev(2, "a tela de cadastro tem de abrir rápido"), t.ev(2, None)]}
        a_refused = []
    b_changes = {
        "c0_R1": {"verification_method": "inspection"},
        "c1_R1": {"statement": "A tela de cadastro deve abrir rapidamente no tablet.", "quality_attributes": ["performance"]},
        "c1_R2": {"evidence": [t.ev(2, "alerta de umidade instantâneo"),
                               other.ev(3, "quero um alerta quando a umidade passar do limite")]},
        "c2_R1": {"evidence": [t.ev(4, "hoje a gente anota tudo num caderno")]},
    }
    if run_index == 1:
        b_changes["c1_R2"] = fixed_alert
    targets = ["c0-R1", "c1-R1", "c1-R2", "c2-R1"]
    return {
        A: (replace(extraction, **a_changes), targets, a_refused, []),
        B: (replace(extraction, **b_changes), targets, [], []),
    }


def finals_a02(t: Text, other: Text, run_index: int) -> dict:
    extraction = extraction_a02(t, other.source_id)
    a = replace(extraction, c1_R3={"evidence": [t.ev(2, "os registros de semeadura devem ser guardados por dois anos")]})
    b = replace(extraction, c1_R1={"priority": "must"},
                c1_R2={"statement": "o sistema deve  exportar relatório em planilha.", "verification_method": "inspection"},
                c1_R3={"evidence": [other.ev(4, "guardados por dois anos")]})
    targets = ["c1-R1", "c1-R2", "c1-R3"]
    a_refused, a_failed = (["c1-R2"], []) if run_index != 1 else ([], ["c1-R2"])
    return {A: (a, targets, a_refused, a_failed), B: (b, targets, [], [])}


def filler(length: int) -> str:
    return ("contexto-sintético-" * 10)[:length]


def context_item(item_id: str, kind: str, rank: int, length: int, source_id: str, chunk_id: str) -> dict:
    return {"item_id": item_id, "kind": kind, "rank": rank, "text": filler(length), "source_id": source_id,
            "chunk_id": chunk_id}


def refinement_context(condition: Condition, key: str, call_chunks: list[tuple[str, str]],
                       graph_extra: list[tuple[str, str, str, str]]) -> dict:
    """LLM-only: os chunks da chamada de extração do alvo. REQKG-grounded: os mesmos chunks e graph_extra,
    (item_id, kind, source_id, chunk_id) de cada item a mais vindo do grafo."""
    items = [context_item(chunk_id, "source_chunk", rank, CHUNK_ITEM_CHARS, source_id, chunk_id)
             for rank, (source_id, chunk_id) in enumerate(call_chunks)]
    strategy = ContextStrategy.SOURCE_CHUNKS
    if condition is B:
        strategy = ContextStrategy.GRAPH_LOCAL
        items += [context_item(item_id, kind, len(items) + i, GRAPH_ITEM_CHARS, source_id, chunk_id)
                  for i, (item_id, kind, source_id, chunk_id) in enumerate(graph_extra)]
    return {"query": f"refinar {key}", "strategy": strategy, "limit": 30, "items": items}


def graph_extra(texts: dict[str, Text], case_id: str, key: str, rejected: bool) -> list[tuple[str, str, str, str]]:
    """Itens a mais de REQKG-grounded. O alvo recusado na gravação recebe um único item; nos dois alvos
    que citam o outro documento, é o chunk citado."""
    t = texts[case_id]
    if not rejected:
        kinds = ("actor", "entity", "quality_attribute", "requirement")
        return [(f"{kind}-{key}", kind, t.source_id, t.chunk(1)) for kind in kinds[:GRAPH_ITEMS_WRITTEN]]
    foreign = {("a01", "c1-R2"): ("a02", 3), ("a02", "c1-R3"): ("a01", 4)}
    if (case_id, key) in foreign:
        other, index = foreign[(case_id, key)]
        return [(texts[other].chunk(index), "source_chunk", texts[other].source_id, texts[other].chunk(index))]
    return [(f"actor-{key}", "actor", t.source_id, t.chunk(1))]


def jsonl(models) -> str:
    return "".join(canonical_json(m) for m in models)


def call(case_id, condition, run_index, stage, key, usage: dict | None, meta: dict) -> CallRecord:
    """Linha de calls.jsonl sem prompt de verdade: as métricas leem só alvo, chunks, estado e consumo."""
    output_model = {"extraction": "ExtractionOutput", "refinement": "RefinementOutput"}.get(stage, "ClassificationOutput")
    return CallRecord(
        timestamp="2026-10-10T00:00:00+00:00",
        target={"case_id": case_id, "condition": condition, "run_index": run_index, "stage": stage, "key": key},
        meta=meta, client={"provider": "synthetic", "model_id": "sintetico"},
        prompt_name=stage, prompt_version=2, prompt_template_sha256=SYNTHETIC_SHA, prompt_sha256=SYNTHETIC_SHA,
        output_model=output_model, output_schema_sha256=SYNTHETIC_SHA, user_prompt="sintético",
        status="returned" if usage is not None else "api_error",
        error=None if usage is not None else "APIConnectionError: sintético",
        raw_response="{}" if usage is not None else None, model="sintetico" if usage is not None else None,
        stop_reason="end_turn" if usage is not None else None, usage=usage or {}, response_id=None,
        temperature={"sent": False, "accepted": None},
    )


REFUSED_RECORDS = [("a01", "W1", "c1-R2"), ("a01", "W1", "c2-R1"), ("a01", "W1", "c0-A1"),
                   ("a02", "W1", "c1-R3"), ("a02", "W5", "relations.2")]


def structural_run(ingested, ingestion_bytes: bytes, config: ExperimentConfig) -> dict[str, str]:
    a01, a02 = Text(ingested, "a01"), Text(ingested, "a02")
    calls_of = {"a01": [("c0", [0, 1]), ("c1", [2, 3]), ("c2", [4])], "a02": [("c0", [0, 1]), ("c1", [2, 3])]}
    texts = {"a01": a01, "a02": a02}
    calls, case_results, finals, rejections, contexts = [], [], [], [], []
    for run_index in range(RUN_COUNT):
        invalid = {"a02"} if run_index == 2 else set()
        per_case = {"a01": (extraction_a01(a01), finals_a01(a01, a02, run_index)),
                    "a02": (extraction_a02(a02, a01.source_id), finals_a02(a02, a01, run_index))}
        for case_id, (extraction, by_condition) in per_case.items():
            corpus = CorpusIndex.from_chunks(texts[case_id].chunks)
            call_chunks = {}
            for prefix, indexes in calls_of[case_id]:
                chunk_ids = [texts[case_id].chunk(i) for i in indexes]
                call_chunks[prefix] = [(texts[case_id].source_id, c) for c in chunk_ids]
                calls.append(call(case_id, None, run_index, "extraction", prefix, EXTRACTION_USAGE,
                                  {"chunk_ids": chunk_ids, "chunks_per_call": config.extraction.chunks_per_call}))
            if case_id in invalid:
                case_results.append(CaseResult(case_id=case_id, run_index=run_index, stage="extraction",
                                               status=RunStatus.INVALID_OUTPUT,
                                               error="c1: JSON inválido na linha 1, coluna 2: Expecting value"))
                finals += [FinalRecord(case_id=case_id, run_index=run_index, condition=c,
                                       status=RunStatus.INVALID_OUTPUT) for c in (A, B)]
                continue
            shared = ExtractionOutput.model_validate(extraction)
            case_results.append(CaseResult(case_id=case_id, run_index=run_index, stage="extraction",
                                           status=RunStatus.OK, extraction=shared))
            for condition, (output, targets, refused, failed) in by_condition.items():
                assert targets == refinement_targets(shared, corpus, config.review.confidence_threshold), case_id
                tokens_in, tokens_out = REFINEMENT_USAGE[condition]
                answered = [k for k in targets if k not in failed]
                for key in targets:
                    rejected = any((case_id, key) == (c, s) for c, _, s in REFUSED_RECORDS)
                    context = refinement_context(condition, key, call_chunks[key.split("-", 1)[0]],
                                                 graph_extra(texts, case_id, key, rejected))
                    contexts.append(ContextRecord(case_id=case_id, run_index=run_index, condition=condition,
                                                  target_key=key, context=context))
                    usage = {"input_tokens": tokens_in, "output_tokens": tokens_out} if key in answered else None
                    meta = {"context_item_ids": [i["item_id"] for i in context["items"]],
                            "context_strategy": context["strategy"]}
                    calls.append(call(case_id, condition, run_index, "refinement", key, usage, meta))
                finals.append(FinalRecord(
                    case_id=case_id, run_index=run_index, condition=condition, status=RunStatus.OK,
                    output=ExtractionOutput.model_validate(output), targets=targets,
                    accepted=[k for k in answered if k not in refused], refused=refused, failed=failed,
                    violations=[ViolationRecord(rule_id="G3", subject=k, detail="cita chunk fora do contexto")
                                for k in refused],
                    input_tokens=tokens_in * len(answered), output_tokens=tokens_out * len(answered),
                ))
        rejections += [RejectionRecord(case_id=case_id, run_index=run_index,
                                       rejection={"rule_id": rule, "subject": subject, "detail": "sintético"})
                       for case_id, rule, subject in REFUSED_RECORDS if case_id not in invalid]
    manifest = RunManifest(
        run_id=STRUCTURAL_RUN, model_id="sintetico", replay=True, runs=RUN_COUNT,
        config_sha256=hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        ingestion_sha256=[hashlib.sha256(ingestion_bytes).hexdigest()],
        prompts_registry_sha256=SYNTHETIC_SHA, command="code/experiments/metrics/fixtures/build.py",
    )
    return {
        "manifest.json": canonical_json(manifest),
        "calls.jsonl": "".join(c.line() for c in calls),
        "case_results.jsonl": jsonl(case_results),
        "contexts.jsonl": jsonl(contexts),
        "finals.jsonl": jsonl(finals),
        "rejections.jsonl": jsonl(rejections),
    }


# promise_id: (rótulo inicial, final LLM-only, final REQKG-grounded).
CLASSIFICATIONS = {
    9001: ("F", "F", "F"),
    9002: ("F", "F", "F"),
    9003: ("SE", "F", "SE"),
    9004: ("SE", "SE", "SE"),
    9005: ("F", "F", "SE"),
    9006: ("PE", "PE", "PE"),
    9007: ("US", "US", "US"),
    9008: ("O", "O", "US"),
    9009: ("PO", "PO", "PO"),
    9010: ("O", "O", "O"),
}
# Refinamento que falhou: o executor mantém o rótulo inicial em final (formato de experiments.runner.execute).
REFINEMENT_FAILURES = {(9008, A): RunStatus.API_ERROR, (9010, B): RunStatus.INVALID_OUTPUT}
# Refinamento válido recusado por regra G: refinement_status ok, não aceito, rótulo inicial em final.
REFINEMENT_REFUSALS = {(9006, A): "G2", (9004, B): "G1"}
# Consumo sintético: extração de cada projeto (100 dos 800 tokens de entrada no cache), primeira classificação
# e refinamento da classificação. A extração agrupa os itens do projeto de dois em dois (chunks_per_call = 2).
PROMISE_EXTRACTION_USAGE = {"input_tokens": 700, "cache_read_input_tokens": 100, "output_tokens": 150}
CLASSIFICATION_USAGE = {"input_tokens": 120, "output_tokens": 10}
CLASSIFICATION_REFINEMENT_USAGE = {"input_tokens": 50, "output_tokens": 5}
# Requisitos do PROMISE no contexto de cada item. LLM-only: os outros itens da mesma chamada. REQKG-grounded:
# esses e os vizinhos no grafo do projeto. 9010 em REQKG-grounded só tem um atributo de qualidade.
PROMISE_CONTEXT = {
    A: {9001: [9002], 9002: [9001], 9003: [9004], 9004: [9003], 9005: [], 9006: [9007], 9007: [9006],
        9008: [9009], 9009: [9008], 9010: []},
    B: {9001: [9002, 9003], 9002: [9001, 9003], 9003: [9004, 9001, 9002], 9004: [9003, 9005], 9005: [9004],
        9006: [9007], 9007: [9006, 9008], 9008: [9009, 9007], 9009: [9008], 9010: []},
}


def promise_project(number: int) -> int:
    return 901 if number <= 9005 else 902


def promise_chunk(number: int) -> str:
    return f"chk-{hashlib.sha256(f'promise-{number}'.encode()).hexdigest()[:16]}"


def promise_context(condition: Condition, number: int) -> dict:
    project = promise_project(number)
    source_id = f"src-{hashlib.sha256(f'promise-{project}'.encode()).hexdigest()[:16]}"
    chunk = promise_chunk
    items = [{"item_id": f"PROMISE-NFR-{n}", "kind": "requirement", "rank": rank, "text": f"Synthetic item {n}.",
              "source_id": source_id, "chunk_id": chunk(n)} for rank, n in enumerate(PROMISE_CONTEXT[condition][number])]
    strategy = ContextStrategy.SOURCE_CHUNKS
    if condition is B:
        strategy = ContextStrategy.GRAPH_LOCAL
        if number == 9010:
            items.append({"item_id": "qa-reliability", "kind": "quality_attribute", "rank": 0,
                          "text": "reliability", "source_id": source_id, "chunk_id": chunk(9009)})
    return {"query": f"classificar PROMISE-NFR-{number}", "strategy": strategy, "limit": 30, "items": items}


def promise_run() -> dict[str, str]:
    records, contexts, calls = [], [], []
    for project in (901, 902):
        numbers = [n for n in CLASSIFICATIONS if promise_project(n) == project]
        for index in range(0, len(numbers), 2):
            calls.append(call(f"promise-project-{project}", None, 0, "extraction", f"c{index // 2}",
                              PROMISE_EXTRACTION_USAGE,
                              {"chunk_ids": [promise_chunk(n) for n in numbers[index:index + 2]], "chunks_per_call": 2}))
    for number, (initial, final_a, final_b) in CLASSIFICATIONS.items():
        promise_id = f"PROMISE-NFR-{number}"
        calls.append(call(promise_id, None, 0, "classification", promise_id, CLASSIFICATION_USAGE, {}))
        for condition, final in ((A, final_a), (B, final_b)):
            failure = REFINEMENT_FAILURES.get((number, condition))
            refusal = REFINEMENT_REFUSALS.get((number, condition))
            assert not refusal or final == initial, promise_id
            context = promise_context(condition, number)
            contexts.append(ContextRecord(case_id=promise_id, run_index=0, condition=condition, target_key=promise_id,
                                          context=context))
            answered = failure is not RunStatus.API_ERROR
            calls.append(call(promise_id, condition, 0, "classification_refinement", promise_id,
                              CLASSIFICATION_REFINEMENT_USAGE if answered else None,
                              {"context_item_ids": [i["item_id"] for i in context["items"]],
                               "context_strategy": context["strategy"]}))
            records.append(ClassificationRecord(
                promise_id=promise_id, project_id=promise_project(number), run_index=0, condition=condition,
                status=RunStatus.OK, initial=initial, final=final, refinement_accepted=not failure and not refusal,
                refinement_status=failure or RunStatus.OK,
                violations=[ViolationRecord(rule_id=refusal, subject=promise_id, detail="sintético")] if refusal else [],
                input_tokens=CLASSIFICATION_REFINEMENT_USAGE["input_tokens"] if answered else 0,
                output_tokens=CLASSIFICATION_REFINEMENT_USAGE["output_tokens"] if answered else 0,
            ))
    manifest = RunManifest(
        run_id=PROMISE_RUN, model_id="sintetico", replay=True, runs=1,
        config_sha256=hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        prompts_registry_sha256=SYNTHETIC_SHA, command="code/experiments/metrics/fixtures/build.py",
    )
    return {"manifest.json": canonical_json(manifest), "calls.jsonl": "".join(c.line() for c in calls),
            "classifications.jsonl": jsonl(records), "contexts.jsonl": jsonl(contexts)}


def outputs() -> dict[Path, str]:
    config = load_toml(CONFIG, ExperimentConfig)
    ingested = ingest(SET_FILE, config.chunking)
    ingestion_bytes = render(ingested)
    files = {INGESTION: ingestion_bytes.decode("utf-8")}
    files |= {RUNS / STRUCTURAL_RUN / n: t for n, t in structural_run(ingested, ingestion_bytes, config).items()}
    files |= {RUNS / PROMISE_RUN / n: t for n, t in promise_run().items()}
    return files


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for path, text in outputs().items():
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                stale.append(path)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    for path in stale:
        print(f"desatualizado: {path.relative_to(HERE)}")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
