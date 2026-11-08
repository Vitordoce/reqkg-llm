"""Normalização do texto e corte em chunks, sem modelo.

Estratégia paragraph: cada parágrafo é um chunk. Parágrafo é uma sequência de linhas não brancas,
separada das outras por uma ou mais linhas brancas. A fronteira de um chunk depende só do próprio
parágrafo, então editar um parágrafo não mexe no identificador de nenhum outro chunk. A exceção
vem de `ocorrência`: textos repetidos são numerados em ordem, e uma edição que cria ou desfaz uma
repetição renumera as cópias seguintes daquele mesmo texto.

Parágrafo maior que size_chars é dividido em pedaços de até size_chars, da esquerda para a direita.
O corte prefere, nesta ordem, a última quebra de linha, o último fim de frase, o último espaço e,
sem nenhum deles, um corte seco que não separa letra de acento combinante. Os pedaços continuam
pertencendo ao parágrafo: editar o parágrafo só muda pedaços dele.

Estratégia window: janelas de size_chars com sobreposição de overlap_chars. Uma inserção no
início do documento troca todos os chunks. Fica disponível para comparação, não como padrão.
"""

import unicodedata
from collections import Counter

from domain import ids
from domain.config import ChunkingConfig
from domain.models import SourceChunk

Span = tuple[int, int]

SENTENCE_END = ".!?;…"


def normalize_text(text: str) -> str:
    """Remove o BOM, converte CRLF e CR em LF e normaliza para NFC."""
    text = text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", text)


def paragraph_spans(text: str) -> list[Span]:
    """Do início da primeira linha não branca ao fim da última, sem o LF final."""
    spans: list[Span] = []
    start: int | None = None
    end = position = 0
    for line in text.split("\n"):
        line_end = position + len(line)
        if line.strip():
            if start is None:
                start = position
            end = line_end
        elif start is not None:
            spans.append((start, end))
            start = None
        position = line_end + 1
    if start is not None:
        spans.append((start, end))
    return spans


def _keeps_combining(text: str, cut: int, floor: int) -> int:
    while cut > floor and unicodedata.combining(text[cut]):
        cut -= 1
    return cut


def _break_point(text: str, start: int, size: int) -> int:
    """Fim exclusivo do pedaço que começa em start, com no máximo size caracteres."""
    candidates = range(start + size, start, -1)
    for accept in (
        lambda b: text[b] == "\n",
        lambda b: text[b].isspace() and text[b - 1] in SENTENCE_END,
        lambda b: text[b].isspace(),
    ):
        for b in candidates:
            if accept(b):
                return b
    return _keeps_combining(text, start + size, start + 1)


def split_long(text: str, start: int, end: int, size: int) -> list[Span]:
    pieces: list[Span] = []
    while end - start > size:
        cut = _break_point(text, start, size)
        piece_end = cut
        while text[piece_end - 1].isspace():
            piece_end -= 1
        pieces.append((start, piece_end))
        start = cut
        while text[start].isspace():
            start += 1
    pieces.append((start, end))
    return pieces


def paragraph_chunk_spans(text: str, size: int) -> list[Span]:
    return [piece for start, end in paragraph_spans(text) for piece in split_long(text, start, end, size)]


def window_spans(text: str, size: int, overlap: int) -> list[Span]:
    spans: list[Span] = []
    start, n = 0, len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            end = _keeps_combining(text, end, start + 1)
        spans.append((start, end))
        if end == n:
            break
        start = _keeps_combining(text, max(end - overlap, start + 1), start + 1)
    return spans


def chunk_spans(text: str, config: ChunkingConfig) -> list[Span]:
    if config.strategy == "paragraph":
        return paragraph_chunk_spans(text, config.size_chars)
    return window_spans(text, config.size_chars, config.overlap_chars)


def chunk_text(text: str, source: str, config: ChunkingConfig) -> list[SourceChunk]:
    """text já normalizado. Janelas só de espaço em branco são descartadas."""
    seen: Counter[str] = Counter()
    chunks: list[SourceChunk] = []
    for start, end in chunk_spans(text, config):
        body = text[start:end]
        if not body.strip():
            continue
        occurrence = seen[body]
        seen[body] += 1
        chunks.append(
            SourceChunk(
                chunk_id=ids.chunk_id(source, body, occurrence),
                source_id=source,
                index=len(chunks),
                occurrence=occurrence,
                char_start=start,
                char_end=end,
                text=body,
                sha256=ids.sha256_text(body),
            )
        )
    return chunks
