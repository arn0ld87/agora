"""Profile für die synthetischen Skeptiker der Quotenregel (Issue #1779).

``simulation_config_agents._ensure_skeptic_quota`` ergänzt die Konfiguration um
Agenten mit ``entity_uuid="synthetic-skeptic-<n>"``, damit mindestens 20 % der
Stimmen der Streitfrage widersprechen. Die Konfiguration entsteht aber NACH der
Persona-Phase: diese Agenten hatten nie ein Profil, existierten in OASIS nicht
und schrieben nie (Lauf ``sim_c8c6b30aa652``: Agenten 50 bis 53, vier von elf
Gegenstimmen stumm).

Dieses Modul baut ihnen nachgelagert ein Profil. Die Zuordnung läuft über
``user_id`` = ``agent_id`` der Konfiguration; ``simulation_agent_identity``
löst darüber die OASIS-Position auf. Reine Funktionen ohne Netzwerkzugriff:
Das Profil ist ein Textbaustein, kein LLM-Aufruf, und trägt deshalb
``generation_source="rule_based"`` — der Bericht und die Persona-Galerie
kennzeichnen es als Platzhalter. Eine Demografie wird nicht erfunden: das
Profil ist ein Kollektiv ("Gegenstimme"), keine Einzelperson.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ..config import Config
from ..contracts.pipeline_degradation_contract import DegradationKind, DegradationSeverity
from ..utils.logger import get_logger
from .degradation_collector import DegradationCollector
from .oasis_profile_models import OasisAgentProfile
from .persona_identity_binding import resolve_identity_binding
from .simulation_stance_graph import SYNTHETIC_SKEPTIC_PREFIX

if TYPE_CHECKING:
    from .simulation_manager import SimulationState

logger = get_logger("agora.prepare")

_STATEMENT_LIMIT = 300

_TEXT_DE = {
    "bio": "Synthetische Gegenstimme der Simulation: lehnt die Streitfrage ab und hinterfragt sie kritisch.",
    "persona": (
        "Du bist eine skeptische Gegenstimme in dieser Diskussion. Du stehst der Streitfrage "
        "„{subject}“ ablehnend gegenüber und willst verhindern, dass sie so umgesetzt wird. "
        "Du hinterfragst Annahmen, verlangst belastbare Belege und benennst Risiken, Kosten und "
        "Folgen, die andere übergehen. In deinen Beiträgen wird deine ablehnende Haltung zur "
        "Streitfrage erkennbar: Du nimmst Stellung gegen sie und begründest das knapp und "
        "sachlich. Du bist keine reale Person und keine bestimmte Organisation, sondern eine "
        "synthetische Stimme der Simulation, die sicherstellt, dass auch die ablehnende Seite "
        "zu Wort kommt. Du erfindest weder Namen noch Beruf noch Lebensdaten und sprichst nicht "
        "im Namen realer Personen oder Institutionen."
    ),
    "handle": "skeptiker_{agent_id}",
}

_TEXT_EN = {
    "bio": "Synthetic dissenting voice of the simulation: rejects the contested question and challenges it critically.",
    "persona": (
        "You are a skeptical dissenting voice in this discussion. You oppose the contested "
        "question \"{subject}\" and want to prevent it from being implemented as proposed. You "
        "question assumptions, demand reliable evidence and name risks, costs and consequences "
        "that others overlook. Your posts make your opposition to the contested question "
        "recognisable: you take a stand against it and give brief, factual reasons. You are not "
        "a real person and not a specific organisation but a synthetic voice of the simulation "
        "that makes sure the opposing side is heard as well. You do not invent names, professions "
        "or biographical details and you do not speak on behalf of real people or institutions."
    ),
    "handle": "skeptic_{agent_id}",
}


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _contested_subject(config: Mapping[str, Any]) -> str:
    """Streitfrage des Laufs; ersatzweise die Simulationsfrage, gekürzt."""
    question = config.get("contested_question")
    statement = question.get("statement") if isinstance(question, Mapping) else None
    subject = str(statement or "").strip() or str(config.get("simulation_requirement") or "").strip()
    subject = " ".join(subject.split())
    if len(subject) > _STATEMENT_LIMIT:
        subject = subject[:_STATEMENT_LIMIT].rstrip() + "…"
    return subject or "das Vorhaben"


def is_synthetic_skeptic(agent_config: Mapping[str, Any]) -> bool:
    """Gehört der Konfigurationseintrag zu einem Agenten der Skeptiker-Quote?"""
    return str(agent_config.get("entity_uuid") or "").startswith(SYNTHETIC_SKEPTIC_PREFIX)


def build_skeptic_profiles(
    config: Mapping[str, Any],
    existing_profiles: Sequence[OasisAgentProfile],
    *,
    language: Optional[str] = None,
) -> List[OasisAgentProfile]:
    """Profile für alle synthetischen Skeptiker der Konfiguration ohne Profil.

    Idempotent: ein Agent, dessen ``agent_id`` schon als ``user_id`` eines
    vorhandenen Profils auftaucht, bekommt kein zweites. Die Reihenfolge
    folgt der Konfiguration; ``user_id`` ist die ``agent_id`` der Konfiguration.
    """
    agent_configs = config.get("agent_configs")
    if not isinstance(agent_configs, list):
        return []
    taken = {profile.user_id for profile in existing_profiles}
    lang = (language or Config.AGENT_LANGUAGE or "de").lower()
    texts = _TEXT_EN if lang.startswith("en") else _TEXT_DE
    subject = _contested_subject(config)

    profiles: List[OasisAgentProfile] = []
    for agent_config in agent_configs:
        if not isinstance(agent_config, Mapping) or not is_synthetic_skeptic(agent_config):
            continue
        agent_id = _as_int(agent_config.get("agent_id"))
        if agent_id is None or agent_id in taken:
            continue
        taken.add(agent_id)
        entity_name = str(agent_config.get("entity_name") or f"Skeptiker {agent_id}")
        entity_uuid = str(agent_config.get("entity_uuid"))
        entity_type = str(agent_config.get("entity_type") or "Person")
        binding = resolve_identity_binding(
            entity_uuid=entity_uuid,
            entity_name=entity_name,
            entity_type=entity_type,
            attributes={"identity_origin": "synthetic_supplement"},
            summary=texts["persona"].format(subject=subject),
            is_collective_type=True,
        ).model_dump(mode="json")
        profiles.append(
            OasisAgentProfile(
                user_id=agent_id,
                user_name=texts["handle"].format(agent_id=agent_id),
                name=entity_name,
                bio=texts["bio"],
                persona=texts["persona"].format(subject=subject),
                country="DE",
                interested_topics=[],
                source_entity_uuid=entity_uuid,
                source_entity_type=entity_type,
                persona_kind="collective",
                voice_register="skeptisch-de",
                generation_source="rule_based",
                identity_binding=binding,
            )
        )
    if profiles:
        logger.info(
            "Skeptiker-Profile erzeugt: %d (agent_ids=%s)",
            len(profiles),
            ", ".join(str(profile.user_id) for profile in profiles),
        )
    return profiles


def _phase_profile_synthetic_skeptics(
    state: "SimulationState",
    sim_dir: str,
    profiles: List[Any],
    config: Dict[str, Any],
    *,
    language: Optional[str],
    degradations: Optional[DegradationCollector] = None,
) -> List[Any]:
    """Phase 3b (#1779): Profile für die synthetischen Skeptiker der Quotenregel.

    ``_ensure_skeptic_quota`` ergänzt die Konfiguration erst NACH der
    Persona-Phase um Agenten wie ``synthetic-skeptic-50``. Ohne Profil
    existierten sie in OASIS nicht und schrieben nie. Dieser Schritt baut aus
    der gerade persistierten Konfiguration die fehlenden Profile
    (``user_id`` = ``agent_id`` der Konfiguration, damit
    ``simulation_agent_identity`` sie auflöst) und schreibt beide Profildateien
    neu. Er läuft innerhalb der Konfigurationsphase und damit hinter dem
    Persona-Checkpoint (#1472c), der am Ende von Phase 2 gelöscht wird: ein
    Resume erzeugt die Persona-Profile über den regulären Pfad, die
    Skeptiker-Profile danach erneut.

    Idempotent (ein Agent mit vorhandenem Profil bekommt kein zweites).
    Rückgabe: die um die Skeptiker erweiterte Profilliste.
    """
    from . import prepare_service as _ps

    skeptics = _ps._prepare_skeptic_profiles.build_skeptic_profiles(
        config, profiles, language=language
    )
    if not skeptics:
        return profiles

    all_profiles = [*profiles, *skeptics]
    # Nur die Persistenzmethoden des Generators werden genutzt; der Platzhalter-
    # Schlüssel löst keinen Aufruf aus.
    writer = _ps.OasisProfileGenerator(api_key="persistence-only")
    if state.enable_reddit:
        writer.save_profiles(
            profiles=all_profiles,
            file_path=os.path.join(sim_dir, "reddit_profiles.json"),
            platform="reddit",
        )
    if state.enable_twitter:
        writer.save_profiles(
            profiles=all_profiles,
            file_path=os.path.join(sim_dir, "twitter_profiles.csv"),
            platform="twitter",
        )
    # Issue #1833 / Befund 5.3: Identity-Bindings nach Ergänzung synthetischer Skeptiker aktualisieren
    _ps._persist_identity_bindings(state, sim_dir, all_profiles)
    state.profiles_count = len(all_profiles)

    if degradations is not None:
        degradations.record(
            kind=DegradationKind.PERSONA_RULE_BASED_FALLBACK,
            severity=DegradationSeverity.WARNING,
            detail=(
                f"{len(skeptics)} synthetische Skeptiker-Personas (Quotenregel) sind "
                "regelbasierte Platzhalter ohne Modellbeteiligung. Ihre Beiträge sind "
                "synthetische Gegenstimmen, keine aus dem Graph belegten Positionen."
            ),
            context={
                "fallback_personas": len(skeptics),
                "total_personas": len(all_profiles),
            },
        )
    return all_profiles


__all__ = [
    "build_skeptic_profiles",
    "is_synthetic_skeptic",
    "_phase_profile_synthetic_skeptics",
]
