"""Gera replay_index.json do executor: SHA-256 de cada prompt de extração apontando para a resposta gravada.

Os prompts saem da ingestão de code/ingestion/fixtures/fixture.toml com o chunking e o
chunks_per_call da configuração congelada. Mudar prompt, texto ou agrupamento faz a resposta
sumir do índice, e o teste acusa.

Uso, a partir da raiz do repositório:
    .venv/bin/python code/experiments/runner/fixtures/build_replays.py          # reescreve
    .venv/bin/python code/experiments/runner/fixtures/build_replays.py --check  # falha se o disco divergir
"""

import json
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from domain import ids  # noqa: E402
from domain.config import ExperimentConfig  # noqa: E402
from domain.serialization import load_toml  # noqa: E402
from experiments.runner.fixtures import (  # noqa: E402
    CONFIG_FILE,
    EXTRACTION_SCENARIOS,
    REPLAY_INDEX,
    RESPONSES,
    SET_FILE,
)
from extraction import prompts  # noqa: E402
from extraction.pipeline import group_chunks  # noqa: E402
from ingestion.corpus import ingest  # noqa: E402


def build_index(config: ExperimentConfig | None = None) -> dict[str, dict[str, object]]:
    config = config or load_toml(CONFIG_FILE, ExperimentConfig)
    ingested = ingest(SET_FILE, config.chunking)
    index: dict[str, dict[str, object]] = {}
    for name, path, call in EXTRACTION_SCENARIOS:
        response = RESPONSES / f"{name}.json"
        if json.loads(response.read_text(encoding="utf-8")).get("synthetic") is not True:
            raise ValueError(f"{response.name}: resposta escrita à mão precisa de \"synthetic\": true")
        groups = group_chunks(ingested.chunks_of(ids.source_id(path)), config.extraction.chunks_per_call)
        prompt = prompts.extraction_prompt(groups[call])
        if prompt.sha256 in index:
            raise ValueError(f"cenários {index[prompt.sha256]['scenario']} e {name} geram o mesmo prompt")
        index[prompt.sha256] = {"scenario": name, "file": f"responses/{response.name}",
                                "prompt_name": prompt.name, "prompt_version": prompt.version}
    return index


def render_index() -> str:
    return json.dumps(build_index(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    content = render_index()
    if "--check" in argv:
        if not REPLAY_INDEX.exists() or REPLAY_INDEX.read_text(encoding="utf-8") != content:
            print(f"{REPLAY_INDEX.name} desatualizado: rode .venv/bin/python code/experiments/runner/fixtures/build_replays.py")
            return 1
        return 0
    REPLAY_INDEX.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
