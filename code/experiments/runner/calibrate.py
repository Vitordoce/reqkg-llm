"""Calibração do dry-run: velocidade medida do modelo local em corridas piloto com dados sintéticos.

PYTHONPATH=code .venv/bin/python -m experiments.runner.calibrate RUN_ID [RUN_ID ...] [--output ARQ]

Lê calls.jsonl, case_results.jsonl e rejections.jsonl de cada corrida e grava, por padrão, em
outputs/calibracao/<model_id>.json: por etapa, chamadas, JSON que valida no contrato, motivo de parada,
tokens e segundos por chamada; os estados dos CaseResult, as violações G e as recusas W; e a taxa que o
dry-run usa (Rate). As taxas são as efetivas da corrida: o Ollama reaproveita o prefixo do prompt em
cache e conta esses tokens em prompt_eval_count sem cronometrá-los, como acontecerá na corrida do
experimento, que tem a mesma ordem de etapas. Só aceita corridas reais do Ollama, que trazem timing.
"""

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from domain.llm_io import CaseResult
from experiments.records import FILES, CallRecord, RejectionRecord, RunManifest
from extraction import prompts
from extraction.client import REPO_ROOT, RUNS_ROOT, CallLog

CALIBRATION_DIR = REPO_ROOT / "outputs" / "calibracao"


def calibration_path(model_id: str) -> Path:
    return CALIBRATION_DIR / f"{re.sub(r'[^A-Za-z0-9._-]', '-', model_id)}.json"


def _valid(record: CallRecord) -> tuple[bool, bool]:
    """(JSON que abre, JSON que valida no modelo de saída do contrato)."""
    try:
        json.loads(record.raw_response or "")
    except json.JSONDecodeError:
        return False, False
    try:
        prompts.OUTPUT_MODELS[record.prompt_name].model_validate_json(record.raw_response)
    except ValidationError:
        return True, False
    return True, True


def _jsonl(path: Path, model):
    if not path.exists():
        return []
    return [model.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _mean(values: list[float]) -> float:
    return round(statistics.fmean(values), 2) if values else 0.0


def calibrate(run_dirs: list[Path]) -> dict[str, object]:
    calls: list[CallRecord] = []
    results: list[CaseResult] = []
    rejections: list[RejectionRecord] = []
    runs = []
    for run_dir in run_dirs:
        manifest = RunManifest.model_validate_json((run_dir / FILES["manifest"]).read_text(encoding="utf-8"))
        logged = CallLog.read(run_dir / FILES["calls"])
        foreign = sorted({str(r.client.get("provider")) for r in logged} - {"ollama"})
        if manifest.replay or foreign:
            raise ValueError(f"{run_dir}: a calibração lê só corridas reais do Ollama (replay {manifest.replay}, "
                             f"provider {foreign or ['ollama']})")
        calls += logged
        results += _jsonl(run_dir / FILES["case_results"], CaseResult)
        rejections += _jsonl(run_dir / FILES["rejections"], RejectionRecord)
        runs.append({"run_id": manifest.run_id, "pilot": manifest.pilot, "calls": len(logged),
                     "first_call": logged[0].timestamp if logged else None,
                     "last_call": logged[-1].timestamp if logged else None})
    clients = sorted({json.dumps({k: r.client.get(k) for k in ("model_id", "model_digest", "num_ctx", "seed",
                                                                   "temperature", "server_version")}, sort_keys=True)
                      for r in calls})
    if len(clients) != 1:
        raise ValueError(f"as corridas misturam configurações de modelo: {clients}")
    timed = [r for r in calls if r.status == "returned" and r.timing is not None]
    if not timed:
        raise ValueError("nenhuma chamada respondida com timing nas corridas dadas")

    stages: dict[str, dict[str, object]] = {}
    for stage in sorted({r.target.stage for r in calls}):
        mine = [r for r in calls if r.target.stage == stage]
        answered = [r for r in mine if r.status == "returned"]
        checks = [_valid(r) for r in answered]
        stages[stage] = {
            "calls": len(mine),
            "api_error": len(mine) - len(answered),
            "json_parsed": sum(p for p, _ in checks),
            "schema_valid": sum(v for _, v in checks),
            "stop_reason": dict(sorted(Counter(str(r.stop_reason) for r in answered).items())),
            "input_tokens_per_call": _mean([r.usage.input_tokens or 0 for r in answered]),
            "output_tokens_per_call": _mean([r.usage.output_tokens or 0 for r in answered]),
            "max_output_tokens": max((r.usage.output_tokens or 0 for r in answered), default=0),
            "seconds_per_call": _mean([r.timing.total_s for r in answered if r.timing]),
            "max_seconds": round(max((r.timing.total_s for r in answered if r.timing), default=0.0), 2),
        }

    chars = tokens = 0
    for record in timed:
        template = prompts.load(record.prompt_name)
        if template.sha256 == record.prompt_template_sha256:
            chars += len(template.system) + len(record.user_prompt)
            tokens += record.usage.input_tokens or 0
    prompt_s = sum(r.timing.prompt_eval_s for r in timed)
    eval_s = sum(r.timing.eval_s for r in timed)
    overhead = [max(0.0, r.timing.total_s - r.timing.prompt_eval_s - r.timing.eval_s) for r in timed]
    rate = {
        "prompt_tokens_per_s": round(sum(r.usage.input_tokens or 0 for r in timed) / prompt_s, 1),
        "output_tokens_per_s": round(sum(r.usage.output_tokens or 0 for r in timed) / eval_s, 2),
        "overhead_s_per_call": round(statistics.median(overhead), 2),
        "chars_per_token": round(chars / tokens, 3) if tokens else None,
        "output_tokens_per_call": {stage: data["output_tokens_per_call"] for stage, data in stages.items()},
        "seconds_per_call": _mean([r.timing.total_s for r in timed]),
        "wall_s": round(sum(r.timing.total_s for r in timed), 1),
    }
    violations = Counter(v.rule_id for r in results for v in r.violations)
    return {
        "model": json.loads(clients[0]),
        "runs": runs,
        "stages": stages,
        "case_results": dict(sorted(Counter(f"{r.stage} {r.status.value}" for r in results).items())),
        "g_violations": dict(sorted(violations.items())),
        "w_rejections": dict(sorted(Counter(r.rejection.rule_id for r in rejections).items())),
        "rate": rate,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m experiments.runner.calibrate", description=__doc__.splitlines()[0])
    parser.add_argument("run_ids", nargs="+", help="corridas reais em outputs/runs/")
    parser.add_argument("--runs-root", type=Path, default=RUNS_ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path, help="padrão: outputs/calibracao/<model_id>.json")
    args = parser.parse_args(argv)
    try:
        data = calibrate([args.runs_root / run_id for run_id in args.run_ids])
    except (OSError, ValueError) as error:
        print(f"calibrate: {error}", file=sys.stderr)
        return 1
    data["command"] = " ".join(["PYTHONPATH=code .venv/bin/python -m experiments.runner.calibrate", *args.run_ids])
    output = args.output or calibration_path(data["model"]["model_id"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"calibrate: {output}")
    print(json.dumps({"stages": data["stages"], "rate": data["rate"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
