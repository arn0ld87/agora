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

import dataclasses
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Optional

from ..contracts.prepare_checkpoint_contract import PreparePersonaCheckpoint
from .artifact_store import resolve_default_store
from ..utils.logger import get_logger

if TYPE_CHECKING:
    from .oasis_profile_models import OasisAgentProfile

logger = get_logger("agora.prepare_checkpoint")

CHECKPOINT_FILENAME = "prepare_persona_checkpoint.json"

__all__ = [
    "CHECKPOINT_FILENAME",
    "PreparePersonaCheckpoint",
    "checkpoint_is_resumable",
        "clear_checkpoint",
    "completed_profiles_from_checkpoint",
    "load_checkpoint",
    "new_checkpoint",
    "profile_from_dict",
    "profile_to_dict",
    "resolve_interruption_status",
    "save_checkpoint",
]


def profile_to_dict(profile: "OasisAgentProfile") -> dict[str, Any]:
    """Serialisiert ein ``OasisAgentProfile`` (Dataclass) für den Checkpoint."""
    return dataclasses.asdict(profile)


def profile_from_dict(data: dict[str, Any]) -> "OasisAgentProfile":
    """Rekonstruiert ein ``OasisAgentProfile`` aus Checkpoint-Daten."""
    from .oasis_profile_models import OasisAgentProfile

    return OasisAgentProfile(**data)


def completed_profiles_from_checkpoint(
    checkpoint: PreparePersonaCheckpoint,
) -> dict[int, "OasisAgentProfile"]:
    """Baut die ``already_done``-Map (Generierungs-Index → Profil) aus dem Checkpoint.

    Ein einzelner defekter Eintrag invalidiert nicht den gesamten
    Checkpoint — er wird übersprungen (und damit beim Resume neu
    generiert), statt den Resume-Versuch komplett scheitern zu lassen.
    """
    result: dict[int, "OasisAgentProfile"] = {}
    for raw_index, profile_data in checkpoint.completed_profiles.items():
        try:
            index = int(raw_index)
            result[index] = profile_from_dict(profile_data)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Prepare-Checkpoint: Eintrag %r nicht rekonstruierbar (%s), wird uebersprungen",
                raw_index,
                exc,
            )
    return result


#: Logischer Artefaktname im ``SimulationArtifactStore`` (dort auf
#: ``prepare_persona_checkpoint.json`` abgebildet).
CHECKPOINT_ARTIFACT = "prepare_checkpoint"


def load_checkpoint(simulation_id: str) -> Optional[PreparePersonaCheckpoint]:
    """Laedt den persistierten Checkpoint, falls vorhanden und valide.

    Ein defekter/fremdformatiger Checkpoint gilt als "kein Checkpoint"
    (``None``) — er darf einen Resume-Versuch nicht mit einer
    ``ValidationError`` zum Absturz bringen; der Aufrufer faellt dann auf
    den regulaeren (Neu-)Startpfad zurueck.
    """
    raw = resolve_default_store().read_json(simulation_id, CHECKPOINT_ARTIFACT)
    if raw is None:
        return None
    try:
        return PreparePersonaCheckpoint.model_validate(raw)
    except Exception:  # noqa: BLE001 — defekter Checkpoint faellt auf "kein Checkpoint" zurueck
        logger.warning(
            "Prepare-Checkpoint von Simulation %s ist nicht lesbar, wird ignoriert",
            simulation_id,
        )
        return None


def save_checkpoint(simulation_id: str, checkpoint: PreparePersonaCheckpoint) -> None:
    """Schreibt den Checkpoint atomar mit fsync (ueber den Artefakt-Store).

    Ein I/O-Fehler propagiert unveraendert (keine Auffangbehandlung hier) —
    das ist Absicht: die Persona-Generierung soll sichtbar scheitern statt
    unbemerkt ohne aktuellen Checkpoint weiterzulaufen (Fehlermuster
    "ungecheckpointete Teilergebnisse").
    """
    resolve_default_store().write_json(
        simulation_id, CHECKPOINT_ARTIFACT, checkpoint.model_dump(mode="json")
    )


def clear_checkpoint(simulation_id: str) -> None:
    """Entfernt den Checkpoint nach erfolgreichem Abschluss oder ungueltigem Resume.

    Best effort — ein bereits fehlendes Artefakt ist kein Fehler.
    """
    resolve_default_store().delete(simulation_id, CHECKPOINT_ARTIFACT)


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
    llm_model: Optional[str] = None,
    language: Optional[str] = None,
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
        llm_model=llm_model,
        language=language,
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
    llm_model: Optional[str] = None,
    language: Optional[str] = None,
) -> bool:
    """Prüft, ob ein Checkpoint zum AKTUELLEN Prepare-Versuch passt.

    Ein Checkpoint ist nur verwertbar, wenn er derselben Simulation und
    demselben Graphen gehört UND alle Parameter trägt, die die Cap-/Quota-
    Auswahl bestimmen (``defined_entity_types``, ``max_agents``,
    ``persona_floor``, ``use_llm_for_profiles``, ``effective_quota_plan``)
    sowie die Parameter, die die Persona-INHALTE bestimmen (``llm_model``,
    ``language`` — Codex-Finding P2, PR #1539) — UND mindestens ein Profil
    bereits abgeschlossen hat. Ohne verwertbaren Zwischenstand ist es kein
    Resume-Kandidat, auch wenn die Parameter sonst passen (Fehlermuster
    "Angebot ohne Deckung").
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
    if checkpoint.llm_model != llm_model:
        return False
    if checkpoint.language != language:
        return False
    if not checkpoint.expanded_entity_uuids:
        return False
    return bool(checkpoint.completed_profiles)


def resolve_interruption_status(simulation_id: str) -> str:
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
    checkpoint = load_checkpoint(simulation_id)
    if checkpoint is not None and checkpoint.completed_profiles:
        return "interrupted"
    return "failed"
