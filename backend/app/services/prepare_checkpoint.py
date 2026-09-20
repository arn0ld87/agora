"""Checkpoint-Persistenz für Prepare-Resume (Issue #1472c).

``_phase_generate_profiles``/``generate_profiles_from_entities`` sind der
teuerste Schritt von ``prepare_simulation`` (parallele LLM-Roundtrips pro
Entity). Wird der Webprozess mittendrin beendet (SIGTERM/Absturz), markiert
der Shutdown-Hook aus Slice 1.1 (``simulation_runner.register_cleanup`` /
``sim/process_shutdown.py``) den Run bisher immer als
``failed``/``process_restart`` — ehrlich, aber endgültig, auch wenn bereits
Dutzende Personas fertig generiert waren.

Dieses Modul haelt den Checkpoint fest: welche Cap-/Quota-Auswahl der
Original-Versuch getroffen hat (als Entity-UUID-Listen, siehe
``prepare_checkpoint_contract.PreparePersonaCheckpoint``) und welche
Profile bereits generiert sind. Ein Resume liest die Auswahl NUR per UUID
nach — er berechnet sie nie neu, weil der Graph-Lesepfad fuer Phase 1 kein
``ORDER BY`` hat (``prepare_entities.py::_cap_entities_across_types``) und
ein erneuter Read deshalb eine andere Typ-Verteilung liefern kann.

Persistenz-Invariante des Repos (analog ``graph_build_checkpoint.py``,
Slice 1.3): Schreibvorgänge sind atomar mit ``fsync``
(``write_json_atomic``); ein fehlgeschlagener Checkpoint-Schreibvorgang wird
NICHT geschluckt — er propagiert, damit die Vorbereitung sichtbar scheitert
statt unbemerkt ohne aktuellen Checkpoint weiterzulaufen.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, Optional

from ..contracts.prepare_checkpoint_contract import PreparePersonaCheckpoint
from ..utils.json_io import read_json_file, write_json_atomic
from ..utils.logger import get_logger

logger = get_logger("agora.prepare_checkpoint")

CHECKPOINT_FILENAME = "prepare_persona_checkpoint.json"

__all__ = [
    "CHECKPOINT_FILENAME",
    "PreparePersonaCheckpoint",
    "checkpoint_is_resumable",
    "checkpoint_path",
    "clear_checkpoint",
    "load_checkpoint",
    "new_checkpoint",
    "resolve_interruption_status",
    "save_checkpoint",
]


def checkpoint_path(sim_dir: str) -> str:
    return os.path.join(sim_dir, CHECKPOINT_FILENAME)


def load_checkpoint(sim_dir: str) -> Optional[PreparePersonaCheckpoint]:
    """Lädt den persistierten Checkpoint, falls vorhanden und valide.

    Ein defekter/fremdformatiger Checkpoint gilt als "kein Checkpoint"
    (``None``) — er darf einen Resume-Versuch nicht mit einer
    ``ValidationError`` zum Absturz bringen; der Aufrufer fällt dann auf
    den regulären (Neu-)Startpfad zurück.
    """
    raw = read_json_file(checkpoint_path(sim_dir))
    if raw is None:
        return None
    try:
        return PreparePersonaCheckpoint.model_validate(raw)
    except Exception:  # noqa: BLE001 — defekter Checkpoint faellt auf "kein Checkpoint" zurueck
        logger.warning(
            "Prepare-Checkpoint unter %s ist nicht lesbar, wird ignoriert",
            checkpoint_path(sim_dir),
        )
        return None


def save_checkpoint(sim_dir: str, checkpoint: PreparePersonaCheckpoint) -> None:
    """Schreibt den Checkpoint atomar mit fsync.

    Ein I/O-Fehler propagiert unverändert (keine Auffangbehandlung hier) —
    das ist Absicht: die Persona-Generierung soll sichtbar scheitern statt
    unbemerkt ohne aktuellen Checkpoint weiterzulaufen (Fehlermuster
    "ungecheckpointete Teilergebnisse", siehe Issue-Auftrag).
    """
    write_json_atomic(checkpoint_path(sim_dir), checkpoint.model_dump(mode="json"))


def clear_checkpoint(sim_dir: str) -> None:
    """Entfernt den Checkpoint nach erfolgreichem Abschluss oder ungültigem Resume.

    Best effort — ein bereits fehlendes File ist kein Fehler.
    """
    try:
        os.remove(checkpoint_path(sim_dir))
    except FileNotFoundError:
        pass


def new_checkpoint(
    *,
    simulation_id: str,
    graph_id: str,
    defined_entity_types: Optional[list[str]],
    max_agents: Optional[int],
    persona_floor: int,
    use_llm_for_profiles: bool,
    effective_quota_plan: Optional[dict[str, Any]],
    primary_entity_uuids: list[str],
    reserve_entity_uuids: list[str],
    expanded_entity_uuids: list[str],
    entities_count: int,
    entity_types: list[str],
) -> PreparePersonaCheckpoint:
    """Baut den initialen Checkpoint eines Prepare-Versuchs (noch ohne Profile)."""
    return PreparePersonaCheckpoint(
        simulation_id=simulation_id,
        graph_id=graph_id,
        defined_entity_types=(
            sorted(defined_entity_types) if defined_entity_types else None
        ),
        max_agents=max_agents,
        persona_floor=persona_floor,
        use_llm_for_profiles=use_llm_for_profiles,
        effective_quota_plan=effective_quota_plan,
        primary_entity_uuids=list(primary_entity_uuids),
        reserve_entity_uuids=list(reserve_entity_uuids),
        expanded_entity_uuids=list(expanded_entity_uuids),
        entities_count=entities_count,
        entity_types=list(entity_types),
        updated_at=datetime.now(UTC),
    )


def checkpoint_is_resumable(
    checkpoint: Optional[PreparePersonaCheckpoint],
    *,
    simulation_id: str,
    graph_id: Optional[str],
    defined_entity_types: Optional[list[str]],
    max_agents: Optional[int],
    persona_floor: int,
    use_llm_for_profiles: bool,
    effective_quota_plan: Optional[dict[str, Any]],
) -> bool:
    """Prüft, ob ein Checkpoint zum AKTUELLEN Prepare-Versuch passt.

    Ein Checkpoint ist nur verwertbar, wenn er derselben Simulation und
    demselben Graphen gehört UND alle Parameter trägt, die die Cap-/Quota-
    Auswahl bestimmen (``defined_entity_types``, ``max_agents``,
    ``persona_floor``, ``use_llm_for_profiles``, ``effective_quota_plan``)
    — UND mindestens ein Profil bereits abgeschlossen hat. Ohne
    verwertbaren Zwischenstand ist es kein Resume-Kandidat, auch wenn die
    Parameter sonst passen (Fehlermuster "Angebot ohne Deckung").
    """
    if checkpoint is None or not graph_id:
        return False
    if checkpoint.simulation_id != simulation_id:
        return False
    if checkpoint.graph_id != graph_id:
        return False
    normalized_types = sorted(defined_entity_types) if defined_entity_types else None
    if checkpoint.defined_entity_types != normalized_types:
        return False
    if checkpoint.max_agents != max_agents:
        return False
    if checkpoint.persona_floor != persona_floor:
        return False
    if checkpoint.use_llm_for_profiles != use_llm_for_profiles:
        return False
    if checkpoint.effective_quota_plan != effective_quota_plan:
        return False
    if not checkpoint.expanded_entity_uuids:
        return False
    return bool(checkpoint.completed_profiles)


def resolve_interruption_status(sim_dir: str) -> str:
    """Liefert ``"interrupted"`` oder ``"failed"`` für einen abgebrochenen Prepare-Lauf.

    Gemeinsam genutzt vom SIGTERM/atexit-Shutdown-Hook
    (``sim/process_shutdown.py`` über ``simulation_runner.register_cleanup``)
    und der Startup-Reconciliation für verwaiste Prozesse ohne
    ordentlichen Shutdown (``sim/reconciliation.py``): beide unterbrechen
    ``simulation_prepare`` an einer beliebigen Stelle, und beide müssen
    dieselbe Frage stellen — liegt ein verwertbarer Zwischenstand vor?
    Ohne mindestens ein abgeschlossenes Profil bleibt es beim ehrlichen
    ``failed`` (Fehlermuster "Angebot ohne Deckung": kein Resume-Angebot
    ohne Deckung durch echte Teilergebnisse).
    """
    checkpoint = load_checkpoint(sim_dir)
    if checkpoint is not None and checkpoint.completed_profiles:
        return "interrupted"
    return "failed"
