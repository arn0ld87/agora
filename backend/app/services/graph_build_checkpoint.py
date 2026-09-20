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

Das reine Datei-I/O liegt nicht hier, sondern in
``app/repositories/graph_build_checkpoint_repository.py``: ``app/services``
darf ``utils.json_io`` nicht direkt importieren (Issue #13, geprüft von
``tests/test_no_json_io_leakage.py``). Dieses Modul hält die Logik —
Gültigkeit eines Checkpoints und das daraus abgeleitete
``resume_capability`` — und reicht die Persistenz an das Repository weiter.

Persistenz-Invariante des Repos: Schreibvorgänge sind atomar mit ``fsync``;
ein fehlgeschlagener Checkpoint-Schreibvorgang wird NICHT geschluckt — er
propagiert, damit der Build sichtbar scheitert statt unbemerkt ohne
Checkpoint weiterzulaufen.

Der Vertrag selbst (``GraphBuildCheckpoint``) liegt unter
``app/contracts/graph_build_checkpoint_contract.py`` — analog
``EmbeddingMigrationProgress``: ein strukturiertes Pydantic-Modell gehört
nach Contracts-first unter ``contracts/``, auch wenn es (wie hier) nie die
HTTP-API-Grenze überquert und deshalb bewusst nicht in
``dump_schemas.CONTRACTS`` steht.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional

from ..contracts.graph_build_checkpoint_contract import GraphBuildCheckpoint
from ..repositories.graph_build_checkpoint_repository import (
    CHECKPOINT_FILENAME,
    clear_checkpoint,
    load_checkpoint,
    save_checkpoint,
)

# Persistenz wird aus dem Repository re-exportiert, damit die bestehenden
# Aufrufer (graph_build, api/runs, process_shutdown, reconciliation) eine
# Import-Quelle behalten und nicht zwischen Logik und I/O unterscheiden
# muessen.
__all__ = [
    "CHECKPOINT_FILENAME",
    "GraphBuildCheckpoint",
    "checkpoint_is_resumable",
    "clear_checkpoint",
    "load_checkpoint",
    "resume_capability_for_checkpoint",
    "resume_capability_for_run",
    "save_checkpoint",
]


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
