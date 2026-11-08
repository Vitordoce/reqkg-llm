"""Conta as chamadas ao modelo de uma corrida e estima os tokens, sem chamar o modelo nem abrir o grafo.

Exato: número de chamadas de extração e de classificação, o texto dos prompts de extração e de
classificação, e o contexto de LLM-only no refinamento da classificação (os outros itens da
chamada). Estimado: número de refinamentos na amostra (os alvos só existem depois da extração),
o tamanho do candidato e do contexto do refinamento de B (o contexto de A mais itens do tamanho
médio de um chunk, até o limite), e a conversão de caracteres em tokens. Na Anthropic, a entrada
conta o schema de saída, que vai em cada chamada; no Ollama, o schema vira gramática e não entra no
prompt. A saída é o teto max_tokens.

Com uma taxa medida (Rate, de um arquivo de calibração gerado por experiments.runner.calibrate ou
das opções do CLI), a estimativa traz também o tempo: tokens de entrada pela taxa de entrada, mais
a saída média medida da etapa pela taxa de saída, mais o tempo fixo de cada chamada.
"""

import functools
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from domain.enums import Condition, ContextStrategy, PromiseLabel, RequirementType
from domain.llm_io import (
    CitedEvidence,
    ClassificationOutput,
    ContextItem,
    RequirementCandidate,
    RetrievedContext,
)
from domain.models import SourceChunk
from experiments.runner.run import Plan
from extraction import prompts
from extraction.pipeline import group_chunks
from extraction.schema import output_schema
from retrieval import PromiseTarget, retrieve_context

TYPICAL_REASONS = ["C2: priority ausente", "C3: verification_method ausente"]
RATE_STAGES = ("extraction", "refinement", "classification", "classification_refinement")


def rate_stage(stage: str) -> str:
    """A etapa do registro de chamadas que corresponde a uma linha do dry-run."""
    return stage.removesuffix(" (estimado)")


@dataclass(frozen=True)
class Rate:
    """Velocidade medida do modelo. output_tokens_per_call: saída média de cada etapa, porque max_tokens é só o teto."""

    prompt_tokens_per_s: float
    output_tokens_per_s: float
    overhead_s_per_call: float
    output_tokens_per_call: dict[str, float]
    origin: str
    chars_per_token: float | None = None

    @classmethod
    def from_calibration(cls, path: Path) -> "Rate":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        rate = data["rate"]
        missing = [s for s in RATE_STAGES if s not in rate["output_tokens_per_call"]]
        if missing:
            raise ValueError(f"{path}: a calibração não mediu a saída de {', '.join(missing)}")
        return cls(rate["prompt_tokens_per_s"], rate["output_tokens_per_s"], rate["overhead_s_per_call"],
                   dict(rate["output_tokens_per_call"]), origin=str(path), chars_per_token=rate.get("chars_per_token"))

    def seconds(self, stage: str, calls: int, input_tokens: int) -> float:
        output = calls * self.output_tokens_per_call[rate_stage(stage)]
        return input_tokens / self.prompt_tokens_per_s + output / self.output_tokens_per_s + calls * self.overhead_s_per_call


@dataclass
class Line:
    part: str
    stage: str
    condition: str
    calls: float = 0
    input_chars: float = 0
    max_chars: float = 0

    def add(self, calls: float, chars_per_call: float) -> None:
        self.calls += calls
        self.input_chars += calls * chars_per_call
        self.max_chars = max(self.max_chars, chars_per_call)


@dataclass
class Estimate:
    chars_per_token: float
    targets_per_chunk: float
    max_tokens: int
    num_ctx: int | None = None
    rate: Rate | None = None
    lines: dict[tuple[str, str, str], Line] = field(default_factory=dict)

    def line(self, part: str, stage: str, condition: Condition | None = None) -> Line:
        name = condition.value if condition else "compartilhada"
        return self.lines.setdefault((part, stage, name), Line(part, stage, name))

    def rows(self) -> list[dict[str, object]]:
        rows = []
        for line in self.lines.values():
            calls = math.ceil(line.calls)
            row = {"part": line.part, "stage": line.stage, "condition": line.condition, "calls": calls,
                   "input_tokens": math.ceil(line.input_chars / self.chars_per_token),
                   "max_input_tokens_per_call": math.ceil(line.max_chars / self.chars_per_token),
                   "output_tokens_max": calls * self.max_tokens}
            if self.rate is not None:
                row["hours"] = round(self.rate.seconds(line.stage, calls, row["input_tokens"]) / 3600, 2)
            rows.append(row)
        return rows

    def totals(self) -> dict[str, object]:
        rows = self.rows()
        totals = {key: sum(r[key] for r in rows) for key in ("calls", "input_tokens", "output_tokens_max")}
        totals["max_input_tokens_per_call"] = max((r["max_input_tokens_per_call"] for r in rows), default=0)
        if self.rate is not None:
            totals["hours"] = round(sum(r["hours"] for r in rows), 2)
        return totals

    def context_warning(self) -> str | None:
        largest = self.totals()["max_input_tokens_per_call"]
        if self.num_ctx is not None and largest + self.max_tokens >= self.num_ctx:
            return (f"aviso: a maior chamada estimada ({largest} tokens de entrada) mais max_tokens "
                    f"({self.max_tokens}) não cabe em num_ctx = {self.num_ctx}; o cliente recusa a resposta que "
                    "encher a janela")
        return None

    def to_json(self) -> dict[str, object]:
        assumptions: dict[str, object] = {"chars_per_token": self.chars_per_token,
                                          "targets_per_chunk": self.targets_per_chunk,
                                          "output": "teto max_tokens por chamada", "num_ctx": self.num_ctx}
        if self.rate is not None:
            assumptions["rate"] = {"origin": self.rate.origin, "prompt_tokens_per_s": self.rate.prompt_tokens_per_s,
                                   "output_tokens_per_s": self.rate.output_tokens_per_s,
                                   "overhead_s_per_call": self.rate.overhead_s_per_call,
                                   "output_tokens_per_call": self.rate.output_tokens_per_call}
        return {"assumptions": assumptions, "rows": self.rows(), "totals": self.totals(),
                "warning": self.context_warning()}

    def render(self) -> str:
        timed = self.rate is not None
        header = (f"{'parte':<11} {'etapa':<26} {'condição':<15} {'chamadas':>9} {'entrada':>11} {'maior':>7} "
                  f"{'saída máx.':>11}" + (f" {'horas':>7}" if timed else ""))
        lines = [header, "-" * len(header)]
        for r in self.rows():
            lines.append(f"{r['part']:<11} {r['stage']:<26} {r['condition']:<15} {r['calls']:>9} "
                         f"{r['input_tokens']:>11} {r['max_input_tokens_per_call']:>7} {r['output_tokens_max']:>11}"
                         + (f" {r['hours']:>7.2f}" if timed else ""))
        t = self.totals()
        lines += ["-" * len(header),
                  f"{'total':<54} {t['calls']:>9} {t['input_tokens']:>11} {t['max_input_tokens_per_call']:>7} "
                  f"{t['output_tokens_max']:>11}" + (f" {t['hours']:>7.2f}" if timed else ""),
                  f"tokens = caracteres / {self.chars_per_token}; refinamentos da amostra estimados com "
                  f"{self.targets_per_chunk} alvo(s) por chunk; saída é o teto de {self.max_tokens} tokens por "
                  "chamada; maior = entrada da maior chamada da linha."]
        if timed:
            r = self.rate
            per_call = ", ".join(f"{s} {v:.0f}" for s, v in r.output_tokens_per_call.items())
            lines.append(f"horas = entrada / {r.prompt_tokens_per_s:.0f} tokens/s + saída média medida ({per_call} "
                         f"tokens por chamada) / {r.output_tokens_per_s:.1f} tokens/s + {r.overhead_s_per_call:.1f} s "
                         f"por chamada; taxa de {r.origin}.")
        warning = self.context_warning()
        return "\n".join(lines + ([warning] if warning else []))


@functools.cache
def _schema_chars(model: type) -> int:
    return len(json.dumps(output_schema(model), ensure_ascii=False))


def prompt_chars(prompt: prompts.RenderedPrompt, schema_in_prompt: bool = True) -> int:
    schema = _schema_chars(prompt.output_model) if schema_in_prompt else 0
    return len(prompt.system) + len(prompt.user) + schema


def _items(count: int, text_chars: int, source: str, chunk: str) -> list[ContextItem]:
    return [ContextItem(item_id=f"item-{i:03d}", kind="source_chunk", rank=0, text="x" * max(1, text_chars),
                        source_id=source, chunk_id=chunk) for i in range(count)]


def _typical_candidate(chunk: SourceChunk) -> RequirementCandidate:
    return RequirementCandidate(key="c0-R1", statement="x" * 160, type=RequirementType.FUNCTIONAL,
                                evidence=[CitedEvidence(source_id=chunk.source_id, chunk_id=chunk.chunk_id,
                                                        quote="x" * 80)])


def _context(items: list[ContextItem], strategy: ContextStrategy) -> RetrievedContext:
    return RetrievedContext(query="estimativa", strategy=strategy, limit=max(1, len(items)), items=items)


def estimate(plan: Plan, *, chars_per_token: float = 3.5, targets_per_chunk: float = 1.0,
             rate: Rate | None = None) -> Estimate:
    config = plan.config
    result = Estimate(chars_per_token, targets_per_chunk, config.model.max_tokens, config.model.num_ctx, rate)
    schema_in_prompt = config.model.provider in {"anthropic", "openrouter"}

    def _chars(prompt: prompts.RenderedPrompt) -> int:
        return prompt_chars(prompt, schema_in_prompt)

    per_call = config.extraction.chunks_per_call
    max_items = config.retrieval.max_items

    if plan.structural is not None:
        chunks = plan.structural.chunks
        average = sum(len(c.text) for c in chunks) / len(chunks)
        graph_items = min(max_items, len(chunks))
        for _ in range(plan.structural_runs):
            for case in plan.structural.cases:
                for group in group_chunks(case.chunks, per_call):
                    result.line("amostra", "extraction").add(1, _chars(prompts.extraction_prompt(group)))
                    targets = targets_per_chunk * len(group)
                    candidate = _typical_candidate(group[0])
                    source = _context([ContextItem(item_id=c.chunk_id, kind="source_chunk", rank=r, text=c.text,
                                                   source_id=c.source_id, chunk_id=c.chunk_id)
                                       for r, c in enumerate(group)], ContextStrategy.SOURCE_CHUNKS)
                    graph = _context(_items(graph_items, round(average), group[0].source_id, group[0].chunk_id),
                                     ContextStrategy.GRAPH_LOCAL)
                    for condition, context in ((Condition.LLM_ONLY, source), (Condition.REQKG_GROUNDED, graph)):
                        prompt = prompts.refinement_prompt(candidate, context, TYPICAL_REASONS)
                        result.line("amostra", "refinement (estimado)", condition).add(targets, _chars(prompt))

    if plan.promise is not None:
        for _ in range(plan.promise_runs):
            for project in plan.promise.projects:
                for group in group_chunks(project.chunks, per_call):
                    result.line("PROMISE", "extraction").add(1, _chars(prompts.extraction_prompt(group)))
                average = sum(len(c.text) for c in project.chunks) / len(project.chunks)
                neighbours = min(max_items, len(project.chunks) - 1)
                chunk = project.chunks[0]
                for item in plan.promise.items[project.project_id]:
                    first = ClassificationOutput(promise_id=item.promise_id, label=PromiseLabel.F, rationale="x" * 120)
                    result.line("PROMISE", "classification").add(
                        1, _chars(prompts.classification_prompt(item.promise_id, item.text)))
                    source = retrieve_context(PromiseTarget(item.promise_id, project), Condition.LLM_ONLY, config)
                    expansion = _items(max(0, neighbours - len(source.items)), round(average), chunk.source_id,
                                       chunk.chunk_id)
                    contexts = {
                        Condition.LLM_ONLY: source,
                        Condition.REQKG_GROUNDED: _context([*source.items, *expansion], ContextStrategy.GRAPH_LOCAL),
                    }
                    for condition, context in contexts.items():
                        prompt = prompts.classification_refinement_prompt(item.promise_id, item.text, first, context)
                        result.line("PROMISE", "classification_refinement", condition).add(1, _chars(prompt))
    return result
