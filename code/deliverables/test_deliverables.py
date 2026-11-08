"""Os quatro artefatos sobre a corrida sintética de fixtures/, sem Neo4j."""

import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from domain.enums import Condition
from domain.persist import to_records
from domain.rules import RULES, check_all
from graph.state import canonical
from deliverables.__main__ import generate, main
from deliverables.catalog import build_catalog
from deliverables.inputs import REPO_ROOT, DeliverableError, Selection, load

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
RUNS = FIXTURES / "runs"
CONFIG = FIXTURES / "experiment.toml"
EXPECTED = FIXTURES / "expected"
RULES_MD = REPO_ROOT / "code" / "domain" / "schema" / "RULES.md"
SET_FILE = REPO_ROOT / "code" / "ingestion" / "fixtures" / "fixture.toml"
OTHER_SET = REPO_ROOT / "code" / "experiments" / "metrics" / "fixtures" / "conjunto.toml"
RUN_ID = "sintetico-entrevista"
NAME = "fixture-sintetico"
ENTREVISTA, ATA, DESCRICAO = "src-3f478d516d9d807d", "src-339ed9b9a545ccbc", "src-71d5fe87d6dfb68a"
B = Selection(RUN_ID, Condition.REQKG_GROUNDED, 0)
A = Selection(RUN_ID, Condition.LLM_ONLY, 0)
REBUILD = "rode .venv/bin/python code/deliverables/fixtures/build.py e confira o diff"


@pytest.fixture(scope="module")
def files() -> dict[str, bytes]:
    return generate(B, NAME, RUNS, CONFIG)


@pytest.fixture(scope="module")
def catalog():
    return build_catalog(load(B, RUNS, CONFIG))


def text(files: dict[str, bytes], name: str) -> str:
    return files[name].decode("utf-8")


def block(document: str, label: str) -> str:
    """Do título do requisito até o próximo título."""
    match = re.search(rf"^#+ {label} · .*?(?=^#)", document, flags=re.M | re.S)
    assert match, f"{label} não tem bloco próprio"
    return match.group(0)


def section(document: str, title: str) -> str:
    """Corpo da seção, com as subseções, até o próximo título do mesmo nível ou acima."""
    lines = document.splitlines()
    for start, line in enumerate(lines):
        heading = re.match(r"^(#+) (.*)$", line)
        if heading and heading.group(2) == title:
            body = []
            for following in lines[start + 1:]:
                other = re.match(r"^(#+) ", following)
                if other and len(other.group(1)) <= len(heading.group(1)):
                    break
                body.append(following)
            return "\n".join(body)
    raise AssertionError(f"seção {title!r} ausente")


def matrix(files: dict[str, bytes]) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text(files, "matriz_proveniencia.csv"))))


def label_of(catalog, case_id: str, key: str) -> str:
    return next(v.label for v in catalog.requirements if v.case_id == case_id and v.candidate.key == key)


# Determinismo


def test_generated_bytes_match_expected_files(files):
    on_disk = {p.name for p in EXPECTED.iterdir()}
    assert set(files) == on_disk, REBUILD
    for name, data in files.items():
        assert (EXPECTED / name).read_bytes() == data, f"{name} difere do esperado: {REBUILD}"


def test_cli_writes_the_same_bytes_under_other_hash_seeds(tmp_path):
    for seed in ("0", "1", "4242"):
        env = {**os.environ, "PYTHONPATH": "code", "PYTHONHASHSEED": seed, "PYTHONDONTWRITEBYTECODE": "1"}
        out = tmp_path / seed
        done = subprocess.run(
            [sys.executable, "-m", "deliverables", RUN_ID, "--condition", "REQKG-grounded", "--run-index", "0",
             "--name", NAME, "--runs-dir", str(RUNS), "--config", str(CONFIG), "--output-root", str(out)],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        for expected in EXPECTED.iterdir():
            assert (out / NAME / expected.name).read_bytes() == expected.read_bytes(), (seed, expected.name)


def test_fixture_build_is_up_to_date():
    done = subprocess.run([sys.executable, str(FIXTURES / "build.py"), "--check"], cwd=REPO_ROOT,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True)
    assert done.returncode == 0, f"{done.stderr}\n{REBUILD}"


def test_check_flags_stale_output_and_write_skips_equal_bytes(tmp_path, capsys):
    args = [RUN_ID, "--run-index", "0", "--name", NAME, "--runs-dir", str(RUNS), "--config", str(CONFIG),
            "--output-root", str(tmp_path)]
    assert main([*args, "--check"]) == 1
    assert main(args) == 0
    assert main([*args, "--check"]) == 0
    assert main(args) == 0
    assert "0 gravado(s)" in capsys.readouterr().out


# Esboço de SRS


def test_srs_leaves_purpose_and_scope_to_the_author(files):
    srs = text(files, "srs.md")
    for title in ("1.1 Propósito", "1.2 Escopo", "1.3 Visão geral do produto"):
        assert section(srs, title).strip() == "_A preencher pelo autor._"


def test_srs_shows_missing_fields_as_pending_and_never_fills_them(files, catalog):
    srs = text(files, "srs.md")
    assert "| Prioridade | pendente |" in block(srs, label_of(catalog, ENTREVISTA, "c0-R1"))
    for view in catalog.requirements:
        body = block(srs, view.label)
        c = view.candidate
        assert ("| Prioridade | pendente |" in body) == (c.priority is None), view.label
        assert ("| Método de verificação | pendente |" in body) == (c.verification_method is None), view.label
        assert ("| Tipo | pendente |" in body) == (c.type is None), view.label
        assert f"| Declaração | {c.statement} |" in body
        assert f"chave `{c.key}`" in body


def test_srs_numbers_every_requirement_once_with_its_requirement_id(files, catalog):
    srs = text(files, "srs.md")
    labels = re.findall(r"^#+ (REQ-\d{3}) · ", srs, flags=re.M)
    assert sorted(labels) == [f"REQ-{n:03d}" for n in range(1, len(catalog.requirements) + 1)]
    for view in catalog.requirements:
        heading = block(srs, view.label).splitlines()[0]
        assert (f"`{view.requirement_id}`" in heading) == (view.requirement_id is not None)


def test_srs_groups_requirements_by_type_and_quality_attribute(files, catalog):
    srs = text(files, "srs.md")
    groups = {
        "4.1 Requisitos funcionais": [(ENTREVISTA, "c0-R1"), (ENTREVISTA, "c0-R2"), (ATA, "c1-R1"),
                                      (ENTREVISTA, "c0-R7")],
        "4.2.1 Desempenho (`performance`)": [(ENTREVISTA, "c0-R3"), (ENTREVISTA, "c0-R4"), (ATA, "c1-R2")],
        "4.2.2 Segurança (`security`)": [(ENTREVISTA, "c0-R5")],
        "4.3 Restrições": [(ENTREVISTA, "c0-R6")],
        "4.4 Tipo pendente (C3)": [(ENTREVISTA, "c0-R8")],
    }
    for title, members in groups.items():
        found = re.findall(r"^#+ (REQ-\d{3}) · ", section(srs, title), flags=re.M)
        assert found == sorted(label_of(catalog, *m) for m in members), title


def test_srs_highlights_requirements_in_human_review(files, catalog):
    srs = text(files, "srs.md")
    review = {label_of(catalog, ENTREVISTA, "c0-R5"), label_of(catalog, ENTREVISTA, "c0-R8")}
    for view in catalog.requirements:
        assert ("> **Em revisão humana**" in block(srs, view.label)) == (view.label in review), view.label
    assert "| Status | em revisão humana (`needs_review`) |" in block(srs, label_of(catalog, ENTREVISTA, "c0-R5"))


def test_srs_keeps_the_statement_before_refinement(files, catalog):
    srs = text(files, "srs.md")
    refined = block(srs, label_of(catalog, ENTREVISTA, "c0-R3"))
    assert "| Declaração antes do refinamento | O sistema deve avisar o responsável quando a calibração vencer. |" in refined
    assert "| Refinamento | aceito, revisão 1 |" in refined
    assert "| Refinamento | recusado |" in block(srs, label_of(catalog, ENTREVISTA, "c0-R5"))
    assert "| Refinamento | chamada falhou |" in block(srs, label_of(catalog, ENTREVISTA, "c0-R1"))
    assert "| Refinamento | não selecionado |" in block(srs, label_of(catalog, ENTREVISTA, "c0-R2"))


def test_srs_marks_quote_outside_the_chunk_and_unrecorded_requirements(files, catalog):
    srs = text(files, "srs.md")
    r6 = block(srs, label_of(catalog, ENTREVISTA, "c0-R6"))
    assert "**não aparece no chunk citado, P3**" in r6
    assert "| Status | pendente: não gravado no grafo (W1:" in r6
    assert "| Fonte | pendente (sem evidência, P1) |" in block(srs, label_of(catalog, ENTREVISTA, "c0-R8"))
    assert "fora do corpus do caso (P2)" in block(srs, label_of(catalog, ENTREVISTA, "c0-R7"))


def test_srs_lists_actors_with_their_sources(files):
    srs = text(files, "srs.md")
    actors = section(srs, "3. Stakeholders e atores")
    row = next(line for line in actors.splitlines() if line.startswith("| Coordenadora do laboratório |"))
    assert "D1 `code/domain/fixtures/corpus/entrevista_sintetica.txt`" in row
    assert "D2 `code/ingestion/fixtures/ata_sintetica.md`" in row
    assert f"| técnico | stakeholder | caso `{ENTREVISTA}`, chave `c0-A3` | pendente | W4:" in actors


def test_conditions_share_the_numbering_and_differ_in_the_refinement(catalog):
    other = build_catalog(load(A, RUNS, CONFIG))
    assert [(v.label, v.case_id, v.candidate.key) for v in other.requirements] == \
           [(v.label, v.case_id, v.candidate.key) for v in catalog.requirements]
    r3 = next(v for v in other.requirements if v.candidate.key == "c0-R3")
    assert r3.refinement == "recusado"
    assert r3.candidate.statement == "O sistema deve avisar o responsável quando a calibração vencer."


# Instância do ReqKG


def test_instance_counts_and_digest_come_from_the_exported_records(files):
    data = json.loads(files["instancia_reqkg.json"])
    state = data["logical_state"]
    assert state["nodes"] == dict(sorted(Counter(n["label"] for n in data["nodes"]).items()))
    assert state["relations"] == dict(sorted(Counter(r["type"] for r in data["relations"]).items()))
    nodes = sorted(([[n["label"]], n["properties"]] for n in data["nodes"]), key=canonical)
    relations = sorted(([r["type"], [r["source"]["label"], r["source"]["id"]],
                         [r["target"]["label"], r["target"]["id"]], r["properties"]] for r in data["relations"]),
                       key=canonical)
    assert hashlib.sha256(canonical({"nodes": nodes, "relations": relations}).encode()).hexdigest() == state["sha256"]
    summary = text(files, "instancia_resumo.md")
    assert f"SHA-256 do estado lógico: `{state['sha256']}`" in summary
    for label, count in state["nodes"].items():
        assert re.search(rf"\| `{label}` \| {count} \|", summary), label


def test_instance_has_only_traceable_records(files):
    data = json.loads(files["instancia_reqkg.json"])
    statements = {n["properties"]["statement"] for n in data["nodes"] if n["label"] == "Requirement"}
    for rejected in ("Os dados de uso devem ser guardados por dois anos para auditoria.",
                     "A coordenação deve listar os equipamentos que exigem calibração.",
                     "O sistema deve funcionar no celular."):
        assert rejected not in statements
    for item in [*data["nodes"], *data["relations"]]:
        if "evidence_json" in item["properties"]:
            evidence = json.loads(item["properties"]["evidence_json"])
            assert evidence and all(e["source_id"] and e["chunk_id"] for e in evidence)
    contract = [r for r in data["relations"] if r["type"] not in ("CONTAINS", "SUPPORTS")]
    assert contract and all("evidence_json" in r["properties"] for r in contract)


def test_refined_requirement_keeps_the_identifier_of_the_shared_extraction(files, catalog):
    inputs = catalog.inputs
    shared = to_records(inputs.shared[ENTREVISTA], inputs.case_corpus(ENTREVISTA), inputs.confidence_threshold)
    node = next(n for n in json.loads(files["instancia_reqkg.json"])["nodes"]
                if n["label"] == "Requirement" and n["properties"].get("revision") == 1
                and n["properties"]["previous_statement"].startswith("O sistema deve avisar"))
    assert node["id"] == shared.key_to_id["c0-R3"]


def test_actor_from_two_cases_unites_the_evidence(files):
    data = json.loads(files["instancia_reqkg.json"])
    actor = next(n for n in data["nodes"] if n["label"] == "Actor"
                 and n["properties"]["name"] == "Coordenadora do laboratório")
    sources = {e["source_id"] for e in json.loads(actor["properties"]["evidence_json"])}
    assert len(sources) == 2


# Matriz de proveniência


def test_matrix_has_one_row_per_evidence_and_checks_each_quote(files, catalog):
    rows = matrix(files)
    assert len(rows) == sum(max(1, len(v.candidate.evidence)) for v in catalog.requirements)
    chunks = {c.chunk_id: c.text.casefold() for c in catalog.inputs.chunks}
    for row in rows:
        if row["citacao_no_chunk"] == "sim":
            assert " ".join(row["citacao"].casefold().split()) in " ".join(chunks[row["chunk_id"]].split())
        if row["citacao_no_chunk"] == "não":
            assert row["citacao"].casefold() not in chunks[row["chunk_id"]]
    status = {r["chave"]: r["citacao_no_chunk"] for r in rows if r["caso"] == ENTREVISTA}
    assert status["c0-R1"] == "sim"
    assert status["c0-R6"] == "não"
    assert status["c0-R7"] == "chunk fora do corpus do caso"
    r7 = next(r for r in rows if r["chave"] == "c0-R7")
    assert r7["chunk_id"] in chunks and r7["citacao"].casefold() in chunks[r7["chunk_id"]], \
        "o chunk existe na ingestão, mas é de outro documento, que o modelo não viu neste caso"
    assert status["c0-R8"] == "sem evidência"


def test_matrix_markdown_matches_the_csv(files):
    md = text(files, "matriz_proveniencia.md")
    for row in matrix(files):
        line = next(line for line in md.splitlines() if line.startswith(f"| {row['requisito']} | ")
                    and line.count("|") == 8)
        assert line.rstrip().endswith(f"| {row['citacao_no_chunk']} |")
        if row["citacao"]:
            assert f"“{row['citacao']}”" in line


# Relatório de lacunas


def rules_md() -> dict[str, str]:
    found = {}
    for line in RULES_MD.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\| ([CPKGW]\d) \| (?:\w+ \| )?(.+?) \|$", line)
        if match:
            found[match.group(1)] = match.group(2)
    return found


def test_gap_report_explains_every_rule_as_rules_md(files):
    report = text(files, "relatorio_lacunas.md")
    explained = rules_md()
    for rule_id in [*(r.rule_id for r in RULES), "W1", "W2", "W3", "W4", "W5", "W6"]:
        assert f"### {rule_id}. {explained[rule_id]}" in report or f"#### {rule_id}. {explained[rule_id]}" in report
    assert f"G3 ({explained['G3']})" in report


def test_gap_report_counts_are_the_rules_over_the_final_outputs(files, catalog):
    report = text(files, "relatorio_lacunas.md")
    counts = Counter(v.rule_id for f in catalog.inputs.finals if f.output for v in check_all(f.output, catalog.inputs.case_corpus(f.case_id)))
    for rule in RULES:
        assert re.search(rf"\| {rule.rule_id} \| [^|]+ \| {counts[rule.rule_id]} \|", report), rule.rule_id
    k3 = section(report, f"K3. {rules_md()['K3']}")
    r1, r2 = label_of(catalog, ENTREVISTA, "c0-R1"), label_of(catalog, ENTREVISTA, "c0-R2")
    assert f"- {r1}, {r2}: ciclo em depends_on" in k3


def test_gap_report_lists_refusals_review_and_unquantified_attributes(files, catalog):
    report = text(files, "relatorio_lacunas.md")
    w1 = section(report, f"W1. {rules_md()['W1']}")
    for key in ("c0-R6", "c0-R7", "c0-R8"):
        assert f"- {label_of(catalog, ENTREVISTA, key)}: requisito sem evidência que resolve" in w1
    assert "ator 'técnico'" in section(report, f"W4. {rules_md()['W4']}")
    assert "Registradas pelo executor" in report and "rejections.jsonl" in report
    review = section(report, "Requisitos em revisão humana")
    assert {m for m in re.findall(r"^- (REQ-\d{3})", review, flags=re.M)} == {
        label_of(catalog, ENTREVISTA, "c0-R5"), label_of(catalog, ENTREVISTA, "c0-R8")}
    unquantified = section(report, "Atributos de qualidade sem valor quantitativo")
    assert f"- {label_of(catalog, ENTREVISTA, 'c0-R4')}: desempenho. Valor quantitativo pendente. " \
           "Marca de valor pendente: sim" in unquantified
    refused = section(report, "Refinamentos recusados")
    assert f"- {label_of(catalog, ENTREVISTA, 'c0-R5')} (caso `{ENTREVISTA}`): G3" in refused
    failed = section(report, "Chamadas de refinamento que falharam")
    assert "`api_error`" in failed and "`invalid_output`" in failed
    assert set(re.findall(r"^- (REQ-\d{3}) \(caso", failed, flags=re.M)) == {
        label_of(catalog, ENTREVISTA, "c0-R1"), label_of(catalog, ENTREVISTA, "c0-R4")}
    assert f"- `{DESCRICAO}`: `invalid_output`" in section(report, "Casos sem saída nesta condição")


def test_gap_report_ends_with_space_for_the_author(files):
    report = text(files, "relatorio_lacunas.md")
    limits = report.split("## Limitações observadas\n", 1)[1]
    assert "O gerador não escreve nesta seção." in limits
    assert limits.count("_A preencher pelo autor._") == 3


def test_pilot_run_and_ingestion_hash_without_file_are_shown(tmp_path, monkeypatch):
    """Uma corrida com PROMISE registra o hash da entrada do PROMISE, que não fica em data/processed/ingestion/."""
    import shutil
    from deliverables import inputs as module

    root = tmp_path / "repo"
    shutil.copytree(RUNS / RUN_ID, root / "runs" / RUN_ID)
    shutil.copy(CONFIG, root / "experiment.toml")
    (root / "ingestion").mkdir()
    shutil.copy(REPO_ROOT / "data" / "processed" / "ingestion" / "fixture.json", root / "ingestion" / "fixture.json")
    manifest_path = root / "runs" / RUN_ID / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    promise = "f" * 64
    manifest |= {"pilot": True, "ingestion_sha256": [*manifest["ingestion_sha256"], promise]}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", root)
    monkeypatch.setattr(module, "INGESTION_DIR", root / "ingestion")

    srs = generate(B, NAME, root / "runs", root / "experiment.toml")["srs.md"].decode("utf-8")
    assert "> - Corrida piloto: sim. Não entra no relatório como resultado." in srs
    assert "> - Ingestão: `ingestion/fixture.json`" in srs
    assert f"> - Entrada da corrida sem arquivo de ingestão lido aqui: SHA-256 `{promise}`." in srs


def test_set_file_is_ingested_in_memory_and_checked_against_the_manifest(files):
    """E2-5: --ingestion aceita o .toml do conjunto, como o executor e as métricas."""
    processed = REPO_ROOT / "data" / "processed" / "ingestion" / "fixture.json"
    before = processed.read_bytes()
    from_json = load(B, RUNS, CONFIG)
    from_toml = load(B, RUNS, CONFIG, [SET_FILE])
    assert processed.read_bytes() == before, "a ingestão em memória não grava nada"
    assert (from_toml.documents, from_toml.chunks) == (from_json.documents, from_json.chunks)
    entry = from_toml.files["ingestion:code/ingestion/fixtures/fixture.toml"]
    assert entry.sha256 == from_toml.manifest.ingestion_sha256[0] == hashlib.sha256(before).hexdigest()
    generated = generate(B, NAME, RUNS, CONFIG, [SET_FILE])
    assert generated["matriz_proveniencia.csv"] == files["matriz_proveniencia.csv"]
    assert "--ingestion code/ingestion/fixtures/fixture.toml" in json.loads(generated["origem.json"])["command"]


# Erros com mensagem útil


@pytest.mark.parametrize("call, message", [
    (lambda: generate(Selection(RUN_ID, Condition.REQKG_GROUNDED, 1), NAME, RUNS, CONFIG), "--run-index 1"),
    (lambda: generate(Selection("nao-existe", Condition.REQKG_GROUNDED, 0), NAME, RUNS, CONFIG),
     "corrida não encontrada"),
    (lambda: generate(B, NAME, RUNS), "difere do config_sha256 da corrida"),
    (lambda: generate(B, "../fora", RUNS, CONFIG), "--name"),
    (lambda: generate(Selection(RUN_ID, Condition.REQKG_GROUNDED, 0, ("outro",)), NAME, RUNS, CONFIG),
     "casos ['outro'] não existem"),
    (lambda: generate(B, NAME, RUNS, CONFIG, [OTHER_SET.with_name("ingestion.json")]), "não está em ingestion_sha256"),
    (lambda: generate(B, NAME, RUNS, CONFIG, [OTHER_SET]), "ingerido em memória"),
    (lambda: generate(B, NAME, RUNS, CONFIG, [RULES_MD]), "arquivo de conjunto (.toml) ou a saída"),
])
def test_bad_inputs_fail_with_a_useful_message(call, message):
    with pytest.raises(DeliverableError, match=re.escape(message)):
        call()


def test_cli_reports_errors_without_traceback(capsys, tmp_path):
    code = main(["nao-existe", "--run-index", "0", "--name", NAME, "--runs-dir", str(RUNS), "--output-root",
                 str(tmp_path)])
    assert code == 2
    assert capsys.readouterr().err.startswith("erro: code/deliverables/fixtures/runs/nao-existe: corrida não encontrada")
