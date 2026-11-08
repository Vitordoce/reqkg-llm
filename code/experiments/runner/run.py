"""Monta e executa uma corrida: pré-condições, manifesto, diretório, laço e fechamento."""

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from domain.config import ExperimentConfig
from domain.serialization import load_toml
from experiments.records import Resumption
from experiments.runner.clients import ResumeClient, UsageMeter
from experiments.runner.execute import Session, execute
from experiments.runner.inputs import PromiseInput, StructuralInput
from experiments.runner.rundir import RunDirectory, RunRefused, build_manifest, check_resume, preflight
from extraction.client import RUNS_ROOT, LLMClient, ReplayClient
from extraction.pipeline import SinglePassGuard
from graph.connection import Graph


class Mode(StrEnum):
    REAL = "real"
    REPLAY = "replay"
    SYNTHETIC = "synthetic"


@dataclass(frozen=True)
class Plan:
    config_path: Path
    config: ExperimentConfig
    structural: StructuralInput | None
    promise: PromiseInput | None
    structural_runs: int
    promise_runs: int

    @property
    def runs(self) -> int:
        """Campo runs do manifesto: repetições da amostra estruturada, ou do PROMISE se só ele roda."""
        return self.structural_runs if self.structural is not None else self.promise_runs

    def ingestion_sha256(self) -> list[str]:
        return list(self.structural.sha256) if self.structural else []

    def promise_sha256(self) -> str | None:
        return self.promise.sha256 if self.promise else None

    def selection_sha256(self) -> str:
        """Casos da amostra e itens do PROMISE com os filtros. Os hashes dos arquivos de entrada não mudam com
        --promise-items ou --promise-limit; este muda, e a retomada o confere."""
        selection = {
            "cases": [c.case_id for c in self.structural.cases] if self.structural else [],
            "promise": self.promise.selection() if self.promise else None,
        }
        return hashlib.sha256(json.dumps(selection, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def make_plan(config_path: Path, *, structural: StructuralInput | None, promise: PromiseInput | None,
              runs: int | None = None, pilot: bool = False) -> Plan:
    """runs troca o número de repetições das duas partes e só vale em corrida piloto."""
    if structural is None and promise is None:
        raise RunRefused("nada a rodar: passe --ingestion, --promise ou os dois")
    config = load_toml(config_path, ExperimentConfig)
    if runs is not None and not pilot:
        raise RunRefused("--runs só vale com --pilot. A corrida do experimento usa repetitions de experiment.toml")
    if runs is not None and runs < 1:
        raise RunRefused("--runs tem de ser pelo menos 1")
    return Plan(config_path=Path(config_path), config=config, structural=structural, promise=promise,
                structural_runs=runs or config.repetitions.structural_sample,
                promise_runs=runs or config.repetitions.promise)


def model_id(mode: Mode, plan: Plan, client: LLMClient) -> str:
    if mode is Mode.REAL:
        return plan.config.model.model_id
    if isinstance(client, ReplayClient):
        return client.source_model()
    return str(client.describe().get("model_id") or mode.value)


class ResumeDiverged(RuntimeError):
    """A corrida retomada não pediu todas as chamadas do registro parcial. A pasta parcial fica para conferir."""


def run(plan: Plan, *, run_id: str, mode: Mode, client: LLMClient, graph: Graph, command: str, pilot: bool = False,
        freeze: Path | None = None, runs_root: Path = RUNS_ROOT, hold_lock: bool = True, resume: bool = False) -> Path:
    """Devolve outputs/runs/<run_id>. Com erro no meio, a corrida fica em .partial-<run_id> e o erro sobe.

    resume: reabre .partial-<run_id>, recusa se o manifesto do início difere do atual (check_resume), e refaz a
    corrida do começo servindo do registro parcial as chamadas já feitas; só o que falta vai ao cliente.
    """
    preflight(plan.config, config_path=plan.config_path, real=mode is Mode.REAL, run_id=run_id, pilot=pilot,
              freeze=freeze)
    manifest = build_manifest(run_id=run_id, model_id=model_id(mode, plan, client), replay=mode is not Mode.REAL,
                              runs=plan.runs, config_path=plan.config_path, ingestion_sha256=plan.ingestion_sha256(),
                              promise_sha256=plan.promise_sha256(), selection_sha256=plan.selection_sha256(),
                              freeze=freeze, command=command)
    directory = RunDirectory(run_id, runs_root, resume=resume)
    resumed: ResumeClient | None = None
    if resume:
        started = directory.read_manifest()
        check_resume(started, manifest)
        logged = directory.logged_calls()
        resumed = ResumeClient(logged, client)
        directory.reset_for_resume(logged)
        manifest = started.model_copy(update={
            "resumptions": [*started.resumptions, Resumption(command=command, logged_calls=resumed.logged)]})
        client = resumed
    directory.write_manifest(manifest)
    session = Session(config=plan.config, client=UsageMeter(client), run=directory,
                      guard=SinglePassGuard.for_config(plan.config, directory.log), graph=graph)
    execute(session, structural=plan.structural, structural_runs=plan.structural_runs, promise=plan.promise,
            promise_runs=plan.promise_runs, hold_lock=hold_lock)
    if resumed is not None and resumed.pending:
        raise ResumeDiverged(f"{len(resumed.pending)} chamada(s) do registro parcial não foram pedidas na retomada; "
                             f"a corrida ficou em {directory.staging}, com o registro anterior em {directory.previous_calls}")
    return directory.finalize()
