"""Cálculo completo de uma corrida e escrita das tabelas CSV e do resumo Markdown em <run>/metrics/."""

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

from domain.config import ExperimentConfig
from domain.enums import Condition
from domain.rules import RULES_VERSION
from experiments.annotation import Reference
from experiments.metrics import bertscore, pairing
from experiments.metrics.loading import Corpus, Run, display_path, sha256_file
from experiments.metrics.promise import CONTRADICTORY_PAIR, EXCLUDED_FROM_MACRO, Gold, PromiseResult, promise
from experiments.metrics.structural import (
    ALL, Aggregate, ConditionRun, ContextSize, SharedRun, aggregate, context_sizes, shared, structural,
)

STRUCTURAL_METRICS = (
    "completeness_ratio", "c4_rate", "unsupported_claim_rate", "rule_violation_rate", "invalid_cases",
    "corrected", "foreign_evidence", "input_tokens_per_corrected", "output_tokens_per_corrected",
    "tokens_per_corrected",
)
OUTPUT_FILES = ("structural_by_run.csv", "shared_by_run.csv", "context_by_run.csv", "pairing_by_run.csv", "pairs.csv",
                "promise_by_label.csv", "promise_macro.csv", "promise_context_agreement.csv", "summary.csv",
                "summary.md")


@dataclass
class PairingResult:
    counts: list[pairing.PairingCounts] = field(default_factory=list)
    assignments: list[pairing.Assignment] = field(default_factory=list)
    decisions: list[pairing.Decisions] = field(default_factory=list)
    pending: list[int] = field(default_factory=list)
    bertscore: dict[tuple[str, str, str, int], float] = field(default_factory=dict)  # (cond, caso, chave, corrida)
    bertscore_model: bertscore.BertScoreModel | None = None
    bertscore_skipped: str | None = None
    reference_statements: dict[str, str] = field(default_factory=dict)

    def bertscore_mean(self, run_index: int, condition: Condition) -> float | None:
        values = [v for (c, _, _, i), v in self.bertscore.items() if c == condition.value and i == run_index]
        return sum(values) / len(values) if values else None


@dataclass
class Result:
    run: Run
    command: str
    inputs: list[tuple[str, str]]
    structural: list[ConditionRun] = field(default_factory=list)
    shared: list[SharedRun] = field(default_factory=list)
    contexts: list[ContextSize] = field(default_factory=list)
    pairing: PairingResult | None = None
    promise: PromiseResult | None = None

    def aggregates(self) -> list[Aggregate]:
        rows = []
        for r in self.structural:
            metrics = r.metrics()
            rows += [(m, r.condition.value, r.run_index, metrics[m]) for m in STRUCTURAL_METRICS]
        for s in self.contexts:
            if s.stratum == ALL:
                rows += [("context_items_mean", s.condition.value, s.run_index, s.items.mean),
                         ("context_chars_mean", s.condition.value, s.run_index, s.chars.mean)]
        if self.pairing:
            for c in self.pairing.counts:
                rows += [
                    ("paired", c.condition.value, c.run_index, float(c.paired)),
                    ("generated_unpaired", c.condition.value, c.run_index, float(c.generated_unpaired)),
                    ("references_unpaired", c.condition.value, c.run_index, float(c.references_unpaired)),
                    ("provenance_coverage", c.condition.value, c.run_index, c.provenance_coverage),
                    ("provenance_coverage_of_references", c.condition.value, c.run_index,
                     c.provenance_coverage_of_references),
                ]
                if self.pairing.bertscore_model:
                    rows.append(("bertscore_f1", c.condition.value, c.run_index,
                                 self.pairing.bertscore_mean(c.run_index, c.condition)))
        if self.promise:
            for s in self.promise.scores:
                for name, value in (("precision", s.macro_precision), ("recall", s.macro_recall), ("f1", s.macro_f1)):
                    rows.append((f"promise_{s.task}_macro_{name}", s.variant, s.run_index, value))
            for (run_index, condition), counts in self.promise.refinement_failures.items():
                rows.append(("promise_refinement_failures", condition, run_index, float(sum(counts.values()))))
            for (run_index, condition), counts in self.promise.refinement_refusals.items():
                rows.append(("promise_refinement_refusals", condition, run_index, float(sum(counts.values()))))
            for a in self.promise.agreement:
                rows += [("promise_context_label_agreement", a.condition.value, a.run_index, a.agreement),
                         ("promise_context_label_agreement_expected", a.condition.value, a.run_index, a.expected)]
        return aggregate(rows)


def compute_pairing(run: Run, corpus: Corpus, reference: Reference, config: ExperimentConfig, skip_bertscore: bool,
                    revision: str, num_layers: int | None) -> PairingResult:
    refs = pairing.references_by_case(reference, corpus, run.case_ids())
    result = PairingResult(reference_statements={r.id: r.statement for r in reference.requirements})
    for run_index in run.run_indices():
        items = pairing.generated(run, corpus, refs, run_index)
        rows = pairing.sheet_rows(items, config.evaluation.seed, run_index)
        decisions = pairing.read_decisions(run.directory, run.manifest.run_id, run_index, rows)
        if decisions is None:
            result.pending.append(run_index)
            continue
        assignments = pairing.assign(items, decisions, refs, corpus)
        result.decisions.append(decisions)
        result.assignments += assignments
        result.counts += pairing.counts(run_index, assignments, refs)
    pairs = [a for a in result.assignments if a.reference]
    if skip_bertscore:
        result.bertscore_skipped = "--skip-bertscore"
    elif pairs:
        model = bertscore.resolve(config.evaluation.bertscore_model, revision, num_layers)
        values = bertscore.score([(a.generated.statement, result.reference_statements[a.reference]) for a in pairs], model)
        result.bertscore_model = model
        for a, value in zip(pairs, values):
            g = a.generated
            result.bertscore[(g.condition.value, g.case_id, g.key, g.run_index)] = value
    else:
        result.bertscore_skipped = "nenhum par registrado"
    return result


def compute(run: Run, config: ExperimentConfig, command: str, inputs: list[tuple[str, str]], corpus: Corpus | None,
            reference: Reference | None, gold: Gold | None, skip_bertscore: bool = False,
            revision: str = "main", num_layers: int | None = None) -> Result:
    result = Result(run, command, inputs)
    result.shared = shared(run)
    if run.finals:
        result.structural = structural(run, corpus)
        result.contexts = context_sizes(run)
        if reference is not None:
            result.pairing = compute_pairing(run, corpus, reference, config, skip_bertscore, revision, num_layers)
    if run.classifications and gold is not None:
        result.promise = promise(run, gold)
    return result


# Escrita


def _csv_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _md(value) -> str:
    if value is None:
        return "indefinido"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _csv(header: list[str], rows: list[list]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows([[_csv_value(v) for v in row] for row in rows])
    return buffer.getvalue()


def _table(header: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines += ["| " + " | ".join(_md(v) for v in row) + " |" for row in rows]
    return lines


def structural_rows(result: Result) -> tuple[list[str], list[list]]:
    header = ["run_index", "condition", "cases", "invalid_cases", "generated", "complete", "completeness_ratio", "c4",
              "c4_rate", "unsupported", "unsupported_claim_rate", "k_violations", "rule_violation_rate", "targets",
              "accepted", "refused", "failed", "corrected", "foreign_evidence", "refinement_calls",
              "refinement_input_tokens", "refinement_output_tokens", "input_tokens_per_corrected",
              "output_tokens_per_corrected", "tokens_per_corrected", "final_record_input_tokens",
              "final_record_output_tokens"]
    rows = []
    for r in result.structural:
        m = r.metrics()
        rows.append([r.run_index, r.condition.value, r.cases, r.invalid_cases, r.generated, r.complete,
                     m["completeness_ratio"], r.c4, m["c4_rate"], r.unsupported, m["unsupported_claim_rate"],
                     r.k_violations, m["rule_violation_rate"], r.targets, r.accepted, r.refused, r.failed, r.corrected,
                     r.foreign_evidence, r.refinement.calls, r.refinement.input_tokens, r.refinement.output_tokens,
                     m["input_tokens_per_corrected"], m["output_tokens_per_corrected"], m["tokens_per_corrected"],
                     r.final_input_tokens, r.final_output_tokens])
    return header, rows


SHARED_PARTS = (("extraction", "sample_extraction"), ("promise_extraction", "promise_extraction"),
                ("classification", "classification"))


def shared_rows(result: Result) -> tuple[list[str], list[list]]:
    header = ["run_index"]
    for prefix, _ in SHARED_PARTS:
        header += [f"{prefix}_calls", f"{prefix}_input_tokens", f"{prefix}_output_tokens"]
    header += ["calls_without_usage", "rejections", "rejections_by_rule"]
    rows = []
    for s in result.shared:
        row = [s.run_index]
        for _, part in SHARED_PARTS:
            usage = getattr(s, part)
            row += [usage.calls, usage.input_tokens, usage.output_tokens]
        rows.append(row + [s.without_usage, sum(s.rejections.values()),
                           ";".join(f"{k}={v}" for k, v in sorted(s.rejections.items()))])
    return header, rows


def context_rows(result: Result) -> tuple[list[str], list[list]]:
    header = ["run_index", "condition", "stratum", "targets", "targets_without_context", "items_mean", "items_median",
              "items_max", "chars_mean", "chars_median", "chars_max"]
    rows = [[s.run_index, s.condition.value, s.stratum, s.items.n, s.without_context, s.items.mean, s.items.median,
             s.items.max, s.chars.mean, s.chars.median, s.chars.max] for s in result.contexts]
    return header, rows


def pairing_rows(result: Result) -> tuple[list[str], list[list]]:
    header = ["run_index", "condition", "generated", "references", "paired", "generated_unpaired",
              "unpaired_no_candidates", "unpaired_decided_none", "unpaired_duplicate", "references_unpaired",
              "covered", "provenance_coverage", "provenance_coverage_of_references", "bertscore_f1"]
    p = result.pairing
    rows = [[c.run_index, c.condition.value, c.generated, c.references, c.paired, c.generated_unpaired,
             c.no_candidates, c.decided_none, c.duplicates, c.references_unpaired, c.covered, c.provenance_coverage,
             c.provenance_coverage_of_references,
             p.bertscore_mean(c.run_index, c.condition) if p.bertscore_model else None] for c in p.counts]
    return header, rows


def agreement_rows(result: Result) -> tuple[list[str], list[list]]:
    header = ["run_index", "condition", "items_with_promise_context", "context_items", "agreeing", "agreement",
              "expected_agreement", "majority_matches", "majority_rate"]
    rows = [[a.run_index, a.condition.value, a.items, a.context_items, a.agreeing, a.agreement, a.expected,
             a.majority_matches, a.majority_rate] for a in result.promise.agreement]
    return header, rows


def pairs_rows(result: Result) -> tuple[list[str], list[list]]:
    header = ["run_index", "condition", "case", "key", "outcome", "reference", "covered", "bertscore_f1",
              "statement", "reference_statement"]
    p = result.pairing
    rows = []
    for a in sorted(p.assignments, key=lambda a: (a.generated.run_index, a.generated.condition.value,
                                                   a.generated.case_id, a.generated.key)):
        g = a.generated
        rows.append([g.run_index, g.condition.value, g.case_id, g.key, a.reason, a.reference or "",
                     int(a.covered) if a.reference else "",
                     p.bertscore.get((g.condition.value, g.case_id, g.key, g.run_index)), g.statement,
                     p.reference_statements.get(a.reference, "")])
    return header, rows


def promise_rows(result: Result) -> tuple[tuple[list[str], list[list]], tuple[list[str], list[list]]]:
    label_header = ["run_index", "variant", "task", "label", "support", "predicted", "precision", "recall", "f1",
                    "in_macro", "note"]
    macro_header = ["run_index", "variant", "task", "items", "invalid", "macro_labels", "macro_precision",
                    "macro_recall", "macro_f1"]
    labels, macro = [], []
    for s in result.promise.scores:
        labels += [[s.run_index, s.variant, s.task, ls.label, ls.support, ls.predicted, ls.precision, ls.recall,
                    ls.f1, int(ls.in_macro), ls.note] for ls in s.labels]
        macro.append([s.run_index, s.variant, s.task, s.items, s.invalid, " ".join(s.macro_labels),
                      s.macro_precision, s.macro_recall, s.macro_f1])
    return (label_header, labels), (macro_header, macro)


def summary_rows(result: Result) -> tuple[list[str], list[list]]:
    header = ["metric", "condition", "n", "mean", "sd", "values"]
    rows = [[a.metric, a.condition, len(a.defined), a.mean, a.sd, ";".join(_csv_value(v) for v in a.values)]
            for a in result.aggregates()]
    return header, rows


FORMULAS = [
    "Denominador das razões da amostra: G, número de requisitos gerados na saída final (FinalRecord.output) da "
    "corrida e da condição. Caso inválido (FinalRecord.status diferente de ok) conta como zero requisito gerado.",
    "Corpus do caso: check_all, is_complete e a cobertura de proveniência usam só os chunks do documento do caso, "
    "como o executor. Evidência que cita chunk de outro documento não resolve e conta como P2.",
    "`completeness_ratio` = #{r em G : rules.is_complete(r, corpus do caso)} / |G|.",
    "`c4_rate` = #{r em G : C4 em check_all com subject = r.key} / |G| (C4 fica fora de is_complete).",
    "`unsupported_claim_rate` = #{r em G : P1, P2 ou P3 em check_all com subject = r.key} / |G|. Violações de "
    "ator, componente, entidade e relação não entram.",
    "`rule_violation_rate` = #{violações K1 a K5 de check_all na saída} / |G|.",
    "`foreign_evidence` = número de citações da saída final (requisitos, atores, componentes, entidades e "
    "relações) cujo chunk_id é de outro documento da ingestão. Contagem, não razão.",
    "`corrected` = #{k em FinalRecord.targets : CP_final(k) < CP_extração(k) e nenhuma violação P nova em k}, com "
    "CP = número de violações C1 a C4 e P1 a P5 de check_all com subject = k, e violação P nova = par (regra, "
    "detalhe) de P1 a P5 que aparece mais vezes na saída final do que na extração. A extração é o CaseResult de "
    "stage extraction da mesma corrida.",
    "`input_tokens_per_corrected` = soma de usage.input_tokens, cache_creation_input_tokens e cache_read_input_tokens "
    "das chamadas de refinamento da condição e da corrida em calls.jsonl / corrected; `output_tokens_per_corrected` "
    "idem com output_tokens; `tokens_per_corrected` com a soma dos dois. Chamada com falha da API conta zero. "
    "Indefinido com corrected = 0 ou com resposta sem usage. As colunas final_record_* somam "
    "FinalRecord.input_tokens e output_tokens, só para conferência.",
    "Chamadas comuns às duas condições (shared_by_run.csv), por corrida, com chamadas e tokens de entrada (com cache) "
    "e saída: extração da amostra = chamadas de stage extraction cujo case_id é um caso de finals.jsonl; extração "
    "dos projetos do PROMISE = as demais chamadas de stage extraction (grafo por projeto de B); classificação = "
    "chamadas de stage classification. Falha da API conta a chamada e zero token.",
    "Tamanho do contexto (context_by_run.csv): para cada alvo de FinalRecord.targets com ContextRecord de mesmo "
    "caso, corrida, condição e chave, itens = len(context.items) e caracteres = soma de len(item.text); média, "
    "mediana e máximo sobre os alvos. Estratos: all, written (alvo gravado no grafo) e rejected_w (alvo com "
    "RejectionRecord de subject igual à chave na mesma corrida). `context_items_mean` e `context_chars_mean` no "
    "agregado são as médias do estrato all.",
    "Pareamento: `paired` = pares depois da atribuição um a um; `generated_unpaired` = |G| - paired (sem candidata, "
    "decisão nenhum ou duplicata); `references_unpaired` = R - paired, com R = referências dos casos da corrida, "
    "inválidos inclusive.",
    "`provenance_coverage` = covered / paired, com covered = #{pares (g, r) : alguma evidência de g resolve no "
    "corpus do caso e cita um chunk que contém r.quote pela comparação de P3}. "
    "`provenance_coverage_of_references` = covered / R: o denominador não depende da condição.",
    "`bertscore_f1` = média do F1 do BERTScore (idf desligado, sem baseline) entre a declaração de g e a de r, "
    "sobre os pares da corrida e da condição.",
    "PROMISE: precisão, revocação e F1 de scikit-learn (precision_recall_fscore_support, zero_division = 0). "
    "Predição inválida (primeira classificação com status diferente de ok) erra o item e não conta para rótulo "
    "nenhum. Refinamento com refinement_status diferente de ok (falha) mantém o rótulo inicial e é contado em "
    "`promise_refinement_failures`. Refinamento com refinement_status ok e refinement_accepted falso (recusa por "
    "regra G) mantém o rótulo inicial em final e é contado em `promise_refinement_refusals`, por regra. Binária: F contra NF sobre todos os itens, média macro de F e NF. Categoria: "
    "onze rótulos não funcionais sobre os itens de referência não funcional; média macro sobre os rótulos com "
    "suporte, sem PO.",
    "PROMISE, diagnóstico do contexto (promise_context_agreement.csv): para cada item avaliado i, N_i = itens do "
    "contexto com item_id PROMISE-NFR-NNNN. `promise_context_label_agreement` = soma dos N_i com o rótulo de "
    "referência de i / soma dos N_i. `promise_context_label_agreement_expected` = soma de N_i * q_i / soma dos N_i, "
    "com q_i = fração dos demais itens do projeto de i com o mesmo rótulo de i: a concordância esperada se o "
    "contexto fosse sorteado no projeto. majority_rate = itens cujo rótulo mais frequente no contexto, quando "
    "único, é o de i / itens com N_i > 0.",
    "Agregado entre corridas: média aritmética e desvio padrão amostral (n - 1) dos valores definidos de cada corrida.",
]


def render_summary(result: Result) -> str:
    run = result.run
    lines = [
        f"# Métricas da corrida {run.manifest.run_id}",
        "",
        "Gerado por `experiments.metrics`. Não editar à mão. O comando abaixo, a partir da raiz do repositório, "
        "regenera cada número deste arquivo e das tabelas CSV da mesma pasta:",
        "",
        "```sh",
        result.command,
        "```",
        "",
        "## Entradas",
        "",
    ]
    lines += [f"- {label}: {value}" for label, value in result.inputs]
    lines += ["", "## Definições", ""] + [f"- {f}" for f in FORMULAS]
    if result.shared:
        lines += _shared_section(result)
    if result.structural:
        lines += _structural_section(result)
    if result.pairing:
        lines += _pairing_section(result)
    if result.promise:
        lines += _promise_section(result)
    lines += ["", "## Agregado entre corridas", "", "Tabela completa em `summary.csv`.", ""]
    lines += _table(["métrica", "condição", "n", "média", "desvio", "valores por corrida"],
                    [[a.metric, a.condition, len(a.defined), a.mean, a.sd, "; ".join(_md(v) for v in a.values)]
                     for a in result.aggregates()])
    return "\n".join(lines) + "\n"


def _shared_section(result: Result) -> list[str]:
    def cell(usage) -> str:
        return f"{usage.calls} / {usage.input_tokens}/{usage.output_tokens}"

    lines = ["", "## Comum às duas condições: chamadas e tokens", "",
             "Chamadas sem condição, feitas uma vez por corrida. Cada célula: chamadas / tokens de entrada (com cache)/"
             "saída. Também em `shared_by_run.csv`.", ""]
    lines += _table(["corrida", "extração da amostra", "extração dos projetos do PROMISE", "classificação do PROMISE"],
                    [[s.run_index, cell(s.sample_extraction), cell(s.promise_extraction), cell(s.classification)]
                     for s in result.shared])
    missing = [s.run_index for s in result.shared if s.without_usage]
    if missing:
        lines += ["", f"Chamadas comuns sem registro de consumo nas corridas {missing}: os tokens delas não entram."]
    return lines


def _structural_section(result: Result) -> list[str]:
    lines = ["", "## Amostra de referência: métricas por regra", "",
             f"Regras de `code/domain/rules.py`, versão {RULES_VERSION}. Por corrida em `structural_by_run.csv`.", ""]
    lines += _table(
        ["corrida", "condição", "casos", "inválidos", "gerados", "completude", "C4", "sem proveniência", "K por requisito",
         "alvos", "aceitos", "recusados", "com falha", "corrigidos", "evidências de outro documento",
         "tokens refino (entrada/saída)", "tokens por corrigido"],
        [[r.run_index, r.condition.value, r.cases, r.invalid_cases, r.generated, r.metrics()["completeness_ratio"],
          r.metrics()["c4_rate"], r.metrics()["unsupported_claim_rate"], r.metrics()["rule_violation_rate"], r.targets,
          r.accepted, r.refused, r.failed, r.corrected, r.foreign_evidence,
          f"{r.refinement.input_tokens}/{r.refinement.output_tokens}", r.metrics()["tokens_per_corrected"]]
         for r in result.structural],
    )
    invalid = [f"corrida {r.run_index}, {r.condition.value}: " + ", ".join(f"{k} {v}" for k, v in sorted(r.invalid.items()))
               for r in result.structural if r.invalid]
    lines += ["", "Casos inválidos por estado: " + ("; ".join(invalid) if invalid else "nenhum") + "."]
    lines += ["", "Recusas na gravação do grafo (regras W): não mudam as métricas e são reportadas à parte.", ""]
    lines += _table(["corrida", "recusas W", "por regra"],
                    [[s.run_index, sum(s.rejections.values()),
                      ", ".join(f"{k} {v}" for k, v in sorted(s.rejections.items())) or "-"]
                     for s in result.shared if s.run_index in result.run.run_indices()])
    missing_usage = [r.run_index for r in result.structural if r.refinement.without_usage]
    differs = [f"corrida {r.run_index}, {r.condition.value}" for r in result.structural
               if (r.refinement.input_tokens, r.refinement.output_tokens) != (r.final_input_tokens, r.final_output_tokens)]
    if differs:
        lines += ["", "Aviso: o consumo de refinamento somado em calls.jsonl difere da soma de FinalRecord.input_tokens e "
                      f"output_tokens em {'; '.join(differs)} (colunas final_record_* de structural_by_run.csv)."]
    if missing_usage:
        lines += ["", f"Chamadas sem registro de consumo nas corridas {sorted(set(missing_usage))}: tokens por "
                      "corrigido ficam indefinidos nelas."]
    lines += ["", "### Tamanho do contexto de refinamento", "",
              "Por alvo, a partir de contexts.jsonl. written: alvo gravado no grafo; rejected_w: alvo recusado na "
              "gravação (regras W). Também em `context_by_run.csv`.", ""]
    lines += _table(["corrida", "condição", "estrato", "alvos", "itens (média/mediana/máx.)",
                     "caracteres (média/mediana/máx.)"],
                    [[s.run_index, s.condition.value, s.stratum, s.items.n,
                      " / ".join(_md(v) for v in (s.items.mean, s.items.median, s.items.max)),
                      " / ".join(_md(v) for v in (s.chars.mean, s.chars.median, s.chars.max))]
                     for s in result.contexts])
    missing = [f"corrida {s.run_index}, {s.condition.value}: {s.without_context}" for s in result.contexts
               if s.without_context]
    if missing:
        lines += ["", "Alvos sem ContextRecord, fora das estatísticas: " + "; ".join(missing) + "."]
    return lines


def _pairing_section(result: Result) -> list[str]:
    p = result.pairing
    lines = ["", "## Pareamento com a amostra de referência", ""]
    if p.pending:
        lines.append(f"Corridas sem decisões registradas (planilha pendente): {p.pending}. Nelas as três contagens, "
                     "a cobertura de proveniência e o BERTScore não são calculados.")
        lines.append("")
    for d in p.decisions:
        lines.append(f"- Corrida {d.run_index}: planilha com SHA-256 `{d.sheet_sha256}`, registrada em {d.locked_at}.")
        for c in d.corrections:
            lines.append(f"  - Correção {c.code} em {c.date}: {c.decision} ({c.reason}).")
    if p.bertscore_model:
        info = p.bertscore_model.describe()
        lines.append("- BERTScore: " + ", ".join(f"{k} {v}" for k, v in info.items()) + ".")
    elif p.bertscore_skipped:
        lines.append(f"- BERTScore não calculado: {p.bertscore_skipped}.")
    if p.counts:
        lines += ["", "Por corrida em `pairing_by_run.csv`; cada requisito gerado em `pairs.csv`.", ""]
        lines += _table(
            ["corrida", "condição", "gerados", "referências", "pareados", "gerados sem par", "sem candidata",
             "decisão nenhum", "duplicata", "referências sem par", "cobertos", "cobertura (cobertos / pareados)",
             "cobertura (cobertos / referências)", "BERTScore F1"],
            [[c.run_index, c.condition.value, c.generated, c.references, c.paired, c.generated_unpaired, c.no_candidates,
              c.decided_none, c.duplicates, c.references_unpaired, c.covered, c.provenance_coverage,
              c.provenance_coverage_of_references,
              p.bertscore_mean(c.run_index, c.condition) if p.bertscore_model else None] for c in p.counts],
        )
    return lines


def _promise_section(result: Result) -> list[str]:
    pr = result.promise
    lines = ["", "## PROMISE NFR", "",
             f"Itens na referência: {pr.reference_items}. Itens com registro na corrida: {pr.run_items}. "
             "Por rótulo em `promise_by_label.csv`; médias em `promise_macro.csv`."]
    missing = [f"corrida {i}, {c}: {n}" for (i, c), n in sorted(pr.missing_records.items()) if n]
    lines.append("Itens sem registro de uma condição, contados como predição inválida: "
                 + ("; ".join(missing) if missing else "nenhum") + ".")
    def by_condition(counts) -> str:
        return "; ".join(f"corrida {i}, {c}: {sum(n.values())}"
                         + (" (" + ", ".join(f"{k} {v}" for k, v in sorted(n.items())) + ")" if n else "")
                         for (i, c), n in sorted(counts.items()))

    lines.append("Refinamentos com falha (refinement_status diferente de ok: resposta inválida ou erro de API), "
                 f"que mantêm o rótulo inicial: {by_condition(pr.refinement_failures)}.")
    lines.append("Refinamentos recusados por regra G (refinement_status ok e refinement_accepted falso), que mantêm "
                 f"o rótulo inicial: {by_condition(pr.refinement_refusals)}.")
    lines += [f"{label} fora da média macro: {why}." for label, why in EXCLUDED_FROM_MACRO.items()]
    if pr.contradictory_pair_present:
        lines.append(f"O par {CONTRADICTORY_PAIR[0]} (SE) e {CONTRADICTORY_PAIR[1]} (F) tem o mesmo texto e rótulos "
                     "diferentes; um dos dois sempre conta como erro.")
    lines += [""]
    lines += _table(["corrida", "classificação", "tarefa", "itens", "inválidas", "rótulos na média", "precisão macro",
                     "revocação macro", "F1 macro"],
                    [[s.run_index, s.variant, s.task, s.items, s.invalid, " ".join(s.macro_labels), s.macro_precision,
                      s.macro_recall, s.macro_f1] for s in pr.scores])
    lines += ["", "Por rótulo:", ""]
    lines += _table(["corrida", "classificação", "tarefa", "rótulo", "suporte", "preditos", "precisão", "revocação", "F1",
                     "na média"],
                    [[s.run_index, s.variant, s.task, ls.label, ls.support, ls.predicted, ls.precision, ls.recall, ls.f1,
                      "sim" if ls.in_macro else "não"] for s in pr.scores for ls in s.labels])
    lines += ["", "### Rótulo dos requisitos do PROMISE no contexto", "",
              "Diagnóstico: se a concordância passa muito da esperada, o contexto funciona como oráculo de rótulo. "
              "Também em `promise_context_agreement.csv`.", ""]
    lines += _table(["corrida", "condição", "itens com requisito do PROMISE no contexto", "itens de contexto",
                     "mesmo rótulo", "concordância", "esperada no projeto", "maioria igual ao rótulo"],
                    [[a.run_index, a.condition.value, a.items, a.context_items, a.agreeing, a.agreement, a.expected,
                      f"{a.majority_matches} ({_md(a.majority_rate)})"] for a in pr.agreement])
    return lines


def write(result: Result, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    if result.shared:
        files["shared_by_run.csv"] = _csv(*shared_rows(result))
    if result.structural:
        files["structural_by_run.csv"] = _csv(*structural_rows(result))
        files["context_by_run.csv"] = _csv(*context_rows(result))
    if result.pairing and result.pairing.counts:
        files["pairing_by_run.csv"] = _csv(*pairing_rows(result))
        files["pairs.csv"] = _csv(*pairs_rows(result))
    if result.promise:
        labels, macro = promise_rows(result)
        files["promise_by_label.csv"] = _csv(*labels)
        files["promise_macro.csv"] = _csv(*macro)
        files["promise_context_agreement.csv"] = _csv(*agreement_rows(result))
    files["summary.csv"] = _csv(*summary_rows(result))
    files["summary.md"] = render_summary(result)
    for name in OUTPUT_FILES:
        if name not in files and (out_dir / name).exists():
            (out_dir / name).unlink()
    written = []
    for name, text in files.items():
        (out_dir / name).write_text(text, encoding="utf-8")
        written.append(out_dir / name)
    return written


def input_lines(run: Run, config_path: Path, corpus: Corpus | None, reference_dir: Path | None,
                reference_hashes: dict[str, str], labels_path: Path | None) -> list[tuple[str, str]]:
    m = run.manifest
    lines = [
        ("corrida", f"`{display_path(run.directory)}`, model_id `{m.model_id or '(vazio)'}`, replay {m.replay}, "
                    f"runs {m.runs}"),
        ("corrida piloto", "sim: dispensa o congelamento e não entra no relatório como resultado" if m.pilot else "não"),
        ("configuração", f"`{display_path(config_path)}`, SHA-256 `{m.config_sha256}` (confere com o manifesto)"),
        ("registro de prompts", f"SHA-256 `{m.prompts_registry_sha256}`"),
    ]
    if m.freeze_manifest_sha256:
        lines.append(("manifesto de congelamento", f"SHA-256 `{m.freeze_manifest_sha256}`"))
    if corpus:
        lines += [("ingestão", f"`{path}`, {how}, SHA-256 `{digest}`") for path, digest, how in corpus.files]
        if not m.ingestion_sha256:
            lines.append(("aviso", "o manifesto não registra ingestion_sha256; a ingestão não pôde ser conferida"))
    if reference_dir:
        lines.append(("referência", f"`{display_path(reference_dir)}`"))
        lines += [(f"  {name}", f"SHA-256 `{digest}`") for name, digest in sorted(reference_hashes.items())]
    if labels_path and run.classifications:
        lines.append(("rótulos do PROMISE", f"`{display_path(labels_path)}`, SHA-256 `{sha256_file(labels_path)}`"))
    return lines
