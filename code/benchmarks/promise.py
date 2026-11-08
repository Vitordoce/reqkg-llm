"""Converte o PROMISE NFR (ARFF original) em JSONL determinístico.

Uso, a partir da raiz do repositório:

    python3 code/benchmarks/promise.py

`python -m code.benchmarks.promise` não funciona: o módulo `code` da biblioteca
padrão tem precedência sobre o diretório `code/`, que não é pacote.

O PROMISE serve só para avaliar classificação (funcional versus não funcional
e categoria de qualidade). Ele não é oráculo de proveniência.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tarfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = REPO_ROOT / "data/raw/promise/nfr.tar"
DEFAULT_OUTPUT = REPO_ROOT / "data/processed/promise/promise_nfr.jsonl"
DEFAULT_STATS = REPO_ROOT / "data/processed/promise/STATS.md"
TAR_MEMBER = "nfr/nfr.arff"
SOURCE_ENCODING = "cp1252"

LABEL_NAMES = {
    "F": "Functional",
    "A": "Availability",
    "L": "Legal",
    "LF": "Look and feel",
    "MN": "Maintainability",
    "O": "Operational",
    "PE": "Performance",
    "SC": "Scalability",
    "SE": "Security",
    "US": "Usability",
    "FT": "Fault tolerance",
    "PO": "Portability",
}
EXPECTED_ATTRIBUTES = ("projectid", "requirementtext", "class")


class ArffError(ValueError):
    pass


@dataclass(frozen=True)
class PromiseRecord:
    promise_id: str
    project_id: int
    text: str
    label: str
    label_name: str
    is_functional: bool


def read_source_bytes(path: Path) -> bytes:
    if tarfile.is_tarfile(path):
        with tarfile.open(path) as tar:
            try:
                member = tar.extractfile(TAR_MEMBER)
            except KeyError:
                raise ArffError(f"{path}: membro {TAR_MEMBER!r} ausente no tar") from None
            if member is None:
                raise ArffError(f"{path}: {TAR_MEMBER!r} não é arquivo regular")
            return member.read()
    return path.read_bytes()


def split_row(line: str, line_no: int) -> list[str]:
    values: list[str] = []
    i, n = 0, len(line)
    while i <= n:
        while i < n and line[i] in " \t":
            i += 1
        if i < n and line[i] in "'\"":
            quote, i, buf = line[i], i + 1, []
            while True:
                if i >= n:
                    raise ArffError(f"linha {line_no}: aspas sem fechamento")
                ch = line[i]
                if ch == "\\" and i + 1 < n:
                    buf.append(line[i + 1])
                    i += 2
                elif ch == quote:
                    i += 1
                    break
                else:
                    buf.append(ch)
                    i += 1
            values.append("".join(buf))
            while i < n and line[i] in " \t":
                i += 1
            if i < n and line[i] != ",":
                raise ArffError(f"linha {line_no}: texto após aspas de fechamento")
        else:
            end = line.find(",", i)
            end = n if end == -1 else end
            values.append(line[i:end].strip())
            i = end
        i += 1
    return values


def parse_nominal(spec: str, line_no: int) -> set[str]:
    start, end = spec.find("{"), spec.find("}")
    if start == -1 or end < start:
        raise ArffError(f"linha {line_no}: atributo nominal sem chaves")
    return {v.strip() for v in spec[start + 1 : end].split(",")}


def parse_arff(raw: bytes) -> list[PromiseRecord]:
    text = raw.decode(SOURCE_ENCODING)
    attributes: list[tuple[str, str, int]] = []
    in_data = False
    rows: list[tuple[int, list[str]]] = []
    for line_no, line in enumerate(text.split("\n"), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("%"):
            continue
        if in_data:
            rows.append((line_no, split_row(stripped, line_no)))
            continue
        keyword = stripped.split(None, 1)[0].lower()
        if keyword == "@attribute":
            parts = stripped.split(None, 2)
            if len(parts) < 3:
                raise ArffError(f"linha {line_no}: @ATTRIBUTE incompleto")
            attributes.append((parts[1].lower(), parts[2], line_no))
        elif keyword == "@data":
            in_data = True
        elif keyword != "@relation":
            raise ArffError(f"linha {line_no}: cabeçalho inesperado {stripped[:40]!r}")

    names = tuple(name for name, _, _ in attributes)
    if names != EXPECTED_ATTRIBUTES:
        raise ArffError(f"atributos {names} diferem de {EXPECTED_ATTRIBUTES}")
    if not in_data:
        raise ArffError("seção @DATA ausente")
    projects = parse_nominal(attributes[0][1], attributes[0][2])
    labels = parse_nominal(attributes[2][1], attributes[2][2])
    unknown = labels - LABEL_NAMES.keys()
    if unknown:
        raise ArffError(f"rótulos declarados sem nome conhecido: {sorted(unknown)}")

    width = max(4, len(str(len(rows))))
    records = []
    for index, (line_no, values) in enumerate(rows, start=1):
        if len(values) != 3:
            raise ArffError(f"linha {line_no}: esperados 3 campos, encontrados {len(values)}")
        project, requirement, label = values
        if project not in projects:
            raise ArffError(f"linha {line_no}: ProjectID {project!r} fora do domínio declarado")
        if label not in labels:
            raise ArffError(f"linha {line_no}: rótulo {label!r} fora do domínio declarado")
        records.append(
            PromiseRecord(
                promise_id=f"PROMISE-NFR-{index:0{width}d}",
                project_id=int(project),
                text=requirement,
                label=label,
                label_name=LABEL_NAMES[label],
                is_functional=label == "F",
            )
        )
    return records


def to_jsonl(records: list[PromiseRecord]) -> bytes:
    lines = [json.dumps(asdict(r), ensure_ascii=False, separators=(",", ":")) for r in records]
    return ("\n".join(lines) + "\n").encode("utf-8")


def compute_stats(records: list[PromiseRecord]) -> dict:
    labels = Counter(r.label for r in records)
    projects = Counter(r.project_id for r in records)
    by_text: dict[str, list[PromiseRecord]] = {}
    for r in records:
        by_text.setdefault(r.text, []).append(r)
    return {
        "total": len(records),
        "functional": sum(r.is_functional for r in records),
        "non_functional": sum(not r.is_functional for r in records),
        "labels": {k: labels[k] for k in sorted(labels, key=lambda k: (-labels[k], k))},
        "projects": {k: projects[k] for k in sorted(projects)},
        "duplicate_texts": len(records) - len(by_text),
        "duplicate_groups": [
            [f"{r.promise_id}:{r.label}" for r in group] for group in by_text.values() if len(group) > 1
        ],
    }


def render_stats_md(stats: dict, source_name: str, source_sha256: str) -> str:
    total = stats["total"]

    def pct(n: int) -> str:
        return f"{100 * n / total:.2f}%"

    out = [
        "# Estatísticas do PROMISE NFR processado",
        "",
        "Arquivo gerado por `code/benchmarks/promise.py`. Não editar à mão.",
        "",
        "Para regenerar, a partir da raiz do repositório:",
        "",
        "```",
        "python3 code/benchmarks/promise.py",
        "```",
        "",
        f"Entrada: `{source_name}`, membro `{TAR_MEMBER}`.",
        f"SHA-256 da entrada: `{source_sha256}`.",
        "Saída: `data/processed/promise/promise_nfr.jsonl`.",
        "",
        "## Totais",
        "",
        "| Medida | Valor |",
        "| --- | ---: |",
        f"| Requisitos | {total} |",
        f"| Funcionais (F) | {stats['functional']} |",
        f"| Não funcionais | {stats['non_functional']} |",
        f"| Projetos | {len(stats['projects'])} |",
        f"| Textos repetidos (além da primeira ocorrência) | {stats['duplicate_texts']} |",
        "",
        "## Distribuição por rótulo",
        "",
        "| Rótulo | Nome | Quantidade | Percentual |",
        "| --- | --- | ---: | ---: |",
    ]
    for label, n in stats["labels"].items():
        out.append(f"| {label} | {LABEL_NAMES[label]} | {n} | {pct(n)} |")
    out += ["", "## Contagem por projeto", "", "| ProjectID | Quantidade |", "| ---: | ---: |"]
    for project, n in stats["projects"].items():
        out.append(f"| {project} | {n} |")
    out += ["", "## Textos repetidos", ""]
    if stats["duplicate_groups"]:
        out.append("Cada linha lista registros com o mesmo `text`, no formato `promise_id:rótulo`.")
        out.append("")
        out += [f"- {', '.join(group)}" for group in stats["duplicate_groups"]]
    else:
        out.append("Nenhum.")
    out += [
        "",
        "## Notas",
        "",
        f"- O `text` é o conteúdo entre aspas no ARFF, decodificado de {SOURCE_ENCODING}, sem outra normalização.",
        "  Espaços iniciais e espaços duplos do original foram mantidos.",
        "- `promise_id` segue a ordem das linhas em `@DATA`.",
        "- O PROMISE serve só para avaliar classificação. Não é oráculo de proveniência.",
    ]
    return "\n".join(out) + "\n"


def write_if_changed(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == data:
        return
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def convert(input_path: Path, output_path: Path, stats_path: Path | None) -> dict:
    raw = read_source_bytes(input_path)
    records = parse_arff(raw)
    write_if_changed(output_path, to_jsonl(records))
    stats = compute_stats(records)
    if stats_path is not None:
        source_sha = hashlib.sha256(input_path.read_bytes()).hexdigest()
        try:
            source_name = input_path.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            source_name = input_path.name
        write_if_changed(stats_path, render_stats_md(stats, source_name, source_sha).encode("utf-8"))
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="nfr.tar ou nfr.arff")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--stats", type=Path, default=DEFAULT_STATS)
    parser.add_argument("--no-stats", action="store_true", help="não grava STATS.md")
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(
            f"erro: entrada {args.input} não existe. Veja data/raw/promise/SOURCE.md para o download.",
            file=sys.stderr,
        )
        return 2
    try:
        stats = convert(args.input, args.output, None if args.no_stats else args.stats)
    except ArffError as exc:
        print(f"erro: {args.input}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
