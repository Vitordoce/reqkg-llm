"""Corrida sintética para os testes de code/deliverables, no formato de experiments.records.

Nenhuma chamada de modelo. As respostas são escritas aqui, à mão, sobre a entrevista de
code/domain/fixtures/corpus/ e a ata de code/ingestion/fixtures/, pelo conjunto de ingestão
data/processed/ingestion/fixture.json. Não é estudo de caso.

    .venv/bin/python code/deliverables/fixtures/build.py           # grava a corrida e os artefatos esperados
    .venv/bin/python code/deliverables/fixtures/build.py --check   # falha se o disco divergir
"""

import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE.parents[1]) not in sys.path:
    sys.path.insert(0, str(HERE.parents[1]))

from domain.enums import Condition, ContextStrategy, RunStatus  # noqa: E402
from domain.llm_io import (  # noqa: E402
    CaseResult, ContextItem, ExtractionOutput, RefinementOutput, RequirementCandidate, RetrievedContext,
    ViolationRecord, merge_outputs,
)
from domain.persist import to_records  # noqa: E402
from domain.rules import CorpusIndex, refinement_targets  # noqa: E402
from domain.serialization import canonical_json, load_toml  # noqa: E402
from domain.config import ExperimentConfig  # noqa: E402
from experiments.records import FILES, ContextRecord, FinalRecord, RejectionRecord, RunManifest  # noqa: E402
from ingestion.corpus import load as load_ingestion  # noqa: E402

REPO_ROOT = HERE.parents[2]
RUN_ID = "sintetico-entrevista"
RUNS = HERE / "runs"
RUN_DIR = RUNS / RUN_ID
EXPECTED = HERE / "expected"
CONFIG = HERE / "experiment.toml"
INGESTION = REPO_ROOT / "data" / "processed" / "ingestion" / "fixture.json"
REGISTRY = REPO_ROOT / "code" / "extraction" / "prompts" / "REGISTRY.json"
NAME = "fixture-sintetico"
ENTREVISTA = "code/domain/fixtures/corpus/entrevista_sintetica.txt"
ATA = "code/ingestion/fixtures/ata_sintetica.md"
DESCRICAO = "code/ingestion/fixtures/descricao_sintetica.txt"
RUN_INDEX = 0

INGESTED = load_ingestion(INGESTION)
THRESHOLD = load_toml(CONFIG, ExperimentConfig).review.confidence_threshold
PER_CALL = load_toml(CONFIG, ExperimentConfig).extraction.chunks_per_call


def chunk(path: str, index: int):
    source = next(d.source_id for d in INGESTED.documents if d.path == path)
    return next(c for c in INGESTED.chunks if c.source_id == source and c.index == index)


def ev(path: str, index: int, quote: str | None) -> dict:
    c = chunk(path, index)
    return {"source_id": c.source_id, "chunk_id": c.chunk_id, "quote": quote}


E1, E2, E3 = ((ENTREVISTA, i) for i in (1, 2, 3))
A6, A7, A10 = ((ATA, i) for i in (6, 7, 10))

# Como no executor, cada caso é um documento, com case_id igual ao source_id.
CASE_ENTREVISTA, CASE_ATA, FAILED_CASE = (chunk(path, 0).source_id for path in (ENTREVISTA, ATA, DESCRICAO))


def case_corpus(case_id: str) -> CorpusIndex:
    return CorpusIndex.from_chunks(c for c in INGESTED.chunks if c.source_id == case_id)


def entrevista_call() -> ExtractionOutput:
    return ExtractionOutput.model_validate({
        "requirements": [
            {"key": "R1", "statement": "O sistema deve permitir que o técnico reserve um equipamento por horário.",
             "type": "functional", "confidence": 0.9,
             "evidence": [ev(*E1, "Os técnicos precisam reservar um equipamento por horário")]},
            {"key": "R2", "statement": "O sistema deve impedir duas reservas do mesmo equipamento no mesmo horário.",
             "type": "functional", "priority": "must", "verification_method": "test", "confidence": 0.95,
             "evidence": [ev(*E1, "o sistema tem de impedir duas reservas no mesmo horário")]},
            {"key": "R3", "statement": "O sistema deve avisar o responsável quando a calibração vencer.",
             "type": "non_functional", "quality_attributes": ["performance"],
             "quantitative_value": "até cinco minutos", "confidence": 0.8,
             "evidence": [ev(*E2, "O sistema deve enviar um aviso ao responsável em até cinco minutos depois "
                                  "que a calibração vence")]},
            {"key": "R4", "statement": "A consulta da agenda deve ser rápida.", "type": "non_functional",
             "quality_attributes": ["performance"], "review_flags": ["quantitative_value_pending"],
             "confidence": 0.85, "evidence": [ev(*E2, "A consulta da agenda precisa ser rápida")]},
            {"key": "R5", "statement": "Somente a coordenação pode cancelar a reserva de outra pessoa.",
             "type": "non_functional", "quality_attributes": ["security"], "confidence": 0.4,
             "evidence": [ev(*E3, "só a coordenação pode cancelar reserva de outra pessoa")]},
            {"key": "R6", "statement": "Os dados de uso devem ser guardados por dois anos para auditoria.",
             "type": "constraint", "confidence": 0.9,
             "evidence": [ev(*E3, "Os dados de uso ficam armazenados por dois anos")]},
            {"key": "R7", "statement": "A coordenação deve listar os equipamentos que exigem calibração.",
             "type": "functional", "confidence": 0.7,
             "evidence": [ev(*A10, "A coordenação vai listar os equipamentos que exigem calibração")]},
            {"key": "R8", "statement": "O sistema deve funcionar no celular.", "review_flags": ["ambiguous_type"],
             "confidence": 0.5},
        ],
        "actors": [
            {"key": "A1", "name": "Coordenadora do laboratório", "kind": "stakeholder",
             "evidence": [ev(*E1, "Coordenadora do laboratório")]},
            {"key": "A2", "name": "Técnico", "kind": "user_role", "evidence": [ev(*E2, "Técnico")]},
            {"key": "A3", "name": "técnico", "kind": "stakeholder", "evidence": [ev(*E1, "Os técnicos")]},
        ],
        "components": [
            {"key": "S1", "name": "Agenda de reservas", "description": "Consulta e registro das reservas.",
             "evidence": [ev(*E2, "A consulta da agenda")]},
        ],
        "entities": [
            {"key": "N1", "name": "calibração", "entity_type": "evento", "evidence": [ev(*E2, "a calibração vence")]},
        ],
        "relations": [
            {"type": "requested_by", "source_key": "R1", "target_key": "A2",
             "evidence": [ev(*E1, "Os técnicos precisam reservar um equipamento por horário")]},
            {"type": "requested_by", "source_key": "R5", "target_key": "A1",
             "evidence": [ev(*E3, "Coordenadora do laboratório: só a coordenação pode cancelar")]},
            {"type": "depends_on", "source_key": "R2", "target_key": "R1",
             "evidence": [ev(*E1, "o sistema tem de impedir duas reservas no mesmo horário")]},
            {"type": "depends_on", "source_key": "R1", "target_key": "R2",
             "evidence": [ev(*E1, "Os técnicos precisam reservar")]},
            {"type": "allocated_to", "source_key": "R4", "target_key": "S1",
             "evidence": [ev(*E2, "A consulta da agenda precisa ser rápida")]},
            {"type": "requested_by", "source_key": "R6", "target_key": "A1",
             "evidence": [ev(*E3, "Os dados de uso ficam guardados")]},
            {"type": "allocated_to", "source_key": "R2", "target_key": "S1"},
            {"type": "benefits_actor", "source_key": "R3", "target_key": "A2",
             "evidence": [ev(*E2, "alguém precisa avisar")]},
        ],
    })


def ata_call() -> ExtractionOutput:
    return ExtractionOutput.model_validate({
        "requirements": [
            {"key": "R1", "statement": "O sistema deve recusar a segunda reserva do mesmo equipamento no mesmo "
                                       "horário e mostrar quem já reservou.",
             "type": "functional", "confidence": 0.9,
             "evidence": [ev(*A6, "Ela pediu que o sistema novo recuse a segunda reserva e mostre quem já reservou")]},
            {"key": "R2", "statement": "O aviso de vencimento da calibração deve aparecer no próprio sistema no mesmo "
                                       "dia do vencimento.",
             "type": "non_functional", "quality_attributes": ["performance"],
             "quantitative_value": "no mesmo dia do vencimento", "confidence": 0.85,
             "evidence": [ev(*A7, "Ele quer o aviso no próprio sistema, no mesmo dia do vencimento")]},
        ],
        "actors": [
            {"key": "A1", "name": "Coordenadora do laboratório", "kind": "stakeholder",
             "evidence": [ev(*A6, "A coordenadora relatou")]},
            {"key": "A2", "name": "Responsável pela calibração", "kind": "stakeholder",
             "evidence": [ev(*A7, "O responsável pela calibração")]},
        ],
        "relations": [
            {"type": "requested_by", "source_key": "R1", "target_key": "A1",
             "evidence": [ev(*A6, "Ela pediu que o sistema novo recuse a segunda reserva")]},
            {"type": "requested_by", "source_key": "R2", "target_key": "A2",
             "evidence": [ev(*A7, "Ele quer o aviso no próprio sistema")]},
        ],
    })


SHARED = {
    CASE_ENTREVISTA: merge_outputs([("c0", entrevista_call())]),
    CASE_ATA: merge_outputs([("c0", ExtractionOutput()), ("c1", ata_call())]),
}

# Resposta de cada refinamento: "echo" devolve o candidato sem mudança, um dicionário muda campos,
# uma tupla (status, erro) é uma chamada que falhou.
ECHO = "echo"
REVISED_R3 = {"statement": "O sistema deve enviar um aviso ao responsável em até cinco minutos depois que a "
                           "calibração vence."}
OUTCOMES = {
    Condition.REQKG_GROUNDED: {
        (CASE_ENTREVISTA, "c0-R1"): (RunStatus.API_ERROR, "falha sintética da API"),
        (CASE_ENTREVISTA, "c0-R3"): REVISED_R3,
        (CASE_ENTREVISTA, "c0-R4"): (RunStatus.INVALID_OUTPUT, "resposta sintética fora do contrato"),
        (CASE_ENTREVISTA, "c0-R5"): {"evidence": [ev(*A6, "A coordenadora relatou")]},
    },
    Condition.LLM_ONLY: {
        (CASE_ENTREVISTA, "c0-R3"): {"used_context_ids": ["item-inexistente"], **REVISED_R3},
    },
}


def context(case_id: str, key: str, condition: Condition) -> RetrievedContext:
    """LLM-only vê os chunks da chamada de extração. REQKG-grounded vê, escrito à mão, o documento inteiro do
    caso. A recuperação real é de code/retrieval/."""
    chunks = [c for c in INGESTED.chunks if c.source_id == case_id]
    if condition is Condition.LLM_ONLY:
        call = int(key.split("-", 1)[0].removeprefix("c"))
        chunks = chunks[call * PER_CALL:(call + 1) * PER_CALL]
    items = [ContextItem(item_id=c.chunk_id, kind="source_chunk", rank=rank, text=c.text, source_id=c.source_id,
                         chunk_id=c.chunk_id) for rank, c in enumerate(chunks)]
    strategy = ContextStrategy.SOURCE_CHUNKS if condition is Condition.LLM_ONLY else ContextStrategy.GRAPH_LOCAL
    return RetrievedContext(query=f"refinar {key}", strategy=strategy, limit=30, items=items)


def refine(case_id: str, condition: Condition, candidate: RequirementCandidate, ctx: RetrievedContext):
    outcome = OUTCOMES[condition].get((case_id, candidate.key), ECHO)
    base = {"case_id": case_id, "condition": condition, "run_index": RUN_INDEX, "stage": "refinement",
            "target_key": candidate.key}
    if isinstance(outcome, tuple):
        return CaseResult(**base, status=outcome[0], error=outcome[1]), None, []
    update = {} if outcome == ECHO else dict(outcome)
    used = update.pop("used_context_ids", [])
    revised = RequirementCandidate.model_validate({**candidate.model_dump(), **update})
    output = RefinementOutput(target_key=candidate.key, revised=revised, used_context_ids=used)
    violations = output.check_against(ctx, candidate, case_corpus(case_id))
    records = [ViolationRecord.of(v) for v in violations]
    result = CaseResult(**base, status=RunStatus.OK, refinements=[output], violations=records)
    return result, (None if violations else revised), records


def run_records() -> dict[str, list]:
    results: list = []
    contexts: list = []
    finals: list = []
    rejections: list = []
    for case_id in sorted([*SHARED, FAILED_CASE]):
        if case_id == FAILED_CASE:
            results.append(CaseResult(case_id=case_id, run_index=RUN_INDEX, stage="extraction",
                                      status=RunStatus.INVALID_OUTPUT, error="c0: resposta sintética fora do contrato"))
            finals += [FinalRecord(case_id=case_id, run_index=RUN_INDEX, condition=c, status=RunStatus.INVALID_OUTPUT)
                       for c in Condition]
            continue
        shared = SHARED[case_id]
        results.append(CaseResult(case_id=case_id, run_index=RUN_INDEX, stage="extraction", status=RunStatus.OK,
                                  extraction=shared))
        rejections += [RejectionRecord(case_id=case_id, run_index=RUN_INDEX, rejection=r)
                       for r in to_records(shared, case_corpus(case_id), THRESHOLD).rejected]
        targets = refinement_targets(shared, case_corpus(case_id), THRESHOLD)
        for condition in Condition:
            accepted, refused, failed, violations, replaced = [], [], [], [], {}
            for key in targets:
                candidate = next(r for r in shared.requirements if r.key == key)
                ctx = context(case_id, key, condition)
                contexts.append(ContextRecord(case_id=case_id, run_index=RUN_INDEX, condition=condition,
                                              target_key=key, context=ctx))
                result, revised, records = refine(case_id, condition, candidate, ctx)
                results.append(result)
                if revised is not None:
                    accepted.append(key)
                    replaced[key] = revised
                elif result.status is RunStatus.OK:
                    refused.append(key)
                    violations += records
                else:
                    failed.append(key)
            output = ExtractionOutput.model_validate({**shared.model_dump(), "requirements": [
                replaced.get(r.key, r).model_dump() for r in shared.requirements]})
            finals.append(FinalRecord(case_id=case_id, run_index=RUN_INDEX, condition=condition, status=RunStatus.OK,
                                      output=output, targets=targets, accepted=accepted, refused=refused,
                                      failed=failed, violations=violations))
    return {"case_results": results, "contexts": contexts, "finals": finals, "rejections": rejections}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_files() -> dict[Path, bytes]:
    manifest = RunManifest(
        run_id=RUN_ID, model_id="nenhum-fixture-sintetico", replay=True, runs=1, config_sha256=sha256(CONFIG),
        ingestion_sha256=[sha256(INGESTION)], prompts_registry_sha256=sha256(REGISTRY),
        command="code/deliverables/fixtures/build.py (corrida sintética, sem chamada de modelo)",
    )
    files = {RUN_DIR / FILES["manifest"]: canonical_json(manifest).encode("utf-8")}
    for name, records in run_records().items():
        files[RUN_DIR / FILES[name]] = "".join(canonical_json(r) for r in records).encode("utf-8")
    return files


def expected_files() -> dict[Path, bytes]:
    from deliverables.__main__ import generate
    from deliverables.inputs import Selection

    generated = generate(Selection(RUN_ID, Condition.REQKG_GROUNDED, RUN_INDEX), NAME, RUNS, CONFIG)
    return {EXPECTED / name: data for name, data in generated.items()}


def stale(files: dict[Path, bytes]) -> list[str]:
    return sorted(str(p.relative_to(REPO_ROOT)) for p, d in files.items() if not p.is_file() or p.read_bytes() != d)


def write(files: dict[Path, bytes]) -> None:
    for path in stale(files):
        target = REPO_ROOT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(files[target])


def main(argv: list[str]) -> int:
    """Os artefatos esperados são gerados a partir da corrida em disco, então a corrida vem primeiro."""
    runs = run_files()
    if "--check" in argv:
        outdated = stale(runs) or stale(expected_files())
        for path in outdated:
            print(f"desatualizado: {path}", file=sys.stderr)
        return 1 if outdated else 0
    write(runs)
    write(expected_files())
    print(f"corrida e artefatos esperados em {HERE.relative_to(REPO_ROOT)} conferidos")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
