#!/usr/bin/env python3
"""Refuse to start Neo4j with a missing, short or example password. Never prints the value."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIN_PASSWORD_LENGTH = 8
HOW_TO_CHANGE = (
    "Edite NEO4J_PASSWORD no .env (mínimo de 8 caracteres) antes da primeira subida. "
    "Se o volume já foi criado com outra senha, apague-o com docker compose down -v e suba de novo."
)


def read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if not match:
            continue
        key, raw = match.groups()
        quoted = re.fullmatch(r"""(['"])(.*)\1\s*(?:#.*)?""", raw)
        values[key] = quoted.group(2) if quoted else re.sub(r"\s+#.*$", "", raw).strip()
    return values


def neo4j_password_problem(env_path: Path, example_path: Path) -> str | None:
    if not env_path.is_file():
        return f"{env_path.name} não existe. Rode cp .env.example .env e troque NEO4J_PASSWORD."
    password = read_dotenv(env_path).get("NEO4J_PASSWORD", "")
    if not password:
        return f"NEO4J_PASSWORD está vazia ou ausente em {env_path.name}. {HOW_TO_CHANGE}"
    if example_path.is_file() and password == read_dotenv(example_path).get("NEO4J_PASSWORD"):
        return f"NEO4J_PASSWORD em {env_path.name} ainda é a senha de exemplo de {example_path.name}. {HOW_TO_CHANGE}"
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"NEO4J_PASSWORD em {env_path.name} tem menos de {MIN_PASSWORD_LENGTH} caracteres. {HOW_TO_CHANGE}"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=ROOT / ".env")
    parser.add_argument("--example", type=Path, default=ROOT / ".env.example")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    problem = neo4j_password_problem(args.env, args.example)
    if problem:
        print(f"check-env: {problem}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
