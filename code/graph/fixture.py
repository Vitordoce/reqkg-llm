"""Fixture do domínio gravado no grafo, para os testes e para a reprodução manual."""

import fcntl
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from domain.llm_io import ExtractionOutput
from domain.models import SourceChunk, SourceDocument
from domain.persist import PersistBatch, to_records
from domain.rules import CorpusIndex
from domain.serialization import load_json
from graph.connection import Graph
from graph.writer import write_batch, write_documents

VALID = Path(__file__).resolve().parents[1] / "domain" / "fixtures" / "valid"
OUTPUTS = ("extraction_output.json", "extraction_with_violations.json")
CONFIDENCE_THRESHOLD = 0.6
LOCK_FILE = Path(__file__).with_name(".neo4j-test.lock")


@contextmanager
def exclusive_database(timeout_seconds: float = 120):
    """Testes e o comando fixture apagam o grafo. Outros processos de pytest rodam a mesma suíte
    contra o mesmo banco, então quem apaga segura esta trava de arquivo."""
    with LOCK_FILE.open("w") as handle:
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise TimeoutError(f"outro processo segura {LOCK_FILE} há mais de {timeout_seconds}s") from None
                time.sleep(0.5)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


@dataclass(frozen=True)
class Fixture:
    document: SourceDocument
    chunks: list[SourceChunk]
    outputs: dict[str, ExtractionOutput]

    @property
    def corpus(self) -> CorpusIndex:
        return CorpusIndex.from_chunks(self.chunks)

    def batch(self, name: str) -> PersistBatch:
        return to_records(self.outputs[name], self.corpus, CONFIDENCE_THRESHOLD)


def load_fixture() -> Fixture:
    return Fixture(
        document=load_json(VALID / "source_document.json", SourceDocument),
        chunks=load_json(VALID / "source_chunks.json", list[SourceChunk]),
        outputs={name: load_json(VALID / name, ExtractionOutput) for name in OUTPUTS},
    )


def aliased_output(fixture: Fixture) -> ExtractionOutput:
    """R1b repete R1 (mesma declaração, mesma evidência). to_records recusa com W6 e aponta R1b para R1.

    As regras leem chaves e não veem ciclo. O grafo lê identificadores e vê R1 e R4 em ciclo.
    """
    data = fixture.outputs["extraction_output.json"].model_dump(mode="json")
    first, fourth = data["requirements"][0], data["requirements"][3]
    data["requirements"] = [first, {**first, "key": "R1b"}, fourth]
    data["actors"], data["entities"] = [], []
    data["relations"] = [
        {"type": "depends_on", "source_key": "R4", "target_key": "R1", "evidence": fourth["evidence"]},
        {"type": "depends_on", "source_key": "R1b", "target_key": "R4", "evidence": first["evidence"]},
    ]
    return ExtractionOutput.model_validate(data)


def write_fixture(graph: Graph, fixture: Fixture, names: tuple[str, ...] = OUTPUTS) -> None:
    write_documents(graph, [fixture.document], fixture.chunks)
    for name in names:
        write_batch(graph, fixture.batch(name))
