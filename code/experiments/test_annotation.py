import shutil
import tomllib
import unicodedata
from pathlib import Path

import pytest
from pydantic import ValidationError

from domain.config import ContractError
from domain.enums import QualityCategory, RequirementType, SourceKind
from domain.llm_io import CitedEvidence
from experiments import annotation
from experiments.annotation import ReferenceRequirement, load_sample, main, validate_sample

FIXTURES = Path(__file__).parent / "fixtures"
VALID = FIXTURES / "valido"
INVALID = FIXTURES / "invalidos"
EXPECTED = tomllib.loads((INVALID / "EXPECTED.toml").read_text(encoding="utf-8"))
TEMPLATE = Path(__file__).parents[2] / "data" / "raw" / "amostra" / "TEMPLATE"

MINIMAL = """protocol_version = "1"

[[artifact]]
id = "a01"
kind = "interview"
title = "Entrevista de teste"

[[requirement]]
id = "a01-R01"
artifact = "a01"
statement = "O sistema deve registrar cada retirada."
type = "functional"
quote = {quote}
"""


def copy_valid(tmp_path: Path) -> Path:
    shutil.copytree(VALID, tmp_path, dirs_exist_ok=True)
    return tmp_path


def errors(directory: Path) -> list[str]:
    return [str(f) for f in validate_sample(directory).errors]


def warnings(directory: Path) -> list[str]:
    return [str(f) for f in validate_sample(directory).warnings]


def test_valid_fixture_has_no_errors_and_counts():
    report = validate_sample(VALID)
    assert report.errors == []
    reference = report.reference
    assert [a.id for a in reference.artifacts] == ["a01", "a02"]
    assert [r.id for r in reference.requirements] == ["a01-R01", "a01-R02", "a01-R03", "a02-R01", "a02-R02"]
    assert [r.type for r in reference.requirements].count(RequirementType.FUNCTIONAL) == 3
    assert len(reference.relations) == 1
    assert sorted(report.hashes) == ["a01.txt", "a02.txt", "referencia.toml"]


def test_every_invalid_fixture_has_an_expectation():
    assert sorted(p.stem for p in INVALID.glob("*.toml") if p.stem != "EXPECTED") == sorted(EXPECTED)


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_invalid_fixture_fails_with_file_subject_and_field(case, tmp_path):
    shutil.copy(VALID / "a01.txt", tmp_path)
    shutil.copy(INVALID / f"{case}.toml", tmp_path / annotation.REFERENCE_FILE)
    assert errors(tmp_path) == [EXPECTED[case]]


def test_template_is_valid():
    report = validate_sample(TEMPLATE)
    assert report.errors == []
    assert len(report.reference.requirements) == 4


def test_quote_uses_the_normalization_of_rule_p3(tmp_path):
    (tmp_path / "a01.txt").write_text(
        "Artefato sintético de teste.\n\nO técnico   precisa\nregistrar a calibração.\n", encoding="utf-8"
    )
    quote = unicodedata.normalize("NFD", "o TÉCNICO precisa registrar a calibração")
    (tmp_path / "referencia.toml").write_text(MINIMAL.format(quote=f'"{quote}"'), encoding="utf-8")
    assert errors(tmp_path) == []


def test_sample_inside_the_ranges_has_no_warnings(tmp_path):
    kinds = list(SourceKind) + [SourceKind.INTERVIEW]
    attributes = list(QualityCategory)
    lines = ['protocol_version = "1"']
    for a in range(1, 7):
        artifact = f"a{a:02d}"
        paragraphs = [f"Frase {artifact} número {n} sobre uma necessidade distinta." for n in range(1, 11)]
        (tmp_path / f"{artifact}.txt").write_text(
            "Artefato sintético de teste.\n\n" + "\n\n".join(paragraphs) + "\n", encoding="utf-8"
        )
        lines += ["[[artifact]]", f'id = "{artifact}"', f'kind = "{kinds[a - 1].value}"', 'title = "Teste"']
        for n in range(1, 11):
            requirement_type = list(RequirementType)[n % 3]
            lines += [
                "[[requirement]]",
                f'id = "{artifact}-R{n:02d}"',
                f'artifact = "{artifact}"',
                f'statement = "Necessidade {n} de {artifact}."',
                f'type = "{requirement_type.value}"',
                f'quote = "Frase {artifact} número {n} sobre"',
            ]
            if requirement_type is RequirementType.NON_FUNCTIONAL:
                lines.append(f'quality_attributes = ["{attributes[(a + n) % 6].value}"]')
    (tmp_path / "referencia.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = validate_sample(tmp_path)
    assert report.errors == []
    assert report.warnings == []
    assert len(report.reference.requirements) == 60


def test_small_sample_warns_about_the_ranges():
    found = warnings(VALID)
    assert "referencia.toml: (amostra): artefatos: 2, fora da faixa 6 a 8 do protocolo" in found
    assert "referencia.toml: (amostra): requisitos de referência: 5, fora da faixa 50 a 70 do protocolo" in found
    assert "referencia.toml: (amostra): nenhum artefato do tipo user_story" in found
    assert "referencia.toml: (amostra): atributo usability em 1 requisito(s), menos que 2" in found


def test_first_line_must_mark_the_artifact_as_synthetic(tmp_path):
    copy_valid(tmp_path)
    path = tmp_path / "a02.txt"
    path.write_text(path.read_text(encoding="utf-8").replace("Artefato sintético", "Texto", 1), encoding="utf-8")
    assert errors(tmp_path) == ["a02.txt: linha 1: a primeira linha tem de começar com 'Artefato sintético'"]


def test_undeclared_and_missing_artifacts(tmp_path):
    copy_valid(tmp_path)
    shutil.copy(tmp_path / "a01.txt", tmp_path / "a09.txt")
    (tmp_path / "a02.txt").unlink()
    assert errors(tmp_path) == [
        "a09.txt: arquivo: artefato não declarado em referencia.toml",
        "referencia.toml: artefato a02: campo id: a02.txt não existe",
    ]


def test_artifact_must_be_utf8(tmp_path):
    copy_valid(tmp_path)
    (tmp_path / "a02.txt").write_bytes("Artefato sintético.\n\nCalibração.\n".encode("latin-1"))
    assert errors(tmp_path) == ["a02.txt: arquivo: não é UTF-8 (byte 13)"]


def test_toml_syntax_error_and_missing_reference(tmp_path):
    shutil.copy(VALID / "a01.txt", tmp_path)
    assert errors(tmp_path) == [f"referencia.toml: arquivo: não existe em {tmp_path}"]
    (tmp_path / "referencia.toml").write_text('protocol_version = "1\n', encoding="utf-8")
    [message] = errors(tmp_path)
    assert message.startswith("referencia.toml: arquivo: TOML inválido:")


def test_long_paragraph_and_repeated_quote_warn(tmp_path):
    long_paragraph = "registrar a calibração " + "texto " * 300
    (tmp_path / "a01.txt").write_text(
        f"Artefato sintético de teste.\n\n{long_paragraph}\n\nregistrar a calibração de novo\n", encoding="utf-8"
    )
    (tmp_path / "referencia.toml").write_text(MINIMAL.format(quote='"registrar a calibração"'), encoding="utf-8")
    found = warnings(tmp_path)
    assert "referencia.toml: requisito a01-R01: campo quote: citação aparece nos parágrafos 1, 2 de a01.txt" in found
    assert any(w.startswith("a01.txt: parágrafo 1: 1822 caracteres passam de chunking.size_chars (1500)") for w in found)


def test_quote_has_the_same_limit_as_cited_evidence():
    long_quote = "x" * 1001
    with pytest.raises(ValidationError):
        CitedEvidence(source_id="s", chunk_id="c", quote=long_quote)
    with pytest.raises(ValidationError):
        ReferenceRequirement(id="a01-R01", artifact="a01", statement="s", type="functional", quote=long_quote)


def test_load_sample(tmp_path):
    reference, texts = load_sample(VALID)
    assert sorted(texts) == ["a01", "a02"]
    assert reference.requirements[0].priority.value == "must"
    shutil.copy(VALID / "a01.txt", tmp_path)
    shutil.copy(INVALID / "citacao_nao_literal.toml", tmp_path / "referencia.toml")
    with pytest.raises(ContractError, match="campo quote: citação não aparece literalmente"):
        load_sample(tmp_path)


def test_cli_exit_codes(tmp_path, capsys):
    assert main([str(VALID)]) == 0
    out = capsys.readouterr().out
    assert "Requisitos de referência: 5" in out
    assert out.rstrip().endswith("Resultado: amostra válida, 0 erro(s) e 11 alerta(s)")

    shutil.copy(VALID / "a01.txt", tmp_path)
    shutil.copy(INVALID / "prioridade_sem_citacao.toml", tmp_path / "referencia.toml")
    assert main([str(tmp_path)]) == 1
    assert EXPECTED["prioridade_sem_citacao"] in capsys.readouterr().out

    assert main([str(tmp_path / "nao_existe")]) == 2
    assert "não é uma pasta" in capsys.readouterr().err
