"""Preenche uma planilha cega dos fixtures como o autor preencheria, pela declaração de cada item.

    .venv/bin/python code/experiments/metrics/fixtures/decisions.py <planilha.toml>

Só para os registros sintéticos de fixtures/runs/fixture-run.
"""

import json
import sys
import tomllib
from pathlib import Path

DECISIONS = {
    "O sistema deve cadastrar cada bandeja com a data de semeadura.": "a01-R01",
    "A tela de cadastro deve abrir rápido.": "a01-R02",
    "A tela de cadastro deve abrir rapidamente no tablet.": "a01-R02",
    "O sistema deve emitir alerta de umidade.": "a01-R03",
    "Os registros de semeadura devem ser guardados por dois anos.": "a02-R01",
    "O sistema deve exportar relatório em planilha.": "a02-R02",
    "O sistema deve guardar os registros de semeadura por dois anos.": "a02-R01",
    "O sistema deve notificar o auditor sobre cada decisão.": "nenhum",
}


def fill(path: Path, decisions: dict[str, str] = DECISIONS) -> None:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    statement = None
    for i, line in enumerate(lines):
        if line.startswith("statement = ") and (i == 0 or not lines[i - 1].startswith("id = ")):
            statement = tomllib.loads(line)["statement"]
        elif line == 'decision = ""':
            lines[i] = f"decision = {json.dumps(decisions[statement], ensure_ascii=False)}"
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    for name in sys.argv[1:]:
        fill(Path(name))
