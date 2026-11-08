import importlib.util
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("promise", Path(__file__).with_name("promise.py"))
promise = importlib.util.module_from_spec(_spec)
sys.modules["promise"] = promise
_spec.loader.exec_module(promise)

MINI_ARFF = (
    "@RELATION nfr\r\n"
    "\r\n"
    "% comentario de cabecalho\r\n"
    "@ATTRIBUTE ProjectID {1,2,3}\r\n"
    "@ATTRIBUTE RequirementText string\r\n"
    "@ATTRIBUTE class {F,A,L,LF,MN,O,PE,SC,SE,US,FT,PO}%nota inline\r\n"
    "\r\n"
    "@DATA\r\n"
    "1,'The system shall refresh the display every 60 seconds.',PE\r\n"
    "1,'The user shall be able to log in, then log out.',F\r\n"
    "2,' Only the organization\u2019s staff shall access records.',SE\r\n"
    "\r\n"
    "3,'The product shall be easy to use.',US\r\n"
).encode("cp1252")


def write_fixture(tmp_path: Path, body: bytes = MINI_ARFF) -> Path:
    path = tmp_path / "mini.arff"
    path.write_bytes(body)
    return path


def test_parse_counts_and_ids():
    records = promise.parse_arff(MINI_ARFF)
    assert [r.promise_id for r in records] == [
        "PROMISE-NFR-0001",
        "PROMISE-NFR-0002",
        "PROMISE-NFR-0003",
        "PROMISE-NFR-0004",
    ]
    assert [r.project_id for r in records] == [1, 1, 2, 3]


def test_text_keeps_commas_and_decodes_cp1252():
    records = promise.parse_arff(MINI_ARFF)
    assert records[1].text == "The user shall be able to log in, then log out."
    assert records[2].text == " Only the organization\u2019s staff shall access records."


def test_labels():
    records = promise.parse_arff(MINI_ARFF)
    assert [(r.label, r.label_name, r.is_functional) for r in records] == [
        ("PE", "Performance", False),
        ("F", "Functional", True),
        ("SE", "Security", False),
        ("US", "Usability", False),
    ]


def test_undeclared_label_fails_with_line_number():
    bad = MINI_ARFF.replace(b"',US", b"',XX")
    with pytest.raises(promise.ArffError, match=r"linha 13: r\u00f3tulo 'XX'"):
        promise.parse_arff(bad)


def test_undeclared_project_fails():
    bad = MINI_ARFF.replace(b"3,'The product", b"9,'The product")
    with pytest.raises(promise.ArffError, match="ProjectID '9'"):
        promise.parse_arff(bad)


def test_wrong_attributes_fail():
    bad = MINI_ARFF.replace(b"RequirementText", b"Texto")
    with pytest.raises(promise.ArffError, match="atributos"):
        promise.parse_arff(bad)


def test_jsonl_schema(tmp_path):
    out = tmp_path / "out.jsonl"
    promise.convert(write_fixture(tmp_path), out, None)
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 4
    assert list(rows[0]) == ["promise_id", "project_id", "text", "label", "label_name", "is_functional"]
    assert rows[1]["is_functional"] is True


def test_output_is_deterministic(tmp_path):
    src = write_fixture(tmp_path)
    out, stats = tmp_path / "out.jsonl", tmp_path / "STATS.md"
    promise.convert(src, out, stats)
    first = (out.read_bytes(), stats.read_bytes())
    promise.convert(src, out, stats)
    assert (out.read_bytes(), stats.read_bytes()) == first
    other = tmp_path / "other.jsonl"
    promise.convert(src, other, None)
    assert other.read_bytes() == first[0]


def test_reads_arff_inside_tar(tmp_path):
    tar_path = tmp_path / "nfr.tar"
    with tarfile.open(tar_path, "w") as tar:
        info = tarfile.TarInfo(promise.TAR_MEMBER)
        info.size = len(MINI_ARFF)
        tar.addfile(info, io.BytesIO(MINI_ARFF))
    out_tar, out_arff = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    promise.convert(tar_path, out_tar, None)
    promise.convert(write_fixture(tmp_path), out_arff, None)
    assert out_tar.read_bytes() == out_arff.read_bytes()


def test_stats():
    stats = promise.compute_stats(promise.parse_arff(MINI_ARFF))
    assert stats["total"] == 4
    assert stats["functional"] == 1
    assert stats["non_functional"] == 3
    assert stats["projects"] == {1: 2, 2: 1, 3: 1}
    assert stats["labels"] == {"F": 1, "PE": 1, "SE": 1, "US": 1}
    assert stats["duplicate_groups"] == []


def test_duplicate_texts_with_different_labels():
    body = MINI_ARFF + b"3,'The product shall be easy to use.',F\r\n"
    stats = promise.compute_stats(promise.parse_arff(body))
    assert stats["duplicate_texts"] == 1
    assert stats["duplicate_groups"] == [["PROMISE-NFR-0004:US", "PROMISE-NFR-0005:F"]]


def test_cli_missing_input(tmp_path, capsys):
    code = promise.main(["--input", str(tmp_path / "nao_existe.tar"), "--no-stats"])
    assert code == 2
    assert "SOURCE.md" in capsys.readouterr().err
