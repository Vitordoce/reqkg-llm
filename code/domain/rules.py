"""Regras de completude, proveniência e consistência, fixadas antes do experimento.

As duas condições são avaliadas sobre um ExtractionOutput. As consultas Cypher do grafo
devem contar as mesmas violações que estas funções contam.
"""

import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum

from domain.enums import Origin, Priority, RelationType, RequirementType
from domain.llm_io import CitedEvidence, ExtractionOutput, RequirementCandidate
from domain.models import SourceChunk
from domain.violations import Violation

RULES_VERSION = "3"


class RuleFamily(StrEnum):
    COMPLETENESS = "completeness"
    PROVENANCE = "provenance"
    CONSISTENCY = "consistency"


@dataclass(frozen=True)
class CorpusIndex:
    chunk_text: dict[str, str]
    chunk_source: dict[str, str]

    @classmethod
    def from_chunks(cls, chunks: Iterable[SourceChunk]) -> "CorpusIndex":
        chunks = list(chunks)
        return cls(
            chunk_text={c.chunk_id: c.text for c in chunks},
            chunk_source={c.chunk_id: c.source_id for c in chunks},
        )

    def resolves(self, evidence: CitedEvidence) -> bool:
        return self.chunk_source.get(evidence.chunk_id) == evidence.source_id

    def quote_found(self, evidence: CitedEvidence) -> bool:
        return _squash(evidence.quote or "") in _squash(self.chunk_text[evidence.chunk_id])

    def supports(self, evidence: CitedEvidence) -> bool:
        """Resolve no corpus e, se houver citação, ela aparece no chunk. É o que pode ir ao grafo."""
        return self.resolves(evidence) and (evidence.quote is None or self.quote_found(evidence))


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


def normalize_text(text: str) -> str:
    """A normalização que P3 usa para comparar citação e chunk: NFC, espaços colapsados, caixa."""
    return _squash(text)


Check = Callable[[ExtractionOutput, CorpusIndex], list[Violation]]


@dataclass(frozen=True)
class Rule:
    rule_id: str
    family: RuleFamily
    description: str
    check: Check


def _missing(field: str, rule_id: str) -> Check:
    def check(output: ExtractionOutput, corpus: CorpusIndex) -> list[Violation]:
        return [
            Violation(rule_id, r.key, f"{field} ausente")
            for r in output.requirements
            if getattr(r, field) is None
        ]

    return check


def _nfr_without_quality(output: ExtractionOutput, corpus: CorpusIndex) -> list[Violation]:
    return [
        Violation("C4", r.key, "não funcional sem atributo de qualidade")
        for r in output.requirements
        if r.type is RequirementType.NON_FUNCTIONAL and not r.quality_attributes
    ]


def _requirement_without_evidence(output: ExtractionOutput, corpus: CorpusIndex) -> list[Violation]:
    return [Violation("P1", r.key, "sem evidência") for r in output.requirements if not r.evidence]


def _all_evidence(output: ExtractionOutput) -> Iterable[tuple[str, CitedEvidence]]:
    for collection in (output.requirements, output.actors, output.components, output.entities):
        for item in collection:
            for evidence in item.evidence:
                yield item.key, evidence
    for index, relation in enumerate(output.relations):
        for evidence in relation.evidence:
            yield f"relations.{index}", evidence


def _unresolved_evidence(output: ExtractionOutput, corpus: CorpusIndex) -> list[Violation]:
    return [
        Violation("P2", subject, f"{e.source_id}/{e.chunk_id} não existe no corpus")
        for subject, e in _all_evidence(output)
        if not corpus.resolves(e)
    ]


def _quote_not_in_chunk(output: ExtractionOutput, corpus: CorpusIndex) -> list[Violation]:
    violations = []
    for subject, e in _all_evidence(output):
        if e.quote is None or not corpus.resolves(e):
            continue
        if not corpus.quote_found(e):
            violations.append(Violation("P3", subject, f"citação não aparece em {e.chunk_id}"))
    return violations


def _fact_without_quote(output: ExtractionOutput, corpus: CorpusIndex) -> list[Violation]:
    def unquoted(item) -> bool:
        return item.origin is Origin.EXTRACTED_FACT and item.evidence and any(e.quote is None for e in item.evidence)

    found = [Violation("P4", r.key, "fato extraído sem citação") for r in output.requirements if unquoted(r)]
    found += [
        Violation("P4", f"relations.{i}", "fato extraído sem citação")
        for i, r in enumerate(output.relations)
        if unquoted(r)
    ]
    return found


def _relation_without_evidence(output: ExtractionOutput, corpus: CorpusIndex) -> list[Violation]:
    return [
        Violation("P5", f"relations.{i}", f"{r.type.value} sem evidência")
        for i, r in enumerate(output.relations)
        if not r.evidence
    ]


def _pair(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((a, b)))


def _conflict_and_duplicate(output: ExtractionOutput, corpus: CorpusIndex) -> list[Violation]:
    by_type: dict[RelationType, set[tuple[str, str]]] = defaultdict(set)
    for r in output.relations:
        by_type[r.type].add(_pair(r.source_key, r.target_key))
    both = by_type[RelationType.CONFLICTS_WITH] & by_type[RelationType.DUPLICATES]
    return [Violation("K1", f"{a}|{b}", "conflicts_with e duplicates no mesmo par") for a, b in sorted(both)]


def _self_relation(output: ExtractionOutput, corpus: CorpusIndex) -> list[Violation]:
    return [
        Violation("K2", f"relations.{i}", f"{r.type.value} de {r.source_key} para ele mesmo")
        for i, r in enumerate(output.relations)
        if r.source_key == r.target_key
    ]


def strongly_connected(edges: Iterable[tuple[str, str]]) -> list[tuple[str, ...]]:
    """Componentes fortemente conexos com dois ou mais nós, cada um com os membros ordenados."""
    graph: dict[str, set[str]] = defaultdict(set)
    for source, target in edges:
        graph[source].add(target)
        graph.setdefault(target, set())

    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    components: list[tuple[str, ...]] = []

    for root in sorted(graph):
        if root in index:
            continue
        work = [(root, iter(sorted(graph[root])))]
        index[root] = low[root] = len(index)
        stack.append(root)
        on_stack.add(root)
        while work:
            node, children = work[-1]
            child = next(children, None)
            if child is None:
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
                if low[node] == index[node]:
                    members = []
                    while True:
                        member = stack.pop()
                        on_stack.discard(member)
                        members.append(member)
                        if member == node:
                            break
                    if len(members) > 1:
                        components.append(tuple(sorted(members)))
            elif child not in index:
                index[child] = low[child] = len(index)
                stack.append(child)
                on_stack.add(child)
                work.append((child, iter(sorted(graph[child]))))
            elif child in on_stack:
                low[node] = min(low[node], index[child])
    return sorted(components)


def _cycles(output: ExtractionOutput, relation: RelationType, rule_id: str) -> list[Violation]:
    edges = [(r.source_key, r.target_key) for r in output.relations if r.type is relation and r.source_key != r.target_key]
    return [
        Violation(rule_id, ",".join(members), f"ciclo em {relation.value}")
        for members in strongly_connected(edges)
    ]


def _must_depends_on_wont(output: ExtractionOutput, corpus: CorpusIndex) -> list[Violation]:
    priority: dict[str, Priority | None] = {r.key: r.priority for r in output.requirements}
    return [
        Violation("K5", f"{r.source_key}->{r.target_key}", "must depende de wont")
        for r in output.relations
        if r.type is RelationType.DEPENDS_ON
        and priority.get(r.source_key) is Priority.MUST
        and priority.get(r.target_key) is Priority.WONT
    ]


RULES: tuple[Rule, ...] = (
    Rule("C1", RuleFamily.COMPLETENESS, "Requisito sem prioridade MoSCoW.", _missing("priority", "C1")),
    Rule("C2", RuleFamily.COMPLETENESS, "Requisito sem método de verificação.", _missing("verification_method", "C2")),
    Rule("C3", RuleFamily.COMPLETENESS, "Requisito sem tipo (funcional, não funcional ou restrição).", _missing("type", "C3")),
    Rule("C4", RuleFamily.COMPLETENESS, "Requisito não funcional sem atributo de qualidade ISO/IEC 25010.", _nfr_without_quality),
    Rule("P1", RuleFamily.PROVENANCE, "Requisito sem nenhuma evidência (fonte e chunk).", _requirement_without_evidence),
    Rule("P2", RuleFamily.PROVENANCE, "Evidência cita fonte ou chunk que não existe no corpus, ou chunk de outra fonte.", _unresolved_evidence),
    Rule("P3", RuleFamily.PROVENANCE, "Citação da evidência não aparece no texto do chunk citado.", _quote_not_in_chunk),
    Rule("P4", RuleFamily.PROVENANCE, "Requisito ou relação marcado como fato extraído com evidência sem citação.", _fact_without_quote),
    Rule("P5", RuleFamily.PROVENANCE, "Relação sem evidência.", _relation_without_evidence),
    Rule("K1", RuleFamily.CONSISTENCY, "O mesmo par de requisitos aparece como conflicts_with e duplicates.", _conflict_and_duplicate),
    Rule("K2", RuleFamily.CONSISTENCY, "Relação de um elemento com ele mesmo.", _self_relation),
    Rule("K3", RuleFamily.CONSISTENCY, "Ciclo em depends_on. Uma violação por componente fortemente conexo.", lambda o, c: _cycles(o, RelationType.DEPENDS_ON, "K3")),
    Rule("K4", RuleFamily.CONSISTENCY, "Ciclo em refines. Uma violação por componente fortemente conexo.", lambda o, c: _cycles(o, RelationType.REFINES, "K4")),
    Rule("K5", RuleFamily.CONSISTENCY, "Requisito Must depende de requisito Won't.", _must_depends_on_wont),
)


def check_all(output: ExtractionOutput, corpus: CorpusIndex) -> list[Violation]:
    return sorted(v for rule in RULES for v in rule.check(output, corpus))


REFINEMENT_TRIGGERS = frozenset({"C1", "C2", "C3", "C4", "P1", "P2", "P3", "P4"})


def refinement_targets(
    output: ExtractionOutput, corpus: CorpusIndex, confidence_threshold: float
) -> list[str]:
    """Chaves dos candidatos refinados, iguais nas duas condições porque vêm da extração compartilhada."""
    flagged = {v.subject for v in check_all(output, corpus) if v.rule_id in REFINEMENT_TRIGGERS}
    for r in output.requirements:
        if r.review_flags or (r.confidence is not None and r.confidence < confidence_threshold):
            flagged.add(r.key)
    return sorted(key for key in flagged if key in {r.key for r in output.requirements})


def is_complete(requirement: RequirementCandidate, corpus: CorpusIndex) -> bool:
    """Campos obrigatórios do esqueleto ISO/IEC/IEEE 29148 usados na razão de completude."""
    return (
        requirement.type is not None
        and requirement.priority is not None
        and requirement.verification_method is not None
        and any(corpus.resolves(e) for e in requirement.evidence)
    )
