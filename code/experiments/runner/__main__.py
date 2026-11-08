"""Executor do experimento. Ver code/experiments/runner/README.md.

PYTHONPATH=code .venv/bin/python -m experiments.runner RUN_ID (--replay ARQ | --synthetic | --real) \\
    [--ingestion CONJUNTO ...] [--promise ...] [--pilot] [--freeze MANIFESTO] [--resume] [--dry-run]
"""

import argparse
import json
import shlex
import sys
from pathlib import Path

from domain.config import ContractError, ExperimentConfig
from domain.serialization import load_toml
from experiments.runner.clients import load_replay
from experiments.runner.calibrate import calibration_path
from experiments.runner.dry_run import RATE_STAGES, Rate, estimate
from experiments.runner.fixtures import CONFIG_FILE
from experiments.runner.fixtures.synthetic import SyntheticClient
from experiments.runner.inputs import InputError, load_promise, load_structural
from experiments.runner.run import Mode, Plan, ResumeDiverged, make_plan, run
from experiments.runner.rundir import RunDirectory, RunRefused, preflight
from extraction.client import RUNS_ROOT, ClientConfigError, LLMClient, MissingReplayError, real_client
from graph.connection import Graph, GraphUnavailable, Neo4jSettings, UnsafeTarget
from ingestion.corpus import IngestionError
from retrieval.promise import PROMISE_JSONL, PromiseError

COMMAND_PREFIX = "PYTHONPATH=code .venv/bin/python -m experiments.runner"


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m experiments.runner", description=__doc__.splitlines()[0])
    parser.add_argument("run_id", nargs="?", help="nome da corrida em outputs/runs/ (dispensável com --dry-run)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--replay", type=Path, metavar="ARQ", help="calls.jsonl de uma corrida ou replay_index.json")
    mode.add_argument("--synthetic", action="store_true", help="cliente sintético dos fixtures, sem modelo")
    mode.add_argument("--real", action="store_true", help="chama o modelo de model.provider (Ollama: servidor no ar e digest conferido)")
    parser.add_argument("--config", type=Path, default=CONFIG_FILE, help="padrão: code/experiments/config/experiment.toml")
    parser.add_argument("--ingestion", type=Path, nargs="+", default=[], metavar="CONJUNTO",
                        help="arquivos de conjunto (.toml) ou saídas da ingestão (.json); cada documento é um caso")
    parser.add_argument("--promise", action="store_true", help="roda a tarefa de classificação do PROMISE")
    parser.add_argument("--promise-file", type=Path, default=PROMISE_JSONL, help="padrão: data/processed/promise/promise_nfr.jsonl")
    parser.add_argument("--promise-projects", metavar="N,N", help="só estes projetos")
    parser.add_argument("--promise-items", metavar="ID,ID", help="só estes promise_id")
    parser.add_argument("--promise-limit", type=int, metavar="N",
                        help="no máximo N itens no total, sorteados com evaluation.seed e espalhados pelos projetos")
    parser.add_argument("--pilot", action="store_true", help="corrida piloto: dispensa o congelamento; run_id começa por pilot-")
    parser.add_argument("--runs", type=int, metavar="N", help="repetições, só com --pilot")
    parser.add_argument("--freeze", type=Path, metavar="MANIFESTO", help="manifesto de make freeze; obrigatório em corrida real")
    parser.add_argument("--resume", action="store_true",
                        help="retoma a corrida interrompida em .partial-RUN_ID, com os mesmos argumentos; "
                             "as chamadas gravadas vêm do registro, só o que falta vai à API")
    parser.add_argument("--runs-root", type=Path, default=RUNS_ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", help="conta chamadas e estima tokens, sem chamar nada")
    parser.add_argument("--chars-per-token", type=float, default=None,
                        help="conversão do dry-run (padrão: a da calibração, ou 3.5 sem ela)")
    parser.add_argument("--targets-per-chunk", type=float, default=1.0, help="alvos de refinamento por chunk no dry-run")
    parser.add_argument("--json", action="store_true", help="dry-run em JSON")
    parser.add_argument("--calibration", type=Path, metavar="ARQ",
                        help="taxa medida para o tempo do dry-run (padrão: outputs/calibracao/<model_id>.json, se existir)")
    parser.add_argument("--rate", metavar="ENTRADA,SAÍDA,FIXO,SAÍDA_POR_CHAMADA",
                        help="taxa sem calibração: tokens/s de entrada, tokens/s de saída, segundos fixos por chamada "
                             "e tokens de saída por chamada em todas as etapas")
    args = parser.parse_args(argv)
    if not args.dry_run:
        if not args.run_id:
            parser.error("falta o RUN_ID")
        if not (args.replay or args.synthetic or args.real):
            parser.error("escolha --replay ARQ, --synthetic ou --real")
    return args


def dry_run_rate(args: argparse.Namespace, model_id: str) -> Rate | None:
    if args.rate:
        try:
            prompt_tps, output_tps, overhead, per_call = (float(v) for v in args.rate.split(","))
        except ValueError:
            raise ValueError(f"--rate {args.rate!r}: use quatro números separados por vírgula") from None
        if min(prompt_tps, output_tps) <= 0 or min(overhead, per_call) < 0:
            raise ValueError(f"--rate {args.rate!r}: taxas positivas, tempo fixo e saída não negativos")
        return Rate(prompt_tps, output_tps, overhead, dict.fromkeys(RATE_STAGES, per_call), origin="--rate")
    if args.calibration:
        return Rate.from_calibration(args.calibration)
    default = calibration_path(model_id) if model_id else None
    return Rate.from_calibration(default) if default and default.is_file() else None


def make_client(args: argparse.Namespace, plan: Plan) -> tuple[Mode, LLMClient]:
    if args.real:
        return Mode.REAL, real_client(plan.config.model)
    if args.synthetic:
        return Mode.SYNTHETIC, SyntheticClient.for_projects(list(plan.promise.projects) if plan.promise else [])
    return Mode.REPLAY, load_replay(args.replay)


def stop_message(error: BaseException, partial: Path) -> str:
    if isinstance(error, MissingReplayError):
        return (f"runner: corrida parada por falta de resposta gravada: {error}. O que já foi gravado ficou em "
                f"{partial}, mas --resume não resolve: a retomada pede de novo a mesma chamada e a resposta continua "
                "faltando. Confira se --ingestion, --promise, os filtros do PROMISE e --config são os da corrida "
                "gravada (o command do manifest.json dela), e rode com outro run_id ou depois de apagar a pasta parcial")
    reason = "interrompida pelo usuário (Ctrl-C)" if isinstance(error, KeyboardInterrupt) else str(error) or type(error).__name__
    return (f"runner: corrida interrompida, {reason}. O que já foi gravado ficou em {partial}. Repita o mesmo "
            "comando com --resume para continuar sem pagar de novo as chamadas gravadas")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = parse_arguments(argv)
    try:
        config = load_toml(args.config, ExperimentConfig)
        structural = load_structural(args.ingestion, config.chunking) if args.ingestion else None
        promise = (load_promise(config.chunking, config.evaluation.seed, args.promise_file,
                                projects=args.promise_projects, items=args.promise_items, limit=args.promise_limit)
                   if args.promise else None)
        plan = make_plan(args.config, structural=structural, promise=promise, runs=args.runs, pilot=args.pilot)
    except (RunRefused, InputError, IngestionError, PromiseError, ContractError, FileNotFoundError) as error:
        print(f"runner: {error}", file=sys.stderr)
        return 1

    if args.dry_run:
        try:
            rate = dry_run_rate(args, plan.config.model.model_id)
        except (OSError, ValueError, KeyError) as error:
            print(f"runner: taxa do dry-run: {error}", file=sys.stderr)
            return 1
        chars_per_token = args.chars_per_token or (rate.chars_per_token if rate else None) or 3.5
        result = estimate(plan, chars_per_token=chars_per_token, targets_per_chunk=args.targets_per_chunk, rate=rate)
        print(json.dumps(result.to_json(), ensure_ascii=False, indent=2) if args.json else result.render())
        return 0

    try:
        preflight(plan.config, config_path=plan.config_path, real=bool(args.real), run_id=args.run_id,
                  pilot=args.pilot, freeze=args.freeze)
        if args.resume:
            RunDirectory.check_resumable(args.run_id, args.runs_root)
        else:
            RunDirectory.check_free(args.run_id, args.runs_root)
        mode, client = make_client(args, plan)
    except (RunRefused, ClientConfigError, FileNotFoundError, ValueError) as error:
        print(f"runner: recusado: {error}", file=sys.stderr)
        return 1
    try:
        graph = Graph(Neo4jSettings.from_env())
    except (GraphUnavailable, UnsafeTarget) as error:
        print(f"runner: {error}. Rode make neo4j-up e make neo4j-wait", file=sys.stderr)
        return 1
    command = " ".join([COMMAND_PREFIX, *map(shlex.quote, argv)])
    with graph:
        try:
            final = run(plan, run_id=args.run_id, mode=mode, client=client, graph=graph, command=command,
                        pilot=args.pilot, freeze=args.freeze, runs_root=args.runs_root, resume=args.resume)
        except RunRefused as error:
            print(f"runner: recusado: {error}", file=sys.stderr)
            return 1
        except ResumeDiverged as error:
            print(f"runner: retomada divergiu: {error}", file=sys.stderr)
            return 2
        except (MissingReplayError, TimeoutError, KeyboardInterrupt) as error:
            print(stop_message(error, args.runs_root / f".partial-{args.run_id}"), file=sys.stderr)
            return 2
    print(f"runner: corrida gravada em {final}")
    for name in sorted(p.name for p in final.iterdir()):
        lines = sum(1 for _ in (final / name).open(encoding="utf-8")) if name.endswith(".jsonl") else 1
        print(f"  {name:<24} {lines} linha(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
