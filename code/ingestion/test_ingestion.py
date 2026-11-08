import hashlib
import os
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

from domain import ids
from domain.config import ChunkingConfig
from domain.models import SourceChunk, SourceDocument
from domain.serialization import load_json
from ingestion.corpus import REPO_ROOT, IngestionError, ingest, load, render, write
from ingestion.__main__ import main
from ingestion.diff import DocumentStatus, diff

PARAGRAPH = ChunkingConfig(strategy="paragraph", size_chars=1500, overlap_chars=0)
FIXTURE_SET = REPO_ROOT / "code" / "ingestion" / "fixtures" / "fixture.toml"
DOMAIN_FIXTURES = REPO_ROOT / "code" / "domain" / "fixtures" / "valid"
DOC = "docs/entrevista.txt"
OTHER = "docs/ata.md"
PARAGRAPHS = [
    "Texto sintético de teste.",
    "Coordenadora: a reserva hoje é feita numa planilha.",
    "Técnico: o aviso de calibração chega atrasado.",
    "Coordenadora: só a coordenação cancela reserva alheia.",
    "Técnico: a agenda precisa abrir rápido.",
]


def write_file(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def write_set(root: Path, *entries: tuple[str, str], name: str = "fontes.toml") -> Path:
    body = "".join(f"[[document]]\npath = '{path}'\nkind = '{kind}'\n\n" for path, kind in entries)
    return write_file(root, name, body)


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    write_file(tmp_path, DOC, "\n\n".join(PARAGRAPHS) + "\n")
    write_file(tmp_path, OTHER, "Texto sintético de teste.\n\n# Ata\n\nNada decidido.\n")
    write_set(tmp_path, (DOC, "interview"), (OTHER, "meeting_record"))
    return tmp_path


def run(root: Path, name: str = "fontes.toml", config: ChunkingConfig = PARAGRAPH):
    return ingest(root / name, config, root=root)


def test_gate_a_same_set_twice_gives_identical_bytes_and_no_duplicates(corpus, tmp_path):
    first, second = run(corpus), run(corpus)
    assert render(first) == render(second)
    assert len({d.source_id for d in first.documents}) == len(first.documents) == 2
    assert len({c.chunk_id for c in first.chunks}) == len(first.chunks) == 8

    output = tmp_path / "out" / "fontes.json"
    assert write(first, output) is True
    stamp = output.stat().st_mtime_ns
    assert write(second, output) is False
    assert output.stat().st_mtime_ns == stamp
    assert render(load(output)) == render(first)

    report = diff(load(output), second)
    assert not report.changed
    assert report.removed_chunks == report.added_chunks == []


def test_gate_b_editing_one_paragraph_invalidates_only_its_chunk(corpus):
    before = run(corpus)
    edited = list(PARAGRAPHS)
    edited[2] = "Técnico: o aviso de calibração tem de chegar em cinco minutos."
    write_file(corpus, DOC, "\n\n".join(edited) + "\n")
    after = run(corpus)

    report = diff(before, after)
    by_path = {d.path: d for d in report.documents}
    changed, untouched = by_path[DOC], by_path[OTHER]
    old_chunks = before.chunks_of(ids.source_id(DOC))
    new_chunks = after.chunks_of(ids.source_id(DOC))

    assert changed.status is DocumentStatus.MODIFIED
    assert changed.removed == [old_chunks[2].chunk_id]
    assert changed.added == [new_chunks[2].chunk_id]
    assert changed.kept == [c.chunk_id for i, c in enumerate(new_chunks) if i != 2]
    assert untouched.status is DocumentStatus.UNCHANGED
    assert untouched.removed == untouched.added == []
    assert report.removed_chunks == [old_chunks[2].chunk_id]


def test_gate_b_line_endings_alone_do_not_change_the_document(corpus):
    before = run(corpus)
    write_file(corpus, DOC, "\r\n\r\n".join(PARAGRAPHS) + "\r\n")
    report = diff(before, run(corpus))
    assert not report.changed


def test_diff_reports_added_removed_documents_and_metadata(corpus):
    before = run(corpus)
    write_file(corpus, "docs/nova.txt", "Texto sintético de teste.\n\nOutro parágrafo.\n")
    write_set(corpus, (DOC, "user_story"), ("docs/nova.txt", "business_document"))
    report = diff(before, run(corpus))
    status = {d.path: (d.status, d.metadata_changed, len(d.added), len(d.removed)) for d in report.documents}
    assert status == {
        OTHER: (DocumentStatus.REMOVED, False, 0, 3),
        DOC: (DocumentStatus.UNCHANGED, True, 0, 0),
        "docs/nova.txt": (DocumentStatus.ADDED, False, 2, 0),
    }
    assert [d.path for d in report.documents] == sorted(status)


def test_diff_flags_chunking_change(corpus):
    window = ChunkingConfig(strategy="window", size_chars=40, overlap_chars=10)
    report = diff(run(corpus), run(corpus, config=window))
    assert report.chunking_changed and report.changed
    assert all(d.status is DocumentStatus.UNCHANGED for d in report.documents)


ACCENTED = "docs/reunião/entrevista.txt"


@pytest.mark.parametrize(
    "spelling",
    [
        "./docs/reunião/entrevista.txt",
        "docs\\reunião\\entrevista.txt",
        "docs//./reunião/entrevista.txt",
        unicodedata.normalize("NFD", ACCENTED),
    ],
    ids=["ponto-barra", "barra-invertida", "barra-dupla", "nfd"],
)
def test_gate_c_path_spellings_give_the_same_source(tmp_path, spelling):
    relative = ACCENTED
    write_file(tmp_path, relative, "Texto sintético de teste.\n\nUm parágrafo.\n")
    write_set(tmp_path, (relative, "interview"), name="canonico.toml")
    write_set(tmp_path, (spelling, "interview"), name="variante.toml")
    assert (tmp_path / "variante.toml").read_bytes() != (tmp_path / "canonico.toml").read_bytes()

    canonical = run(tmp_path, "canonico.toml")
    variant = run(tmp_path, "variante.toml")
    assert [d.model_dump() for d in variant.documents] == [d.model_dump() for d in canonical.documents]
    assert [c.model_dump() for c in variant.chunks] == [c.model_dump() for c in canonical.chunks]
    assert variant.documents[0].path == relative
    assert variant.documents[0].source_id == ids.source_id(relative)


def test_gate_c_file_stored_with_nfd_name_is_found_by_nfc_path(tmp_path):
    relative = "docs/calibração.txt"
    write_file(tmp_path, unicodedata.normalize("NFD", relative), "Texto sintético de teste.\n")
    write_set(tmp_path, (relative, "interview"))
    assert run(tmp_path).documents[0].path == relative


def test_gate_c_same_file_listed_twice_is_refused(corpus):
    write_set(corpus, (DOC, "interview"), ("./" + DOC, "interview"))
    with pytest.raises(IngestionError, match=r"fontes\.toml: document\.1\.path: .*repete document\.0\.path"):
        run(corpus)


@pytest.mark.parametrize(
    "entries, pattern",
    [
        (((DOC, "interview"), ("docs/ausente.txt", "interview")),
         r"fontes\.toml: document\.1\.path: arquivo 'docs/ausente\.txt' não existe"),
        (((DOC, "entrevista"),), r"fontes\.toml: .*\n  document\.0\.kind: "),
        (((DOC, "interview"), ("docs/manual.pdf", "interview")),
         r"fontes\.toml: document\.1\.path: 'docs/manual\.pdf' não é \.txt nem \.md"),
        (((DOC, "interview"), ("../fora.txt", "interview")),
         r"fontes\.toml: document\.1\.path: .*sem '\.\.'"),
        (((DOC, "interview"), ("/etc/hosts.txt", "interview")),
         r"fontes\.toml: document\.1\.path: .*relativo à raiz"),
    ],
)
def test_gate_d_errors_name_the_set_file_and_the_field(corpus, entries, pattern):
    write_set(corpus, *entries)
    with pytest.raises(IngestionError, match=pattern):
        run(corpus)


def test_gate_d_unknown_field_and_empty_set(corpus):
    write_file(corpus, "fontes.toml", f'[[document]]\npath = "{DOC}"\nkind = "interview"\ntitulo = "x"\n')
    with pytest.raises(IngestionError, match=r"fontes\.toml: .*\n  document\.0\.titulo: "):
        run(corpus)
    write_file(corpus, "fontes.toml", "# vazio\n")
    with pytest.raises(IngestionError, match=r"fontes\.toml: .*\n  document: "):
        run(corpus)


def test_gate_d_invalid_utf8_and_blank_document_name_the_file(corpus):
    write_file(corpus, "docs/branco.txt", "\n  \n\t\n")
    (corpus / "docs" / "latin1.txt").write_bytes("calibração".encode("latin-1"))
    write_set(corpus, (DOC, "interview"), ("docs/latin1.txt", "interview"))
    with pytest.raises(IngestionError, match=r"document\.1\.path: 'docs/latin1\.txt': não é UTF-8"):
        run(corpus)
    write_set(corpus, ("docs/branco.txt", "interview"))
    with pytest.raises(IngestionError, match=r"document\.0\.path: 'docs/branco\.txt' não tem texto"):
        run(corpus)


def test_set_file_must_live_under_root(tmp_path, corpus):
    outside = tmp_path.parent / "fora_da_raiz.toml"
    with pytest.raises(IngestionError, match="tem de ficar dentro de"):
        ingest(outside, PARAGRAPH, root=corpus / "docs")


def test_text_is_stored_in_nfc_with_lf(tmp_path):
    raw = "Texto sintético de teste.\r\n\r\nCalibrac\u0327a\u0303o vencida.\r\n"
    write_file(tmp_path, DOC, raw)
    write_set(tmp_path, (DOC, "interview"))
    result = run(tmp_path)
    assert result.chunks[1].text == "Calibração vencida."
    assert result.documents[0].sha256 == ids.sha256_text("Texto sintético de teste.\n\nCalibração vencida.\n")


def test_fixture_set_matches_domain_fixtures_for_the_interview():
    """O corpus do contrato, ingerido aqui, gera os mesmos registros que os fixtures do domínio."""
    result = ingest(FIXTURE_SET, PARAGRAPH)
    expected_document = load_json(DOMAIN_FIXTURES / "source_document.json", SourceDocument)
    expected_chunks = load_json(DOMAIN_FIXTURES / "source_chunks.json", list[SourceChunk])
    by_id = {d.source_id: d for d in result.documents}
    assert by_id[expected_document.source_id] == expected_document
    assert result.chunks_of(expected_document.source_id) == expected_chunks


def test_fixture_output_on_disk_is_current():
    output = REPO_ROOT / "data" / "processed" / "ingestion" / "fixture.json"
    assert output.read_bytes() == render(ingest(FIXTURE_SET, PARAGRAPH))
    assert load(output).set_sha256 == hashlib.sha256(FIXTURE_SET.read_bytes()).hexdigest()


def test_gate_e_bytes_do_not_depend_on_hash_seed(tmp_path):
    digests = set()
    for seed in ("0", "1", "4242"):
        output = tmp_path / f"seed{seed}.json"
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(REPO_ROOT / "code"),
               "PYTHONDONTWRITEBYTECODE": "1"}
        subprocess.run(
            [sys.executable, "-m", "ingestion", str(FIXTURE_SET), "--output", str(output)],
            cwd=REPO_ROOT, env=env, check=True, capture_output=True,
        )
        digests.add(hashlib.sha256(output.read_bytes()).hexdigest())
    assert digests == {hashlib.sha256(render(ingest(FIXTURE_SET, PARAGRAPH))).hexdigest()}


def test_cli_refuses_output_written_from_another_set_file(tmp_path, capsys):
    output = tmp_path / "fixture.json"
    other = ingest(FIXTURE_SET, PARAGRAPH).model_copy(update={"set_path": "data/raw/outro/fixture.toml"})
    write(other, output)
    before = output.read_bytes()

    for extra in ([], ["--check"]):
        assert main([str(FIXTURE_SET), "--output", str(output), *extra]) == 1
        error = capsys.readouterr().err
        assert "veio de outro arquivo de conjunto (data/raw/outro/fixture.toml)" in error
        assert "não de code/ingestion/fixtures/fixture.toml" in error
        assert "--output data/processed/ingestion/<nome>.json" in error
        assert "removido" not in error
        assert output.read_bytes() == before

    output.unlink()
    assert main([str(FIXTURE_SET), "--output", str(output)]) == 0
    assert main([str(FIXTURE_SET), "--output", str(output)]) == 0


def test_cli_check_and_error_exit_codes(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "code"), "PYTHONDONTWRITEBYTECODE": "1"}
    output = tmp_path / "fixture.json"
    command = [sys.executable, "-m", "ingestion", str(FIXTURE_SET), "--output", str(output)]
    assert subprocess.run(command + ["--check"], cwd=REPO_ROOT, env=env, capture_output=True).returncode == 1
    assert subprocess.run(command, cwd=REPO_ROOT, env=env, capture_output=True).returncode == 0
    checked = subprocess.run(command + ["--check"], cwd=REPO_ROOT, env=env, capture_output=True, text=True)
    assert checked.returncode == 0 and "=4 chunks" in checked.stdout

    bad = REPO_ROOT / "code" / "ingestion" / "fixtures" / ".teste_invalido.toml"
    bad.write_text('[[document]]\npath = "nao/existe.txt"\nkind = "interview"\n', encoding="utf-8")
    try:
        failed = subprocess.run([sys.executable, "-m", "ingestion", str(bad), "--output", str(output)],
                                cwd=REPO_ROOT, env=env, capture_output=True, text=True)
    finally:
        bad.unlink()
    assert failed.returncode == 1
    assert "fixtures/.teste_invalido.toml: document.0.path: arquivo 'nao/existe.txt' não existe" in failed.stderr
