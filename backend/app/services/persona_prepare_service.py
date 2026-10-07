"""Simulation direkt aus gespeicherten Personas vorbereiten (ohne Graph).

ZIEL: Eine Simulation soll allein aus ``PersonaLibrary``-Einträgen auf
``READY`` gebracht werden können — ohne Dokument, ohne Ontologie, ohne
Knowledge-Graph. Strukturell an ``branching_service.create_branch`` angelehnt
(gleiches Muster: Funktionen nehmen einen ``SimulationManager`` als ersten
Parameter, um zirkuläre Importe zu vermeiden), aber ohne Source-Simulation —
die Profile kommen direkt aus der übergebenen Personaliste.

Das Profildatei-Format (Keys, Defaults, ``user_id``-Vergabe, Username-Dedupe)
spiegelt bewusst ``api.simulation_profiles.add_simulation_profile``: dort ist
das Format bereits korrekt für OASIS. Ein direkter Funktionsimport war nicht
möglich (die API-Funktion hängt an ``flask.request`` und an
``current_app``-gebundenem ``get_artifact_store()``), deshalb wird hier
dieselbe Feldliste/-logik noch einmal nachgebildet statt importiert.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, get_args

from ..config import Config
from ..contracts.persona_contract import PERSONA_SCHEMA_VERSION
from ..contracts.persona_set_contract import PersonaOrigin
from ..contracts.pipeline_degradation_contract import (
    DegradationKind,
    DegradationSeverity,
    PipelineDegradationReport,
)
from ..utils.artifact_locator import ArtifactLocator
from ..utils.logger import get_logger
from .degradation_collector import DegradationCollector
from .llm_routing_seed import workspace_credential_metadata
from .run_registry import RunRegistry
from .simulation_config_generator import (
    EventConfig,
    PlatformConfig,
    SimulationParameters,
    TimeSimulationConfig,
)

if TYPE_CHECKING:
    from .simulation_manager import SimulationManager, SimulationState

logger = get_logger("agora.persona_prepare")

# Felder, die im OASIS-Profilformat immer vorhanden sein müssen (siehe
# oasis_profile_generator.py: agent_info[i]["mbti"]/["age"]/["gender"] werden
# ungeschützt indiziert). PersonaLibrary._normalize lässt leere Werte weg,
# ein Bibliothekseintrag kann sie also fehlen.
_ALWAYS_PRESENT_DEFAULTS = {
    "age": "",
    "gender": "other",
    "mbti": "",
    "country": "DE",
    "profession": "",
    "interested_topics": [],
}

#: Gültige Werte von ``persona_set_origin`` (Quelle: ``PersonaOrigin``).
_PERSONA_SET_ORIGINS = frozenset(get_args(PersonaOrigin))


def prepare_from_personas(
    manager: "SimulationManager",
    simulation_id: str,
    personas: List[Dict[str, Any]],
    persona_set_id: Optional[str] = None,
    degradations: Optional[DegradationCollector] = None,
) -> "SimulationState":
    """Bereitet eine frisch angelegte Simulation aus Bibliotheks-Personas vor.

    Durchläuft denselben FSM-Pfad wie ``branching_service.create_branch``
    (``CREATED -> PREPARING -> READY``, kein Direktsprung), schreibt
    ``reddit_profiles.json``/``twitter_profiles.csv`` und eine
    ``simulation_config.json`` und registriert einen abgeschlossenen
    ``simulation_prepare``-Run.

    Args:
        manager: Simulation-Manager, dessen Store/Status-Setter genutzt wird.
        simulation_id: ID einer Simulation im Status ``CREATED``.
        personas: Nicht-leere Liste von Bibliotheks-Personas (Dicts).
        persona_set_id: Kennung des Personasatzes (#1807), aus dem die Liste
            als Kopie stammt. Landet in den Metadaten des Prepare-Runs
            (``persona_source="set"``); ohne Wert bleibt es bei ``"library"``.
        degradations: Sammler des Aufrufers (wie im normalen Prepare-Pfad,
            #1034). Tragen Personas ``generation_source="rule_based"``,
            meldet dieser Pfad ``PERSONA_RULE_BASED_FALLBACK`` genau einmal
            fuer die ganze Liste; der Befund steht zusaetzlich in den
            Metadaten des Prepare-Runs (``degradations``). Ohne Sammler legt
            die Funktion einen eigenen an, damit der Run-Eintrag nie fehlt.

    Raises:
        ValueError: bei leerer Personaliste, unbekannter Simulation oder
            falschem Ausgangsstatus.
    """
    from .simulation_manager import SimulationStatus  # avoid import cycle

    if not personas:
        raise ValueError("personas darf nicht leer sein")

    state = manager.get_simulation(simulation_id)
    if not state:
        raise ValueError(f"Simulation does not exist: {simulation_id}")
    if state.status != SimulationStatus.CREATED:
        raise ValueError(
            "Nur frisch angelegte Simulationen (CREATED) können aus einer "
            "Personaliste vorbereitet werden"
        )

    manager._set_status(state, SimulationStatus.PREPARING)

    profiles = _translate_personas(personas, from_set=persona_set_id is not None)
    manager._store.write_json(simulation_id, "reddit_profiles", profiles)
    _write_twitter_csv(manager._get_simulation_dir(simulation_id), profiles)

    config = _build_config(state, len(profiles))
    manager._store.write_json(simulation_id, "simulation_config", config)

    state.entities_count = len(profiles)
    state.profiles_count = len(profiles)
    state.entity_types = sorted({p["persona_kind"] for p in profiles})
    state.config_generated = True

    collector = degradations if degradations is not None else DegradationCollector()
    _report_rule_based_fallback(profiles, collector, persona_set_id)

    # Rueckverweis erst kurz vor READY setzen: ein gescheiterter Lauf verweist
    # nicht auf einen Satz, den ``record_run`` nie gesperrt hat. Der Statuswechsel
    # persistiert das Feld mit.
    state.persona_set_id = persona_set_id
    manager._set_status(state, SimulationStatus.READY)
    _register_run(state, len(profiles), persona_set_id, collector.report())
    return state


def _report_rule_based_fallback(
    profiles: List[Dict[str, Any]],
    degradations: DegradationCollector,
    persona_set_id: Optional[str],
) -> None:
    """Meldet regelbasierte Platzhalter einmal fuer die ganze Liste (#1029).

    Gleicher Befundtyp, gleiche Schweregradregel und gleicher Wortlaut-Aufbau
    wie ``oasis_profile_rule_based._report_persona_degradation``: sind alle
    Personas Platzhalter, gibt es keine echte Stimme mehr (``BLOCKING``),
    sonst ``WARNING``.
    """
    fallback = [p for p in profiles if p.get("generation_source") == "rule_based"]
    if not fallback:
        return
    context: Dict[str, str | int | float] = {
        "fallback_personas": len(fallback),
        "total_personas": len(profiles),
    }
    if persona_set_id is not None:
        context["persona_set_id"] = persona_set_id
    degradations.record(
        kind=DegradationKind.PERSONA_RULE_BASED_FALLBACK,
        severity=(
            DegradationSeverity.BLOCKING
            if len(fallback) == len(profiles)
            else DegradationSeverity.WARNING
        ),
        detail=(
            f"{len(fallback)} von {len(profiles)} Personas sind regelbasierte "
            "Platzhalter und wurden nicht vom Modell erzeugt. "
            "Ihre Beiträge tragen keine belastbaren Aussagen."
        ),
        context=context,
    )


def _translate_personas(
    personas: List[Dict[str, Any]], *, from_set: bool = False
) -> List[Dict[str, Any]]:
    """Übersetzt Bibliotheks-Personas ins OASIS-Profilformat.

    Vergibt fortlaufende ``user_id`` (ab 1) und dedupliziert Usernamen
    case-insensitiv — gleiches Muster wie ``add_simulation_profile``.

    ``from_set``: Der Lauf stammt aus einem Personasatz (#1807). Dann tragen
    ALLE Profile ``persona_set_origin`` (siehe ``_translate_persona``).
    """
    existing_names: set = set()
    profiles = []
    for index, persona in enumerate(personas, start=1):
        profile = _translate_persona(persona, index, existing_names, from_set=from_set)
        existing_names.add(profile["username"].lower())
        profiles.append(profile)
    return profiles


def _dedupe_username(username: str, existing_names: set) -> str:
    if username.lower() not in existing_names:
        return username
    suffix = 1
    while f"{username}_{suffix}".lower() in existing_names:
        suffix += 1
    return f"{username}_{suffix}"


def _translate_persona(
    persona: Dict[str, Any],
    user_id: int,
    existing_names: set,
    *,
    from_set: bool = False,
) -> Dict[str, Any]:
    """Schließt Feldlücken eines Bibliothekseintrags fürs Profilformat.

    Bei ``from_set`` steht zusätzlich ``persona_set_origin`` im Profil: die
    Herkunft aus dem Satz (``graph|manual|ai_draft|fallback``). Nur so bleibt
    ein KI-Entwurf am Laufprofil erkennbar, denn ``generation_source`` kennt
    kein ``ai_draft``. Ohne Satz fehlt der Schlüssel, die Profile bleiben
    unverändert. Ein Profil aus einem Satz ohne gültige Herkunft ist ein
    Programmfehler (``ValueError``), kein stiller Standardwert.
    """
    username = _dedupe_username(
        str(persona.get("username") or f"user_{user_id}").strip(), existing_names
    )
    display_name = persona.get("name") or username
    bio = persona.get("bio") or display_name
    persona_text = persona.get("persona") or (
        f"{display_name} is a participant in social discussions."
    )

    profile: Dict[str, Any] = {
        # Issue #1663: Formatversion des geschriebenen Eintrags, nie aus dem
        # Bibliothekseintrag übernommen.
        "schema_version": PERSONA_SCHEMA_VERSION,
        "user_id": user_id,
        "username": username,
        "name": display_name,
        "bio": bio,
        "persona": persona_text,
        "karma": _coerce_karma(persona.get("karma")),
        # OasisAgentProfile-Format: reines Datum, kein Zeit-Anteil (spiegelt
        # add_simulation_profile). Der Bibliothekseintrag trägt ggf. einen
        # ISO-Timestamp mit Uhrzeit (PersonaLibrary._now()) — der wird hier
        # bewusst NICHT übernommen, sondern auf das erwartete Format normiert.
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source_entity_uuid": persona.get("source_entity_uuid"),
        "source_entity_type": persona.get("source_entity_type") or "persona_library",
        "persona_kind": persona.get("persona_kind") or "individual",
        "is_manual": bool(persona.get("is_manual", False)),
        # Immer gesetzt (nie nur bei Fallback): ``_write_twitter_csv`` leitet die
        # Spalten aus dem ersten Profil ab, ein spaeteres Profil mit
        # zusaetzlichem Schluessel brachte den CSV-Writer zum Absturz.
        "generation_source": (
            "rule_based" if persona.get("generation_source") == "rule_based" else "llm"
        ),
    }
    for key, default in _ALWAYS_PRESENT_DEFAULTS.items():
        value = persona.get(key)
        profile[key] = value if value not in (None, "") else default
    if from_set:
        origin = persona.get("persona_set_origin")
        if origin not in _PERSONA_SET_ORIGINS:
            raise ValueError(
                f"Persona {username!r} aus einem Satz ohne gültige Herkunft: {origin!r}"
            )
        profile["persona_set_origin"] = origin
    return profile


def _coerce_karma(karma_raw: Any) -> int:
    if karma_raw in (None, "", "null"):
        return 1000
    try:
        return int(str(karma_raw))
    except (ValueError, TypeError):
        return 1000


def _write_twitter_csv(sim_dir: str, profiles: List[Dict[str, Any]]) -> None:
    path = os.path.join(sim_dir, "twitter_profiles.csv")
    fieldnames = list(profiles[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(profiles)


def _build_config(state: "SimulationState", profile_count: int) -> Dict[str, Any]:
    """Baut eine schema-kompatible ``simulation_config.json`` ohne LLM/Graph.

    Nutzt bewusst nur die Datenklassen aus ``simulation_config_generator``
    (gleiches JSON-Schema wie ein LLM-generierter Config), statt
    ``SimulationConfigGenerator.generate_config`` aufzurufen: der volle
    Generator braucht ``document_text``/Entities, verlangt zwingend einen
    konfigurierten LLM-Key und erzwingt einen 30-Personas-Floor
    (``_validate_persona_quota``) — alles Voraussetzungen, die dem Ziel
    "allein aus Personas, ohne Dokument/Graph" widersprechen.
    """
    twitter_config = (
        PlatformConfig(
            platform="twitter",
            recency_weight=0.4,
            popularity_weight=0.3,
            relevance_weight=0.3,
            viral_threshold=10,
            echo_chamber_strength=0.5,
        )
        if state.enable_twitter
        else None
    )
    reddit_config = (
        PlatformConfig(
            platform="reddit",
            recency_weight=0.3,
            popularity_weight=0.4,
            relevance_weight=0.3,
            viral_threshold=15,
            echo_chamber_strength=0.6,
        )
        if state.enable_reddit
        else None
    )

    params = SimulationParameters(
        simulation_id=state.simulation_id,
        project_id=state.project_id,
        graph_id=state.graph_id,
        simulation_requirement="Vorbereitung aus gespeicherten Personas (kein Dokument).",
        time_config=TimeSimulationConfig(),
        agent_configs=[],
        event_config=EventConfig(),
        twitter_config=twitter_config,
        reddit_config=reddit_config,
        llm_model=Config.LLM_MODEL_NAME,
        llm_base_url=Config.LLM_BASE_URL,
        language=Config.AGENT_LANGUAGE,
        enable_agent_tools=getattr(Config, "ENABLE_AGENT_TOOLS", False),
        max_tool_calls_per_action=getattr(Config, "MAX_TOOL_CALLS_PER_ACTION", 2),
        neo4j_uri=Config.NEO4J_URI,
        neo4j_user=Config.NEO4J_USER,
        generation_reasoning=(
            f"{profile_count} Personas direkt aus der Persona-Bibliothek "
            "übernommen; kein Dokument, keine Ontologie, kein Graph."
        ),
    )
    config = params.to_dict()
    config["enable_twitter"] = state.enable_twitter
    config["enable_reddit"] = state.enable_reddit
    return config


def _register_run(
    state: "SimulationState",
    profile_count: int,
    persona_set_id: Optional[str] = None,
    degradation_report: Optional[PipelineDegradationReport] = None,
) -> None:
    from_set = persona_set_id is not None
    source_metadata: Dict[str, Any] = {"persona_source": "set" if from_set else "library"}
    if persona_set_id is not None:
        source_metadata["persona_set_id"] = persona_set_id
    if degradation_report:
        source_metadata["degradations"] = degradation_report.model_dump(mode="json")
    RunRegistry().create_run(
        run_type="simulation_prepare",
        entity_id=state.simulation_id,
        status="completed",
        progress=100,
        message=(
            f"Simulation aus {profile_count} Personas des Personasatzes vorbereitet"
            if from_set
            else f"Simulation aus {profile_count} Bibliotheks-Personas vorbereitet"
        ),
        linked_ids={
            "simulation_id": state.simulation_id,
            "project_id": state.project_id,
        },
        artifacts=ArtifactLocator.existing_paths(
            {"simulation": ArtifactLocator.simulation_artifacts(state.simulation_id)}
        ),
        # Finding H1 (#1688): explizit persistierter credential_scope, sonst
        # faellt die spaetere Routen-Aufloesung fuer diesen Run ausserhalb
        # eines gebundenen Kontexts auf den Operator zurueck.
        metadata={
            **source_metadata,
            "persona_count": profile_count,
            **workspace_credential_metadata(),
        },
    )


__all__ = ["prepare_from_personas"]
