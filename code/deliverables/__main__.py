"""Gera os quatro artefatos do estudo de caso a partir de uma corrida.

    PYTHONPATH=code .venv/bin/python -m deliverables <run_id> --condition REQKG-grounded --run-index 0 --name <nome>

Grava em outputs/caso/<nome>/. Bytes iguais não são regravados. --check não grava e sai com 1 se
algum artefato estiver desatualizado.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from domain.enums import Condition

from deliverables.catalog import build_catalog
from deliverables.inputs import CASE_DIR, CONFIG, RUNS_DIR, DeliverableError, Selection, load, relative
from deliverables.render import render_all

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
ORIGIN_FILE = "origem.json"


def command_line(selection: Selection, name: str, runs_dir: Path, config: Path, ingestion: list[Path]) -> str:
    """O comando que regenera os artefatos, com caminhos relativos à raiz e só as opções fora do padrão."""
    parts = ["PYTHONPATH=code .venv/bin/python -m deliverables", selection.run_id,
             "--condition", selection.condition.value, "--run-index", str(selection.run_index), "--name", name]
    if Path(runs_dir).resolve() != RUNS_DIR:
        parts += ["--runs-dir", relative(runs_dir)]
    if Path(config).resolve() != CONFIG:
        parts += ["--config", relative(config)]
    for path in ingestion:
        parts += ["--ingestion", relative(path)]
    for case in selection.cases:
        parts += ["--case", case]
    return " ".join(parts)


def generate(selection: Selection, name: str, runs_dir: Path = RUNS_DIR, config: Path = CONFIG,
             ingestion: list[Path] | None = None) -> dict[str, bytes]:
    if not NAME.fullmatch(name):
        raise DeliverableError(f"--name {name!r}: use letras, dígitos, '.', '_' ou '-', até 64 caracteres")
    ingestion = list(ingestion or [])
    inputs = load(selection, runs_dir, config, ingestion)
    command = command_line(selection, name, runs_dir, config, ingestion)
    texts = render_all(build_catalog(inputs), name, command)
    files = {file: text.encode("utf-8") for file, text in texts.items()}
    origin = {
        "command": command,
        "selection": {"run_id": selection.run_id, "condition": selection.condition.value,
                      "run_index": selection.run_index, "cases": inputs.cases},
        "inputs": {k: {"path": f.path, "sha256": f.sha256} for k, f in sorted(inputs.files.items())},
        "artifacts": {file: hashlib.sha256(data).hexdigest() for file, data in sorted(files.items())},
    }
    files[ORIGIN_FILE] = (json.dumps(origin, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return files


def write(files: dict[str, bytes], directory: Path) -> list[str]:
    """Grava só o que mudou. Devolve os nomes gravados."""
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for file, data in sorted(files.items()):
        target = directory / file
        if target.is_file() and target.read_bytes() == data:
            continue
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, target)
        written.append(file)
    return written


def stale(files: dict[str, bytes], directory: Path) -> list[str]:
    return [f for f, data in sorted(files.items()) if not (directory / f).is_file() or (directory / f).read_bytes() != data]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m deliverables", description=__doc__.split("\n")[0])
    parser.add_argument("run_id", help="diretório da corrida em --runs-dir")
    parser.add_argument("--condition", default=Condition.REQKG_GROUNDED.value, choices=[c.value for c in Condition])
    parser.add_argument("--run-index", type=int, required=True, help="repetição da corrida, a partir de 0")
    parser.add_argument("--name", required=True, help="nome do diretório em outputs/caso/")
    parser.add_argument("--case", action="append", default=[], help="restringe aos casos dados (repetível)")
    parser.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    parser.add_argument("--config", type=Path, default=CONFIG, help="configuração usada na corrida")
    parser.add_argument("--ingestion", type=Path, action="append", default=[],
                        help="arquivo de ingestão (repetível). Padrão: os de data/processed/ingestion/ registrados "
                             "na corrida")
    parser.add_argument("--output-root", type=Path, default=CASE_DIR, help=argparse.SUPPRESS)
    parser.add_argument("--check", action="store_true", help="não grava; sai com 1 se algo estiver desatualizado")
    args = parser.parse_args(argv)

    selection = Selection(args.run_id, Condition(args.condition), args.run_index, tuple(sorted(set(args.case))))
    try:
        files = generate(selection, args.name, args.runs_dir, args.config, args.ingestion)
    except DeliverableError as error:
        print(f"erro: {error}", file=sys.stderr)
        return 2
    directory = args.output_root / args.name
    if args.check:
        outdated = stale(files, directory)
        for file in outdated:
            print(f"desatualizado: {directory / file}", file=sys.stderr)
        return 1 if outdated else 0
    written = write(files, directory)
    print(f"{directory}: {len(written)} gravado(s), {len(files) - len(written)} sem mudança")
    return 0


if __name__ == "__main__":
    sys.exit(main())
