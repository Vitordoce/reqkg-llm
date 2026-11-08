"""Formato e validação da amostra de referência anotada à mão.

O protocolo está em instructions/PROTOCOLO_ANOTACAO.md. Uso, a partir da raiz do repositório:

    PYTHONPATH=code .venv/bin/python -m experiments.annotation data/raw/amostra
"""

import argparse
import hashlib
import re
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, TypeAdapter, ValidationError

from domain.config import ContractError, ExperimentConfig
from domain.enums import (
    RELATION_ENDPOINTS,
    NodeKind,
    Priority,
    QualityCategory,
    RelationType,
    RequirementType,
    SourceKind,
    VerificationMethod,
)
from domain.llm_io import CitedEvidence
from domain.models import ContractModel, NonEmpty
from domain.rules import CorpusIndex, strongly_connected
from domain.serialization import load_toml

PROTOCOL_VERSION = "1"
REFERENCE_FILE = "referencia.toml"
MARKER = "Artefato sintético"
CONFIG_PATH = Path(__file__).parent / "config" / "experiment.toml"

# Faixas da seção "Tamanho" do protocolo. Mudá-las exige mudar o protocolo antes da anotação.
ARTIFACT_RANGE = range(6, 9)
REQUIREMENT_RANGE = range(50, 71)
MIN_PER_QUALITY_ATTRIBUTE = 2

ArtifactId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
RequirementId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}-R\d{2}$")]
# O mesmo limite de CitedEvidence.quote: o modelo não consegue citar um trecho maior.
Quote = Annotated[str, StringConstraints(min_length=1, max_length=1000, strip_whitespace=True)]
Notes = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]

REQUIREMENT_TO_REQUIREMENT = frozenset(
    t for t, ends in RELATION_ENDPOINTS.items() if ends == (NodeKind.REQUIREMENT, NodeKind.REQUIREMENT)
)


class Artifact(ContractModel):
    id: ArtifactId
    kind: SourceKind
    title: NonEmpty
    notes: Notes | None = None


class ReferenceRequirement(ContractModel):
    id: RequirementId
    artifact: ArtifactId
    statement: Annotated[str, StringConstraints(min_length=1, max_length=2000, strip_whitespace=True)]
    type: RequirementType
    quote: Quote
    priority: Priority | None = None
    priority_quote: Quote | None = None
    verification_method: VerificationMethod | None = None
    verification_quote: Quote | None = None
    quality_attributes: list[QualityCategory] = Field(default_factory=list)
    notes: Notes | None = None


class ReferenceRelation(ContractModel):
    type: RelationType
    source: RequirementId
    target: RequirementId
    quote: Quote
    notes: Notes | None = None


class ReferenceFile(ContractModel):
    protocol_version: Literal["1"]
    artifact: list[dict] = Field(min_length=1)
    requirement: list[dict] = Field(min_length=1)
    relation: list[dict] = Field(default_factory=list)


class Reference(ContractModel):
    protocol_version: Literal["1"]
    artifacts: list[Artifact]
    requirements: list[ReferenceRequirement]
    relations: list[ReferenceRelation] = Field(default_factory=list)


Level = Literal["erro", "alerta"]


@dataclass(frozen=True, order=True)
class Finding:
    level: Level
    file: str
    subject: str
    field: str | None
    message: str

    def __str__(self) -> str:
        where = f"{self.file}: {self.subject}"
        if self.field:
            where += f": campo {self.field}"
        return f"{where}: {self.message}"


@dataclass
class ArtifactText:
    text: str
    paragraphs: list[str]
    sha256: str


@dataclass
class Report:
    directory: Path
    findings: list[Finding] = field(default_factory=list)
    reference: Reference | None = None
    texts: dict[str, ArtifactText] = field(default_factory=dict)
    hashes: dict[str, str] = field(default_factory=dict)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "erro"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "alerta"]

    def add(self, level: Level, file: str, subject: str, field_name: str | None, message: str) -> None:
        self.findings.append(Finding(level, file, subject, field_name, message))


def split_paragraphs(text: str) -> tuple[str, list[str]]:
    """Primeira linha (marcação) e parágrafos do corpo, separados por linha em branco."""
    first, _, body = text.replace("\r\n", "\n").partition("\n")
    paragraphs = [p.strip() for p in re.split(r"\n[ \t]*\n", body) if p.strip()]
    return first, paragraphs


def quote_paragraphs(artifact_id: str, paragraphs: list[str], quote: str) -> list[int]:
    """Índices dos parágrafos que contêm a citação, pela mesma comparação que a regra P3 usa."""
    keys = [f"p{i}" for i in range(len(paragraphs))]
    index = CorpusIndex(chunk_text=dict(zip(keys, paragraphs)), chunk_source=dict.fromkeys(keys, artifact_id))
    return [
        i for i, key in enumerate(keys)
        if index.quote_found(CitedEvidence(source_id=artifact_id, chunk_id=key, quote=quote))
    ]


def _parse_items(raw: list, model: type, kind: str, report: Report) -> list:
    parsed = []
    for position, item in enumerate(raw, start=1):
        item_id = item.get("id") if isinstance(item, dict) else None
        subject = f"{kind} {item_id}" if isinstance(item_id, str) else f"{kind} #{position}"
        try:
            parsed.append(TypeAdapter(model).validate_python(item))
        except ValidationError as error:
            for e in error.errors():
                location = ".".join(str(part) for part in e["loc"]) or None
                report.add("erro", REFERENCE_FILE, subject, location, e["msg"])
    return parsed


def _check_unique(ids: list[str], kind: str, report: Report) -> None:
    for item_id, count in sorted(Counter(ids).items()):
        if count > 1:
            report.add("erro", REFERENCE_FILE, f"{kind} {item_id}", "id", f"identificador repetido {count} vezes")


def _read_artifacts(declared: set[str], report: Report, size_chars: int) -> None:
    for path in sorted(report.directory.glob("*.txt")):
        if path.stem not in declared:
            report.add("erro", path.name, "arquivo", None, f"artefato não declarado em {REFERENCE_FILE}")
    for artifact_id in sorted(declared):
        name = f"{artifact_id}.txt"
        path = report.directory / name
        if not path.is_file():
            report.add("erro", REFERENCE_FILE, f"artefato {artifact_id}", "id", f"{name} não existe")
            continue
        data = path.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            report.add("erro", name, "arquivo", None, f"não é UTF-8 (byte {error.start})")
            continue
        first, paragraphs = split_paragraphs(text)
        if not first.startswith(MARKER):
            report.add("erro", name, "linha 1", None, f"a primeira linha tem de começar com {MARKER!r}")
        if not paragraphs:
            report.add("erro", name, "arquivo", None, "sem texto depois da linha de marcação")
        for i, paragraph in enumerate(paragraphs, start=1):
            if len(paragraph) > size_chars:
                report.add(
                    "alerta", name, f"parágrafo {i}", None,
                    f"{len(paragraph)} caracteres passam de chunking.size_chars ({size_chars}); "
                    "a ingestão pode cortar o parágrafo e separar uma citação",
                )
        report.texts[artifact_id] = ArtifactText(text, paragraphs, hashlib.sha256(data).hexdigest())


def _check_quote(report: Report, subject: str, field_name: str, artifact_id: str, quote: str) -> None:
    source = report.texts.get(artifact_id)
    if source is None:
        return
    found = quote_paragraphs(artifact_id, source.paragraphs, quote)
    if not found:
        whole = quote_paragraphs(artifact_id, ["\n\n".join(source.paragraphs)], quote)
        message = (
            f"citação atravessa parágrafos de {artifact_id}.txt; com chunking por parágrafo ela pode cair em dois chunks"
            if whole else f"citação não aparece literalmente em {artifact_id}.txt"
        )
        report.add("erro", REFERENCE_FILE, subject, field_name, message)
    elif len(found) > 1:
        where = ", ".join(str(i + 1) for i in found)
        report.add("alerta", REFERENCE_FILE, subject, field_name, f"citação aparece nos parágrafos {where} de {artifact_id}.txt")


def _check_requirement(r: ReferenceRequirement, declared: set[str], report: Report) -> None:
    subject = f"requisito {r.id}"
    if r.artifact not in declared:
        report.add("erro", REFERENCE_FILE, subject, "artifact", f"artefato {r.artifact!r} não declarado")
        return
    if not r.id.startswith(f"{r.artifact}-R"):
        report.add("erro", REFERENCE_FILE, subject, "id", f"tem de começar com '{r.artifact}-R'")
    _check_quote(report, subject, "quote", r.artifact, r.quote)
    for value, quote, value_field, quote_field in (
        (r.priority, r.priority_quote, "priority", "priority_quote"),
        (r.verification_method, r.verification_quote, "verification_method", "verification_quote"),
    ):
        if value is not None and quote is None:
            report.add("erro", REFERENCE_FILE, subject, quote_field, f"{value_field} preenchido sem a citação que o sustenta")
        elif value is None and quote is not None:
            report.add("erro", REFERENCE_FILE, subject, value_field, f"{quote_field} presente com {value_field} vazio")
        elif quote is not None:
            _check_quote(report, subject, quote_field, r.artifact, quote)
    if len(set(r.quality_attributes)) != len(r.quality_attributes):
        report.add("erro", REFERENCE_FILE, subject, "quality_attributes", "atributo repetido")
    if r.type is RequirementType.NON_FUNCTIONAL and not r.quality_attributes:
        report.add("erro", REFERENCE_FILE, subject, "quality_attributes", "não funcional sem atributo de qualidade (regra C4)")
    if r.type is RequirementType.FUNCTIONAL and r.quality_attributes:
        report.add("alerta", REFERENCE_FILE, subject, "quality_attributes", "funcional com atributo de qualidade; confira o tipo")


def _check_relations(reference: Reference, report: Report) -> None:
    by_id = {r.id: r for r in reference.requirements}
    pairs: dict[RelationType, set[tuple[str, str]]] = {t: set() for t in RelationType}
    for position, rel in enumerate(reference.relations, start=1):
        subject = f"relação #{position} ({rel.source} {rel.type.value} {rel.target})"
        if rel.type not in REQUIREMENT_TO_REQUIREMENT:
            allowed = ", ".join(sorted(t.value for t in REQUIREMENT_TO_REQUIREMENT))
            report.add("erro", REFERENCE_FILE, subject, "type", f"só entram relações entre requisitos: {allowed}")
            continue
        missing = [end for end in (rel.source, rel.target) if end not in by_id]
        for end in missing:
            report.add("erro", REFERENCE_FILE, subject, "source" if end == rel.source else "target", f"requisito {end} não existe")
        if missing:
            continue
        if rel.source == rel.target:
            report.add("erro", REFERENCE_FILE, subject, "target", "relação do requisito com ele mesmo (regra K2)")
            continue
        artifacts = sorted({by_id[rel.source].artifact, by_id[rel.target].artifact})
        if set(artifacts) <= report.texts.keys() and not any(quote_paragraphs(a, report.texts[a].paragraphs, rel.quote) for a in artifacts):
            names = " ou ".join(f"{a}.txt" for a in artifacts)
            report.add("erro", REFERENCE_FILE, subject, "quote", f"citação não aparece num parágrafo de {names}")
        pair = (rel.source, rel.target)
        pairs[rel.type].add(tuple(sorted(pair)) if rel.type in (RelationType.CONFLICTS_WITH, RelationType.DUPLICATES) else pair)
        if (
            rel.type is RelationType.DEPENDS_ON
            and by_id[rel.source].priority is Priority.MUST
            and by_id[rel.target].priority is Priority.WONT
        ):
            report.add("erro", REFERENCE_FILE, subject, "type", "must depende de wont (regra K5)")
    for a, b in sorted(pairs[RelationType.CONFLICTS_WITH] & pairs[RelationType.DUPLICATES]):
        report.add("erro", REFERENCE_FILE, f"par {a}|{b}", "type", "conflicts_with e duplicates no mesmo par (regra K1)")
    for relation_type, rule in ((RelationType.DEPENDS_ON, "K3"), (RelationType.REFINES, "K4")):
        for members in strongly_connected(pairs[relation_type]):
            report.add("erro", REFERENCE_FILE, ",".join(members), "type", f"ciclo em {relation_type.value} (regra {rule})")


def _check_totals(reference: Reference, report: Report) -> None:
    def outside(value: int, allowed: range, what: str) -> None:
        if value not in allowed:
            report.add(
                "alerta", REFERENCE_FILE, "(amostra)", None,
                f"{what}: {value}, fora da faixa {allowed.start} a {allowed.stop - 1} do protocolo",
            )

    outside(len(reference.artifacts), ARTIFACT_RANGE, "artefatos")
    outside(len(reference.requirements), REQUIREMENT_RANGE, "requisitos de referência")
    per_artifact = Counter(r.artifact for r in reference.requirements)
    for artifact in reference.artifacts:
        if not per_artifact[artifact.id]:
            report.add("alerta", REFERENCE_FILE, f"artefato {artifact.id}", None, "nenhum requisito de referência")
    kinds = {a.kind for a in reference.artifacts}
    for kind in SourceKind:
        if kind not in kinds:
            report.add("alerta", REFERENCE_FILE, "(amostra)", None, f"nenhum artefato do tipo {kind.value}")
    types = Counter(r.type for r in reference.requirements)
    for requirement_type in RequirementType:
        if not types[requirement_type]:
            report.add("alerta", REFERENCE_FILE, "(amostra)", None, f"nenhum requisito do tipo {requirement_type.value}")
    attributes = Counter(a for r in reference.requirements for a in r.quality_attributes)
    for attribute in QualityCategory:
        if attributes[attribute] < MIN_PER_QUALITY_ATTRIBUTE:
            report.add(
                "alerta", REFERENCE_FILE, "(amostra)", None,
                f"atributo {attribute.value} em {attributes[attribute]} requisito(s), menos que {MIN_PER_QUALITY_ATTRIBUTE}",
            )
    statements = Counter(" ".join(r.statement.casefold().split()) for r in reference.requirements)
    for r in reference.requirements:
        if statements[" ".join(r.statement.casefold().split())] > 1:
            report.add("alerta", REFERENCE_FILE, f"requisito {r.id}", "statement", "declaração idêntica à de outro requisito")


def validate_sample(directory: Path, config_path: Path = CONFIG_PATH) -> Report:
    report = Report(Path(directory))
    size_chars = load_toml(config_path, ExperimentConfig).chunking.size_chars
    reference_path = report.directory / REFERENCE_FILE
    if not reference_path.is_file():
        report.add("erro", REFERENCE_FILE, "arquivo", None, f"não existe em {report.directory}")
        return report
    data = reference_path.read_bytes()
    report.hashes[REFERENCE_FILE] = hashlib.sha256(data).hexdigest()
    try:
        raw = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        report.add("erro", REFERENCE_FILE, "arquivo", None, f"TOML inválido: {error}")
        return report
    try:
        header = ReferenceFile.model_validate(raw)
    except ValidationError as error:
        for e in error.errors():
            report.add("erro", REFERENCE_FILE, "arquivo", ".".join(str(p) for p in e["loc"]) or None, e["msg"])
        return report

    artifacts = _parse_items(header.artifact, Artifact, "artefato", report)
    requirements = _parse_items(header.requirement, ReferenceRequirement, "requisito", report)
    relations = _parse_items(header.relation, ReferenceRelation, "relação", report)
    _check_unique([a.id for a in artifacts], "artefato", report)
    _check_unique([r.id for r in requirements], "requisito", report)
    # Um artefato com campo inválido continua declarado, para o erro não se repetir nos requisitos.
    declared = {i["id"] for i in header.artifact if isinstance(i, dict) and isinstance(i.get("id"), str)}
    _read_artifacts(declared, report, size_chars)
    for artifact_id, source in sorted(report.texts.items()):
        report.hashes[f"{artifact_id}.txt"] = source.sha256

    for requirement in requirements:
        _check_requirement(requirement, declared, report)
    reference = Reference(
        protocol_version=header.protocol_version, artifacts=artifacts, requirements=requirements, relations=relations
    )
    _check_relations(reference, report)
    _check_totals(reference, report)
    if len(artifacts) == len(header.artifact) and len(requirements) == len(header.requirement) and len(relations) == len(header.relation):
        report.reference = reference
    report.findings.sort()
    return report


def load_sample(directory: Path) -> tuple[Reference, dict[str, ArtifactText]]:
    """Referência e textos de uma amostra sem erros. Alertas não impedem a leitura."""
    report = validate_sample(directory)
    if report.errors or report.reference is None:
        lines = [f"{directory}: {len(report.errors)} erro(s) na amostra de referência"]
        lines += [f"  {f}" for f in report.errors]
        raise ContractError("\n".join(lines))
    return report.reference, report.texts


def _counts(values: Counter, keys) -> str:
    return " | ".join(f"{k.value} {values[k]}" for k in keys)


def render(report: Report) -> str:
    lines = [f"Amostra: {report.directory}"]
    reference = report.reference
    if reference is not None:
        total = len(reference.requirements)
        per_artifact = Counter(r.artifact for r in reference.requirements)
        lines += ["", f"Artefatos ({len(reference.artifacts)})"]
        for a in reference.artifacts:
            source = report.texts.get(a.id)
            size = f"{len(source.paragraphs)} parágrafos, {len(source.text)} caracteres" if source else "sem texto"
            lines.append(f"  {a.id:<10} {a.kind.value:<28} {size}, {per_artifact[a.id]} requisitos")
        lines += [
            "",
            f"Requisitos de referência: {total}",
            "  por tipo: " + _counts(Counter(r.type for r in reference.requirements), RequirementType),
            "  por atributo: " + _counts(
                Counter(q for r in reference.requirements for q in r.quality_attributes), QualityCategory
            ),
            f"  com prioridade sustentada pelo texto: {sum(r.priority is not None for r in reference.requirements)} de {total}",
            f"  com método de verificação sustentado: {sum(r.verification_method is not None for r in reference.requirements)} de {total}",
            f"Relações esperadas: {len(reference.relations)}",
        ]
    if report.hashes:
        lines += ["", "SHA-256"] + [f"  {digest}  {name}" for name, digest in sorted(report.hashes.items())]
    for title, items in (("Alertas", report.warnings), ("Erros", report.errors)):
        lines += ["", f"{title} ({len(items)})"] + [f"  {f}" for f in items]
    verdict = "inválida" if report.errors else "válida"
    lines += ["", f"Resultado: amostra {verdict}, {len(report.errors)} erro(s) e {len(report.warnings)} alerta(s)"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valida a amostra de referência anotada.")
    parser.add_argument("directory", type=Path, help=f"pasta com os artefatos <id>.txt e {REFERENCE_FILE}")
    args = parser.parse_args(argv)
    if not args.directory.is_dir():
        print(f"erro: {args.directory} não é uma pasta", file=sys.stderr)
        return 2
    report = validate_sample(args.directory)
    print(render(report))
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
