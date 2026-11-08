"""Diretório da corrida, manifesto e as recusas antes de rodar.

A corrida grava em outputs/runs/.partial-<run_id>/ e só vira outputs/runs/<run_id>/ no fim, por
um rename. Quem lê outputs/runs/<run_id>/ vê uma corrida completa. Um run_id completo nunca é
sobrescrito. Um interrompido só é reaberto por --resume, que refaz a corrida servindo do calls.jsonl
parcial as chamadas já pagas.
"""

import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import unicodedata
from pathlib import Path

from pydantic import BaseModel, TypeAdapter, ValidationError

from domain.config import ContractError, ExperimentConfig
from domain.rules import RULES_VERSION
from domain.serialization import canonical_json
from experiments.records import FILES, CallRecord, RunId, RunManifest
from extraction import prompts
from extraction.client import REPO_ROOT, RUNS_ROOT, CallLog

FREEZE_TOOL = REPO_ROOT / "tools" / "freeze_manifest.py"
CONFIG_DIR = REPO_ROOT / "code" / "experiments" / "config"
PILOT_PREFIX = "pilot-"
PREVIOUS_CALLS = ".calls-before-resume.jsonl"


class RunRefused(RuntimeError):
    """Uma pré-condição da corrida falhou. Nada foi gravado."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def packages() -> dict[str, str]:
    found = {"python": platform.python_version()}
    for dist in importlib.metadata.distributions():
        name = dist.metadata["Name"]
        if name:
            found[name.lower()] = dist.version
    return dict(sorted(found.items()))


def check_run_id(run_id: str) -> str:
    try:
        return TypeAdapter(RunId).validate_python(run_id)
    except ValidationError:
        raise RunRefused(f"run_id {run_id!r}: use letras, números, ponto, hífen ou sublinhado, até 64 caracteres") from None


def check_registry() -> None:
    if prompts.REGISTRY_PATH.read_text(encoding="utf-8") != prompts.render_registry():
        raise RunRefused(f"{prompts.REGISTRY_PATH.name} não bate com os prompts em disco: "
                         "rode .venv/bin/python code/extraction/prompts.py e registre a mudança")


def check_freeze(path: Path, config_path: Path) -> None:
    """O manifesto de congelamento confere com a árvore atual (tools/freeze_manifest.py --check), e a
    configuração da corrida é um arquivo congelado de code/experiments/config/, com o mesmo SHA-256. O
    congelamento cobre code/ inteiro, então estar congelado não basta: o TOML de um fixture também está."""
    if not Path(path).is_file():
        raise RunRefused(f"{path}: manifesto de congelamento não encontrado")
    spec = importlib.util.spec_from_file_location("freeze_manifest", FREEZE_TOOL)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        problems = tool.compare(manifest, REPO_ROOT)
    except tool.FreezeError as error:
        raise RunRefused(f"{path}: {error}") from None
    if problems:
        shown = "; ".join(problems[:5]) + (f"; e mais {len(problems) - 5}" if len(problems) > 5 else "")
        raise RunRefused(f"a árvore mudou desde o congelamento {path}: {shown}")
    resolved = Path(config_path).resolve()
    if not resolved.is_relative_to(REPO_ROOT):
        raise RunRefused(f"--config {config_path} fica fora do repositório e não está no congelamento {path}. "
                         "Use a configuração congelada, code/experiments/config/experiment.toml")
    key = unicodedata.normalize("NFC", resolved.relative_to(REPO_ROOT).as_posix())
    if not resolved.is_relative_to(CONFIG_DIR.resolve()):
        raise RunRefused(f"--config {key} não fica em {CONFIG_DIR.relative_to(REPO_ROOT).as_posix()}/. Uma corrida "
                         "com --freeze usa a configuração do experimento, code/experiments/config/experiment.toml, "
                         "mesmo que outro TOML também esteja no congelamento")
    frozen = manifest.get("files", {}).get(key)
    if frozen is None:
        raise RunRefused(f"--config {key} não está no congelamento {path}. Use a configuração congelada, "
                         "code/experiments/config/experiment.toml, ou congele de novo")
    if frozen != sha256_file(resolved):
        raise RunRefused(f"--config {key} difere da versão congelada em {path}")


def preflight(config: ExperimentConfig, *, config_path: Path, real: bool, run_id: str, pilot: bool,
              freeze: Path | None) -> None:
    check_run_id(run_id)
    check_registry()
    if config.rules_version != RULES_VERSION:
        raise RunRefused(f"rules_version {config.rules_version!r} difere das regras em código ({RULES_VERSION!r})")
    if pilot and not run_id.startswith(PILOT_PREFIX):
        raise RunRefused(f"corrida piloto precisa de run_id começando por {PILOT_PREFIX!r}: o manifesto grava "
                         "pilot = true, e o prefixo deixa o piloto visível pelo nome da pasta")
    if not pilot and run_id.startswith(PILOT_PREFIX):
        raise RunRefused(f"run_id começando por {PILOT_PREFIX!r} é reservado para --pilot")
    if real:
        try:
            config.ensure_runnable()
        except ContractError as error:
            raise RunRefused(str(error)) from None
        if freeze is None and not pilot:
            raise RunRefused("corrida real sem manifesto de congelamento: rode make freeze e passe --freeze "
                             "outputs/runs/freeze-<data>.json, ou use --pilot para uma corrida piloto")
    if freeze is not None:
        check_freeze(freeze, config_path)


def build_manifest(*, run_id: str, model_id: str, replay: bool, runs: int, config_path: Path,
                   ingestion_sha256: list[str], freeze: Path | None, command: str,
                   promise_sha256: str | None = None, selection_sha256: str | None = None) -> RunManifest:
    return RunManifest(
        run_id=run_id, model_id=model_id, replay=replay, runs=runs, pilot=run_id.startswith(PILOT_PREFIX),
        config_sha256=sha256_file(config_path),
        ingestion_sha256=ingestion_sha256,
        promise_sha256=promise_sha256,
        selection_sha256=selection_sha256,
        prompts_registry_sha256=sha256_file(prompts.REGISTRY_PATH),
        freeze_manifest_sha256=sha256_file(freeze) if freeze else None,
        packages=packages(),
        command=command,
    )


RESUME_FIELDS = ("model_id", "replay", "pilot", "runs", "config_sha256", "ingestion_sha256", "promise_sha256",
                 "selection_sha256", "prompts_registry_sha256", "freeze_manifest_sha256", "packages")


def check_resume(started: RunManifest, now: RunManifest) -> None:
    """A retomada só vale com a mesma configuração, entradas, seleção, prompts, congelamento, modelo e pacotes."""
    changed = [name for name in RESUME_FIELDS if getattr(started, name) != getattr(now, name)]
    if changed:
        hint = (" A seleção mudou: --ingestion, --promise, --promise-projects, --promise-items ou --promise-limit "
                "diferem do comando original, que está em command do manifesto parcial."
                if "selection_sha256" in changed else "")
        raise RunRefused(f"retomada recusada: mudou desde o início da corrida {started.run_id}: {', '.join(changed)}."
                         f"{hint} Uma corrida não mistura duas configurações; retome com o comando original mais "
                         "--resume, ou rode com outro run_id")


class RunDirectory:
    """resume=True reabre outputs/runs/.partial-<run_id>/ de uma corrida interrompida (ver reset_for_resume)."""

    def __init__(self, run_id: str, root: Path = RUNS_ROOT, *, resume: bool = False) -> None:
        if resume:
            self.final, self.staging = self.check_resumable(run_id, root)
        else:
            self.final, self.staging = self.check_free(run_id, root)
            self.staging.mkdir(parents=True)
        self.log = CallLog(self.staging)
        self.previous_calls = self.staging / PREVIOUS_CALLS

    @staticmethod
    def check_free(run_id: str, root: Path = RUNS_ROOT) -> tuple[Path, Path]:
        check_run_id(run_id)
        final, staging = Path(root) / run_id, Path(root) / f".partial-{run_id}"
        if final.exists():
            raise RunRefused(f"{final} já existe. Um run_id nunca é sobrescrito: escolha outro")
        if staging.exists():
            raise RunRefused(f"{staging} sobrou de uma corrida interrompida com o mesmo run_id. "
                             "Retome com --resume (as chamadas gravadas não são pagas de novo) ou escolha outro run_id")
        return final, staging

    @staticmethod
    def check_resumable(run_id: str, root: Path = RUNS_ROOT) -> tuple[Path, Path]:
        check_run_id(run_id)
        final, staging = Path(root) / run_id, Path(root) / f".partial-{run_id}"
        if final.exists():
            raise RunRefused(f"{final} já terminou: não há o que retomar")
        if not (staging / FILES["manifest"]).is_file():
            raise RunRefused(f"{staging} não existe ou não tem manifest.json: não há corrida interrompida com esse run_id")
        return final, staging

    def read_manifest(self) -> RunManifest:
        return RunManifest.model_validate_json(self.path("manifest").read_text(encoding="utf-8"))

    def logged_calls(self) -> list[CallRecord]:
        """As chamadas já gravadas: as de retomadas anteriores e as do calls.jsonl parcial. Uma última linha
        cortada no meio (queda durante a gravação) é descartada e a chamada é refeita."""
        records = CallLog.read(self.previous_calls) if self.previous_calls.exists() else []
        if self.log.path.exists():
            lines = self.log.path.read_text(encoding="utf-8").splitlines()
            try:
                CallRecord.model_validate_json(lines[-1]) if lines else None
            except ValueError:
                lines = lines[:-1]
            for number, line in enumerate(lines, start=1):
                try:
                    records.append(CallRecord.model_validate_json(line))
                except ValueError as error:
                    raise RunRefused(f"{self.log.path}:{number}: linha inválida no meio do registro parcial: {error}") from None
        unique = {record.line(): record for record in records}
        return list(unique.values())

    def reset_for_resume(self, logged: list[CallRecord]) -> None:
        """Guarda as chamadas gravadas à parte e apaga os outros registros: a corrida recomeça do início, e o
        ResumeClient serve do registro o que já foi pago."""
        temporary = self.previous_calls.with_suffix(".tmp")
        temporary.write_text("".join(record.line() for record in logged), encoding="utf-8")
        os.replace(temporary, self.previous_calls)
        for kind, name in FILES.items():
            if kind != "manifest":
                (self.staging / name).unlink(missing_ok=True)

    def path(self, kind: str) -> Path:
        return self.staging / FILES[kind]

    def write_manifest(self, manifest: RunManifest) -> None:
        self.path("manifest").write_text(canonical_json(manifest), encoding="utf-8")

    def append(self, kind: str, record: BaseModel) -> None:
        with self.path(kind).open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(record))

    def finalize(self) -> Path:
        self.previous_calls.unlink(missing_ok=True)
        for kind, name in FILES.items():
            if kind != "manifest":
                (self.staging / name).touch()
        if self.final.exists():
            raise RunRefused(f"{self.final} apareceu durante a corrida. A corrida ficou em {self.staging}")
        os.rename(self.staging, self.final)
        return self.final
