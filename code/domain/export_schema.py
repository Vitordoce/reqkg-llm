"""Exporta o JSON Schema dos contratos do modelo e a lista de regras.

Uso, a partir da raiz do repositório:
    .venv/bin/python code/domain/export_schema.py          # reescreve
    .venv/bin/python code/domain/export_schema.py --check  # falha se o disco divergir
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from domain.config import ExperimentConfig  # noqa: E402
from domain.llm_io import (  # noqa: E402
    REFINEMENT_RULES,
    CaseResult,
    ClassificationOutput,
    ExtractionOutput,
    RefinementOutput,
    RetrievedContext,
)
from domain.persist import REJECTION_RULES  # noqa: E402
from domain.rules import REFINEMENT_TRIGGERS, RULES, RULES_VERSION  # noqa: E402

SCHEMAS = {
    "extraction_output.schema.json": ExtractionOutput,
    "refinement_output.schema.json": RefinementOutput,
    "classification_output.schema.json": ClassificationOutput,
    "retrieved_context.schema.json": RetrievedContext,
    "case_result.schema.json": CaseResult,
    "experiment_config.schema.json": ExperimentConfig,
}


def rules_markdown() -> str:
    lines = [
        "# Regras do ReqKG",
        "",
        f"Arquivo gerado por `code/domain/export_schema.py`. Versão das regras: `{RULES_VERSION}`.",
        "",
        "| Regra | Família | O que conta |",
        "| --- | --- | --- |",
    ]
    lines += [f"| {r.rule_id} | {r.family.value} | {r.description} |" for r in RULES]
    lines += [
        "",
        "## Escolha dos candidatos refinados",
        "",
        f"As duas condições refinam os mesmos candidatos: os que têm violação {', '.join(sorted(REFINEMENT_TRIGGERS))}, "
        "alguma marca de revisão, ou confiança abaixo de `review.confidence_threshold`. A escolha sai da extração "
        "compartilhada, antes de qualquer contexto.",
        "",
        "## Refinamento recusado",
        "",
        "Com qualquer violação G, o sistema recusa o refinamento e mantém o candidato original.",
        "",
        "| Regra | O que conta |",
        "| --- | --- |",
    ]
    lines += [f"| {rule_id} | {text} |" for rule_id, text in REFINEMENT_RULES.items()]
    lines += [
        "",
        "## Recusa na gravação do grafo",
        "",
        "Recusas não mudam as métricas, que leem a resposta do modelo. Elas são reportadas à parte.",
        "",
        "| Regra | O que conta |",
        "| --- | --- |",
    ]
    lines += [f"| {rule_id} | {text} |" for rule_id, text in REJECTION_RULES.items()]
    return "\n".join(lines) + "\n"


def outputs() -> dict[str, str]:
    files = {
        name: json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        for name, model in SCHEMAS.items()
    }
    files["RULES.md"] = rules_markdown()
    return files


def main(argv: list[str]) -> int:
    target = HERE / "schema"
    stale = []
    for name, content in outputs().items():
        path = target / name
        if "--check" in argv:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                stale.append(name)
            continue
        target.mkdir(exist_ok=True)
        path.write_text(content, encoding="utf-8")
    if stale:
        print("schema desatualizado, rode export_schema.py:", *stale, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
