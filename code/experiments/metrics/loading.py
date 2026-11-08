"""Leitura dos registros de uma corrida, do conjunto de ingestão e da configuração congelada.

Os registros seguem experiments.records. Do calls.jsonl (CallRecord) só se usa o alvo da chamada,
a lista de chunks da extração (meta.chunk_ids), o estado e o consumo (usage).
"""

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from domain.config import ChunkingConfig, ContractError, ExperimentConfig
from domain.enums import Condition
from domain.llm_io import CaseResult, ExtractionOutput
from domain.models import SourceDocument
from domain.rules import CorpusIndex
from domain.serialization import load_toml, parse
from experiments.records import (
    FILES, CallRecord, ClassificationRecord, ContextRecord, FinalRecord, RejectionRecord, RunManifest, TokenUsage,
)
from ingestion.corpus import IngestedSet, IngestionError, ingest, render
from ingestion.corpus import load as load_ingested

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNS_ROOT = REPO_ROOT / "outputs" / "runs"
CONFIG_PATH = REPO_ROOT / "code" / "experiments" / "config" / "experiment.toml"
PROMISE_LABELS = REPO_ROOT / "data" / "processed" / "promise" / "promise_nfr.jsonl"
INPUT_USAGE_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def display_path(path: Path) -> str:
    path = Path(path).resolve()
    return path.relative_to(REPO_ROOT).as_posix() if path.is_relative_to(REPO_ROOT) else path.as_posix()


def read_jsonl(path: Path, model: type) -> list:
    if not path.is_file():
        return []
    items = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as error:
            raise ContractError(f"{path}:{number}: JSON inválido: {error.msg}") from None
        items.append(parse(data, model, f"{path}:{number}"))
    return items


@dataclass(frozen=True)
class CallUsage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    without_usage: int = 0

    def add(self, usage: TokenUsage, returned: bool) -> "CallUsage":
        """Entrada inclui os tokens de cache. Falha da API não consome; resposta sem usage fica sem registro."""
        if not returned:
            return CallUsage(self.calls + 1, self.input_tokens, self.output_tokens, self.without_usage)
        if usage.input_tokens is None or usage.output_tokens is None:
            return CallUsage(self.calls + 1, self.input_tokens, self.output_tokens, self.without_usage + 1)
        tokens_in = sum(getattr(usage, k) or 0 for k in INPUT_USAGE_KEYS)
        return CallUsage(self.calls + 1, self.input_tokens + tokens_in, self.output_tokens + usage.output_tokens,
                         self.without_usage)


@dataclass
class Run:
    directory: Path
    manifest: RunManifest
    finals: list[FinalRecord]
    case_results: list[CaseResult]
    rejections: list[RejectionRecord]
    classifications: list[ClassificationRecord]
    contexts: list[ContextRecord] = field(default_factory=list)
    # (case_id, run_index, prefixo da chamada) -> chunks enviados na chamada de extração
    call_chunks: dict[tuple[str, int, str], tuple[str, ...]] = field(default_factory=dict)
    # (stage, condition ou None, run_index) -> consumo das chamadas, menos as de extração
    usage: dict[tuple[str, Condition | None, int], CallUsage] = field(default_factory=dict)
    # (run_index, case_id) -> consumo da extração. O caso é um documento da amostra ou um projeto do PROMISE.
    extraction_usage: dict[tuple[int, str], CallUsage] = field(default_factory=dict)

    def final(self, case_id: str, run_index: int, condition: Condition) -> FinalRecord:
        for record in self.finals:
            if (record.case_id, record.run_index, record.condition) == (case_id, run_index, condition):
                return record
        raise ContractError(f"{self.directory}: sem FinalRecord para {case_id}, corrida {run_index}, {condition.value}")

    def extraction(self, case_id: str, run_index: int) -> ExtractionOutput:
        found = [r for r in self.case_results
                 if r.stage == "extraction" and r.case_id == case_id and r.run_index == run_index]
        if len(found) != 1 or found[0].extraction is None:
            raise ContractError(
                f"{self.directory / FILES['case_results']}: esperada uma extração válida de {case_id} na corrida "
                f"{run_index}, encontradas {len(found)}"
            )
        return found[0].extraction

    def run_indices(self) -> list[int]:
        return sorted({r.run_index for r in self.finals})

    def case_ids(self) -> list[str]:
        return sorted({r.case_id for r in self.finals})


def _read_calls(path: Path, run: Run) -> None:
    for record in read_jsonl(path, CallRecord):
        target = record.target
        returned = record.status == "returned"
        if target.stage != "extraction":
            key = (target.stage, target.condition, target.run_index)
            run.usage[key] = run.usage.get(key, CallUsage()).add(record.usage, returned)
            continue
        case = (target.run_index, target.case_id)
        run.extraction_usage[case] = run.extraction_usage.get(case, CallUsage()).add(record.usage, returned)
        call = (target.case_id, target.run_index, target.key)
        previous = run.call_chunks.setdefault(call, tuple(record.meta.chunk_ids))
        if previous != tuple(record.meta.chunk_ids):
            raise ContractError(f"{path}: a chamada {call} aparece com listas de chunks diferentes")


def _check_unique_finals(run: Run) -> None:
    seen: dict[tuple, int] = defaultdict(int)
    for record in run.finals:
        seen[(record.case_id, record.run_index, record.condition)] += 1
    repeated = sorted(k for k, n in seen.items() if n > 1)
    if repeated:
        raise ContractError(f"{run.directory / FILES['finals']}: FinalRecord repetido para {repeated[0]}")
    for run_index in run.run_indices():
        cases = {c: {r.case_id for r in run.finals if r.run_index == run_index and r.condition is c} for c in Condition}
        if cases[Condition.LLM_ONLY] != cases[Condition.REQKG_GROUNDED]:
            missing = sorted(cases[Condition.LLM_ONLY] ^ cases[Condition.REQKG_GROUNDED])
            raise ContractError(f"{run.directory / FILES['finals']}: corrida {run_index} sem as duas condições para {missing}")
    expected = list(range(run.manifest.runs))
    if run.finals and run.run_indices() != expected:
        raise ContractError(
            f"{run.directory / FILES['finals']}: o manifesto declara runs = {run.manifest.runs}, "
            f"e os registros têm as corridas {run.run_indices()}"
        )


def load_run(directory: Path) -> Run:
    directory = Path(directory)
    manifest_path = directory / FILES["manifest"]
    if not manifest_path.is_file():
        raise ContractError(f"{manifest_path}: manifesto da corrida não encontrado")
    try:
        manifest = parse(json.loads(manifest_path.read_text(encoding="utf-8")), RunManifest, str(manifest_path))
    except json.JSONDecodeError as error:
        raise ContractError(f"{manifest_path}: JSON inválido: {error.msg}") from None
    if manifest.run_id != directory.name:
        raise ContractError(f"{manifest_path}: run_id {manifest.run_id!r} difere da pasta {directory.name!r}")
    run = Run(
        directory=directory,
        manifest=manifest,
        finals=read_jsonl(directory / FILES["finals"], FinalRecord),
        case_results=read_jsonl(directory / FILES["case_results"], CaseResult),
        rejections=read_jsonl(directory / FILES["rejections"], RejectionRecord),
        classifications=read_jsonl(directory / FILES["classifications"], ClassificationRecord),
        contexts=read_jsonl(directory / FILES["contexts"], ContextRecord),
    )
    _read_calls(directory / FILES["calls"], run)
    _check_unique_finals(run)
    _check_unique_contexts(run)
    return run


def _check_unique_contexts(run: Run) -> None:
    seen: set[tuple] = set()
    for record in run.contexts:
        key = (record.case_id, record.run_index, record.condition, record.target_key)
        if key in seen:
            raise ContractError(f"{run.directory / FILES['contexts']}: ContextRecord repetido para {key}")
        seen.add(key)


def load_config(path: Path, manifest: RunManifest) -> ExperimentConfig:
    """A configuração tem de ser a mesma da corrida: o SHA-256 dos bytes bate com o manifesto."""
    path = Path(path)
    if not path.is_file():
        raise ContractError(f"{path}: configuração não encontrada")
    digest = sha256_file(path)
    if digest != manifest.config_sha256:
        raise ContractError(
            f"{display_path(path)}: SHA-256 {digest} difere do config_sha256 da corrida ({manifest.config_sha256}). "
            "Use a configuração congelada com que a corrida rodou (--config)."
        )
    return load_toml(path, ExperimentConfig)


@dataclass(frozen=True)
class Corpus:
    """index tem os chunks de todos os conjuntos. As regras usam case(), o corpus do caso, como o executor:
    o modelo só viu os chunks do documento do caso, e evidência de outro documento conta como P2."""

    index: CorpusIndex
    documents: tuple[SourceDocument, ...]
    files: tuple[tuple[str, str, str], ...]  # (caminho exibido, SHA-256 conferido, como foi lido)
    by_document: dict[str, CorpusIndex] = field(default_factory=dict)  # source_id -> chunks do documento

    def case(self, case_id: str) -> CorpusIndex:
        return self.by_document[self.document_for(case_id, "caso").source_id]

    def document_of_chunk(self, chunk_id: str) -> str | None:
        return self.index.chunk_source.get(chunk_id)

    def document_for(self, name: str, what: str) -> SourceDocument:
        """Documento pelo source_id, pelo caminho ou pelo nome do arquivo sem extensão."""
        found = [d for d in self.documents if name in (d.source_id, d.path, PurePosixPath(d.path).stem)]
        if len(found) != 1:
            raise ContractError(
                f"{what} {name!r}: {len(found)} documentos da ingestão correspondem; o identificador tem de ser o "
                "source_id, o caminho ou o nome do arquivo sem extensão de exatamente um documento"
            )
        return found[0]


def _read_set(path: Path, chunking: ChunkingConfig) -> tuple[IngestedSet, str, set[str], str]:
    """(conjunto, SHA-256 exibido, SHA-256 aceitos contra o manifesto, como foi lido).

    .toml: arquivo de conjunto, ingerido em memória com o [chunking] da configuração, sem gravar nada. O
    SHA-256 é o dos bytes canônicos do conjunto ingerido, o mesmo que o executor grava em ingestion_sha256.
    .json: saída da ingestão; vale o SHA-256 do arquivo ou o set_sha256 que ele registra.
    """
    try:
        if path.suffix == ".toml":
            ingested = ingest(path, chunking)
            digest = hashlib.sha256(render(ingested)).hexdigest()
            return ingested, digest, {digest}, "ingerido em memória, SHA-256 dos bytes canônicos"
        if path.suffix == ".json":
            ingested = load_ingested(path)
            digest = sha256_file(path)
            return ingested, digest, {digest, ingested.set_sha256}, "saída da ingestão"
    except IngestionError as error:
        raise ContractError(str(error)) from None
    raise ContractError(f"{display_path(path)}: o conjunto de ingestão é o arquivo de conjunto (.toml) ou a saída da "
                        "ingestão (.json)")


def load_corpus(paths: list[Path], manifest: RunManifest, chunking: ChunkingConfig) -> Corpus:
    """Conjuntos de ingestão da corrida (_read_set). Cada um tem de bater com um hash registrado no manifesto."""
    if not paths:
        raise ContractError("informe o arquivo de ingestão da corrida com --ingestion")
    sets: list[IngestedSet] = []
    files = []
    matched: set[str] = set()
    for path in paths:
        ingested, digest, accepted, how = _read_set(Path(path), chunking)
        if manifest.ingestion_sha256:
            hits = accepted & set(manifest.ingestion_sha256)
            if not hits:
                raise ContractError(
                    f"{display_path(path)}: SHA-256 {', '.join(sorted(accepted))} ({how}) não está em "
                    "ingestion_sha256 da corrida"
                )
            matched |= hits
        sets.append(ingested)
        files.append((display_path(path), digest, how))
    missing = sorted(set(manifest.ingestion_sha256) - matched)
    if missing:
        raise ContractError(f"faltam os conjuntos de ingestão da corrida com SHA-256 {', '.join(missing)}")
    chunks = [c for s in sets for c in s.chunks]
    if len({c.chunk_id for c in chunks}) != len(chunks):
        raise ContractError("os conjuntos de ingestão repetem chunk_id")
    documents = tuple(d for s in sets for d in s.documents)
    by_document = {d.source_id: CorpusIndex.from_chunks(s.chunks_of(d.source_id)) for s in sets for d in s.documents}
    return Corpus(CorpusIndex.from_chunks(chunks), documents, tuple(files), by_document)
