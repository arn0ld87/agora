"""Checkpoint-Persistenz für Graph-Build-Resume (Issue #1472b).

``GraphBuilderService.add_text_batches`` verarbeitet Chunks parallel
(``ThreadPoolExecutor``) und damit außerhalb ihrer Ursprungsreihenfolge —
ein einzelner "höchster Cursor" wie bei
``EmbeddingMigrationProgress.last_processed_id`` (Vorbild aus
``embedding_reembedder.py``) reicht deshalb nicht: der Checkpoint hält die
tatsächliche MENGE bereits committeter Chunk-Indizes, nicht nur einen
Höchstwert.

Persistiert je Projekt (nicht je Run-ID): ein Resume-Versuch legt einen
eigenen, neuen Run an (dieselbe Kette wie ``restart``), der Fortschritt
selbst gehört aber zum Graph-Build-Vorhaben des Projekts als Ganzes und muss
über mehrere Versuche (Original + Resume 1 + Resume 2 …) hinweg erhalten
bleiben. Deshalb liegt die Datei im Projektverzeichnis
(``ProjectManager._get_project_dir``), nicht unter
``ArtifactLocator.run_dir(run_id)``.

Persistenz-Invariante des Repos: Schreibvorgänge sind atomar mit ``fsync``
(``write_json_atomic``); ein fehlgeschlagener Checkpoint-Schreibvorgang wird
NICHT geschluckt — er propagiert, damit der Build sichtbar scheitert statt
unbemerkt ohne Checkpoint weiterzulaufen.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..models.project import ProjectManager
from ..utils.json_io import read_json_file, write_json_atomic

CHECKPOINT_FILENAME = "graph_build_checkpoint.json"

_STRICT = ConfigDict(extra="forbid")


class GraphBuildCheckpoint(BaseModel):
    """Fortschritts-Checkpoint eines ``graph_build``-Laufs.

    ``chunk_size``/``chunk_overlap``/``manifest_anchored`` werden
    mitgeführt, weil ``TextProcessor.split_text`` bzw.
    ``split_text_into_chunks_with_documents`` deterministisch, aber NICHT
    stabil gegen Parameter- oder Methodenänderungen sind — ein Chunk-Index
    bedeutet nur dann dasselbe Textstück wie beim Original-Lauf, wenn Größe,
    Overlap UND die Chunking-Methode (manifest-verankert vs. Legacy)
    unverändert sind.
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


def _checkpoint_path(project_id: str) -> str:
    return os.path.join(ProjectManager._get_project_dir(project_id), CHECKPOINT_FILENAME)


def load_checkpoint(project_id: str) -> Optional[GraphBuildCheckpoint]:
    """Lädt den persistierten Checkpoint, falls vorhanden und valide.

    Ein defekter/fremdformatiger Checkpoint gilt als "kein Checkpoint"
    (``None``) — er darf einen Resume-Versuch nicht mit einer
    ``ValidationError`` zum Absturz bringen; der Aufrufer fällt dann auf
    den Restart-Pfad zurück.
    """
    raw = read_json_file(_checkpoint_path(project_id))
    if raw is None:
        return None
    try:
        return GraphBuildCheckpoint.model_validate(raw)
    except Exception:  # noqa: BLE001 — defekter Checkpoint faellt auf "kein Checkpoint" zurueck
        return None


def save_checkpoint(project_id: str, checkpoint: GraphBuildCheckpoint) -> None:
    """Schreibt den Checkpoint atomar mit fsync.

    Ein I/O-Fehler propagiert unverändert (keine Auffangbehandlung hier) —
    das ist Absicht: der aufrufende Build-Loop soll sichtbar scheitern statt
    unbemerkt ohne aktuellen Checkpoint weiterzulaufen.
    """
    write_json_atomic(_checkpoint_path(project_id), checkpoint.model_dump(mode="json"))


def clear_checkpoint(project_id: str) -> None:
    """Entfernt den Checkpoint nach erfolgreichem Abschluss oder explizitem Restart.

    Best effort — ein bereits fehlendes File ist kein Fehler.
    """
    try:
        os.remove(_checkpoint_path(project_id))
    except FileNotFoundError:
        pass


def checkpoint_is_resumable(
    checkpoint: Optional[GraphBuildCheckpoint],
    *,
    graph_id: Optional[str],
    total_chunks: int,
    chunk_size: int,
    chunk_overlap: int,
    manifest_anchored: bool,
) -> bool:
    """Prüft, ob ein Checkpoint zum AKTUELLEN Build-Versuch passt.

    Ein Checkpoint ist nur verwertbar, wenn er densselben Graphen, dieselbe
    Chunk-Zerlegung (Größe, Overlap, Methode) UND dieselbe Gesamt-Chunkzahl
    trägt wie der Versuch, der ihn fortsetzen will, und mindestens einen
    abgeschlossenen Chunk verzeichnet. Ein angebotenes Resume, das doch bei
    null beginnt, ist schlimmer als keins.
    """
    if checkpoint is None or not graph_id:
        return False
    if checkpoint.graph_id != graph_id:
        return False
    if checkpoint.total_chunks != total_chunks:
        return False
    if checkpoint.chunk_size != chunk_size or checkpoint.chunk_overlap != chunk_overlap:
        return False
    if checkpoint.manifest_anchored != manifest_anchored:
        return False
    return bool(checkpoint.completed_chunk_indices)


def resume_capability_for_checkpoint(
    checkpoint: Optional[GraphBuildCheckpoint],
) -> dict[str, Any]:
    """``resume_capability`` für einen Build-Loop, der seinen eigenen
    Checkpoint bereits im Speicher hält (keine erneute Disk-Lesung, kein
    Graph-Identitäts-Check nötig — der Checkpoint gehört per Konstruktion
    zu diesem Versuch)."""
    if checkpoint is not None and checkpoint.completed_chunk_indices:
        return {
            "available": True,
            "action": "resume",
            "label": "Resume graph build",
        }
    return {
        "available": True,
        "action": "restart",
        "label": "Restart graph build",
    }


def resume_capability_for_run(run: Mapping[str, Any]) -> dict[str, Any]:
    """Bestimmt ``resume_capability`` für einen terminalisierten ``graph_build``-Run.

    Leichtgewichtige Prüfung (nur Graph-Identität + "mindestens ein Chunk
    fertig") — für Massen-Terminalisierungen wie Shutdown-Hook und
    Startup-Reconciliation, wo ein volles Re-Chunking pro Run zu teuer
    wäre. Feingranularer validiert erst der eigentliche Resume-Versuch
    (``checkpoint_is_resumable``, inkl. Chunk-Parameter) — bei Ablehnung
    fällt er sauber auf den Restart-Pfad zurück, das UI-Angebot "resume"
    ist also im schlimmsten Fall ein no-op, nie eine stille Dateninkonsistenz.
    """
    linked_ids = run.get("linked_ids") or {}
    project_id = linked_ids.get("project_id") or run.get("entity_id")
    graph_id = linked_ids.get("graph_id")
    restart_capability = {
        "available": True,
        "action": "restart",
        "label": "Restart graph build",
    }
    if not project_id or not graph_id:
        return restart_capability
    checkpoint = load_checkpoint(project_id)
    if (
        checkpoint is not None
        and checkpoint.graph_id == graph_id
        and checkpoint.completed_chunk_indices
    ):
        return {
            "available": True,
            "action": "resume",
            "label": "Resume graph build",
        }
    return restart_capability
