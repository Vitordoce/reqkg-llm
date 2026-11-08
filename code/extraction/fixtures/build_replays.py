"""Gera replay_index.json: SHA-256 de cada prompt de cenário apontando para a resposta gravada.

As respostas em responses/ são escritas à mão. Este script só calcula o índice, para que uma
mudança de prompt ou de entrada apareça como resposta ausente, e não passe em silêncio.

Uso, a partir da raiz do repositório:
    .venv/bin/python code/extraction/fixtures/build_replays.py          # reescreve
    .venv/bin/python code/extraction/fixtures/build_replays.py --check  # falha se o disco divergir
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE.parents[1]))

from extraction.client import REPLAY_INDEX  # noqa: E402
from extraction.fixtures.scenarios import RESPONSES, SCENARIOS  # noqa: E402


def build_index() -> dict[str, dict[str, object]]:
    index: dict[str, dict[str, object]] = {}
    for scenario in SCENARIOS:
        response = RESPONSES / f"{scenario.name}.json"
        if not response.exists():
            raise FileNotFoundError(f"cenário {scenario.name}: falta a resposta gravada {response}")
        if json.loads(response.read_text(encoding="utf-8")).get("synthetic") is not True:
            raise ValueError(f"{response.name}: resposta escrita à mão precisa de \"synthetic\": true")
        prompt = scenario.build()
        if prompt.sha256 in index:
            raise ValueError(f"cenários {index[prompt.sha256]['scenario']} e {scenario.name} geram o mesmo prompt")
        index[prompt.sha256] = {
            "scenario": scenario.name,
            "file": f"responses/{response.name}",
            "prompt_name": prompt.name,
            "prompt_version": prompt.version,
        }
    return index


def render_index() -> str:
    return json.dumps(build_index(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    content = render_index()
    if "--check" in argv:
        if not REPLAY_INDEX.exists() or REPLAY_INDEX.read_text(encoding="utf-8") != content:
            print(f"{REPLAY_INDEX.name} desatualizado: rode .venv/bin/python code/extraction/fixtures/build_replays.py")
            return 1
        return 0
    REPLAY_INDEX.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
