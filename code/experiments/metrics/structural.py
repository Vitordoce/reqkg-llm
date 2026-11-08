"""Métricas por regra sobre a saída final de cada caso, corrida e condição.

Toda razão usa como denominador os requisitos gerados da corrida e da condição. Caso inválido
conta como zero requisito gerado: entra na contagem de casos inválidos e em nenhum denominador.
As regras rodam sobre o corpus do caso (Corpus.case), o mesmo que o executor usa.
"""

import statistics
from collections import Counter
from dataclasses import dataclass, field

from domain.enums import Condition, RunStatus
from domain.llm_io import ExtractionOutput
from domain.rules import CorpusIndex, check_all, is_complete
from experiments.metrics.loading import CallUsage, Corpus, Run

UNSUPPORTED_RULES = frozenset({"P1", "P2", "P3"})
CONSISTENCY_RULES = frozenset({"K1", "K2", "K3", "K4", "K5"})
CORRECTION_FAMILIES = ("C", "P")


def ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _requirement_violations(output: ExtractionOutput, corpus: CorpusIndex) -> dict[str, list[tuple[str, str]]]:
    """(regra, detalhe) violados por chave de requisito. Violações de ator, relação ou par ficam de fora."""
    keys = {r.key for r in output.requirements}
    found: dict[str, list[tuple[str, str]]] = {key: [] for key in keys}
    for v in check_all(output, corpus):
        if v.subject in keys:
            found[v.subject].append((v.rule_id, v.detail))
    return found


def _rules(violations: list[tuple[str, str]]) -> set[str]:
    return {rule for rule, _ in violations}


def is_corrected(before: list[tuple[str, str]], after: list[tuple[str, str]]) -> bool:
    """Menos violações C e P do que na extração e nenhuma violação P nova, comparada por regra e detalhe."""
    def cp(violations):
        return sum(rule.startswith(CORRECTION_FAMILIES) for rule, _ in violations)

    new_p = Counter(v for v in after if v[0].startswith("P")) - Counter(v for v in before if v[0].startswith("P"))
    return cp(after) < cp(before) and not new_p


def foreign_evidence(output: ExtractionOutput, corpus: Corpus, case_id: str) -> int:
    """Citações da saída (requisitos, atores, componentes, entidades e relações) cujo chunk é de outro
    documento da ingestão. Cada uma conta como P2 no corpus do caso."""
    own = corpus.case(case_id).chunk_text
    items = [*output.requirements, *output.actors, *output.components, *output.entities, *output.relations]
    return sum(
        e.chunk_id not in own and corpus.document_of_chunk(e.chunk_id) is not None
        for item in items for e in item.evidence
    )


@dataclass
class ConditionRun:
    run_index: int
    condition: Condition
    cases: int = 0
    invalid: Counter = field(default_factory=Counter)  # status -> casos
    generated: int = 0
    complete: int = 0
    c4: int = 0
    unsupported: int = 0
    k_violations: int = 0
    targets: int = 0
    accepted: int = 0
    refused: int = 0
    failed: int = 0
    corrected: int = 0
    foreign_evidence: int = 0
    refinement: CallUsage = field(default_factory=CallUsage)
    final_input_tokens: int = 0
    final_output_tokens: int = 0

    @property
    def invalid_cases(self) -> int:
        return sum(self.invalid.values())

    def metrics(self) -> dict[str, float | None]:
        tokens_known = self.refinement.without_usage == 0
        per_corrected = (lambda n: ratio(n, self.corrected) if tokens_known else None)
        return {
            "completeness_ratio": ratio(self.complete, self.generated),
            "c4_rate": ratio(self.c4, self.generated),
            "unsupported_claim_rate": ratio(self.unsupported, self.generated),
            "rule_violation_rate": ratio(self.k_violations, self.generated),
            "invalid_cases": float(self.invalid_cases),
            "corrected": float(self.corrected),
            "foreign_evidence": float(self.foreign_evidence),
            "input_tokens_per_corrected": per_corrected(self.refinement.input_tokens),
            "output_tokens_per_corrected": per_corrected(self.refinement.output_tokens),
            "tokens_per_corrected": per_corrected(self.refinement.input_tokens + self.refinement.output_tokens),
        }


def condition_run(run: Run, corpus: Corpus, run_index: int, condition: Condition) -> ConditionRun:
    result = ConditionRun(run_index, condition)
    result.refinement = run.usage.get(("refinement", condition, run_index), CallUsage())
    for case_id in run.case_ids():
        final = run.final(case_id, run_index, condition)
        result.cases += 1
        result.final_input_tokens += final.input_tokens
        result.final_output_tokens += final.output_tokens
        if final.status is not RunStatus.OK:
            result.invalid[final.status.value] += 1
            continue
        output = final.output
        case_corpus = corpus.case(case_id)
        after = _requirement_violations(output, case_corpus)
        result.generated += len(output.requirements)
        result.complete += sum(is_complete(r, case_corpus) for r in output.requirements)
        result.c4 += sum("C4" in _rules(v) for v in after.values())
        result.unsupported += sum(bool(UNSUPPORTED_RULES & _rules(v)) for v in after.values())
        result.k_violations += sum(v.rule_id in CONSISTENCY_RULES for v in check_all(output, case_corpus))
        result.foreign_evidence += foreign_evidence(output, corpus, case_id)
        result.targets += len(final.targets)
        result.accepted += len(final.accepted)
        result.refused += len(final.refused)
        result.failed += len(final.failed)
        if final.targets:
            before = _requirement_violations(run.extraction(case_id, run_index), case_corpus)
            for key in final.targets:
                if key not in after or key not in before:
                    raise ValueError(f"{case_id}, corrida {run_index}, {condition.value}: alvo {key} fora da saída")
                result.corrected += is_corrected(before[key], after[key])
    return result


def structural(run: Run, corpus: Corpus) -> list[ConditionRun]:
    return [condition_run(run, corpus, i, c) for i in run.run_indices() for c in Condition]


# Tamanho do contexto de refinamento

WRITTEN = "written"
REJECTED_W = "rejected_w"
ALL = "all"
CONTEXT_STRATA = (ALL, WRITTEN, REJECTED_W)


@dataclass(frozen=True)
class Spread:
    n: int
    mean: float | None
    median: float | None
    max: float | None

    @classmethod
    def of(cls, values: list[int]) -> "Spread":
        if not values:
            return cls(0, None, None, None)
        return cls(len(values), statistics.fmean(values), float(statistics.median(values)), float(max(values)))


@dataclass(frozen=True)
class ContextSize:
    """Itens e caracteres (soma de len(item.text)) do contexto de cada alvo da amostra, por estrato.
    written: o alvo foi gravado no grafo; rejected_w: a gravação recusou o alvo (RejectionRecord com subject = chave)."""

    run_index: int
    condition: Condition
    stratum: str
    items: Spread
    chars: Spread
    without_context: int = 0  # alvos de FinalRecord.targets sem ContextRecord; só no estrato all


def context_sizes(run: Run) -> list[ContextSize]:
    cases = set(run.case_ids())
    by_target = {(c.case_id, c.run_index, c.condition, c.target_key): c.context for c in run.contexts
                 if c.case_id in cases}
    rejected = {(r.case_id, r.run_index, r.rejection.subject) for r in run.rejections}
    found = []
    for run_index in run.run_indices():
        for condition in Condition:
            samples: dict[str, list[tuple[int, int]]] = {s: [] for s in CONTEXT_STRATA}
            targets, missing = set(), 0
            for case_id in sorted(cases):
                final = run.final(case_id, run_index, condition)
                for key in final.targets:
                    targets.add((case_id, key))
                    context = by_target.get((case_id, run_index, condition, key))
                    if context is None:
                        missing += 1
                        continue
                    size = (len(context.items), sum(len(item.text) for item in context.items))
                    stratum = REJECTED_W if (case_id, run_index, key) in rejected else WRITTEN
                    samples[ALL].append(size)
                    samples[stratum].append(size)
            extra = sorted(k[3] for k in by_target if k[1:3] == (run_index, condition)
                           and (k[0], k[3]) not in targets)
            if extra:
                raise ValueError(f"corrida {run_index}, {condition.value}: contexto sem alvo correspondente em "
                                 f"finals.jsonl para {extra}")
            for stratum in CONTEXT_STRATA:
                values = samples[stratum]
                found.append(ContextSize(run_index, condition, stratum, Spread.of([v[0] for v in values]),
                                         Spread.of([v[1] for v in values]), missing if stratum == ALL else 0))
    return found


@dataclass(frozen=True)
class SharedRun:
    """O que é comum às duas condições, por corrida. sample_extraction: extração dos casos da amostra (os casos
    de finals.jsonl). promise_extraction: extração dos projetos do PROMISE para o grafo de B (os demais casos de
    extração). classification: primeira classificação do PROMISE. rejections: recusas W na gravação da amostra."""

    run_index: int
    sample_extraction: CallUsage
    promise_extraction: CallUsage
    classification: CallUsage
    rejections: Counter

    @property
    def without_usage(self) -> int:
        return sum(u.without_usage for u in (self.sample_extraction, self.promise_extraction, self.classification))


def _total(usages) -> CallUsage:
    total = CallUsage()
    for u in usages:
        total = CallUsage(total.calls + u.calls, total.input_tokens + u.input_tokens,
                          total.output_tokens + u.output_tokens, total.without_usage + u.without_usage)
    return total


def shared(run: Run) -> list[SharedRun]:
    sample = set(run.case_ids())
    indices = sorted(set(run.run_indices()) | {i for i, _ in run.extraction_usage}
                     | {r.run_index for r in run.classifications}
                     | {i for stage, _, i in run.usage if stage == "classification"})
    return [
        SharedRun(
            i,
            _total(u for (j, case), u in run.extraction_usage.items() if j == i and case in sample),
            _total(u for (j, case), u in run.extraction_usage.items() if j == i and case not in sample),
            run.usage.get(("classification", None, i), CallUsage()),
            Counter(r.rejection.rule_id for r in run.rejections if r.run_index == i),
        )
        for i in indices
    ]


@dataclass(frozen=True)
class Aggregate:
    metric: str
    condition: str
    values: tuple[float | None, ...]

    @property
    def defined(self) -> list[float]:
        return [v for v in self.values if v is not None]

    @property
    def mean(self) -> float | None:
        return statistics.fmean(self.defined) if self.defined else None

    @property
    def sd(self) -> float | None:
        """Desvio padrão amostral (n - 1) entre corridas."""
        return statistics.stdev(self.defined) if len(self.defined) >= 2 else None


def aggregate(rows: list[tuple[str, str, int, float | None]]) -> list[Aggregate]:
    """rows: (métrica, condição, corrida, valor). Valores ordenados pela corrida."""
    grouped: dict[tuple[str, str], list[tuple[int, float | None]]] = {}
    for metric, condition, run_index, value in rows:
        grouped.setdefault((metric, condition), []).append((run_index, value))
    return [
        Aggregate(metric, condition, tuple(v for _, v in sorted(values)))
        for (metric, condition), values in grouped.items()
    ]
