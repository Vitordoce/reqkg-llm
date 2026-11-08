"""Métricas de uma corrida em outputs/runs/<run_id>/metrics/.

Uso, a partir da raiz do repositório:

    PYTHONPATH=code .venv/bin/python -m experiments.metrics <run_id> sheet --ingestion <conjunto>.json --reference data/raw/amostra
    PYTHONPATH=code .venv/bin/python -m experiments.metrics <run_id> lock --run-index 0 --ingestion ... --reference ...
    PYTHONPATH=code .venv/bin/python -m experiments.metrics <run_id> compute --ingestion ... --reference ...

sheet gera uma planilha cega por corrida (metrics/pairing/sheet_run<i>.toml) e guarda a chave em
metrics/pairing/key/. Depois de preencher a planilha, lock registra o SHA-256 dela; só então compute
abre a chave. compute calcula tudo o que os registros permitem e grava as tabelas e o summary.md.
"""

import argparse
import shlex
import sys
from pathlib import Path

from domain.config import ContractError
from domain.ids import sha256_text
from experiments.annotation import validate_sample
from ingestion.chunking import normalize_text
from experiments.metrics import pairing, report
from experiments.metrics.loading import (
    CONFIG_PATH,
    PROMISE_LABELS,
    RUNS_ROOT,
    display_path,
    load_config,
    load_corpus,
    load_run,
)
from experiments.metrics.promise import load_gold


def load_reference(directory: Path, corpus):
    """A amostra validada, com cada artefato conferido contra o documento ingerido de mesmo nome pelo SHA-256 do
    texto (pairing.check_artifact_texts)."""
    found = validate_sample(directory)
    if found.errors or found.reference is None:
        lines = [f"{directory}: {len(found.errors)} erro(s) na amostra de referência"] + [f"  {f}" for f in found.errors]
        raise ContractError("\n".join(lines))
    pairing.check_artifact_texts({a: sha256_text(normalize_text(t.text)) for a, t in found.texts.items()}, corpus)
    return found.reference, found.hashes


def command_line(args: argparse.Namespace) -> str:
    parts = [args.run_id]
    if Path(args.runs_root).resolve() != RUNS_ROOT.resolve():
        parts += ["--runs-root", display_path(args.runs_root)]
    if Path(args.config).resolve() != CONFIG_PATH.resolve():
        parts += ["--config", display_path(args.config)]
    parts.append("compute")
    for path in args.ingestion:
        parts += ["--ingestion", display_path(path)]
    if args.reference:
        parts += ["--reference", display_path(args.reference)]
    if Path(args.promise_labels).resolve() != PROMISE_LABELS.resolve():
        parts += ["--promise-labels", display_path(args.promise_labels)]
    if args.skip_bertscore:
        parts.append("--skip-bertscore")
    if args.bertscore_revision:
        parts += ["--bertscore-revision", args.bertscore_revision]
    if args.bertscore_num_layers is not None:
        parts += ["--bertscore-num-layers", str(args.bertscore_num_layers)]
    return "PYTHONPATH=code .venv/bin/python -m experiments.metrics " + shlex.join(parts)


def _rows_by_run(args, run, config):
    corpus = load_corpus(args.ingestion, run.manifest, config.chunking)
    reference, _ = load_reference(args.reference, corpus)
    refs = pairing.references_by_case(reference, corpus, run.case_ids())
    rows = {i: pairing.sheet_rows(pairing.generated(run, corpus, refs, i), config.evaluation.seed, i)
            for i in run.run_indices()}
    return rows, reference


def cmd_sheet(args, run, config) -> int:
    if not run.finals:
        raise ContractError(f"{run.directory}: sem finals.jsonl, não há requisito gerado para parear")
    rows, reference = _rows_by_run(args, run, config)
    for run_index, items in rows.items():
        path = pairing.write_sheet(run.directory, run.manifest.run_id, run_index, items, reference, args.force)
        print(f"corrida {run_index}: {len(items)} itens em {display_path(path)}")
    print(f"A chave fica em {display_path(pairing.pairing_dir(run.directory) / 'key')}. Não abra antes de rodar lock.")
    return 0


def cmd_lock(args, run, config) -> int:
    rows, _ = _rows_by_run(args, run, config)
    if args.run_index not in rows:
        raise ContractError(f"a corrida não tem a repetição {args.run_index}; tem {sorted(rows)}")
    record = pairing.lock(run.directory, run.manifest.run_id, args.run_index, rows[args.run_index])
    print(f"Decisões da repetição {args.run_index} registradas em {record['locked_at']}: {record['items']} itens, "
          f"{record['decided_none']} com {pairing.NONE!r}.")
    print(f"SHA-256 da planilha preenchida: {record['sheet_sha256']}")
    print("Registre este hash em PROGRESS.md antes de abrir a chave.")
    return 0


def cmd_compute(args, run, config) -> int:
    corpus = load_corpus(args.ingestion, run.manifest, config.chunking) if run.finals else None
    reference, hashes = load_reference(args.reference, corpus) if args.reference and run.finals else (None, {})
    gold = load_gold(args.promise_labels) if run.classifications else None
    if not run.finals and not run.classifications:
        raise ContractError(f"{run.directory}: sem finals.jsonl nem classifications.jsonl, nada a calcular")
    inputs = report.input_lines(run, args.config, corpus, args.reference if reference else None, hashes,
                                args.promise_labels)
    revision = args.bertscore_revision or config.evaluation.bertscore_revision or "main"
    num_layers = args.bertscore_num_layers or config.evaluation.bertscore_num_layers
    result = report.compute(run, config, command_line(args), inputs, corpus, reference, gold, args.skip_bertscore,
                            revision, num_layers)
    written = report.write(result, run.directory / "metrics")
    for path in written:
        print(display_path(path))
    if result.pairing and result.pairing.pending:
        print(f"pareamento pendente nas corridas {result.pairing.pending}: rode sheet, preencha e rode lock")
    return 0


def parser() -> argparse.ArgumentParser:
    main = argparse.ArgumentParser(prog="python -m experiments.metrics", description=__doc__.split("\n")[0])
    main.add_argument("run_id")
    main.add_argument("--runs-root", type=Path, default=RUNS_ROOT, help="pasta das corridas (padrão outputs/runs)")
    main.add_argument("--config", type=Path, default=CONFIG_PATH,
                      help="configuração congelada da corrida; o SHA-256 tem de bater com o manifesto")
    sub = main.add_subparsers(dest="command", required=True)

    def with_inputs(p: argparse.ArgumentParser, reference_required: bool) -> argparse.ArgumentParser:
        p.add_argument("--ingestion", type=Path, action="append", default=[], help="arquivo de conjunto (.toml, ingerido em memória) ou saída da ingestão (.json); "
                       "repetível")
        p.add_argument("--reference", type=Path, required=reference_required, help="pasta da amostra de referência")
        return p

    sheet = with_inputs(sub.add_parser("sheet", help="gera as planilhas cegas de pareamento"), True)
    sheet.add_argument("--force", action="store_true", help="sobrescreve planilha ainda não registrada")
    lock = with_inputs(sub.add_parser("lock", help="registra o SHA-256 das decisões de uma corrida"), True)
    lock.add_argument("--run-index", type=int, required=True)
    compute = with_inputs(sub.add_parser("compute", help="calcula as métricas e grava metrics/"), False)
    compute.add_argument("--promise-labels", type=Path, default=PROMISE_LABELS)
    compute.add_argument("--skip-bertscore", action="store_true", help="não calcula o BERTScore")
    compute.add_argument("--bertscore-revision", default="", help="revisão do modelo no Hugging Face; padrão: a da configuração")
    compute.add_argument("--bertscore-num-layers", type=int, default=None, help="camada usada pelo BERTScore")
    return main


COMMANDS = {"sheet": cmd_sheet, "lock": cmd_lock, "compute": cmd_compute}


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        run_dir = Path(args.runs_root) / args.run_id
        if not run_dir.is_dir():
            raise ContractError(f"{run_dir}: corrida não encontrada")
        run = load_run(run_dir)
        config = load_config(args.config, run.manifest)
        return COMMANDS[args.command](args, run, config)
    except (ContractError, ValueError) as error:
        print(f"erro: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
