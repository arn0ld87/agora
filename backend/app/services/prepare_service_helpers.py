"""Profile generation and phase-1 checkpoint resolution helpers for prepare_service."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from ..contracts import PersonaQuotaPlan
from ..contracts.llm_routing_contract import ResolvedRoute
from . import prepare_checkpoint as _prepare_checkpoint
from . import prepare_service as _ps
from .degradation_collector import DegradationCollector
from .llm_runtime import RuntimeLlmConfig
from .oasis_profile_generator import OasisAgentProfile, OasisProfileGenerator
from .report_agent import MIN_PERSONA_TABLE_ROWS

if TYPE_CHECKING:
    from .oasis_profile_models import PersonaDemographicSlot
    from .simulation_manager import SimulationManager, SimulationState

LlmRuntimeInput = RuntimeLlmConfig | ResolvedRoute


def _entity_uuids_or_none(entities: List[Any]) -> Optional[List[str]]:
    """Extrahiert ``uuid``-Strings für den Checkpoint, oder ``None`` bei Fremdkörpern.

    Issue #1472c: Checkpointing setzt echte ``EntityNode.uuid``-Strings
    voraus (Pydantic-Contract, ``extra="forbid"`` + ``str``-Typisierung).
    Test-Doubles unterhalb dieser Ebene reichen teils Objekte ohne
    (echtes) ``uuid``-Attribut herein — für die wird das Checkpointing
    dieses Aufrufs deaktiviert statt mit einer ``ValidationError``
    abzubrechen (siehe Aufrufer).
    """
    uuids: List[str] = []
    for entity in entities:
        uuid = getattr(entity, "uuid", None)
        if not isinstance(uuid, str) or not uuid:
            return None
        uuids.append(uuid)
    return uuids


def _selection_reasons_or_empty(filtered: Any) -> List[Any]:
    """Auswahlbegruendungen (#1759 A5) aus ``filtered``; Test-Doubles liefern ``[]``."""
    reasons = getattr(filtered, "selection_decisions", None)
    return list(reasons) if isinstance(reasons, list) else []


def _build_profile_checkpoint_hooks(
    *,
    state: SimulationState,
    filtered: Any,
    entities: List[Any],
    sim_dir: str,
    defined_entity_types: Optional[List[str]],
    max_agents: Optional[int],
    persona_floor: int,
    use_llm_for_profiles: bool,
    quota_plan: Optional[PersonaQuotaPlan],
    resume_checkpoint: Optional["_prepare_checkpoint.PreparePersonaCheckpoint"],
    generator: OasisProfileGenerator,
    llm_model: Optional[str] = None,
    language: Optional[str] = None,
    requirement_hash: Optional[str] = None,
) -> Tuple[
    Optional[Dict[int, OasisAgentProfile]],
    Optional[Callable[[int, OasisAgentProfile], None]],
    Optional[List["PersonaDemographicSlot"]],
]:
    """Baut ``already_done``/``on_profile_saved``/Slot-Plan für ``_phase_generate_profiles`` (Issue #1472c).

    Ausgelagert in eine eigene Funktion statt inline in
    ``_phase_generate_profiles`` — Lehre aus Slice 1.3: zusätzliche
    Resume-Zweige direkt in der Phasenfunktion kippen deren zyklomatische
    Komplexität schnell über den Radon-Schwellenwert; ein neuer Eintrag in
    ``radon-allowlist.txt`` ist keine Lösung, eine Auslagerung schon.

    Checkpointing ist eine Zusatzabsicherung, kein hartes Erfordernis für
    die Generierung selbst: fehlt ``state.simulation_id`` (Test-Doubles
    unterhalb dieser Ebene) oder tragen die Entities kein echtes
    ``uuid``-Attribut, liefert diese Funktion ``(None, None, None)`` — die
    Generierung läuft normal weiter, nur ohne Checkpoint (und die
    demografischen Slots werden wie vor Issue #1472c pro Aufruf neu
    gewürfelt).

    Der dritte Rückgabewert (Codex-Finding P1, PR #1539) ist der fixierte
    demografische Slot-Plan: bei einem Resume der aus dem Checkpoint
    übernommene Plan (siehe ``PreparePersonaCheckpoint``-Docstring — ein
    Resume darf ihn NIE neu würfeln), bei einem neuen Versuch ein frisch
    gewürfelter Plan, der zusammen mit der Auswahl im Checkpoint landet.
    """
    # Bewusst als ``str | None`` gefuehrt und vor jeder Checkpoint-Schreibung
    # geprueft: Test-Doubles tragen nicht zwingend eine ``simulation_id``, und
    # der Artefakt-Store weist eine fehlende hart zurueck. ``isinstance`` statt
    # blosser Truthiness, weil ein ``MagicMock`` truthy ist und sonst bis in
    # den Store durchschlagen wuerde.
    _raw_simulation_id = getattr(state, "simulation_id", None)
    simulation_id: Optional[str] = (
        _raw_simulation_id if isinstance(_raw_simulation_id, str) and _raw_simulation_id else None
    )

    if resume_checkpoint is not None:
        already_done = _ps._prepare_checkpoint.completed_profiles_from_checkpoint(
            resume_checkpoint
        )
        _ps.logger.info(
            "Prepare-Resume: %d/%d Personas aus Checkpoint übernommen für %s",
            len(already_done),
            len(entities),
            simulation_id,
        )
        checkpoint_box: List[Any] = [resume_checkpoint]
        demographic_slots = _ps._prepare_checkpoint.demographic_slots_from_checkpoint(
            resume_checkpoint
        )
    elif simulation_id:
        primary_uuids = _ps._entity_uuids_or_none(filtered.entities)
        reserve_uuids = _ps._entity_uuids_or_none(
            getattr(filtered, "reserve_entities", None) or []
        )
        expanded_uuids = _ps._entity_uuids_or_none(entities)
        if primary_uuids is None or reserve_uuids is None or expanded_uuids is None:
            _ps.logger.debug(
                "Prepare-Checkpoint übersprungen für %s: Entities ohne "
                "echtes uuid-Attribut (Test-/Fake-Pfad)",
                simulation_id,
            )
            return None, None, None
        # Codex-Finding P1 (PR #1539): EINMAL würfeln, dann sowohl an den
        # Checkpoint als auch an die Generierung reichen — sonst würfelt
        # ``generate_profiles_from_entities`` intern ein zweites Mal und der
        # Checkpoint hielte einen Plan fest, der nie tatsächlich verwendet
        # wurde.
        demographic_slots = generator._build_demographic_slots(entities)
        checkpoint_box = [
            _ps._prepare_checkpoint.new_checkpoint(
                simulation_id=simulation_id,
                graph_id=state.graph_id,
                defined_entity_types=defined_entity_types,
                max_agents=max_agents,
                persona_floor=persona_floor,
                use_llm_for_profiles=use_llm_for_profiles,
                effective_quota_plan=(
                    quota_plan.model_dump() if quota_plan is not None else None
                ),
                primary_entity_uuids=primary_uuids,
                reserve_entity_uuids=reserve_uuids,
                expanded_entity_uuids=expanded_uuids,
                entities_count=state.entities_count,
                entity_types=state.entity_types,
                llm_model=llm_model,
                language=language,
                demographic_slots=[
                    _ps._prepare_checkpoint.demographic_slot_to_dict(slot)
                    for slot in demographic_slots
                ],
                requirement_hash=requirement_hash,
                selection_reasons=_ps._selection_reasons_or_empty(filtered),
            )
        ]
        already_done = None
    else:
        return None, None, None

    # Ab hier steht fest, dass eine ``simulation_id`` vorliegt: der
    # ``resume_checkpoint``-Zweig traegt sie im Checkpoint, der ``elif``-Zweig
    # hat sie geprueft, und jeder andere Fall ist oben mit ``None, None, None``
    # ausgestiegen. Die eigene Bindung macht das fuer die Closure explizit,
    # statt sich auf ein Narrowing zu verlassen, das dort nicht mehr greift.
    checkpoint_simulation_id: str = simulation_id or checkpoint_box[0].simulation_id

    def _on_profile_saved(index: int, profile: OasisAgentProfile) -> None:
        checkpoint_box[0] = checkpoint_box[0].with_completed_profile(
            index, _ps._prepare_checkpoint.profile_to_dict(profile)
        )
        _ps._prepare_checkpoint.save_checkpoint(checkpoint_simulation_id, checkpoint_box[0])

    return already_done, _on_profile_saved, demographic_slots


def _persist_identity_bindings(
    state: SimulationState, sim_dir: str, profiles: List[OasisAgentProfile]
) -> None:
    """Schreibt das Laufartefakt ``persona_identity_bindings.json`` (Issue #1833).

    Direkt nach dem abschließenden Speichern der Profildateien. Storage- und
    Berechtigungsfehler werden bewusst nicht abgefangen. ``isinstance``, nicht
    blosse Truthiness: Test-Doubles tragen nicht zwingend eine ``simulation_id``.
    Das Log nennt Zählungen, keine Personen- oder Organisationsnamen.
    """
    simulation_id = getattr(state, "simulation_id", None)
    if not isinstance(simulation_id, str) or not simulation_id:
        return
    manifest = _ps.write_identity_binding_manifest(sim_dir, simulation_id, profiles)
    by_origin: Dict[str, int] = {}
    for entry in manifest.entries:
        by_origin[entry.binding.origin] = by_origin.get(entry.binding.origin, 0) + 1
    _ps.logger.info(
        "persona identity bindings: entries=%d by_origin=%s unverifiable=%d role_deviations=%d",
        len(manifest.entries),
        by_origin,
        sum(1 for entry in manifest.entries if not entry.binding.is_verifiable),
        sum(1 for entry in manifest.entries if entry.binding.role_deviation),
    )


def _phase_generate_profiles(
    state: SimulationState,
    storage: Any,
    filtered,
    sim_dir: str,
    *,
    llm_model: Optional[str],
    llm_runtime: Optional[LlmRuntimeInput] = None,
    language: Optional[str],
    run_id: Optional[str] = None,
    use_llm_for_profiles: bool,
    parallel_profile_count: int,
    progress_callback: Optional[Callable] = None,
    quota_plan: Optional[PersonaQuotaPlan] = None,
    persona_floor: int = MIN_PERSONA_TABLE_ROWS,
    max_agents: Optional[int] = None,
    degradations: Optional[DegradationCollector] = None,
    defined_entity_types: Optional[List[str]] = None,
    resume_checkpoint: Optional[_prepare_checkpoint.PreparePersonaCheckpoint] = None,
    precomputed_entities: Optional[List[Any]] = None,
    requirement_hash: Optional[str] = None,
) -> Tuple[List[Any], List[Any]]:
    """Phase 2: OASIS-Profiles generieren und im Sim-Dir ablegen.

    Aktualisiert ``state.profiles_count`` als Seiteneffekt und gibt ein
    Tuple ``(profiles, expanded_entities)`` zurück: die Liste der
    generierten Profile sowie die auf die Quota expandierte
    Entity-Liste, die Phase 3 weiterverarbeitet.

    Sub-Slice 20b — Quota-Erzwingung: wenn ``quota_plan`` gesetzt ist,
    wird ``filtered.entities`` vor der Generation per
    ``_expand_entities_for_quota`` auf die Quota expandiert (Round-Robin
    auf zu kleinen Pools). Ohne Plan bleibt das Verhalten "1 Persona pro
    Entity" unverändert.

    Issue #1472c (Prepare-Resume): ``precomputed_entities`` überspringt die
    Expansion komplett — die Auswahl ist dann bereits im Checkpoint
    fixiert (siehe ``prepare_checkpoint_contract``). Ohne ``resume_checkpoint``
    wird ein neuer Checkpoint angelegt und nach jedem generierten Profil
    inkrementell fortgeschrieben (``on_profile_saved``); mit
    ``resume_checkpoint`` läuft die Generierung nur für die noch fehlenden
    Indizes (``already_done`` überspringt den LLM-Call für bereits
    vorliegende Profile).
    """
    if precomputed_entities is not None:
        # Resume: die Cap-/Quota-Auswahl steht bereits fest — NICHT neu
        # berechnen (siehe Moduldocstring ``prepare_checkpoint.py``: der
        # Graph-Lesepfad hat kein ``ORDER BY``, ein erneuter Read könnte
        # eine andere Typ-Verteilung liefern).
        entities = precomputed_entities
        total_entities = len(entities)
    else:
        entities = _ps._expand_entities_for_quota(filtered.entities, quota_plan)
        if quota_plan is None:
            entities = _ps._apply_persona_floor_to_entities(entities, minimum=persona_floor)
        # UAT-001: Der Floor-Aufschlag wiederholt vorhandene Entitaeten, er
        # erzeugt keine neuen. Die Nachruecker-Reserve ist aber genau das, was
        # der ``max_agents``-Cap wegschchnitten hat — ist der Pool kleiner als
        # der Cap (der Fall, fuer den der Aufschlag existiert), ist sie leer.
        # Jede Ablehnung des Generators (LLM-Eignungs- oder Kohaerenz-Gate)
        # faellt dann ersatzlos unter den Floor, den der Report-Contract
        # verlangt. Produktionsbeleg: Pool 9 -> 20 Plaetze, 2 Ablehnungen,
        # ``Reserve: 0 Kandidaten``, 18 Personas erzeugt -> Bericht INCOMPLETE.
        # Der aufgefuellte Pool traegt die Reserve deshalb selbst: die
        # vorhandenen Entitaeten sind die einzigen moeglichen Nachruecker.
        current_reserve = getattr(filtered, "reserve_entities", None) or []
        if len(entities) > len(filtered.entities) and not current_reserve:
            filtered.reserve_entities = list(filtered.entities)
        # Issue #1034: Der Nenner des Fortschrittszählers kommt aus derselben
        # Funktion, die auch die Preview-Antwort füllt. Vorher stand hier
        # ``len(entities)`` — richtig, aber eben nur hier: die UI bekam den
        # Vor-Floor-Wert aus einer zweiten Berechnung und zeigte „22 / 7“.
        total_entities = _ps.compute_persona_target(
            len(filtered.entities),
            max_agents=max_agents,
            quota_plan=quota_plan,
            floor=persona_floor,
        ).persona_target_count

    if progress_callback:
        progress_callback(
            "generating_profiles", 0,
            "Starting generation...",
            current=0,
            total=total_entities,
        )

    # Pass graph_id to enable graph retrieval functionality, get richer context.
    # Per-simulation overrides for model + language come from API request.
    # Issue #215: Branchenverteilung-Plan für LLM-Prompt — Default Destatis WZ 2008
    # (IT-Cap ≤ 12 %). total_entities als Pool-Größe für proportionale Verteilung.
    industry_plan = _ps.default_dach_industry_quota(max(total_entities, 1))

    # ``require`` folgt dem expliziten Nutzerwunsch: nur wenn LLM-Personas
    # verlangt sind, ist eine fehlende Route ein Fehler. Bei
    # ``use_llm_for_profiles=False`` ist regelbasiert das gewollte Ergebnis.
    api_key, base_url, provider_type = _ps._resolve_llm_connection(
        llm_runtime, require=use_llm_for_profiles
    )

    generator = _ps.OasisProfileGenerator(
        api_key=api_key,
        base_url=base_url,
        provider_type=provider_type,
        storage=storage,
        graph_id=state.graph_id,
        model_name=llm_model,
        language=language,
        industry_quota_plan=industry_plan,
        # Budget-Enforcement (#984): run-gebundene LLM-Calls statt budgetfrei.
        run_id=run_id,
    )

    def profile_progress(current, total, msg):
        if progress_callback:
            progress_callback(
                "generating_profiles",
                int(current / total * 100),
                msg,
                current=current,
                total=total,
                item_name=msg,
            )

    # Set real-time save file path (prefer Reddit JSON format)
    realtime_output_path: Optional[str] = None
    realtime_platform = "reddit"
    if state.enable_reddit:
        realtime_output_path = os.path.join(sim_dir, "reddit_profiles.json")
        realtime_platform = "reddit"
    elif state.enable_twitter:
        realtime_output_path = os.path.join(sim_dir, "twitter_profiles.csv")
        realtime_platform = "twitter"

    # Issue #1472c (Prepare-Resume): Checkpoint aufsetzen bzw. fortsetzen.
    # Ausgelagert in ``_build_profile_checkpoint_hooks`` (Komplexitäts-
    # Gründe, siehe deren Docstring).
    already_done, on_profile_saved, demographic_slots = _ps._build_profile_checkpoint_hooks(
        state=state,
        filtered=filtered,
        entities=entities,
        sim_dir=sim_dir,
        defined_entity_types=defined_entity_types,
        max_agents=max_agents,
        persona_floor=persona_floor,
        use_llm_for_profiles=use_llm_for_profiles,
        quota_plan=quota_plan,
        resume_checkpoint=resume_checkpoint,
        generator=generator,
        llm_model=llm_model,
        language=language,
        requirement_hash=requirement_hash,
    )

    profiles = generator.generate_profiles_from_entities(
        entities=entities,
        use_llm=use_llm_for_profiles,
        progress_callback=profile_progress,
        graph_id=state.graph_id,
        parallel_count=parallel_profile_count,
        realtime_output_path=realtime_output_path,
        output_platform=realtime_platform,
        # Codex-Finding P1 (PR #1539, Issue #1472c): fixierter Slot-Plan
        # (neu gewürfelt oder aus dem Checkpoint übernommen) — verhindert,
        # dass ein Resume die demografische Mischung neu würfelt.
        demographic_slots=demographic_slots,
        # Issue #1034: Der Parameter existiert seit #1029 (Slice 12,
        # regelbasierte Fallback-Profile), wurde aus dem produktiven
        # Prepare-Pfad aber nie gefüllt — ``_report_persona_degradation``
        # lief damit nie. Ohne diese Zeile bleibt die Meldung dort tot.
        degradations=degradations,
        already_done=already_done,
        on_profile_saved=on_profile_saved,
        # Issue #1247: Nachrücker für Kandidaten, die der Generator als nicht
        # personenfähig zurückweist.
        reserve_entities=getattr(filtered, "reserve_entities", None),
    )

    state.profiles_count = len(profiles)

    # Issue #1472c: Phase 2 ist regulär beendet (erfolgreich oder
    # kooperativ abgebrochen, siehe ``PrepareCancelledError`` — beide Fälle
    # erreichen diese Zeile normal, nur ein SIGTERM/Absturz MITTEN in der
    # Generierung tut das nicht). Der Checkpoint hat seinen Zweck erfüllt;
    # ein Retry nach Cancel/Erfolg startet Phase 2 wie bisher komplett neu.
    # ``getattr`` wie in ``_build_profile_checkpoint_hooks``: Test-Doubles
    # tragen nicht zwingend eine ``simulation_id``, und ohne sie gibt es auch
    # keinen Checkpoint, der aufzuraeumen waere.
    # ``isinstance``, nicht blosse Truthiness: ein ``MagicMock`` aus einem
    # Test-Double ist truthy und kaeme bis in den Artefakt-Store, der ihn
    # zu Recht als ungueltige ``simulation_id`` zurueckweist.
    _cleanup_simulation_id = getattr(state, "simulation_id", None)
    if isinstance(_cleanup_simulation_id, str) and _cleanup_simulation_id:
        _ps._prepare_checkpoint.clear_checkpoint(_cleanup_simulation_id)

    # Save Profile files (Note: Twitter uses CSV format, Reddit uses JSON format)
    # Reddit has been saved in real-time during generation, save once more here to ensure completeness
    if progress_callback:
        progress_callback(
            "generating_profiles", 95,
            "Saving Profile files...",
            current=total_entities,
            total=total_entities,
        )

    if state.enable_reddit:
        generator.save_profiles(
            profiles=profiles,
            file_path=os.path.join(sim_dir, "reddit_profiles.json"),
            platform="reddit",
        )

    if state.enable_twitter:
        # Twitter uses CSV format! This is OASIS requirement
        generator.save_profiles(
            profiles=profiles,
            file_path=os.path.join(sim_dir, "twitter_profiles.csv"),
            platform="twitter",
        )

    # Issue #1833: Herkunft der Identität jeder Persona als Laufartefakt.
    _ps._persist_identity_bindings(state, sim_dir, profiles)

    if progress_callback:
        progress_callback(
            "generating_profiles", 100,
            f"Completed, total {len(profiles)} Profiles",
            current=len(profiles),
            total=len(profiles),
        )

    return profiles, entities


def _resolve_phase1_result(
    *,
    state: SimulationState,
    storage: Any,
    simulation_id: str,
    sim_dir: str,
    defined_entity_types: Optional[List[str]],
    max_agents: Optional[int],
    persona_floor: int,
    use_llm_for_profiles: bool,
    effective_quota_plan_snapshot: Optional[Dict[str, Any]],
    progress_callback: Optional[Callable],
    degradations: Optional[DegradationCollector],
    llm_model: Optional[str] = None,
    language: Optional[str] = None,
    simulation_requirement: Optional[str] = None,
    llm_runtime: Optional[LlmRuntimeInput] = None,
    run_id: Optional[str] = None,
) -> Tuple[Any, Optional["_prepare_checkpoint.PreparePersonaCheckpoint"], Optional[List[Any]]]:
    """Phase 1 oder deren Resume-Variante (Issue #1472c).

    Ausgelagert aus ``prepare_simulation`` — die Resume-Erkennung (Checkpoint
    laden, Gültigkeit prüfen, zwei Rückfallpfade) hob dessen zyklomatische
    Komplexität über den Radon-Schwellenwert (Rank D). Ein neuer Eintrag in
    ``radon-allowlist.txt`` ist dafür keine Lösung, eine Auslagerung schon.

    Liefert ``(filtered, resume_checkpoint, precomputed_entities)``:
    ``resume_checkpoint``/``precomputed_entities`` sind nur bei einem
    tatsächlich verwertbaren Checkpoint gesetzt (sonst beide ``None`` und
    ``filtered`` kommt aus einer regulär ausgeführten Phase 1).
    """
    existing_checkpoint = _ps._prepare_checkpoint.load_checkpoint(simulation_id)
    resumable = _ps._prepare_checkpoint.checkpoint_is_resumable(
        existing_checkpoint,
        simulation_id=simulation_id,
        graph_id=state.graph_id,
        defined_entity_types=defined_entity_types,
        max_agents=max_agents,
        persona_floor=persona_floor,
        use_llm_for_profiles=use_llm_for_profiles,
        effective_quota_plan=effective_quota_plan_snapshot,
        llm_model=llm_model,
        language=language,
        requirement_hash=_ps._requirement_hash(simulation_requirement),
    )

    if resumable:
        # ``checkpoint_is_resumable`` liefert nur dann True, wenn
        # ``checkpoint is not None`` geprüft wurde (erste Zeile der
        # Funktion) — die Invariante gilt per Konstruktion, mypy kann sie
        # nur nicht über den Funktionsaufruf hinweg herleiten.
        assert existing_checkpoint is not None

        # Resume: die Cap-/Quota-Auswahl steht bereits fest — Phase 1
        # berechnet NICHTS neu, sie schlägt nur per UUID nach (der
        # Graph-Lesepfad hat kein ``ORDER BY``, ein erneuter Read könnte
        # eine andere Typ-Verteilung liefern, siehe
        # ``prepare_checkpoint.py`` Moduldocstring).
        filtered = _ps._phase_read_entities_from_checkpoint(
            state, storage, existing_checkpoint, progress_callback=progress_callback
        )
        precomputed_entities = (
            _ps._lookup_expanded_entities_from_checkpoint(storage, existing_checkpoint)
            if filtered is not None
            else None
        )
        if filtered is not None and precomputed_entities is not None:
            _ps.logger.info(
                "Prepare-Resume erkannt für %s: %d/%d Personas aus Checkpoint übernommen",
                simulation_id,
                len(existing_checkpoint.completed_profiles),
                len(existing_checkpoint.expanded_entity_uuids),
            )
            return filtered, existing_checkpoint, precomputed_entities
        # Checkpoint verwertet sich doch nicht (z. B. eine fixierte Entity
        # wurde im Graphen gelöscht) — auf den regulären Pfad zurückfallen
        # statt mit einer beschädigten Auswahl weiterzumachen.

    if existing_checkpoint is not None:
        # Nicht verwertbar (Parameter-Mismatch oder verschwundene Entity)
        # — als Altlast entfernen. Sonst läse
        # ``resolve_interruption_status`` beim nächsten Absturz diese
        # stale Datei fälschlich als Resume-Angebot.
        _ps._prepare_checkpoint.clear_checkpoint(simulation_id)

    filtered = _ps._phase_read_entities(
        state,
        storage,
        defined_entity_types,
        max_agents,
        progress_callback=progress_callback,
        degradations=degradations,
        simulation_requirement=simulation_requirement,
        llm_runtime=llm_runtime,
        llm_model=llm_model,
        run_id=run_id,
        use_llm_for_profiles=use_llm_for_profiles,
        has_quota_plan=effective_quota_plan_snapshot is not None,
    )
    return filtered, None, None


def _phase_generate_config(
    manager: SimulationManager,
    state: SimulationState,
    simulation_id: str,
    simulation_requirement: str,
    document_text: str,
    *,
    expanded_entities: List[Any],
    llm_model: Optional[str],
    llm_runtime: Optional[LlmRuntimeInput] = None,
    language: Optional[str],
    run_id: Optional[str] = None,
    use_llm: bool = True,
    progress_callback: Optional[Callable] = None,
    quota_plan: Optional[PersonaQuotaPlan] = None,
    degradations: Optional[DegradationCollector] = None,
    contested_question_override: Optional[str] = None,
    activity_mode: Optional[str] = None,
    profiles: Optional[List[Any]] = None,
    sim_dir: Optional[str] = None,
) -> None:
    """Phase 3: Simulation-Config per LLM erzeugen + atomar persistieren.

    ``profiles`` und ``sim_dir`` (#1779): Profile der Persona-Phase. Sind beide
    gesetzt, erhalten die synthetischen Skeptiker der Quotenregel direkt nach dem
    Schreiben der Konfiguration ein Profil
    (:func:`_phase_profile_synthetic_skeptics`).

    ``activity_mode`` (#1779): ``realistic`` oder ``active``; ``None`` liest
    ``AGORA_SIM_ACTIVITY_MODE``.

    ``contested_question_override`` (#1778): Nutzervorgabe für die Streitfrage.
    Gesetzt ersetzt sie den Vorschlag des Konfigurations-Assistenten.

    ``degradations`` (#1759 A6): Sammler des Prepare-Laufs. Der Generator
    meldet darüber ``stance_position_unrepresented`` und
    ``initial_post_stance_conflict`` sichtbar im Task-Ergebnis, statt nur ins
    Log zu schreiben.

    Aktualisiert ``state.config_generated`` und ``state.config_reasoning``
    als Seiteneffekt; speichert die Config über den ``ArtifactStore``.

    Sub-Slice 22 (Gemini-Followup auf 20a): wenn ``quota_plan`` gesetzt
    ist, wird er als Top-Level-Key ``quota_plan`` in
    ``simulation_config.json`` mitgeschrieben — der Restart-Pfad in
    ``runs.py`` liest ihn von dort über ``_parse_quota_plan(config)``
    wieder ein. Ohne Persistenz war der Plan beim Restart immer ``None``.
    """
    if progress_callback:
        progress_callback(
            "generating_config", 0,
            "Analyzing simulation requirements...",
            current=0,
            total=3,
        )

    api_key, base_url, provider_type = _ps._resolve_llm_connection(llm_runtime, require=use_llm)

    config_generator = _ps.SimulationConfigGenerator(
        api_key=api_key,
        base_url=base_url,
        provider_type=provider_type,
        model_name=llm_model,
        language=language,
        # Budget-Enforcement (#984): run-gebundene LLM-Calls statt budgetfrei.
        run_id=run_id,
    )

    if progress_callback:
        progress_callback(
            "generating_config", 30,
            "Calling LLM to generate config...",
            current=1,
            total=3,
        )

    sim_params = config_generator.generate_config(
        simulation_id=simulation_id,
        project_id=state.project_id,
        graph_id=state.graph_id,
        simulation_requirement=simulation_requirement,
        document_text=document_text,
        entities=expanded_entities,
        enable_twitter=state.enable_twitter,
        enable_reddit=state.enable_reddit,
        degradations=degradations,
        contested_question_override=contested_question_override,
        activity_mode=activity_mode,
    )

    if progress_callback:
        progress_callback(
            "generating_config", 70,
            "Saving config files...",
            current=2,
            total=3,
        )

    # Save config files (atomic via store — fixes prior non-atomic write).
    config_payload = json.loads(sim_params.to_json())
    if quota_plan is not None:
        config_payload["quota_plan"] = quota_plan.model_dump()
    manager._store.write_json(
        simulation_id,
        "simulation_config",
        config_payload,
    )

    state.config_generated = True
    state.config_reasoning = sim_params.generation_reasoning

    if profiles is not None and sim_dir:
        _ps._phase_profile_synthetic_skeptics(
            state,
            sim_dir,
            profiles,
            config_payload,
            language=language,
            degradations=degradations,
        )

    if progress_callback:
        progress_callback(
            "generating_config", 100,
            "Config generation completed",
            current=3,
            total=3,
        )
