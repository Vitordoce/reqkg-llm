"""Os quatro artefatos do estudo de caso, em texto. Mesma entrada, mesmos bytes.

O gerador não preenche campo: o que falta nos registros aparece como "pendente".
"""

import csv
import io
import json
from collections import Counter

from domain.enums import (
    RELATION_ENDPOINTS, ActorKind, Origin, Priority, QualityCategory, RelationType, RequirementStatus,
    RequirementType, ReviewFlag, RunStatus, VerificationMethod,
)
from domain.llm_io import REFINEMENT_RULES
from domain.persist import REJECTION_RULES
from domain.rules import RULES, RuleFamily
from graph.schema import CONTAINS, LABELS, SUPPORTS

from deliverables.catalog import (
    NO_EVIDENCE, NO_QUOTE, OUTSIDE_CORPUS, QUOTE_FOUND, QUOTE_MISSING, Catalog, EvidenceView, RequirementView,
)

PENDING = "pendente"
AUTHOR = "_A preencher pelo autor._"

TYPE = {RequirementType.FUNCTIONAL: "funcional", RequirementType.NON_FUNCTIONAL: "não funcional",
        RequirementType.CONSTRAINT: "restrição"}
PRIORITY = {Priority.MUST: "Must", Priority.SHOULD: "Should", Priority.COULD: "Could", Priority.WONT: "Won't"}
METHOD = {VerificationMethod.INSPECTION: "inspeção", VerificationMethod.ANALYSIS: "análise",
          VerificationMethod.DEMONSTRATION: "demonstração", VerificationMethod.TEST: "teste"}
STATUS = {RequirementStatus.DRAFT: "rascunho", RequirementStatus.NEEDS_REVIEW: "em revisão humana",
          RequirementStatus.APPROVED: "aprovado", RequirementStatus.REJECTED: "rejeitado"}
QUALITY = {QualityCategory.PERFORMANCE: "Desempenho", QualityCategory.SECURITY: "Segurança",
           QualityCategory.USABILITY: "Usabilidade", QualityCategory.RELIABILITY: "Confiabilidade",
           QualityCategory.MAINTAINABILITY: "Manutenibilidade", QualityCategory.PORTABILITY: "Portabilidade"}
ORIGIN = {Origin.EXTRACTED_FACT: "fato extraído", Origin.SYSTEM_INFERENCE: "inferência do sistema",
          Origin.RESEARCHER_DECISION: "decisão do pesquisador"}
ACTOR_KIND = {ActorKind.STAKEHOLDER: "stakeholder", ActorKind.EXTERNAL_SYSTEM: "sistema externo",
              ActorKind.USER_ROLE: "papel de usuário"}
FLAG = {ReviewFlag.LOW_CONFIDENCE: "baixa confiança", ReviewFlag.AMBIGUOUS_TYPE: "tipo ambíguo",
        ReviewFlag.QUANTITATIVE_VALUE_PENDING: "valor quantitativo pendente"}
CLASSES = (("Requirement", "Requisito"), ("Actor", "Ator"), ("SourceDocument", "Artefato-fonte"),
           ("SourceChunk", "Trecho de fonte"), ("QualityAttribute", "Atributo de qualidade"),
           ("SoftwareComponent", "Componente de software"), ("Entity", "Entidade interna"))
FAMILY = {RuleFamily.COMPLETENESS: "completude", RuleFamily.PROVENANCE: "proveniência",
          RuleFamily.CONSISTENCY: "consistência"}

ARTIFACTS = ("srs.md", "instancia_reqkg.json", "instancia_resumo.md", "matriz_proveniencia.csv",
             "matriz_proveniencia.md", "relatorio_lacunas.md")


def cell(text: object) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def code(text: object) -> str:
    return f"`{text}`"


def quoted(text: str) -> str:
    return f"“{' '.join(text.split())}”"


def table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    return lines


def doc_labels(catalog: Catalog) -> dict[str, str]:
    return {d.source_id: f"D{i}" for i, d in enumerate(catalog.inputs.documents, start=1)}


def header(catalog: Catalog, title: str, command: str) -> list[str]:
    inputs = catalog.inputs
    manifest = inputs.manifest
    selection = inputs.selection
    ingestion = [f for k, f in sorted(inputs.files.items()) if k.startswith("ingestion:")]
    config = inputs.files["config"]
    return [
        f"# {title}", "",
        "> Gerado pelo ReqKG-LLM a partir dos registros da corrida, sem edição manual. "
        f"Para regenerar: {code(command)}.",
        ">",
        f"> - Corrida: {code(manifest.run_id)}, condição {code(selection.condition.value)}, "
        f"repetição {selection.run_index} (a corrida tem {manifest.runs}).",
        "> - Corrida piloto: " + ("sim. Não entra no relatório como resultado." if manifest.pilot else "não."),
        f"> - Modelo: {code(manifest.model_id or PENDING)}. Respostas gravadas (replay): "
        f"{'sim' if manifest.replay else 'não'}.",
        f"> - Comando da corrida: {code(manifest.command)}.",
        f"> - Casos: {', '.join(f'{code(c)} ({code(inputs.document(c).path)})' for c in inputs.cases)}.",
        f"> - Configuração: {code(config.path)} (SHA-256 {code(config.sha256)}).",
        *[f"> - Ingestão: {code(f.path)} (SHA-256 {code(f.sha256)})." for f in ingestion],
        *[f"> - Entrada da corrida sem arquivo de ingestão lido aqui: SHA-256 {code(h)}."
          for h in inputs.unread_ingestion],
        "",
    ]


# SRS


def _source(view: EvidenceView, labels: dict[str, str]) -> str:
    e = view.evidence
    if view.quote_status == OUTSIDE_CORPUS:
        return f"{code(e.source_id)} / {code(e.chunk_id)}: fora do corpus do caso (P2)"
    return (f"{labels[e.source_id]} {code(view.document.path)}, chunk {code(e.chunk_id)} "
            f"(índice {view.chunk.index})")


def _quote(view: EvidenceView) -> str:
    quote = view.evidence.quote
    if view.quote_status == NO_QUOTE:
        return f"{PENDING} (evidência sem citação)"
    if view.quote_status == QUOTE_FOUND:
        return f"{quoted(quote)} (aparece no chunk)"
    if view.quote_status == QUOTE_MISSING:
        return f"{quoted(quote)} (**não aparece no chunk citado, P3**)"
    return f"{quoted(quote)} (não conferida: chunk fora do corpus do caso)"


def _status(view: RequirementView, catalog: Catalog) -> str:
    if view.requirement is not None:
        status = view.requirement.status
        return f"{STATUS[status]} ({code(status.value)})"
    if view.rejection is None:
        return f"{PENDING}: não gravado no grafo"
    if view.rejection.rule_id == "W6":
        twin = next(v.label for v in catalog.requirements
                    if v.requirement is not None and v.requirement_id == view.requirement_id)
        return f"{PENDING}: não gravado, mesmo identificador de {twin} (W6)"
    return f"{PENDING}: não gravado no grafo ({view.rejection.rule_id}: {REJECTION_RULES[view.rejection.rule_id]})"


def _review_reason(view: RequirementView, threshold: float) -> str:
    reasons = []
    for flag in view.flags:
        if flag is ReviewFlag.LOW_CONFIDENCE and view.candidate.confidence is not None \
                and view.candidate.confidence < threshold:
            reasons.append(f"baixa confiança ({view.candidate.confidence} abaixo do limiar {threshold})")
        elif flag in (ReviewFlag.LOW_CONFIDENCE, ReviewFlag.AMBIGUOUS_TYPE):
            reasons.append(FLAG[flag])
    return "; ".join(reasons)


def _has_quality_fields(view: RequirementView) -> bool:
    return view.candidate.type is RequirementType.NON_FUNCTIONAL or bool(view.candidate.quality_attributes)


def requirement_block(view: RequirementView, catalog: Catalog, level: str) -> list[str]:
    candidate = view.candidate
    threshold = catalog.inputs.confidence_threshold
    labels = doc_labels(catalog)
    title = f"{level} {view.label} · {code(view.requirement_id) if view.requirement_id else 'sem requirement_id'}"
    lines = [title, ""]
    if view.in_review:
        lines += [f"> **Em revisão humana**: {_review_reason(view, threshold)}.", ""]
    rows = [["Declaração", candidate.statement]]
    if view.requirement is not None and view.requirement.previous_statement is not None:
        rows.append(["Declaração antes do refinamento", view.requirement.previous_statement])
    rows.append(["Tipo", TYPE[candidate.type] if candidate.type else PENDING])
    if _has_quality_fields(view):
        attributes = ", ".join(f"{QUALITY[q].lower()} ({code(q.value)})" for q in candidate.quality_attributes)
        rows.append(["Atributos de qualidade", attributes or PENDING])
        rows.append(["Valor quantitativo", candidate.quantitative_value or PENDING])
    rows += [
        ["Prioridade", PRIORITY[candidate.priority] if candidate.priority else PENDING],
        ["Método de verificação", METHOD[candidate.verification_method] if candidate.verification_method else PENDING],
        ["Status", _status(view, catalog)],
        ["Marcas de revisão", ", ".join(FLAG[f] for f in view.flags) or "nenhuma"],
        ["Confiança declarada", str(candidate.confidence) if candidate.confidence is not None else "não informada"],
    ]
    if view.requirement is not None:
        rows.append(["Origem", ORIGIN[view.requirement.provenance.origin]])
    else:
        rows.append(["Origem", f"{ORIGIN[candidate.origin]} (declarada pelo modelo, não gravada)"])
    refinement = view.refinement
    if refinement == "aceito" and view.requirement is not None and view.requirement.revision == 1:
        refinement = "aceito, revisão 1"
    rows.append(["Refinamento", refinement])
    if not view.evidence:
        rows += [["Fonte", f"{PENDING} (sem evidência, P1)"], ["Citação", PENDING]]
    for number, evidence in enumerate(view.evidence, start=1):
        suffix = f" {number}" if len(view.evidence) > 1 else ""
        rows += [[f"Fonte{suffix}", _source(evidence, labels)], [f"Citação{suffix}", _quote(evidence)]]
    rows.append(["Registro", f"caso {code(view.case_id)}, chave {code(candidate.key)}"])
    return lines + table(["Campo", "Valor"], rows) + [""]


def _group(views: list[RequirementView], catalog: Catalog, level: str) -> list[str]:
    if not views:
        return ["Nenhum requisito.", ""]
    return [line for view in views for line in requirement_block(view, catalog, level)]


def srs(catalog: Catalog, name: str, command: str) -> str:
    inputs = catalog.inputs
    views = catalog.requirements
    labels = doc_labels(catalog)
    by_type = lambda t: [v for v in views if v.candidate.type is t]  # noqa: E731
    functional, nfr, constraints = (by_type(t) for t in RequirementType)
    untyped = [v for v in views if v.candidate.type is None]

    lines = header(catalog, f"Esboço de SRS: {name}", command)
    lines += [
        "Esboço na estrutura de SRS da ISO/IEC/IEEE 29148:2018. O gerador não preenche nenhum campo: o que falta "
        "nos registros aparece como \"pendente\". Propósito, escopo e visão geral ficam com o autor. Requisito "
        "marcado **Em revisão humana** tem baixa confiança ou tipo ambíguo e ainda não foi aceito.", "",
        "## 1. Introdução", "",
        "### 1.1 Propósito", "", AUTHOR, "",
        "### 1.2 Escopo", "", AUTHOR, "",
        "### 1.3 Visão geral do produto", "", AUTHOR, "",
        "### 1.4 Convenções deste esboço", "",
        "- `REQ-NNN` numera os requisitos pela ordem de leitura da primeira evidência que resolve no corpus, na "
        "extração compartilhada pelas duas condições. O mesmo candidato tem o mesmo número nas duas condições. Ao "
        "lado vem o `requirement_id` do ReqKG. Candidato que não entrou no grafo diz o motivo no campo Status.",
        "- Prioridade em MoSCoW. Método de verificação: inspeção, análise, demonstração ou teste. Atributos de "
        "qualidade da ISO/IEC 25010.",
        "- \"pendente\" marca campo ausente nos registros. O modelo só preenche prioridade e método com sinal "
        "explícito no texto, citado.",
        "- A citação é o trecho que o modelo deu como evidência, conferido contra o texto do chunk com a "
        "normalização da regra P3.",
        "",
        "## 2. Referências", "",
        "### 2.1 Documentos-fonte", "",
    ]
    lines += table(["Documento", "Caminho", "Tipo", "Título", "SHA-256", "source_id"], [
        [labels[d.source_id], code(d.path), code(d.kind.value), d.title or PENDING, code(d.sha256), code(d.source_id)]
        for d in inputs.documents
    ]) + [""]
    lines += ["## 3. Stakeholders e atores", ""]
    actor_rows = []
    for actor in catalog.actors:
        sources = "; ".join(_source(e, labels) for e in actor.evidence)
        quotes = "; ".join(_quote(e) for e in actor.evidence)
        actor_rows.append([actor.actor.name, ACTOR_KIND[actor.actor.kind], code(actor.actor.actor_id), sources, quotes,
                           ", ".join(actor.requirements) or "nenhum"])
    if actor_rows:
        lines += table(["Ator", "Tipo", "actor_id", "Fonte", "Citação", "Requisitos ligados"], actor_rows)
    else:
        lines.append("Nenhum ator gravado.")
    lines.append("")
    if catalog.rejected_actors:
        lines += ["Atores propostos pelo modelo e não gravados no grafo:", ""]
        lines += table(["Ator", "Tipo", "Registro", "Fonte", "Motivo"], [
            [a.name, ACTOR_KIND[ActorKind(a.kind)], f"caso {code(a.case_id)}, chave {code(a.key)}", PENDING,
             f"{a.rejection.rule_id}: {REJECTION_RULES[a.rejection.rule_id]}"]
            for a in catalog.rejected_actors
        ]) + [""]

    lines += ["## 4. Requisitos específicos", ""]
    groups = [("Funcionais", functional), ("Não funcionais", nfr), ("Restrições", constraints),
              ("Tipo pendente", untyped)]
    lines += table(["Grupo", "Requisitos", "Em revisão humana"],
                   [[g, str(len(v)), str(sum(x.in_review for x in v))] for g, v in groups]
                   + [["Total", str(len(views)), str(sum(x.in_review for x in views))]]) + [""]
    lines += ["### 4.1 Requisitos funcionais", ""] + _group(functional, catalog, "####")
    lines += ["### 4.2 Requisitos não funcionais", "",
              "Cada requisito aparece uma vez, no primeiro dos seus atributos na ordem abaixo. O campo Atributos de "
              "qualidade lista todos.", ""]
    for number, category in enumerate(QualityCategory, start=1):
        members = [v for v in nfr if v.candidate.quality_attributes and v.candidate.quality_attributes[0] is category]
        lines += [f"#### 4.2.{number} {QUALITY[category]} ({code(category.value)})", ""]
        lines += _group(members, catalog, "#####")
    lines += [f"#### 4.2.{len(QualityCategory) + 1} Sem atributo de qualidade (C4)", ""]
    lines += _group([v for v in nfr if not v.candidate.quality_attributes], catalog, "#####")
    lines += ["### 4.3 Restrições", ""] + _group(constraints, catalog, "####")
    lines += ["### 4.4 Tipo pendente (C3)", ""] + _group(untyped, catalog, "####")

    lines += ["## 5. Verificação", ""]
    methods = Counter(v.candidate.verification_method for v in views)
    rows = [[METHOD[m], str(methods[m])] for m in VerificationMethod if methods[m]]
    rows.append([PENDING, str(methods[None])])
    lines += table(["Método de verificação", "Requisitos"], rows) + ["", f"Plano de verificação: {AUTHOR}", ""]
    lines += ["## Apêndice A. Rastreabilidade", "",
              "A matriz de proveniência está em `matriz_proveniencia.md` e `matriz_proveniencia.csv`. As lacunas "
              "estão em `relatorio_lacunas.md`, e a instância do ReqKG em `instancia_reqkg.json`.", ""]
    return "\n".join(lines)


# Instância


def instance_json(catalog: Catalog, command: str) -> str:
    instance = catalog.instance
    nodes, relations, digest = instance.logical_state()
    inputs = catalog.inputs
    data = {
        "format": "reqkg-instance/1",
        "origin": {
            "run_id": inputs.manifest.run_id, "condition": inputs.selection.condition.value,
            "run_index": inputs.selection.run_index, "cases": inputs.cases, "model_id": inputs.manifest.model_id,
            "replay": inputs.manifest.replay, "command": command,
            "inputs": {k: {"path": f.path, "sha256": f.sha256} for k, f in sorted(inputs.files.items())},
        },
        "logical_state": {"nodes": nodes, "relations": relations, "sha256": digest},
        "nodes": [{"label": label, "id": key, "properties": props} for label, key, props in instance.node_rows()],
        "relations": [{"type": kind, "source": {"label": a[0], "id": a[1]}, "target": {"label": b[0], "id": b[1]},
                       "properties": props} for kind, a, b, props in instance.relation_rows()],
    }
    return json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def instance_summary(catalog: Catalog, name: str, command: str) -> str:
    instance = catalog.instance
    nodes, relations, digest = instance.logical_state()
    lines = header(catalog, f"Instância parcial do ReqKG: {name}", command)
    lines += [
        "A instância é o que uma carga limpa da saída final desta condição gravaria no Neo4j. Cada caso passa por "
        "`domain.persist.to_records` sobre a saída final, e os casos são unidos em ordem de `case_id` pela regra de "
        "união do grafo (`graph.properties.merge_provenance`). Documentos e chunks vêm do conjunto de ingestão. "
        "Requisito refinado e aceito entra como revisão 1, com a declaração anterior e o identificador calculado "
        "da declaração original.", "",
        f"SHA-256 do estado lógico: {code(digest)}. É o mesmo valor que `graph.state.logical_state` calcula sobre o "
        "Neo4j depois de gravar estes registros num banco vazio.", "",
        "Os registros completos estão em `instancia_reqkg.json`.", "",
        "## Nós por classe", "",
    ]
    lines += table(["Classe ReqKG", "Rótulo no grafo", "Nós"],
                   [[pt, code(label), str(nodes.get(label, 0))] for label, pt in CLASSES]) + [""]
    lines += ["## Relações por tipo", ""]
    rows = []
    for relation in sorted(RelationType, key=lambda t: t.neo4j_type):
        source, target = (LABELS[k][0] for k in RELATION_ENDPOINTS[relation])
        rows.append([code(relation.value), code(relation.neo4j_type), f"{source} → {target}",
                     str(relations.get(relation.neo4j_type, 0))])
    rows += [["estrutural", code(CONTAINS), "SourceDocument → SourceChunk", str(relations.get(CONTAINS, 0))],
             ["estrutural", code(SUPPORTS), "SourceChunk → Requirement", str(relations.get(SUPPORTS, 0))]]
    lines += table(["Relação", "Tipo no grafo", "De → para", "Arestas"], rows) + [""]

    lines += ["## Origem dos registros com proveniência", "",
              "Fato extraído tem citação em toda evidência. Fato sem citação é gravado como inferência do sistema.", ""]
    origin_rows = []
    groups = [("Requirement", instance.requirements.values()), ("Actor", instance.actors.values()),
              ("SoftwareComponent", instance.components.values()), ("Entity", instance.entities.values())]
    for label, models in groups:
        counts = Counter(m.provenance.origin for m in models)
        origin_rows.append([code(label), *(str(counts[o]) for o in Origin)])
    counts = Counter(r.provenance.origin for r in instance.relations.values())
    origin_rows.append(["relações do contrato", *(str(counts[o]) for o in Origin)])
    lines += table(["Registro", *(ORIGIN[o] for o in Origin)], origin_rows) + [""]

    lines += ["## Requisitos por status", ""]
    status = Counter(r.status for r in instance.requirements.values())
    revised = sum(r.revision == 1 for r in instance.requirements.values())
    lines += table(["Status", "Requisitos"], [[f"{STATUS[s]} ({code(s.value)})", str(status[s])]
                                               for s in RequirementStatus])
    lines += ["", f"Requisitos na revisão 1 (refinamento aceito): {revised}.", "",
              "## Fora da instância", "",
              f"{len(instance.rejected)} recusa(s) na gravação (regras W) ficaram fora destes registros. A lista está "
              "em `relatorio_lacunas.md`.", ""]
    return "\n".join(lines)


# Matriz de proveniência

MATRIX_COLUMNS = ["requisito", "requirement_id", "caso", "chave", "documento", "caminho", "source_id", "chunk_id",
                  "indice_chunk", "citacao", "citacao_no_chunk"]


def matrix_rows(catalog: Catalog) -> list[list[str]]:
    labels = doc_labels(catalog)
    rows = []
    for view in catalog.requirements:
        base = [view.label, view.requirement_id or "", view.case_id, view.candidate.key]
        if not view.evidence:
            rows.append(base + ["", "", "", "", "", "", NO_EVIDENCE])
        for e in view.evidence:
            known = e.quote_status != OUTSIDE_CORPUS
            rows.append(base + [
                labels.get(e.evidence.source_id, "") if known else "", e.document.path if known else "",
                e.evidence.source_id, e.evidence.chunk_id, str(e.chunk.index) if known else "",
                e.evidence.quote or "", e.quote_status,
            ])
    return rows


def matrix_csv(catalog: Catalog) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(MATRIX_COLUMNS)
    writer.writerows(matrix_rows(catalog))
    return buffer.getvalue()


def matrix_md(catalog: Catalog, name: str, command: str) -> str:
    labels = doc_labels(catalog)
    documents = catalog.inputs.documents
    lines = header(catalog, f"Matriz de proveniência: {name}", command)
    lines += [
        "Uma linha por evidência citada pelo requisito na saída final. A coluna \"Citação no chunk\" confere a "
        "citação contra o texto do chunk com a normalização da regra P3 (NFC, espaços colapsados, sem diferença "
        f"de maiúsculas). Valores: \"{QUOTE_FOUND}\", \"{QUOTE_MISSING}\" (P3), \"{NO_QUOTE}\", "
        f"\"{OUTSIDE_CORPUS}\" (P2) e \"{NO_EVIDENCE}\" (P1). A mesma tabela está em `matriz_proveniencia.csv`.", "",
        "## Documentos", "",
    ]
    lines += table(["Documento", "Caminho", "Tipo"],
                   [[labels[d.source_id], code(d.path), code(d.kind.value)] for d in documents]) + [""]
    lines += ["## Requisito por documento", "",
              "Número de evidências do requisito em cada documento. \"—\" quando não há nenhuma.", ""]
    rows = []
    for view in catalog.requirements:
        cited = Counter(e.evidence.source_id for e in view.evidence if e.quote_status != OUTSIDE_CORPUS)
        outside = sum(e.quote_status == OUTSIDE_CORPUS for e in view.evidence)
        rows.append([view.label, *(str(cited[d.source_id]) if cited[d.source_id] else "—" for d in documents),
                     str(outside) if outside else "—", "sim" if not view.evidence else "—"])
    lines += table(["Requisito", *(labels[d.source_id] for d in documents), "Fora do corpus", "Sem evidência"],
                   rows) + [""]
    lines += ["## Detalhe por evidência", ""]
    detail = [[r[0], code(r[1]) if r[1] else PENDING, r[4] or "—", code(r[7]) if r[7] else "—", r[8] or "—",
               quoted(r[9]) if r[9] else "—", r[10]] for r in matrix_rows(catalog)]
    lines += table(["Requisito", "requirement_id", "Documento", "Chunk", "Índice", "Citação", "Citação no chunk"],
                   detail) + [""]
    return "\n".join(lines)


# Relatório de lacunas


def _items(lines: list[str], items: list[str]) -> None:
    lines.extend([f"- {item}" for item in items] or ["Nenhuma ocorrência."])
    lines.append("")


def gaps(catalog: Catalog, name: str, command: str) -> str:
    inputs = catalog.inputs
    violations = catalog.violations
    by_rule = Counter(v.violation.rule_id for v in violations)
    instance_w = Counter(r.rule_id for _, r in catalog.instance.rejected)
    review = [v for v in catalog.requirements if v.in_review]
    unquantified = [v for v in catalog.requirements if v.candidate.quality_attributes
                    and v.candidate.quantitative_value is None]
    failed_cases = [f for f in inputs.finals if f.status is not RunStatus.OK]
    refused = [(f.case_id, k) for f in inputs.finals for k in f.refused]

    lines = header(catalog, f"Relatório de lacunas: {name}", command)
    lines += [
        "As violações C, P e K são as de `domain.rules.check_all` sobre a saída final de cada caso, o mesmo ponto "
        "de medida das métricas. As recusas W são as de `domain.persist.to_records` ao montar a instância. As "
        "explicações das regras são as de `code/domain/schema/RULES.md`.", "",
        "## Resumo", "",
    ]
    rows = [[FAMILY[r.family], r.rule_id, r.description, str(by_rule[r.rule_id])] for r in RULES]
    rows += [["recusa na gravação", rule, text, str(instance_w[rule])] for rule, text in REJECTION_RULES.items()]
    lines += table(["Família", "Regra", "O que conta", "Ocorrências"], rows) + [""]
    lines += table(["Outras lacunas", "Ocorrências"], [
        ["Requisitos em revisão humana", str(len(review))],
        ["Atributos de qualidade sem valor quantitativo", str(len(unquantified))],
        ["Refinamentos recusados (regras G)", str(len(refused))],
        ["Casos sem saída nesta condição", str(len(failed_cases))],
    ]) + [""]

    for family, title in ((RuleFamily.COMPLETENESS, "Completude (C1 a C4)"),
                          (RuleFamily.PROVENANCE, "Proveniência (P1 a P5)"),
                          (RuleFamily.CONSISTENCY, "Consistência (K1 a K5)")):
        lines += [f"## {title}", ""]
        for rule in (r for r in RULES if r.family is family):
            lines += [f"### {rule.rule_id}. {rule.description}", ""]
            _items(lines, [f"{v.subject}: {v.violation.detail} (caso {code(v.case_id)})"
                           for v in violations if v.violation.rule_id == rule.rule_id])

    lines += ["## Recusas na gravação (W1 a W6)", "",
              "### Nesta instância", "",
              "Recusas de `to_records` sobre a saída final desta condição. O item recusado não está na instância.", ""]
    for rule, text in REJECTION_RULES.items():
        lines += [f"#### {rule}. {text}", ""]
        _items(lines, [f"{catalog.describe(case, r.subject)}: {r.detail} (caso {code(case)})"
                       for case, r in catalog.instance.rejected if r.rule_id == rule])
    lines += ["### Registradas pelo executor", ""]
    if inputs.rejections is None:
        lines += [f"{code(inputs.files['rejections'].path)} não existe nesta corrida.", ""]
    else:
        lines += [f"Recusas de {code(inputs.files['rejections'].path)} nesta repetição, da gravação da extração "
                  "compartilhada no grafo. Podem diferir das recusas acima, que partem da saída final depois do "
                  "refinamento. Os assuntos são chaves da extração compartilhada.", ""]
        _items(lines, [f"{r.rejection.rule_id}: {catalog.describe(r.case_id, r.rejection.subject)}: "
                       f"{r.rejection.detail} (caso {code(r.case_id)})" for r in inputs.rejections])

    lines += ["## Refinamento de uma passagem", ""]
    lines += table(["Caso", "Alvos", "Aceitos", "Recusados", "Chamada falhou", "Sem resultado registrado"], [
        [code(f.case_id), str(len(f.targets)), str(len(f.accepted)), str(len(f.refused)), str(len(f.failed)),
         str(len(set(f.targets) - set(f.accepted) - set(f.refused) - set(f.failed)))] for f in inputs.finals
    ]) + [""]
    lines += ["### Refinamentos recusados", "",
              "Com qualquer violação G, o sistema recusa o refinamento e mantém o candidato original.", ""]
    results = {(r.case_id, r.target_key): r for r in inputs.refinements}
    missing = "sem CaseResult de refinamento com essa chave"
    items = []
    for case, key in refused:
        result = results.get((case, key))
        found = [f"{v.rule_id} ({REFINEMENT_RULES.get(v.rule_id, 'regra desconhecida')}): {v.detail}"
                 for v in result.violations] if result else [missing]
        items.append(f"{catalog.describe(case, key)} (caso {code(case)}): {'; '.join(found)}")
    _items(lines, items)
    lines += ["### Chamadas de refinamento que falharam", "",
              "O candidato original fica. Alvos de `FinalRecord.failed`, com o erro do `CaseResult` do mesmo alvo:", ""]
    failures = []
    for f in inputs.finals:
        for key in f.failed:
            result = results.get((f.case_id, key))
            error = f"{code(result.status.value)}: {result.error}" if result else missing
            failures.append(f"{catalog.describe(f.case_id, key)} (caso {code(f.case_id)}): {error}")
    _items(lines, failures)

    lines += ["## Requisitos em revisão humana", "",
              "Candidato com baixa confiança (abaixo de `review.confidence_threshold`, "
              f"{inputs.confidence_threshold}) ou tipo ambíguo. Fica em `needs_review` e não é descartado.", ""]
    _items(lines, [f"{v.label}: {quoted(v.candidate.statement)}. Motivo: "
                   f"{_review_reason(v, inputs.confidence_threshold)}" for v in review])
    lines += ["## Atributos de qualidade sem valor quantitativo", "",
              "Requisito com atributo de qualidade e sem `quantitative_value`. A expressão vaga foi normalizada para "
              "a categoria, e o valor fica para refinamento.", ""]
    _items(lines, [f"{v.label}: {', '.join(QUALITY[q].lower() for q in v.candidate.quality_attributes)}. "
                   f"Valor quantitativo {PENDING}. Marca de valor pendente: "
                   f"{'sim' if ReviewFlag.QUANTITATIVE_VALUE_PENDING in v.flags else 'não'}" for v in unquantified])
    lines += ["## Casos sem saída nesta condição", "",
              "Caso inválido conta como zero requisito gerado. Nenhum artefato acima tem requisito dele.", ""]
    _items(lines, [f"{code(f.case_id)}: {code(f.status.value)}" for f in failed_cases])
    lines += ["## Limitações observadas", "",
              "Espaço do autor. O gerador não escreve nesta seção.", "",
              f"- O que o grafo não conseguiu representar: {AUTHOR}",
              f"- Requisitos que a fonte não sustenta: {AUTHOR}",
              f"- Outras observações: {AUTHOR}", ""]
    return "\n".join(lines)


def render_all(catalog: Catalog, name: str, command: str) -> dict[str, str]:
    return {
        "srs.md": srs(catalog, name, command),
        "instancia_reqkg.json": instance_json(catalog, command),
        "instancia_resumo.md": instance_summary(catalog, name, command),
        "matriz_proveniencia.csv": matrix_csv(catalog),
        "matriz_proveniencia.md": matrix_md(catalog, name, command),
        "relatorio_lacunas.md": gaps(catalog, name, command),
    }
