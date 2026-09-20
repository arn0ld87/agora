"""Persistenz des Graph-Build-Checkpoints als Projekt-Sidecar (Issue #1472b).

Warum diese Datei hier und nicht im Service
-------------------------------------------
``tests/test_no_json_io_leakage.py`` (Issue #13) verbietet ``app/services``
und ``app/api`` den direkten Zugriff auf ``utils.json_io``: I/O gehoert
hinter einen Port, damit die Domaenenlogik nicht an einer konkreten
Ablageform klebt. Der etablierte Port dafuer ist der
``SimulationArtifactStore`` (``services/artifact_store.py``) — der deckt
aber ``uploads/simulations/<sim_id>/`` ab.

Der Graph-Build-Checkpoint ist kein Simulations-, sondern ein
**Projekt**-Sidecar: er liegt neben ``extracted_text.txt`` und dem
Dokument-Manifest im Projektverzeichnis, weil ein Resume-Versuch einen
eigenen neuen Run anlegt und der Fortschritt trotzdem ueber alle Versuche
hinweg zum Graph-Build-Vorhaben des Projekts gehoert. Fuer diese Klasse von
Artefakten ist die Repository-Schicht der Ort — dieselbe, in der auch
``project_repository`` und ``llm_profile_repository`` liegen.

Persistenz-Invariante des Repos: atomar mit ``fsync``
(``write_json_atomic``). Ein fehlgeschlagener Schreibvorgang wird NICHT
geschluckt, er propagiert — der Build soll sichtbar scheitern, statt
unbemerkt ohne aktuellen Checkpoint weiterzulaufen.
"""
from __future__ import annotations

import os
from typing import Optional

from ..contracts.graph_build_checkpoint_contract import GraphBuildCheckpoint
from ..models.project import ProjectManager
from ..utils.json_io import read_json_file, write_json_atomic

CHECKPOINT_FILENAME = "graph_build_checkpoint.json"

__all__ = [
    "CHECKPOINT_FILENAME",
    "clear_checkpoint",
    "load_checkpoint",
    "save_checkpoint",
]


def _checkpoint_path(project_id: str) -> str:
    return os.path.join(ProjectManager._get_project_dir(project_id), CHECKPOINT_FILENAME)


def load_checkpoint(project_id: str) -> Optional[GraphBuildCheckpoint]:
    """Laedt den persistierten Checkpoint, falls vorhanden und valide.

    Ein defekter oder fremdformatiger Checkpoint gilt als "kein Checkpoint"
    (``None``) — er darf einen Resume-Versuch nicht mit einer
    ``ValidationError`` zum Absturz bringen; der Aufrufer faellt dann auf
    den Restart-Pfad zurueck.
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

    Ein I/O-Fehler propagiert unveraendert (keine Auffangbehandlung hier) —
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
