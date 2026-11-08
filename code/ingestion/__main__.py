"""Ingere um conjunto de documentos e grava data/processed/ingestion/<conjunto>.json.

Uso, a partir da raiz do repositório:

    PYTHONPATH=code .venv/bin/python -m ingestion code/ingestion/fixtures/fixture.toml

Se a saída já existe, mostra o que mudou em relação a ela antes de gravar. Saída gravada a partir
de outro arquivo de conjunto é recusada, com ou sem --check.
"""

import argparse
import sys
from pathlib import Path

from ingestion.corpus import (
    EXPERIMENT_CONFIG,
    IngestionError,
    check_same_set,
    default_output,
    ingest,
    load,
    load_chunking,
    render,
    write,
)
from ingestion.diff import DocumentStatus, IngestionDiff, diff

STATUS = {
    DocumentStatus.ADDED: "novo",
    DocumentStatus.REMOVED: "removido",
    DocumentStatus.MODIFIED: "modificado",
    DocumentStatus.UNCHANGED: "inalterado",
}


def describe(report: IngestionDiff) -> list[str]:
    lines = ["  configuração de chunking mudou"] if report.chunking_changed else []
    for d in report.documents:
        status = STATUS[d.status]
        if d.status is DocumentStatus.MODIFIED:
            status += f" (sha256 {d.previous_sha256[:12]} para {d.sha256[:12]})"
        if d.metadata_changed:
            status += ", tipo ou título mudou"
        lines.append(f"  {d.path}: {status}, +{len(d.added)} -{len(d.removed)} ={len(d.kept)} chunks")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ingestion", description=__doc__.splitlines()[0])
    parser.add_argument("set_file", type=Path, help="arquivo TOML do conjunto")
    parser.add_argument("--config", type=Path, default=EXPERIMENT_CONFIG, help="TOML com a tabela [chunking]")
    parser.add_argument("--output", type=Path, help="padrão: data/processed/ingestion/<conjunto>.json")
    parser.add_argument("--check", action="store_true", help="não grava; sai com 1 se a saída mudaria")
    args = parser.parse_args(argv)
    output = args.output or default_output(args.set_file)

    try:
        current = ingest(args.set_file, load_chunking(args.config))
        previous = load(output) if output.is_file() else None
        if previous is not None:
            check_same_set(previous, current, output)
    except IngestionError as error:
        print(f"erro: {error}", file=sys.stderr)
        return 1

    print(f"{output.name}: {len(current.documents)} documentos, {len(current.chunks)} chunks")
    if previous is None:
        print("  sem ingestão anterior")
    else:
        print(*describe(diff(previous, current)), sep="\n")

    if args.check:
        same = output.is_file() and output.read_bytes() == render(current)
        print("  saída em dia" if same else "  saída desatualizada")
        return 0 if same else 1
    print(f"  {'gravado' if write(current, output) else 'bytes iguais, nada gravado'}: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
