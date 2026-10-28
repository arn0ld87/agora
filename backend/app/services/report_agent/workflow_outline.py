from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional

from pydantic import ValidationError

from ...contracts.report_contract import ReportOutlineModel, ReportOutlineSectionModel
from ...models.report import Report, ReportStatus
from ...utils.logger import get_logger
from .contract_constants import MIN_PERSONA_TABLE_ROWS
from .section_kinds import coerce_section_kind
from . import workflow as _wf

logger = get_logger("agora.report_agent")


def _load_persona_count(agent: Any) -> int:
    """Best-effort count of generated personas for the report contract gate."""
    for attr in ("personas", "profiles", "persona_ids"):
        value = getattr(agent, attr, None)
        if isinstance(value, list):
            return len(value)

    # ``or 0`` ist die Gate-Semantik: "nicht ermittelbar" darf hier nicht
    # durchrutschen (UAT-001). Die Vorabpruefung beim Report-Start nutzt
    # dagegen ``load_persona_count_for`` direkt und unterscheidet None von 0.
    return _wf.load_persona_count_for(getattr(agent, "simulation_id", None)) or 0


def load_persona_count_for(simulation_id: Any) -> Optional[int]:
    """Anzahl gespeicherter Personas eines Laufs — ``None``, wenn nicht lesbar.

    Einzige Quelle fuer das Gate (``_load_persona_count``) und die
    Vorabpruefung beim Report-Start (``report_generation``, UAT-001), damit
    beide dieselbe Zahl sehen und die Erklaerung vor dem Start nicht von der
    Schwelle abweicht, an der der Lauf sonst spaeter scheitert.

    ``None`` heisst "nicht ermittelbar", nicht "null": ein Lesefehler am
    Store darf eine Vorabpruefung nicht als Floor-Unterschreitung auslegen
    und damit einen moeglichen Bericht blockieren.
    """
    try:
        profiles = _wf.resolve_default_store().read_json(
            simulation_id,
            "reddit_profiles",
            default=None,
        )
    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        _wf.logger.warning(
            "persona-floor check: failed to read profiles for simulation %s: %r",
            simulation_id,
            exc,
        )
        return None
    return len(profiles) if isinstance(profiles, list) else None


def _compute_stance_analysis(agent: Any, report_id: str) -> Optional[Dict[str, Any]]:
    """Haltung je Beitrag und Positionierungsquote des Laufs (Issue #1778).

    Läuft einmal vor dem ersten Abschnitt. Die Klassifikation nutzt den
    LLM-Client des Report-Agenten, damit ihre Aufrufe im Budget-Ledger des
    Berichts landen; ``BudgetExceededError`` wird nicht gefangen.

    Kann die Analyse nicht gerechnet werden, bleibt das sichtbar
    (``stance_analysis_unavailable``, Review PR #1780): ein Lese- oder
    Rechtefehler, ein fehlendes Aktionsprotokoll oder beschädigte
    Protokollzeilen sind keine Quote von null. Nur ohne Simulationskonfiguration
    wird nichts behauptet (``None``) — dann ist nicht bekannt, ob der Lauf
    überhaupt eine Streitfrage hat.
    """
    simulation_id = getattr(agent, "simulation_id", "<unknown>")
    report_folder = _wf.ReportManager._get_report_folder(report_id)
    actions: list[Dict[str, Any]] = []
    try:
        from ..simulation_runner import SimulationRunner

        config = _wf.resolve_default_store().read_json(
            agent.simulation_id,
            "simulation_config",
            default=None,
        )
        if not isinstance(config, dict):
            return None
        # Issue #1778: Das Aktionsprotokoll zählt die Agenten nach ihrer
        # Position in der Profildatei (so nummeriert OASIS). Die
        # Konfiguration wird darauf umgeschrieben, sonst bekäme eine Stimme
        # Namen und Starthaltung eines anderen Agenten, sobald ein Profil
        # fehlt.
        config, _agents_without_profile = _wf.align_config_to_profiles(
            config,
            _wf.load_simulation_profiles(
                os.path.join(SimulationRunner.RUN_STATE_DIR, agent.simulation_id)
            ),
        )
        # Ein Resume derselben ``report_id`` übernimmt die gespeicherte
        # Analyse, statt alle Beiträge erneut zu klassifizieren (Budget des
        # Resumes) — aber nur, wenn sie zur aktuellen Streitfrage gehört.
        stored = _wf.load_stance_analysis(report_folder)
        # Und nur, wenn ihre Stimmen zur angeglichenen Konfiguration passen:
        # eine Analyse mit verschobenen Agenten-Nummern wird neu gerechnet
        # (#1778).
        if (
            stored is not None
            and stored.contested_statement == _wf.contested_statement_of(config)
            and _wf.voices_match_config(stored, config)
        ):
            return stored.model_dump(mode="json")
        # Ohne Streitfrage ist die Analyse nicht anwendbar: das Protokoll
        # wird dann gar nicht erst gelesen.
        if _wf.has_contested_statement(config):
            actions = [
                action.to_dict()
                for action in SimulationRunner.get_all_actions(agent.simulation_id)
            ]
            log_files, unreadable_lines = _wf.action_log_health(
                agent.simulation_id, SimulationRunner.RUN_STATE_DIR
            )
            if log_files == 0:
                _wf.logger.warning("stance analysis: no action log for simulation %s", simulation_id)
                return _wf.stance_analysis_unavailable("action_log_missing")
            if unreadable_lines:
                _wf.logger.warning(
                    "stance analysis: %d unreadable action log lines for simulation %s",
                    unreadable_lines,
                    simulation_id,
                )
                return _wf.stance_analysis_unavailable("action_log_unreadable")
    except Exception as exc:  # noqa: BLE001 — logged; surfaced as run degradation
        _wf.reraise_if_budget_exceeded(exc)
        _wf.logger.warning(
            "stance analysis: failed to read config or actions for simulation %s: %r",
            simulation_id,
            exc,
        )
        return _wf.stance_analysis_unavailable("read_failed")

    analysis = _wf.build_stance_analysis(
        agent.simulation_id, config, actions, None, agent.llm
    )
    _wf.save_stance_analysis(report_folder, analysis)
    return analysis.model_dump(mode="json")


def _stance_analysis_of(agent: Any) -> Optional[Dict[str, Any]]:
    """Die am Agenten abgelegte Analyse; ein Test-Double liefert ``None``."""
    analysis = getattr(agent, "stance_analysis", None)
    return analysis if isinstance(analysis, dict) else None


def _load_persona_fallback_stats(agent: Any) -> tuple[int, int]:
    """(Platzhalter, gesamt) fuer die Degradierungssumme des Laufs (#1419).

    Gezaehlt wird ``generation_error``, nicht ``generation_source``: die
    bewusste Wahl ``use_llm_for_profiles=False`` erzeugt ebenfalls
    regelbasierte Profile und ist keine Degradierung. Nur der Ausfall nach
    gescheiterten LLM-Versuchen zaehlt.

    Wie beim Persona-Floor gilt: das Gate darf am Store nicht scheitern.
    Ohne lesbare Profile wird nichts behauptet.
    """
    try:
        profiles = _wf.resolve_default_store().read_json(
            agent.simulation_id,
            "reddit_profiles",
            default=[],
        )
    except Exception as exc:  # noqa: BLE001 — Gate darf am Store nicht scheitern
        logger.warning(
            "persona-fallback check: failed to read profiles for simulation %s: %r",
            getattr(agent, "simulation_id", "<unknown>"),
            exc,
        )
        return (0, 0)

    if not isinstance(profiles, list):
        return (0, 0)

    failed = sum(
        1
        for profile in profiles
        if isinstance(profile, dict) and profile.get("generation_error")
    )
    return (failed, len(profiles))


def _load_persona_floor(agent: Any) -> int:
    """Effektiver Persona-Floor für das Report-Contract-Gate.

    Liest den bei der Preparation persistierten ``persona_floor`` aus dem
    Simulation-State (Task: 50-Personas-Minimum dynamisch). Fallback ist
    MIN_PERSONA_TABLE_ROWS; ein persistierter Wert kann den Floor nur
    senken, nie über den Contract anheben.
    """
    return _wf.load_persona_floor_for(getattr(agent, "simulation_id", None))


def load_persona_floor_for(simulation_id: Any) -> int:
    """Wirksamer Persona-Floor eines Laufs — Gate und Vorabpruefung (UAT-001).

    Dieselbe Aufloesung wie ``_load_persona_floor``: persistierter
    ``persona_floor`` aus dem Simulation-State, gedeckelt durch
    ``MIN_PERSONA_TABLE_ROWS``. Ein nicht lesbarer State faellt auf den
    Contract-Wert zurueck — der Floor ist die Zusage, nicht der Istzustand.
    """
    try:
        data = _wf.resolve_default_store().read_json(
            simulation_id,
            "state",
            default=None,
        )
    except Exception as exc:  # noqa: BLE001 — Gate darf am Store nicht scheitern
        logger.warning(
            "persona-floor check: failed to read state for simulation %s: %r",
            simulation_id,
            exc,
        )
        return _wf.MIN_PERSONA_TABLE_ROWS

    floor = data.get("persona_floor") if isinstance(data, dict) else None
    if isinstance(floor, int) and floor > 0:
        return min(floor, _wf.MIN_PERSONA_TABLE_ROWS)
    return _wf.MIN_PERSONA_TABLE_ROWS


def _load_persona_candidate_count(agent: Any) -> Optional[int]:
    """Kandidatenzahl vor der Profilgenerierung, fuer die Gate-Fehlermeldung (#1420).

    ``state.entities_count`` wird in ``prepare_service.py::_phase_read_entities``
    nach Dedup und Cap, aber vor dem Aufruf des Persona-Generators persistiert
    (``state.entities_count = filtered.filtered_count``) — das deckt sich mit
    dem Log ``Simulation preparation completed: entities=N, profiles=M``. Diese
    Zahl ist die Kandidatenmenge, die der Generator sieht.

    ``None`` wenn der Wert (noch) nicht vorliegt — der Aufrufer degradiert dann
    auf die knappe Fehlermeldung ohne Ablehnungszahl.
    """
    try:
        data = _wf.resolve_default_store().read_json(
            agent.simulation_id,
            "state",
            default=None,
        )
    except Exception as exc:  # noqa: BLE001 — Gate darf am Store nicht scheitern
        logger.warning(
            "persona-floor check: failed to read entities_count for simulation %s: %r",
            getattr(agent, "simulation_id", "<unknown>"),
            exc,
        )
        return None

    if not isinstance(data, dict):
        return None
    count = data.get("entities_count")
    return count if isinstance(count, int) and count > 0 else None


def _mark_incomplete_for_persona_floor(
    report: Report,
    *,
    report_id: str,
    persona_count: int,
    floor: int = MIN_PERSONA_TABLE_ROWS,
    candidate_count: Optional[int] = None,
    progress_callback: Optional[Callable[[str, int, str], None]] = None,
) -> Report:
    report.status = ReportStatus.INCOMPLETE
    message = (
        "Persona-Mindestanzahl nicht erreicht: "
        f"{persona_count}/{floor} Personas vorhanden."
    )
    if candidate_count is not None and candidate_count >= persona_count:
        deficit_count = candidate_count - persona_count
        message += (
            f" Von {candidate_count} Persona-Kandidaten sind nur {persona_count} "
            f"als Personas vorhanden — ein Defizit von {deficit_count}. Moegliche "
            "Ursachen sind das Eignungs-Gate (Ablehnung technischer Artefakte "
            "ohne eigene Interessenlage) oder eine nachtraegliche Entfernung "
            "(z. B. in einem Branch); aus dieser Zahl allein laesst sich das "
            "nicht unterscheiden."
        )
    report.missing_sections = [message]
    report.error = message
    _wf.ReportManager.update_progress(
        report_id,
        "incomplete",
        0,
        message,
        completed_sections=[],
    )
    _wf.ReportManager.save_report(report)
    if progress_callback:
        progress_callback("incomplete", 0, message)
    return report


def _validate_outline_structure(outline: Any) -> None:
    ReportOutlineModel(
        title=outline.title,
        summary=outline.summary,
        sections=[
            ReportOutlineSectionModel(
                title=section.title,
                description=section.description,
                section_kind=coerce_section_kind(getattr(section, "kind", None)),
            )
            for section in outline.sections
        ],
    )


def _reusable_persisted_outline(
    existing_report: Optional[Report], report_id: str
) -> Optional[Any]:
    """Gueltige freie Outline wiederverwenden; alte Ersatzschemas neu planen."""
    outline = existing_report.outline if existing_report else None
    if outline is None:
        return None
    if _wf.ReportManager.load_fallback_outline_used(report_id) is True:
        logger.info(
            "Persistierter Outline stammt aus dem Fallback — wird verworfen und neu geplant",
            extra={"report_id": report_id},
        )
        return None
    try:
        _validate_outline_structure(outline)
    except ValidationError:
        logger.info("Persistierter Outline ist strukturell ungueltig — wird neu geplant")
        return None
    return outline
