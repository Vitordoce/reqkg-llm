import random
import unicodedata

import pytest

from domain import ids
from domain.config import ChunkingConfig
from ingestion.chunking import chunk_text, normalize_text, paragraph_spans

SEED = 20261010
SOURCE = ids.source_id("code/ingestion/fixtures/gerado.txt")
WORDS = (
    "reserva equipamento calibração técnico coordenação agenda aviso horário sistema dados "
    "auditoria laboratório prazo relatório acesso usuário planilha conflito vencimento exportação"
).split()
SEPARATORS = ("\n\n", "\n\n\n", "\n  \n", "\n\t\n\n", "\n \n \n")


def paragraph(rng: random.Random, size: int) -> str:
    count = rng.randint(size // 4, size // 2) if rng.random() < 0.15 else rng.randint(1, 20)
    parts = []
    for i in range(count):
        parts.append(rng.choice(WORDS))
        if i < count - 1:
            parts.append(rng.choice((" ", " ", " ", ". ", "\n", ", ", "  ")))
    return "".join(parts).strip() or "x"


def document(rng: random.Random, size: int) -> list[str]:
    paragraphs = [paragraph(rng, size) for _ in range(rng.randint(1, 25))]
    for i in range(1, len(paragraphs)):
        if rng.random() < 0.12:
            paragraphs[i] = rng.choice(paragraphs[:i])
    return paragraphs


def assemble(paragraphs: list[str], separators: list[str], lead: str, tail: str) -> tuple[str, list[tuple[int, int]]]:
    text, spans = lead, []
    for i, p in enumerate(paragraphs):
        if i:
            text += separators[i - 1]
        spans.append((len(text), len(text) + len(p)))
        text += p
    return text + tail, spans


def edit(rng: random.Random, paragraphs: list[str], size: int) -> tuple[str, list[str], int]:
    """Uma edição de um parágrafo. Devolve o tipo, os parágrafos novos e o índice editado."""
    k = rng.randrange(len(paragraphs))
    old = paragraphs[k]
    kind = rng.choice(("word", "append", "truncate", "duplicate", "grow", "insert", "delete"))
    words = old.split(" ")
    if kind == "word":
        words[rng.randrange(len(words))] = rng.choice(WORDS) + "ç"
        new = " ".join(words).strip() or "y"
    elif kind == "append":
        new = old + " " + " ".join(rng.choice(WORDS) for _ in range(rng.randint(1, 40)))
    elif kind == "truncate":
        new = old[: rng.randint(1, len(old))].strip() or "z"
    elif kind == "duplicate":
        new = rng.choice(paragraphs)
    elif kind == "grow":
        new = old + " " + " ".join(rng.choice(WORDS) for _ in range(size // 3))
    elif kind == "insert":
        return kind, paragraphs[:k] + [paragraph(rng, size)] + paragraphs[k:], k
    else:
        if len(paragraphs) == 1:
            return "noop", paragraphs, k
        return kind, paragraphs[:k] + paragraphs[k + 1 :], k
    return kind, paragraphs[:k] + [new] + paragraphs[k + 1 :], k


def owned(chunks, span):
    if span is None:
        return []
    return [c for c in chunks if span[0] <= c.char_start < span[1]]


@pytest.mark.parametrize("size", [60, 200, 1500])
def test_editing_one_paragraph_keeps_every_other_chunk_id(size):
    """Invariante da estratégia paragraph, provado sobre textos gerados.

    Depois de editar, inserir ou apagar o parágrafo k, todo chunk que não pertence a k mantém o
    chunk_id. A única exceção permitida é a renumeração de ocorrência: um chunk depois de k cujo
    texto é igual ao texto antigo ou novo de um pedaço de k.
    """
    rng = random.Random(f"{SEED}-{size}")
    config = ChunkingConfig(strategy="paragraph", size_chars=size, overlap_chars=0)
    checked = renumbered = split_cases = 0
    for _ in range(400):
        paragraphs = document(rng, size)
        separators = [rng.choice(SEPARATORS) for _ in range(30)]
        lead, tail = rng.choice(("", "\n", "\n \n")), rng.choice(("", "\n", "\n\n"))
        kind, edited, k = edit(rng, paragraphs, size)
        if edited == paragraphs:
            continue
        old_text, old_spans = assemble(paragraphs, separators, lead, tail)
        new_text, new_spans = assemble(edited, separators, lead, tail)
        before = chunk_text(old_text, SOURCE, config)
        after = chunk_text(new_text, SOURCE, config)
        old_own = owned(before, None if kind == "insert" else old_spans[k])
        new_own = owned(after, None if kind == "delete" else new_spans[k])
        shared = {c.text for c in old_own + new_own}
        old_ids, new_ids = {c.chunk_id for c in before}, {c.chunk_id for c in after}
        anchor = old_spans[k][0] if k < len(old_spans) else len(old_text)

        for c in before:
            if c in old_own or c.chunk_id in new_ids:
                continue
            assert c.text in shared and c.char_start >= anchor, (kind, k, c.text, old_text, new_text)
            renumbered += 1
        for c in after:
            if c in new_own or c.chunk_id in old_ids:
                continue
            assert c.text in shared, (kind, k, c.text, old_text, new_text)
        assert all(len(c.text) <= size for c in before + after)
        split_cases += any(len(owned(before, s)) > 1 for s in old_spans)
        checked += 1

    assert checked >= 300
    assert renumbered > 0, "o gerador não exercitou a exceção de ocorrência"
    assert split_cases > 0, "o gerador não exercitou parágrafo maior que size_chars"


def test_paragraph_spans_cover_text_and_ignore_blank_lines():
    text = "\n  \nprimeiro\nsegue\n\n \t \n\nsegundo  \n\n"
    spans = paragraph_spans(text)
    assert [text[a:b] for a, b in spans] == ["primeiro\nsegue", "segundo  "]


def test_long_paragraph_prefers_line_then_sentence_then_space():
    config = ChunkingConfig(strategy="paragraph", size_chars=20, overlap_chars=0)
    text = "abc def. ghi jkl mno\npqr stu vwx yz abc. def"
    pieces = [c.text for c in chunk_text(text, SOURCE, config)]
    assert pieces == ["abc def. ghi jkl mno", "pqr stu vwx yz abc.", "def"]
    assert [c.text for c in chunk_text("x" * 45, SOURCE, config)] == ["x" * 20, "x" * 20, "x" * 5]


def test_hard_cut_does_not_separate_combining_mark():
    config = ChunkingConfig(strategy="paragraph", size_chars=5, overlap_chars=0)
    text = "abcd" + "e\u0301" * 3
    pieces = [c.text for c in chunk_text(text, SOURCE, config)]
    assert "".join(pieces) == text
    assert not any(unicodedata.combining(p[0]) for p in pieces)


def test_repeated_text_gets_distinct_ids_by_occurrence():
    config = ChunkingConfig(strategy="paragraph", size_chars=100, overlap_chars=0)
    chunks = chunk_text("Sim.\n\nNão.\n\nSim.", SOURCE, config)
    assert [(c.text, c.occurrence) for c in chunks] == [("Sim.", 0), ("Não.", 0), ("Sim.", 1)]
    assert len({c.chunk_id for c in chunks}) == 3


def test_documented_exception_editing_a_repeated_paragraph_renumbers_later_copies():
    """Some o identificador da última cópia, e cada identificador restante passa a apontar para a
    cópia seguinte, de texto idêntico. A citação continua batendo; a posição muda."""
    config = ChunkingConfig(strategy="paragraph", size_chars=100, overlap_chars=0)
    before = chunk_text("Sim.\n\nA.\n\nSim.\n\nB.\n\nSim.", SOURCE, config)
    after = chunk_text("Talvez.\n\nA.\n\nSim.\n\nB.\n\nSim.", SOURCE, config)
    lost = {c.chunk_id for c in before} - {c.chunk_id for c in after}
    assert [(c.text, c.occurrence) for c in before if c.chunk_id in lost] == [("Sim.", 2)]
    assert [(c.index, c.occurrence) for c in after if c.text == "Sim."] == [(2, 0), (4, 1)]


def test_window_covers_text_with_overlap_and_shifts_on_insertion():
    config = ChunkingConfig(strategy="window", size_chars=10, overlap_chars=3)
    text = "abcdefghijklmnopqrstuvwxyz"
    chunks = chunk_text(text, SOURCE, config)
    assert [c.text for c in chunks] == ["abcdefghij", "hijklmnopq", "opqrstuvwx", "vwxyz"]
    shifted = chunk_text("0" + text, SOURCE, config)
    assert not {c.chunk_id for c in chunks} & {c.chunk_id for c in shifted}


def test_normalize_text_line_endings_bom_and_nfc():
    assert normalize_text("\ufeffa\r\nb\rc\n") == "a\nb\nc\n"
    assert normalize_text("calibrac\u0327a\u0303o") == "calibração"
