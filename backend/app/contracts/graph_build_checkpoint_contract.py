"""Graph-Build-Checkpoint-Contract (Issue #1472b).

Rein interner Zustandsvertrag — analog ``EmbeddingMigrationProgress``
(``embedding_contract.py``): lebt unter ``contracts/`` wie jedes strukturierte
Pydantic-Modell dieses Repos, überquert aber nie die HTTP-API-Grenze (er
landet nie in einer Response, insbesondere nicht in ``resume_capability`` —
das bleibt ein einfaches ``{available, action, label}``-Dict) und wird
deshalb bewusst NICHT in ``dump_schemas.CONTRACTS`` aufgenommen.
"""
from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")


class GraphBuildCheckpoint(BaseModel):
    """Fortschritts-Checkpoint eines ``graph_build``-Laufs.

    ``GraphBuilderService.add_text_batches`` verarbeitet Chunks parallel
    (``ThreadPoolExecutor``) und damit außerhalb ihrer Ursprungsreihenfolge
    — ein einzelner "höchster Cursor" wie bei
    ``EmbeddingMigrationProgress.last_processed_id`` reicht deshalb nicht:
    der Checkpoint hält die tatsächliche MENGE bereits committeter
    Chunk-Indizes, nicht nur einen Höchstwert.

    ``chunk_size``/``chunk_overlap``/``manifest_anchored`` werden
    mitgeführt, weil ``TextProcessor.split_text`` bzw.
    ``split_text_into_chunks_with_documents`` deterministisch, aber NICHT
    stabil gegen Parameter- oder Methodenänderungen sind — ein Chunk-Index
    bedeutet nur dann dasselbe Textstück wie beim Original-Lauf, wenn
    Größe, Overlap UND die Chunking-Methode (manifest-verankert vs.
    Legacy) unverändert sind.
    """

    model_config = _STRICT

    graph_id: str
    total_chunks: int = Field(ge=0)
    chunk_size: int = Field(gt=0)
    chunk_overlap: int = Field(ge=0)
    manifest_anchored: bool
    completed_chunk_indices: list[int] = Field(default_factory=list)
    # JSON-Objektschlüssel sind immer Strings — der Chunk-Index steckt als
    # str(idx) im Key, der Wert ist die zugehörige Episode-UUID.
    episode_uuids: dict[str, str] = Field(default_factory=dict)
    updated_at: datetime

    def with_completed_chunk(self, index: int, episode_uuid: str) -> "GraphBuildCheckpoint":
        """Liefert einen neuen Checkpoint mit einem zusätzlich abgeschlossenen Chunk.

        Unveränderlich (kein In-Place-Mutate) — der Aufrufer hält die
        jeweils aktuelle Referenz selbst in seiner Closure.
        """
        indices = sorted(set(self.completed_chunk_indices) | {index})
        uuids = {**self.episode_uuids, str(index): episode_uuid}
        return self.model_copy(
            update={
                "completed_chunk_indices": indices,
                "episode_uuids": uuids,
                "updated_at": datetime.now(UTC),
            }
        )
