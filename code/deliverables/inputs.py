"""Leitura de uma corrida, da configuração e do conjunto de ingestão, com a seleção de condição e corrida.

Tudo o que os artefatos mostram sai daqui. Nada é lido do Neo4j.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from domain.config import ChunkingConfig, ContractError, ExperimentConfig
from domain.enums import Condition, RunStatus
from domain.llm_io import CaseResult, ExtractionOutput
from domain.models import SourceChunk, SourceDocument
from domain.rules import CorpusIndex
from domain.serialization import load_toml, parse
from experiments.records import FILES, FinalRecord, RejectionRecord, RunManifest
from ingestion.corpus import IngestedSet, IngestionError, ingest, render
from ingestion.corpus import load as load_ingestion

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "outputs" / "runs"
CASE_DIR = REPO_ROOT / "outputs" / "caso"
INGESTION_DIR = REPO_ROOT / "data" / "processed" / "ingestion"
CONFIG = REPO_ROOT / "code" / "experiments" / "config" / "experiment.toml"

M = TypeVar("M", bound=BaseModel)


class DeliverableError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative(path: Path) -> str:
    """Caminho relativo à raiz do repositório. Os artefatos nunca guardam caminho absoluto."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        raise DeliverableError(f"{resolved}: a entrada tem de ficar dentro de {REPO_ROOT}") from None


def read_jsonl(path: Path, model: type[M], required: bool = True) -> list[M] | None:
    label = relative(path)
    if not path.is_file():
        if required:
            raise DeliverableError(f"{label}: arquivo da corrida não encontrado")
        return None
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as error:
            raise DeliverableError(f"{label}:{number}: JSON inválido: {error.msg}") from None
        try:
            records.append(parse(data, model, f"{label}:{number}"))
        except ContractError as error:
            raise DeliverableError(str(error)) from None
    return records


@dataclass(frozen=True)
class Selection:
    run_id: str
    condition: Condition
    run_index: int
    cases: tuple[str, ...] = ()


@dataclass(frozen=True)
class InputFile:
    path: str
    sha256: str | None


@dataclass(frozen=True)
class Inputs:
    selection: Selection
    manifest: RunManifest
    finals: list[FinalRecord]
    shared: dict[str, ExtractionOutput]
    refinements: list[CaseResult]
    rejections: list[RejectionRecord] | None
    documents: list[SourceDocument]
    chunks: list[SourceChunk]
    confidence_threshold: float
    files: dict[str, InputFile]
    unread_ingestion: list[str]

    def case_corpus(self, case_id: str) -> CorpusIndex:
        """O executor confere a evidência só contra o documento do caso, o único que o modelo viu."""
        return CorpusIndex.from_chunks(c for c in self.chunks if c.source_id == case_id)

    @property
    def cases(self) -> list[str]:
        return [f.case_id for f in self.finals]

    def document(self, case_id: str) -> SourceDocument:
        return next(d for d in self.documents if d.source_id == case_id)


def _config(path: Path, manifest: RunManifest) -> tuple[ExperimentConfig, InputFile]:
    label = relative(path)
    if not path.is_file():
        raise DeliverableError(f"{label}: configuração não encontrada")
    digest = sha256_file(path)
    if digest != manifest.config_sha256:
        raise DeliverableError(
            f"{label}: SHA-256 {digest} difere do config_sha256 da corrida ({manifest.config_sha256}). "
            "Passe --config com a configuração usada na corrida")
    try:
        return load_toml(path, ExperimentConfig), InputFile(label, digest)
    except ContractError as error:
        raise DeliverableError(str(error)) from None


@dataclass(frozen=True)
class IngestionInput:
    path: Path
    sha256: str
    ingested: IngestedSet


def _read_ingestion(path: Path, chunking: ChunkingConfig) -> IngestionInput:
    """.json: saída da ingestão, pelo SHA-256 do arquivo. .toml: arquivo de conjunto, ingerido em memória com o
    [chunking] da corrida, sem gravar nada; vale o SHA-256 dos bytes canônicos, o que o executor grava."""
    label = relative(path)
    if not path.is_file():
        raise DeliverableError(f"{label}: arquivo de ingestão não encontrado")
    try:
        if path.suffix == ".toml":
            ingested = ingest(path, chunking)
            return IngestionInput(path, hashlib.sha256(render(ingested)).hexdigest(), ingested)
        if path.suffix == ".json":
            return IngestionInput(path, sha256_file(path), load_ingestion(path))
    except IngestionError as error:
        raise DeliverableError(str(error)) from None
    raise DeliverableError(f"{label}: o conjunto de ingestão é o arquivo de conjunto (.toml) ou a saída da "
                           "ingestão (.json)")


def _ingestion_inputs(given: list[Path], manifest: RunManifest, chunking: ChunkingConfig) -> tuple[list[IngestionInput], list[str]]:
    """Conjuntos lidos e hashes da corrida que ficaram sem arquivo, como a entrada do PROMISE."""
    expected = set(manifest.ingestion_sha256)
    if not expected:
        raise DeliverableError("manifest.json: a corrida não registra ingestion_sha256, e sem ele o artefato não aponta "
                               "para as fontes usadas")
    if given:
        inputs = [_read_ingestion(path, chunking) for path in given]
        for item in inputs:
            if item.sha256 not in expected:
                how = (" (ingerido em memória com o [chunking] da configuração; conjunto diferente do da corrida?)"
                       if item.path.suffix == ".toml" else "")
                raise DeliverableError(f"{relative(item.path)}: SHA-256 {item.sha256}{how} não está em "
                                       f"ingestion_sha256 da corrida {sorted(expected)}")
    else:
        found = {sha256_file(p): p for p in sorted(INGESTION_DIR.glob("*.json"))}
        inputs = [_read_ingestion(found[h], chunking) for h in expected if h in found]
        if not inputs:
            raise DeliverableError(f"{relative(INGESTION_DIR)}: nenhum arquivo com SHA-256 em ingestion_sha256 da "
                                   f"corrida {sorted(expected)}. Regenere a ingestão usada ou passe --ingestion "
                                   "com o arquivo de conjunto (.toml)")
    inputs.sort(key=lambda item: relative(item.path))
    return inputs, sorted(expected - {item.sha256 for item in inputs})


def _corpus(inputs: list[IngestionInput]) -> tuple[list[SourceDocument], list[SourceChunk]]:
    documents: dict[str, SourceDocument] = {}
    chunks: dict[str, SourceChunk] = {}
    for item in inputs:
        path, ingested = item.path, item.ingested
        for document in ingested.documents:
            if documents.setdefault(document.source_id, document) != document:
                raise DeliverableError(f"{relative(path)}: {document.path} aparece com outra versão em outro "
                                       "arquivo de ingestão")
        for chunk in ingested.chunks:
            chunks.setdefault(chunk.chunk_id, chunk)
    ordered = sorted(documents.values(), key=lambda d: d.path)
    position = {d.source_id: i for i, d in enumerate(ordered)}
    return ordered, sorted(chunks.values(), key=lambda c: (position[c.source_id], c.index))


def _select_finals(finals: list[FinalRecord], selection: Selection, label: str) -> list[FinalRecord]:
    chosen = [f for f in finals if f.condition is selection.condition and f.run_index == selection.run_index]
    if not chosen:
        available = sorted({f"{f.condition.value} corrida {f.run_index}" for f in finals})
        raise DeliverableError(f"{label}: nenhum FinalRecord de {selection.condition.value} na corrida "
                               f"{selection.run_index}. Disponíveis: {available}")
    if selection.cases:
        unknown = sorted(set(selection.cases) - {f.case_id for f in chosen})
        if unknown:
            raise DeliverableError(f"{label}: casos {unknown} não existem nessa condição e corrida")
        chosen = [f for f in chosen if f.case_id in selection.cases]
    cases = [f.case_id for f in chosen]
    if len(set(cases)) != len(cases):
        raise DeliverableError(f"{label}: caso repetido na mesma condição e corrida: {sorted(cases)}")
    return sorted(chosen, key=lambda f: f.case_id)


def _shared(results: list[CaseResult], finals: list[FinalRecord], run_index: int, label: str) -> dict[str, ExtractionOutput]:
    wanted = {f.case_id for f in finals}
    shared: dict[str, ExtractionOutput] = {}
    for result in results:
        if result.stage != "extraction" or result.run_index != run_index or result.case_id not in wanted:
            continue
        if result.case_id in shared:
            raise DeliverableError(f"{label}: duas extrações compartilhadas do caso {result.case_id}")
        if result.status is RunStatus.OK:
            shared[result.case_id] = result.extraction
    for final in finals:
        if final.output is None:
            continue
        if final.case_id not in shared:
            raise DeliverableError(f"{label}: falta a extração compartilhada do caso {final.case_id} na corrida "
                                   f"{run_index}, de onde saem a ordem dos requisitos e a declaração anterior")
        if [r.key for r in final.output.requirements] != [r.key for r in shared[final.case_id].requirements]:
            raise DeliverableError(f"caso {final.case_id}: as chaves de requisito da saída final diferem das da "
                                   "extração compartilhada")
    return shared


def load(selection: Selection, runs_dir: Path = RUNS_DIR, config: Path = CONFIG,
         ingestion: list[Path] | None = None) -> Inputs:
    run_dir = Path(runs_dir) / selection.run_id
    if not run_dir.is_dir():
        raise DeliverableError(f"{relative(run_dir)}: corrida não encontrada")
    manifest_path = run_dir / FILES["manifest"]
    if not manifest_path.is_file():
        raise DeliverableError(f"{relative(manifest_path)}: arquivo da corrida não encontrado")
    try:
        manifest = parse(json.loads(manifest_path.read_text(encoding="utf-8")), RunManifest, relative(manifest_path))
    except (ContractError, json.JSONDecodeError) as error:
        raise DeliverableError(str(error)) from None
    if manifest.run_id != selection.run_id:
        raise DeliverableError(f"{relative(manifest_path)}: run_id {manifest.run_id!r} difere do diretório "
                               f"{selection.run_id!r}")
    if selection.run_index >= manifest.runs:
        raise DeliverableError(f"--run-index {selection.run_index}: a corrida tem {manifest.runs} repetição(ões), "
                               f"de 0 a {manifest.runs - 1}")

    experiment, config_file = _config(Path(config), manifest)
    ingestion_inputs, unread = _ingestion_inputs([Path(p) for p in ingestion or []], manifest, experiment.chunking)
    documents, chunks = _corpus(ingestion_inputs)

    finals_path = run_dir / FILES["finals"]
    finals = _select_finals(read_jsonl(finals_path, FinalRecord), selection, relative(finals_path))
    sources = {d.source_id for d in documents}
    for final in finals:
        if final.case_id not in sources:
            raise DeliverableError(f"{relative(finals_path)}: caso {final.case_id!r} não é o source_id de nenhum "
                                   "documento da ingestão. O executor usa o source_id do documento como case_id")
    results_path = run_dir / FILES["case_results"]
    results = read_jsonl(results_path, CaseResult)
    shared = _shared(results, finals, selection.run_index, relative(results_path))
    cases = {f.case_id for f in finals}
    refinements = [r for r in results if r.stage == "refinement" and r.condition is selection.condition
                   and r.run_index == selection.run_index and r.case_id in cases]
    rejections_path = run_dir / FILES["rejections"]
    rejections = read_jsonl(rejections_path, RejectionRecord, required=False)
    if rejections is not None:
        rejections = sorted((r for r in rejections if r.run_index == selection.run_index and r.case_id in cases),
                            key=lambda r: (r.case_id, r.rejection.rule_id, r.rejection.subject))

    files = {
        "manifest": InputFile(relative(manifest_path), sha256_file(manifest_path)),
        "finals": InputFile(relative(finals_path), sha256_file(finals_path)),
        "case_results": InputFile(relative(results_path), sha256_file(results_path)),
        "rejections": InputFile(relative(rejections_path),
                                sha256_file(rejections_path) if rejections is not None else None),
        "config": config_file,
    }
    files |= {f"ingestion:{relative(i.path)}": InputFile(relative(i.path), i.sha256) for i in ingestion_inputs}
    return Inputs(selection=selection, manifest=manifest, finals=finals, shared=shared, refinements=refinements,
                  rejections=rejections, documents=documents, chunks=chunks,
                  confidence_threshold=experiment.review.confidence_threshold, files=files, unread_ingestion=unread)
