"""Classificação do PROMISE NFR: precisão, revocação e F1 por rótulo e em média macro, com scikit-learn.

Três classificações por corrida: a inicial, compartilhada pelas duas condições, e a final de cada
condição. Primeira classificação inválida ou com falha da API (status diferente de ok, sem rótulo) entra
como predição inválida nas três: erra o item e não conta como predição de nenhum rótulo. Refinamento que
falha (refinement_status diferente de ok) mantém o rótulo inicial, como o executor grava em final, e é
contado à parte por condição.

Tarefa binária: F contra os demais (NF), sobre todos os itens. Tarefa de categoria: os onze rótulos não
funcionais, sobre os itens cuja referência é não funcional; predizer F num desses itens é erro. A média
macro inclui os rótulos com pelo menos um item na referência, menos PO.

Diagnóstico do contexto: entre os itens de contexto que são requisitos do PROMISE (item_id no formato
PROMISE-NFR-NNNN), a fração com o mesmo rótulo de referência do item avaliado, comparada com a fração
esperada se o contexto fosse sorteado entre os demais itens do mesmo projeto.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from domain.config import ContractError
from domain.enums import Condition, PromiseLabel, RunStatus
from experiments.metrics.loading import Run

INVALID = "invalid"
NON_FUNCTIONAL = "NF"
INITIAL = "initial"
CATEGORY_LABELS = tuple(label.value for label in PromiseLabel if label is not PromiseLabel.F)
EXCLUDED_FROM_MACRO = {"PO": "um único item no PROMISE publicado; um acerto ou um erro levaria o F1 do rótulo a 1 ou a 0"}
CONTRADICTORY_PAIR = ("PROMISE-NFR-0426", "PROMISE-NFR-0460")
PROMISE_ITEM = re.compile(r"^PROMISE-NFR-\d{4}$")


@dataclass(frozen=True)
class Gold:
    labels: dict[str, str]  # promise_id -> rótulo de referência
    projects: dict[str, int]  # promise_id -> project_id


def load_gold(path: Path) -> Gold:
    labels, projects = {}, {}
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            promise_id, label, project = item["promise_id"], PromiseLabel(item["label"]).value, int(item["project_id"])
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as error:
            raise ContractError(f"{path}:{number}: linha sem promise_id, project_id e rótulo do PROMISE ({error})") from None
        if promise_id in labels:
            raise ContractError(f"{path}:{number}: {promise_id} repetido")
        labels[promise_id], projects[promise_id] = label, project
    return Gold(labels, projects)


@dataclass(frozen=True)
class LabelScore:
    label: str
    support: int
    predicted: int
    precision: float | None  # None quando indefinida e fora da média: sem suporte e sem predição
    recall: float | None
    f1: float | None
    in_macro: bool
    note: str = ""


@dataclass(frozen=True)
class TaskScore:
    run_index: int
    variant: str  # initial, LLM-only ou REQKG-grounded
    task: str  # binary ou category
    items: int
    invalid: int
    labels: tuple[LabelScore, ...]
    macro_labels: tuple[str, ...]
    macro_precision: float | None
    macro_recall: float | None
    macro_f1: float | None


def _score(y_true: list[str], y_pred: list[str], labels: tuple[str, ...], excluded: dict[str, str]) -> tuple:
    try:
        from sklearn.metrics import precision_recall_fscore_support
    except ImportError:
        raise ContractError("scikit-learn ausente; rode make venv-metrics") from None
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=list(labels), average=None, zero_division=0
    )
    rows = []
    for i, label in enumerate(labels):
        predicted = sum(p == label for p in y_pred)
        if label in excluded:
            in_macro, note = False, f"fora da média macro: {excluded[label]}"
        elif not support[i]:
            in_macro, note = False, "fora da média macro: nenhum item com este rótulo na referência"
        else:
            in_macro, note = True, "" if predicted else "nenhuma predição; precisão 0/0 contada como 0"
        if support[i]:
            rows.append(LabelScore(label, int(support[i]), predicted, float(precision[i]), float(recall[i]),
                                   float(f1[i]), in_macro, note))
        else:
            rows.append(LabelScore(label, 0, predicted, float(precision[i]) if predicted else None, None, None,
                                   in_macro, note))
    macro = [r.label for r in rows if r.in_macro]
    if not macro:
        return tuple(rows), (), None, None, None
    p, r, f, _ = precision_recall_fscore_support(y_true, y_pred, labels=macro, average="macro", zero_division=0)
    return tuple(rows), tuple(macro), float(p), float(r), float(f)


def _binary(label: str) -> str:
    return label if label in (PromiseLabel.F.value, INVALID) else NON_FUNCTIONAL


def task_scores(run_index: int, variant: str, gold: dict[str, str], predicted: dict[str, str]) -> list[TaskScore]:
    items = sorted(predicted)
    invalid = sum(predicted[i] == INVALID for i in items)
    binary = _score([_binary(gold[i]) for i in items], [_binary(predicted[i]) for i in items],
                    (PromiseLabel.F.value, NON_FUNCTIONAL), {})
    nfr = [i for i in items if gold[i] != PromiseLabel.F.value]
    category = _score([gold[i] for i in nfr], [predicted[i] for i in nfr], CATEGORY_LABELS, EXCLUDED_FROM_MACRO)
    return [
        TaskScore(run_index, variant, "binary", len(items), invalid, *binary),
        TaskScore(run_index, variant, "category", len(nfr), sum(predicted[i] == INVALID for i in nfr), *category),
    ]


@dataclass(frozen=True)
class ContextAgreement:
    """Itens de contexto que são requisitos do PROMISE, por corrida e condição.

    agreeing / context_items: fração com o rótulo de referência do item avaliado. majority_matches: itens
    cujo rótulo mais frequente no contexto, quando único, é o do item. expected: fração esperada se cada item
    de contexto fosse sorteado entre os demais itens do projeto do item avaliado.
    """

    run_index: int
    condition: Condition
    items: int  # itens avaliados com pelo menos um requisito do PROMISE no contexto
    context_items: int
    agreeing: int
    majority_matches: int
    expected_agreeing: float

    @property
    def agreement(self) -> float | None:
        return self.agreeing / self.context_items if self.context_items else None

    @property
    def expected(self) -> float | None:
        return self.expected_agreeing / self.context_items if self.context_items else None

    @property
    def majority_rate(self) -> float | None:
        return self.majority_matches / self.items if self.items else None


@dataclass(frozen=True)
class PromiseResult:
    scores: list[TaskScore]
    missing_records: dict[tuple[int, str], int]  # (corrida, condição) -> itens sem registro
    reference_items: int
    run_items: int
    contradictory_pair_present: bool
    refinement_failures: dict[tuple[int, str], Counter]  # (corrida, condição) -> refinement_status -> itens
    # (corrida, condição) -> regra G -> itens. Recusa: refinamento válido com violação G (refinement_status ok e
    # refinement_accepted falso); o executor mantém o rótulo inicial em final.
    refinement_refusals: dict[tuple[int, str], Counter]
    agreement: list[ContextAgreement]


def _predicted(record) -> str:
    """ClassificationRecord garante final igual a initial quando o refinamento falhou."""
    if record.status is not RunStatus.OK:
        return INVALID
    if record.refinement_status is not RunStatus.OK:
        return record.initial.value
    return record.final.value


def _same_project_share(promise_id: str, gold: Gold) -> float:
    others = [i for i, p in gold.projects.items() if p == gold.projects[promise_id] and i != promise_id]
    if not others:
        return 0.0
    return sum(gold.labels[i] == gold.labels[promise_id] for i in others) / len(others)


def context_agreement(run: Run, gold: Gold) -> list[ContextAgreement]:
    evaluated = {r.promise_id for r in run.classifications}
    grouped: dict[tuple[int, Condition], list] = {}
    for record in run.contexts:
        if record.case_id in evaluated:
            grouped.setdefault((record.run_index, record.condition), []).append(record)
    found = []
    for (run_index, condition), records in sorted(grouped.items(), key=lambda kv: (kv[0][0], kv[0][1].value)):
        items = context_items = agreeing = majority = 0
        expected = 0.0
        for record in sorted(records, key=lambda r: r.case_id):
            label = gold.labels[record.case_id]
            neighbours = [item.item_id for item in record.context.items if PROMISE_ITEM.match(item.item_id)]
            unknown = sorted(set(neighbours) - gold.labels.keys())
            if unknown:
                raise ContractError(f"{run.directory}: item de contexto {unknown[0]} não está nos rótulos de referência")
            if not neighbours:
                continue
            labels = Counter(gold.labels[n] for n in neighbours)
            top = labels.most_common()
            items += 1
            context_items += len(neighbours)
            agreeing += labels[label]
            majority += top[0][0] == label and (len(top) == 1 or top[0][1] > top[1][1])
            expected += len(neighbours) * _same_project_share(record.case_id, gold)
        found.append(ContextAgreement(run_index, condition, items, context_items, agreeing, majority, expected))
    return found


def _is_refused(record) -> bool:
    return (record.status is RunStatus.OK and record.refinement_status is RunStatus.OK
            and not record.refinement_accepted)


def promise(run: Run, gold: Gold) -> PromiseResult:
    scores, missing, failures, refusals = [], {}, {}, {}
    run_items = set()
    for run_index in sorted({r.run_index for r in run.classifications}):
        records = [r for r in run.classifications if r.run_index == run_index]
        unknown = sorted({r.promise_id for r in records} - gold.labels.keys())
        if unknown:
            raise ContractError(f"{run.directory}: {unknown[0]} não está nos rótulos de referência")
        ids = sorted({r.promise_id for r in records})
        run_items |= set(ids)
        by_condition: dict[Condition, dict[str, object]] = {c: {} for c in Condition}
        for r in records:
            if r.promise_id in by_condition[r.condition]:
                raise ContractError(f"{run.directory}: {r.promise_id} repetido na corrida {run_index}, {r.condition.value}")
            by_condition[r.condition][r.promise_id] = r
        initial = {}
        for promise_id in ids:
            labels = {r.initial.value for c in Condition if (r := by_condition[c].get(promise_id)) and r.initial}
            if len(labels) > 1:
                raise ContractError(
                    f"{run.directory}: {promise_id} tem classificações iniciais diferentes nas duas condições "
                    f"({sorted(labels)}), mas a inicial é compartilhada"
                )
            initial[promise_id] = labels.pop() if labels else INVALID
        scores += task_scores(run_index, INITIAL, gold.labels, initial)
        for condition in Condition:
            mine = by_condition[condition]
            missing[(run_index, condition.value)] = len(set(ids) - mine.keys())
            failures[(run_index, condition.value)] = Counter(
                r.refinement_status.value for r in mine.values()
                if r.status is RunStatus.OK and r.refinement_status is not RunStatus.OK
            )
            refused = [r for r in mine.values() if _is_refused(r)]
            refusals[(run_index, condition.value)] = Counter(
                ",".join(sorted({v.rule_id for v in r.violations})) or "sem violação registrada" for r in refused
            )
            final = {i: (_predicted(mine[i]) if i in mine else INVALID) for i in ids}
            scores += task_scores(run_index, condition.value, gold.labels, final)
    return PromiseResult(scores, missing, len(gold.labels), len(run_items), set(CONTRADICTORY_PAIR) <= run_items,
                         failures, refusals, context_agreement(run, gold))
