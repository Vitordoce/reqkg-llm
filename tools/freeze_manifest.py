#!/usr/bin/env python3
"""Write or check the SHA-256 freeze manifest of the experiment inputs and code.

The work is not versioned in Git. This manifest is the proof that the code that
produces the results, the environment locks, the configuration, the prompts and
the evaluation data did not change after the freeze.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORMAT = "reqkg-freeze/1"
# Test files and fixtures stay in: some fixtures are imported by the runner (the synthetic
# client), and the package ships them, so the frozen set is a subset of the package.
# PUBLICACAO.toml stays out on purpose: the published runs are chosen after the runs exist.
DEFAULT_PATHS = (
    "code",
    "tools",
    "requirements*.lock",
    "pyproject.toml",
    "Makefile",
    "docker-compose.yml",
    "code/experiments/config",
    "code/extraction/prompts",
    "data/raw/amostra",
    "data/raw/promise",
)
# A root on the left only counts as present when the file on the right exists. TEMPLATE/
# alone keeps data/raw/amostra non-empty, so the folder existing proves nothing.
REQUIRED_INSIDE = {"data/raw/amostra": "data/raw/amostra/referencia.toml"}
# Hidden entries are ignored like in the package: the Neo4j lock in code/graph/, the
# .partial-<run_id> folders and the temporary files that tests create.
IGNORED_DIRS = {"__pycache__"}
IGNORED_FILES = {".DS_Store"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


class FreezeError(Exception):
    pass


def canonical_json(value: object) -> bytes:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def relative_key(path: Path, root: Path) -> str:
    return unicodedata.normalize("NFC", path.relative_to(root).as_posix())


def is_ignored(path: Path, root: Path) -> bool:
    parts = path.relative_to(root).parts
    return (
        any(part in IGNORED_DIRS or part.startswith(".") for part in parts)
        or path.name in IGNORED_FILES
        or path.suffix in IGNORED_SUFFIXES
    )


def hash_tree(root: Path, paths: list[str]) -> tuple[dict[str, str], list[str]]:
    files: dict[str, str] = {}
    missing: list[str] = []
    for entry in paths:
        targets = sorted(root.glob(entry)) if "*" in entry else [root / entry]
        candidates = []
        for target in targets:
            if target.is_file():
                candidates.append(target)
            elif target.is_dir():
                candidates.extend(p for p in target.rglob("*") if p.is_file())
        if not candidates:
            missing.append(entry)
            continue
        required = REQUIRED_INSIDE.get(entry)
        if required and not (root / required).is_file():
            missing.append(required)
        for path in candidates:
            if not is_ignored(path, root):
                files[relative_key(path, root)] = sha256_file(path)
    return dict(sorted(files.items())), sorted(missing)


def normalize_paths(paths: list[str]) -> list[str]:
    normalized = []
    for entry in paths:
        posix = unicodedata.normalize("NFC", Path(entry).as_posix()).rstrip("/")
        if Path(posix).is_absolute() or ".." in Path(posix).parts:
            raise FreezeError(f"caminho precisa ser relativo à raiz, sem '..': {entry}")
        normalized.append(posix)
    return sorted(set(normalized))


def build_manifest(root: Path, paths: list[str], date: str, allow_missing: bool) -> dict:
    roots = normalize_paths(paths)
    files, missing = hash_tree(root, roots)
    if missing and not allow_missing:
        hints = [
            f" {required} é a amostra anotada; {folder}/TEMPLATE/ sozinho não conta como amostra."
            for folder, required in REQUIRED_INSIDE.items() if required in missing
        ]
        raise FreezeError(
            "caminhos ausentes: " + ", ".join(missing) + "." + "".join(hints)
            + " Crie-os antes do congelamento. Congelamento de teste, que não vale como o oficial: "
            "make freeze FREEZE_FLAGS=--allow-missing (no script: --allow-missing)."
        )
    if not files:
        raise FreezeError("nenhum arquivo para congelar")
    return {
        "format": FORMAT,
        "date": date,
        "roots": roots,
        "missing": missing,
        "files": files,
        "tree_sha256": hashlib.sha256(canonical_json(files)).hexdigest(),
    }


def display_path(path: Path, root: Path) -> str:
    path = path.resolve()
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()


def write_manifest(manifest: dict, output: Path, root: Path) -> bool:
    """Write the manifest. Return False when an identical one already exists."""
    data = canonical_json(manifest)
    if output.exists():
        if output.read_bytes() == data:
            return False
        shown = display_path(output, root)
        other = shown[: -len(".json")] + "-b.json" if shown.endswith(".json") else shown + "-b"
        raise FreezeError(
            f"{shown} já existe com outro conteúdo, e um congelamento não é sobrescrito. "
            f"Veja o que mudou com make freeze-check MANIFEST={shown}. Se o congelamento novo for "
            f'o certo, grave com outro nome e registre o motivo: make freeze FREEZE_FLAGS="--output {other}" '
            "(no script: --output)."
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    return True


def compare(manifest: dict, root: Path) -> list[str]:
    if manifest.get("format") != FORMAT:
        raise FreezeError(f"formato de manifesto desconhecido: {manifest.get('format')!r}")
    frozen: dict[str, str] = manifest["files"]
    current, _ = hash_tree(root, manifest["roots"])
    problems = []
    for key in sorted(frozen.keys() | current.keys()):
        if key not in current:
            problems.append(f"removido: {key}")
        elif key not in frozen:
            problems.append(f"novo: {key}")
        elif frozen[key] != current[key]:
            problems.append(f"alterado: {key}")
    return problems


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", help="caminhos relativos à raiz, aceita * (padrão: código, locks e entradas do experimento)")
    parser.add_argument("--check", type=Path, metavar="MANIFESTO", help="confere a árvore contra um manifesto")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--date", help="data do congelamento, AAAA-MM-DD (padrão: hoje)")
    parser.add_argument("--output", type=Path, help="padrão: outputs/runs/freeze-<data>.json")
    parser.add_argument("--allow-missing", action="store_true", help="registra caminhos ausentes em vez de falhar")
    args = parser.parse_args(argv)
    if args.check is not None and (args.paths or args.date or args.output or args.allow_missing):
        parser.error("--check só aceita o manifesto")
    if args.date is not None:
        try:
            datetime.date.fromisoformat(args.date)
        except ValueError:
            parser.error(f"--date inválida: {args.date}")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(sys.argv[1:] if argv is None else argv)
    root = args.root.resolve()
    try:
        if args.check is not None:
            if not args.check.is_file():
                raise FreezeError(f"manifesto não encontrado: {args.check}")
            problems = compare(json.loads(args.check.read_text(encoding="utf-8")), root)
            if problems:
                print(f"freeze: {len(problems)} diferença(s) contra {args.check}:", file=sys.stderr)
                for line in problems:
                    print(f"  {line}", file=sys.stderr)
                return 1
            print(f"freeze: árvore igual a {args.check}")
            return 0

        date = args.date or datetime.date.today().isoformat()
        manifest = build_manifest(root, args.paths or list(DEFAULT_PATHS), date, args.allow_missing)
        output = args.output or root / "outputs" / "runs" / f"freeze-{date}.json"
        written = write_manifest(manifest, output, root)
        state = "gravado" if written else "já existia, idêntico"
        print(f"freeze: {output} {state}: {len(manifest['files'])} arquivos, tree_sha256 {manifest['tree_sha256']}")
        print(f"freeze: sha256 do manifesto {sha256_file(output)}")
        for entry in manifest["missing"]:
            print(f"freeze: ausente, registrado no manifesto: {entry}", file=sys.stderr)
        return 0
    except FreezeError as error:
        print(f"freeze: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
