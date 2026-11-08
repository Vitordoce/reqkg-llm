"""Fixtures sintéticos do executor. Nenhum texto vem do PROMISE, da amostra anotada ou do caso.

Conjunto estrutural: code/ingestion/fixtures/fixture.toml (entrevista, ata e descrição sintéticas).
PROMISE: code/retrieval/fixtures/promise_sintetico.jsonl (promise_id 9001 em diante, projetos 97 e 98).
As respostas de extração em responses/ são escritas à mão e indexadas pelo SHA-256 do prompt em
replay_index.json, gerado por build_replays.py com o chunks_per_call da configuração congelada.
"""

from pathlib import Path

from extraction.client import REPO_ROOT
from retrieval.fixtures import PROMISE_JSONL

HERE = Path(__file__).resolve().parent
RESPONSES = HERE / "responses"
REPLAY_INDEX = HERE / "replay_index.json"
SET_FILE = REPO_ROOT / "code" / "ingestion" / "fixtures" / "fixture.toml"
CONFIG_FILE = REPO_ROOT / "code" / "experiments" / "config" / "experiment.toml"
PROMISE_FILE = PROMISE_JSONL

ENTREVISTA = "code/domain/fixtures/corpus/entrevista_sintetica.txt"
ATA = "code/ingestion/fixtures/ata_sintetica.md"
DESCRICAO = "code/ingestion/fixtures/descricao_sintetica.txt"

# (resposta gravada, documento, índice da chamada de extração)
EXTRACTION_SCENARIOS = (
    ("entrevista_c0", ENTREVISTA, 0),
    ("ata_c0", ATA, 0),
    ("ata_c1", ATA, 1),
    ("descricao_c0_invalida", DESCRICAO, 0),
)
