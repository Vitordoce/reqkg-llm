"""Pareamento com a amostra de referência, em duas etapas (instructions/PROTOCOLO_ANOTACAO.md, seções 8 e 9).

Etapa 1, mecânica: um requisito gerado só pode parear com uma referência do mesmo caso cuja citação
aparece, pela comparação da regra P3, num dos chunks da chamada de extração que o produziu. O prefixo
da chave na saída final (c0, c1, ...) diz a chamada; o refinado herda a chave do candidato.

Etapa 2, humana e cega: uma planilha por corrida, com códigos sorteados por evaluation.seed e pelo
número da corrida. Declarações iguais do mesmo caso, depois da normalização da regra P3, e com as
mesmas candidatas aparecem uma vez só, venham de uma condição ou das duas. A chave que liga código a
condição e chave fica em key/. Antes de abrir a chave, `lock` grava o SHA-256 da planilha preenchida;
depois disso a planilha não muda, e erro achado mais tarde entra no arquivo de correções.
"""

import hashlib
import json
import random
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from domain.config import ContractError
from domain.enums import Condition, RunStatus
from domain.llm_io import CitedEvidence
from domain.rules import CorpusIndex
from domain.rules import normalize_text as p3_normalize
from experiments.annotation import Reference, ReferenceRequirement
from experiments.metrics.loading import Corpus, Run

NONE = "nenhum"
SHEET_FORMAT = "reqkg-pairing-sheet/1"
KEY_FORMAT = "reqkg-pairing-key/1"
LOCK_FORMAT = "reqkg-pairing-lock/1"
CODE_ALPHABET = "ACDEFHJKLMNPQRTUVWXY34679"
CODE_LENGTH = 4


def pairing_dir(run_dir: Path) -> Path:
    return Path(run_dir) / "metrics" / "pairing"


def sheet_path(run_dir: Path, run_index: int) -> Path:
    return pairing_dir(run_dir) / f"sheet_run{run_index}.toml"


def key_path(run_dir: Path, run_index: int) -> Path:
    return pairing_dir(run_dir) / "key" / f"key_run{run_index}.json"


def lock_path(run_dir: Path, run_index: int) -> Path:
    return pairing_dir(run_dir) / f"lock_run{run_index}.json"


def corrections_path(run_dir: Path, run_index: int) -> Path:
    return pairing_dir(run_dir) / f"corrections_run{run_index}.toml"


def quote_in_chunk(corpus: CorpusIndex, chunk_id: str, quote: str) -> bool:
    if chunk_id not in corpus.chunk_text:
        return False
    return corpus.quote_found(CitedEvidence(source_id=corpus.chunk_source[chunk_id], chunk_id=chunk_id, quote=quote))


def check_artifact_texts(text_sha256: dict[str, str], corpus: Corpus) -> None:
    """O artefato da referência e o documento ingerido de mesmo nome têm o mesmo texto (SHA-256 do texto
    normalizado pela ingestão). O nome sozinho pareia um aNN.txt com outro arquivo de mesmo nome."""
    differ = []
    for artifact, digest in sorted(text_sha256.items()):
        document = corpus.document_for(artifact, "artefato da referência")
        if document.sha256 != digest:
            differ.append(f"{artifact}.txt (texto {digest[:12]}) e {document.path} (texto {document.sha256[:12]})")
    if differ:
        raise ContractError(
            "artefato da referência e documento ingerido com o mesmo nome e textos diferentes: " + "; ".join(differ)
            + ". A referência foi anotada sobre outro texto; ingira os arquivos da própria pasta da amostra, ou "
            "confira qual versão é a certa antes de parear")


def references_by_case(reference: Reference, corpus: Corpus, case_ids: list[str]) -> dict[str, list[ReferenceRequirement]]:
    """Referências de cada caso. Caso e artefato se ligam pelo mesmo documento da ingestão."""
    case_document = {case: corpus.document_for(case, "caso").source_id for case in case_ids}
    artifact_document = {a.id: corpus.document_for(a.id, "artefato da referência").source_id for a in reference.artifacts}
    orphans = sorted(a for a, doc in artifact_document.items() if doc not in case_document.values())
    if orphans:
        raise ContractError(f"artefatos da referência sem caso na corrida: {', '.join(orphans)}")
    return {
        case: [r for r in reference.requirements if artifact_document[r.artifact] == document]
        for case, document in case_document.items()
    }


@dataclass(frozen=True)
class Generated:
    run_index: int
    case_id: str
    condition: Condition
    key: str
    statement: str
    evidence: tuple[CitedEvidence, ...]
    candidates: tuple[str, ...]

    @property
    def member(self) -> tuple[str, str, str]:
        return (self.case_id, self.condition.value, self.key)


def generated(run: Run, corpus: Corpus, refs: dict[str, list[ReferenceRequirement]], run_index: int) -> list[Generated]:
    """Requisitos gerados da corrida, nas duas condições, com as candidatas da etapa 1."""
    found = []
    for case_id in run.case_ids():
        case_corpus = corpus.case(case_id)
        for condition in Condition:
            final = run.final(case_id, run_index, condition)
            if final.status is not RunStatus.OK:
                continue
            for requirement in final.output.requirements:
                prefix = requirement.key.split("-", 1)[0]
                chunks = run.call_chunks.get((case_id, run_index, prefix))
                if chunks is None:
                    raise ContractError(
                        f"{case_id}, corrida {run_index}, {condition.value}: a chave {requirement.key} não corresponde a "
                        "nenhuma chamada de extração registrada em calls.jsonl"
                    )
                candidates = tuple(sorted(
                    r.id for r in refs[case_id] if any(quote_in_chunk(case_corpus, c, r.quote) for c in chunks)
                ))
                found.append(Generated(run_index, case_id, condition, requirement.key, requirement.statement,
                                       tuple(requirement.evidence), candidates))
    return found


@dataclass(frozen=True)
class SheetRow:
    code: str
    case_id: str
    statement: str
    candidates: tuple[str, ...]
    members: tuple[tuple[str, str, str], ...]  # (caso, condição, chave)


def sheet_rows(items: list[Generated], seed: int, run_index: int) -> list[SheetRow]:
    """Linhas da planilha, na ordem embaralhada. Requisito sem candidata não entra: não há o que decidir."""
    groups: dict[tuple[str, str, tuple[str, ...]], list[Generated]] = defaultdict(list)
    for g in items:
        if g.candidates:
            groups[(g.case_id, p3_normalize(g.statement), g.candidates)].append(g)
    ordered = sorted(groups.items())
    rng = random.Random(f"{seed}:{run_index}")
    rng.shuffle(ordered)
    numbers = rng.sample(range(len(CODE_ALPHABET) ** CODE_LENGTH), len(ordered))
    rows = []
    for number, ((case_id, _, candidates), members) in zip(numbers, ordered):
        code = ""
        for _ in range(CODE_LENGTH):
            number, digit = divmod(number, len(CODE_ALPHABET))
            code += CODE_ALPHABET[digit]
        rows.append(SheetRow(code, case_id, min(g.statement for g in members), candidates,
                             tuple(sorted(g.member for g in members))))
    return rows


def _toml_string(text: str) -> str:
    return json.dumps(text, ensure_ascii=False).replace("\x7f", "\\u007f")


def render_sheet(run_id: str, run_index: int, rows: list[SheetRow], reference: Reference) -> str:
    by_id = {r.id: r for r in reference.requirements}
    lines = [
        f"# Planilha cega de pareamento da corrida {run_id}, repetição {run_index}.",
        "# Critério: instructions/PROTOCOLO_ANOTACAO.md, seção 8. Para cada item, preencha decision com o id",
        f"# de uma das referências candidatas, ou com \"{NONE}\" se nenhuma expressa a mesma necessidade.",
        "# Não abra a pasta key/ antes de registrar as decisões. Para registrar, a partir da raiz do repositório:",
        f"#   PYTHONPATH=code .venv/bin/python -m experiments.metrics {run_id} lock --run-index {run_index} ...",
        "# O comando imprime o SHA-256 desta planilha, que vai para PROGRESS.md antes de abrir a chave.",
        f"format = {_toml_string(SHEET_FORMAT)}",
        f"run_id = {_toml_string(run_id)}",
        f"run_index = {run_index}",
    ]
    for row in rows:
        lines += [
            "",
            "[[item]]",
            f"code = {_toml_string(row.code)}",
            f"case = {_toml_string(row.case_id)}",
            f"statement = {_toml_string(row.statement)}",
            'decision = ""',
        ]
        for candidate in row.candidates:
            lines += [
                "",
                "[[item.candidate]]",
                f"id = {_toml_string(candidate)}",
                f"statement = {_toml_string(by_id[candidate].statement)}",
                f"quote = {_toml_string(by_id[candidate].quote)}",
            ]
    return "\n".join(lines) + "\n"


def render_key(run_id: str, run_index: int, rows: list[SheetRow]) -> str:
    data = {
        "format": KEY_FORMAT,
        "run_id": run_id,
        "run_index": run_index,
        "items": {
            row.code: {"case": row.case_id, "candidates": list(row.candidates),
                       "members": [{"case": case, "condition": c, "key": k} for case, c, k in row.members]}
            for row in rows
        },
    }
    return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=1) + "\n"


def write_sheet(run_dir: Path, run_id: str, run_index: int, rows: list[SheetRow], reference: Reference,
                force: bool = False) -> Path:
    sheet, key, lock = sheet_path(run_dir, run_index), key_path(run_dir, run_index), lock_path(run_dir, run_index)
    if lock.exists():
        raise ContractError(f"{lock}: as decisões desta corrida já foram registradas; a planilha não é refeita")
    if sheet.exists() and not force:
        raise ContractError(f"{sheet}: a planilha já existe e pode ter decisões preenchidas; apague-a ou use --force")
    key.parent.mkdir(parents=True, exist_ok=True)
    sheet.write_text(render_sheet(run_id, run_index, rows, reference), encoding="utf-8")
    key.write_text(render_key(run_id, run_index, rows), encoding="utf-8")
    return sheet


def _valid_decision(row: SheetRow, decision: str) -> bool:
    return decision == NONE or decision in row.candidates


def read_sheet(path: Path, run_id: str, run_index: int, rows: list[SheetRow], require_all: bool = True) -> dict[str, str]:
    """Decisão por código. Confere que a planilha é a gerada para estes registros, a menos das decisões."""
    if not path.is_file():
        raise ContractError(f"{path}: planilha não encontrada; gere com o subcomando sheet")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ContractError(f"{path}: TOML inválido: {error}") from None
    if (data.get("format"), data.get("run_id"), data.get("run_index")) != (SHEET_FORMAT, run_id, run_index):
        raise ContractError(f"{path}: cabeçalho não é o da planilha de {run_id}, repetição {run_index}")
    expected = {row.code: row for row in rows}
    items = data.get("item", [])
    codes = [item.get("code") for item in items]
    if sorted(codes) != sorted(expected):
        raise ContractError(f"{path}: os códigos da planilha não batem com os registros da corrida; gere a planilha de novo")
    errors, decisions = [], {}
    for item in items:
        row = expected[item["code"]]
        shown = (item.get("case"), item.get("statement"), tuple(c.get("id") for c in item.get("candidate", [])))
        if shown != (row.case_id, row.statement, row.candidates):
            errors.append(f"item {row.code}: caso, declaração ou candidatas foram alteradas")
            continue
        decision = str(item.get("decision", "")).strip()
        if not decision:
            if require_all:
                errors.append(f"item {row.code}: decision vazio")
            continue
        if not _valid_decision(row, decision):
            errors.append(f"item {row.code}: decision {decision!r} não é {NONE!r} nem uma das candidatas {list(row.candidates)}")
            continue
        decisions[row.code] = decision
    if errors:
        raise ContractError(f"{path}: {len(errors)} problema(s)\n  " + "\n  ".join(errors))
    return decisions


def lock(run_dir: Path, run_id: str, run_index: int, rows: list[SheetRow], clock=lambda: datetime.now(UTC)) -> dict:
    """Registra o SHA-256 da planilha preenchida. Idempotente para a mesma planilha."""
    path = sheet_path(run_dir, run_index)
    decisions = read_sheet(path, run_id, run_index, rows)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    target = lock_path(run_dir, run_index)
    if target.exists():
        previous = json.loads(target.read_text(encoding="utf-8"))
        if previous["sheet_sha256"] != digest:
            raise ContractError(
                f"{target}: as decisões já foram registradas com SHA-256 {previous['sheet_sha256']}, e a planilha mudou "
                f"depois disso. Decisão registrada não muda; corrija em {corrections_path(run_dir, run_index).name}"
            )
        return previous
    record = {
        "format": LOCK_FORMAT,
        "run_id": run_id,
        "run_index": run_index,
        "sheet": path.name,
        "sheet_sha256": digest,
        "items": len(decisions),
        "decided_none": sum(d == NONE for d in decisions.values()),
        "locked_at": clock().isoformat(timespec="seconds"),
    }
    target.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    return record


@dataclass(frozen=True)
class Correction:
    code: str
    decision: str
    date: str
    reason: str


@dataclass(frozen=True)
class Decisions:
    run_index: int
    sheet_sha256: str
    locked_at: str
    by_member: dict[tuple[str, str, str], str]
    corrections: tuple[Correction, ...]


def _read_corrections(path: Path, rows: dict[str, SheetRow]) -> list[Correction]:
    if not path.is_file():
        return []
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8")).get("correction", [])
    except tomllib.TOMLDecodeError as error:
        raise ContractError(f"{path}: TOML inválido: {error}") from None
    found = []
    for position, item in enumerate(raw, start=1):
        try:
            correction = Correction(*(str(item[f]).strip() for f in ("code", "decision", "date", "reason")))
        except KeyError as error:
            raise ContractError(f"{path}: correção #{position} sem o campo {error}") from None
        if correction.code not in rows:
            raise ContractError(f"{path}: correção #{position}: código {correction.code!r} não existe na planilha")
        if not _valid_decision(rows[correction.code], correction.decision):
            raise ContractError(f"{path}: correção #{position}: decisão {correction.decision!r} inválida para {correction.code}")
        if not correction.date or not correction.reason:
            raise ContractError(f"{path}: correção #{position}: data e motivo são obrigatórios")
        found.append(correction)
    return found


def read_decisions(run_dir: Path, run_id: str, run_index: int, rows: list[SheetRow]) -> Decisions | None:
    """Decisões registradas, decodificadas pela chave. None se a corrida ainda não tem registro."""
    target = lock_path(run_dir, run_index)
    if not target.exists():
        return None
    record = json.loads(target.read_text(encoding="utf-8"))
    path = sheet_path(run_dir, run_index)
    digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    if digest != record["sheet_sha256"]:
        raise ContractError(
            f"{path}: SHA-256 {digest} difere do registrado em {target.name} ({record['sheet_sha256']}). "
            f"Decisão registrada não muda; corrija em {corrections_path(run_dir, run_index).name}"
        )
    decisions = read_sheet(path, run_id, run_index, rows)
    key = json.loads(key_path(run_dir, run_index).read_text(encoding="utf-8"))
    expected = json.loads(render_key(run_id, run_index, rows))
    if key != expected:
        raise ContractError(f"{key_path(run_dir, run_index)}: a chave não corresponde aos registros da corrida")
    by_code = {row.code: row for row in rows}
    corrections = _read_corrections(corrections_path(run_dir, run_index), by_code)
    for correction in corrections:
        decisions[correction.code] = correction.decision
    by_member = {member: decisions[row.code] for row in rows for member in row.members}
    return Decisions(run_index, record["sheet_sha256"], record["locked_at"], by_member, tuple(corrections))


@dataclass(frozen=True)
class Assignment:
    generated: Generated
    reference: str | None
    reason: str  # paired, no_candidates, none, duplicate
    covered: bool = False


def evidence_covers(evidence: tuple[CitedEvidence, ...], quote: str, corpus: CorpusIndex) -> bool:
    """Fonte correta: uma evidência que resolve no corpus do caso cita um chunk que contém a citação esperada."""
    return any(corpus.resolves(e) and quote_in_chunk(corpus, e.chunk_id, quote) for e in evidence)


def assign(items: list[Generated], decisions: Decisions, refs: dict[str, list[ReferenceRequirement]],
           corpus: Corpus) -> list[Assignment]:
    """Um a um por corrida, caso e condição. Duas chaves na mesma referência: fica a menor chave."""
    quotes = {r.id: r.quote for rs in refs.values() for r in rs}
    claims: dict[tuple[str, Condition, str], list[Generated]] = defaultdict(list)
    result: list[Assignment] = []
    for g in items:
        if not g.candidates:
            result.append(Assignment(g, None, "no_candidates"))
            continue
        decision = decisions.by_member[g.member]
        if decision == NONE:
            result.append(Assignment(g, None, "none"))
        else:
            claims[(g.case_id, g.condition, decision)].append(g)
    for (case_id, _, reference), claimants in claims.items():
        winner, *others = sorted(claimants, key=lambda g: g.key)
        covered = evidence_covers(winner.evidence, quotes[reference], corpus.case(case_id))
        result.append(Assignment(winner, reference, "paired", covered))
        result += [Assignment(g, None, "duplicate") for g in others]
    return sorted(result, key=lambda a: (a.generated.condition.value, a.generated.case_id, a.generated.key))


@dataclass(frozen=True)
class PairingCounts:
    run_index: int
    condition: Condition
    generated: int
    references: int
    paired: int
    no_candidates: int
    decided_none: int
    duplicates: int
    covered: int

    @property
    def generated_unpaired(self) -> int:
        return self.generated - self.paired

    @property
    def references_unpaired(self) -> int:
        return self.references - self.paired

    @property
    def provenance_coverage(self) -> float | None:
        return self.covered / self.paired if self.paired else None

    @property
    def provenance_coverage_of_references(self) -> float | None:
        """Denominador igual nas duas condições: todas as referências dos casos da corrida."""
        return self.covered / self.references if self.references else None


def counts(run_index: int, assignments: list[Assignment], refs: dict[str, list[ReferenceRequirement]]) -> list[PairingCounts]:
    references = sum(len(rs) for rs in refs.values())
    found = []
    for condition in Condition:
        mine = [a for a in assignments if a.generated.condition is condition]
        by_reason = defaultdict(int)
        for a in mine:
            by_reason[a.reason] += 1
        found.append(PairingCounts(
            run_index, condition, len(mine), references, by_reason["paired"], by_reason["no_candidates"],
            by_reason["none"], by_reason["duplicate"], sum(a.covered for a in mine),
        ))
    return found
