"""Diferença entre duas ingestões do mesmo conjunto. Alimenta a invalidação no grafo.

Chunk mantido é chunk com o mesmo `chunk_id`, isto é, mesma fonte, mesmo texto e mesma ocorrência.
Posição (`index`, `char_start`, `char_end`) pode mudar num chunk mantido e vem da ingestão nova.
"""

from enum import StrEnum

from domain.models import ChunkId, ContractModel, Sha256, SourceId
from ingestion.corpus import IngestedSet


class DocumentStatus(StrEnum):
    """Estado do conteúdo do documento, medido pelo SHA-256 do texto normalizado."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


class DocumentDiff(ContractModel):
    source_id: SourceId
    path: str
    status: DocumentStatus
    previous_sha256: Sha256 | None
    sha256: Sha256 | None
    metadata_changed: bool
    added: list[ChunkId]
    removed: list[ChunkId]
    kept: list[ChunkId]


class IngestionDiff(ContractModel):
    chunking_changed: bool
    documents: list[DocumentDiff]

    @property
    def removed_chunks(self) -> list[str]:
        return [chunk for d in self.documents for chunk in d.removed]

    @property
    def added_chunks(self) -> list[str]:
        return [chunk for d in self.documents for chunk in d.added]

    @property
    def changed(self) -> bool:
        return self.chunking_changed or any(
            d.status is not DocumentStatus.UNCHANGED or d.metadata_changed or d.added or d.removed
            for d in self.documents
        )


def diff(previous: IngestedSet, current: IngestedSet) -> IngestionDiff:
    """Função pura. Documentos em ordem de caminho. Chunks na ordem do arquivo de onde vêm:
    adicionados e mantidos pela ingestão nova, removidos pela anterior."""
    before = {d.source_id: d for d in previous.documents}
    after = {d.source_id: d for d in current.documents}
    reports = []
    for source in sorted(before.keys() | after.keys(), key=lambda s: (after.get(s) or before[s]).path):
        old, new = before.get(source), after.get(source)
        old_ids = [c.chunk_id for c in previous.chunks_of(source)]
        new_ids = [c.chunk_id for c in current.chunks_of(source)]
        old_set, new_set = set(old_ids), set(new_ids)
        if old is None:
            status = DocumentStatus.ADDED
        elif new is None:
            status = DocumentStatus.REMOVED
        elif old.sha256 != new.sha256:
            status = DocumentStatus.MODIFIED
        else:
            status = DocumentStatus.UNCHANGED
        reports.append(
            DocumentDiff(
                source_id=source,
                path=(new or old).path,
                status=status,
                previous_sha256=old.sha256 if old else None,
                sha256=new.sha256 if new else None,
                metadata_changed=bool(old and new and (old.kind, old.title) != (new.kind, new.title)),
                added=[c for c in new_ids if c not in old_set],
                removed=[c for c in old_ids if c not in new_set],
                kept=[c for c in new_ids if c in old_set],
            )
        )
    return IngestionDiff(chunking_changed=previous.chunking != current.chunking, documents=reports)
