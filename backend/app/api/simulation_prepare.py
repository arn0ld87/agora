"""
Preparation-related simulation API routes split from the main module.
"""

import os
from typing import Any, Optional

from flask import request
from pydantic import ValidationError

from . import simulation_bp
from ..config import Config
from ..contracts import PersonaQuotaPlan
from ..models.project import ProjectManager
from ..services.entity_reader import EntityReader
from ..services.llm_routing_seed import (
    build_runtime_llm_config,
    resolve_route_api_key,
    seed_run_stage_routing,
)
from ..services.llm_runtime import parse_runtime_llm_config
from ..services.report_agent import MIN_SIMULATION_AGENTS
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.stage_model_router import StageModelRouter
from ..utils.validation import validate_simulation_id, validate_task_id
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import handle_api_errors, json_success, json_error
from .simulation_common import (
    get_artifact_store,
    get_simulation_storage,
    logger,
    run_registry,
    simulation_run_artifacts as _simulation_run_artifacts,
)


_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"})

# Lokale OpenAI-kompatible Server (z. B. Ollama) ignorieren den API-Key
# vollstaendig, das OpenAI-SDK verlangt aber einen nicht-leeren String (#778).
# Dieser Platzhalter macht die No-Auth-Freigabe fuer lokale Endpoints explizit
# sichtbar, statt still `None` an die Generatoren durchzureichen — deren
# Vertrag "Key und Base-URL aus derselben Quelle" (#778) wuerde sonst bei
# String-Mismatch (z. B. host.docker.internal vs. localhost) faelschlich
# einen ValueError werfen, obwohl die API-Schicht den Lauf bereits freigegeben hat.
LOCAL_NO_AUTH_API_KEY = "local-no-auth"


def _is_local_endpoint(base_url: Optional[str]) -> bool:
    """Prüft, ob eine Base-URL auf einen lokalen Endpunkt zeigt.

    Nutzt ``urllib.parse.urlparse`` und vergleicht den Hostnamen explizit gegen
    eine Whitelist (``localhost``, ``127.0.0.1``, ``::1``, ``0.0.0.0``,
    ``host.docker.internal``). Das verhindert Subdomain-Smuggling wie
    ``http://not-localhost.com`` oder ``http://remote-server:11434``, die ein
    reines Substring-Match fälschlich als lokal akzeptiert hätte
    (Gemini-Review PR #466).
    """
    if not base_url:
        return False
    from urllib.parse import urlparse

    try:
        parsed = urlparse(base_url if "://" in base_url else f"http://{base_url}")
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return host in _LOCAL_HOSTS


def _parse_quota_plan(data: dict) -> Optional[PersonaQuotaPlan]:
    """Parse ``quota_plan`` aus dem POST-Body in ein ``PersonaQuotaPlan``.

    Sub-Slice 20a — API-Boundary für Persona-Quoten. Backwards-Compat:
    fehlendes oder ``None``-Feld → ``None`` (Service verhält sich wie
    bisher). Leerer Dict ``{}`` zählt ebenfalls als „nicht gesetzt", weil
    ein leerer Plan keinerlei Aussagekraft hat und sonst eine
    ``ValidationError`` für „targets darf nicht leer sein" werfen würde —
    Frontend kann den Eintrag dann mit `{}` defaulten ohne 400.

    Bei strukturell vorhandenem, aber inkonsistentem Plan
    (``total != sum(targets)``, ``targets`` mit ``count<1``,
    nicht-Dict-Payload) wird die ``pydantic.ValidationError`` propagiert
    und vom Caller in eine HTTP-400-Antwort übersetzt.
    """
    raw: Any = data.get("quota_plan")
    if raw is None:
        return None
    if isinstance(raw, dict) and not raw:
        return None
    return PersonaQuotaPlan.model_validate(raw)


def _resolve_max_agents_with_floor(raw_value: object) -> int | None:
    """Parse optional ``max_agents`` and enforce the simulation-pool floor.

    Der Floor steht bewusst auf ``MIN_SIMULATION_AGENTS`` (10), nicht auf
    ``MIN_PERSONA_TABLE_ROWS`` (50). Das erlaubt Schnell-Tests mit Mini-Seeds
    (Smoke #6 2026-05-15); die Report-Generation skaliert den Persona-Pool im
    Nachgang via Round-Robin auf ``MIN_PERSONA_TABLE_ROWS`` hoch
    (``_apply_persona_floor_to_entities`` in prepare_service.py).
    """
    if raw_value is None or raw_value == "" or raw_value == 0:
        return None
    if not isinstance(raw_value, (str, int, float)):
        return None
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    if parsed < MIN_SIMULATION_AGENTS:
        logger.info(
            "Applying simulation-agents floor for max_agents: requested=%s floor=%s",
            parsed,
            MIN_SIMULATION_AGENTS,
        )
        return MIN_SIMULATION_AGENTS
    return parsed


def _check_simulation_prepared(simulation_id: str) -> tuple:
    """
    Check whether a simulation already has all preparation artifacts.
    """
    simulation_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
    if not os.path.exists(simulation_dir):
        return False, {"reason": "Simulation directory does not exist"}

    store = get_artifact_store()

    # JSON-Artefakte gehen über den Store; CSV (twitter_profiles) bleibt FS-direkt
    # (out of scope für Issue #13).
    json_artifacts = {
        "state.json": ("state", lambda: store.exists(simulation_id, "state")),
        "simulation_config.json": (
            "simulation_config",
            lambda: store.exists(simulation_id, "simulation_config"),
        ),
        "reddit_profiles.json": (
            "reddit_profiles",
            lambda: store.exists(simulation_id, "reddit_profiles"),
        ),
    }

    existing_files = []
    missing_files = []
    for filename, (_, exists_fn) in json_artifacts.items():
        if exists_fn():
            existing_files.append(filename)
        else:
            missing_files.append(filename)

    twitter_csv = os.path.join(simulation_dir, "twitter_profiles.csv")
    if os.path.exists(twitter_csv):
        existing_files.append("twitter_profiles.csv")
    else:
        missing_files.append("twitter_profiles.csv")

    if missing_files:
        return False, {
            "reason": "Missing required files",
            "missing_files": missing_files,
            "existing_files": existing_files,
        }

    try:
        state_data = store.read_json(simulation_id, "state", default=None)
        if not state_data:
            return False, {"reason": "State file is unreadable or temporarily incomplete"}

        status = state_data.get("status", "")
        config_generated = state_data.get("config_generated", False)
        logger.debug(
            f"Detect simulation preparation status: {simulation_id}, status={status}, config_generated={config_generated}"
        )

        prepared_statuses = ["ready", "preparing", "running", "completed", "stopped", "failed"]
        if status in prepared_statuses and config_generated:
            profiles_data = store.read_json(simulation_id, "reddit_profiles", default=[]) or []
            profiles_count = len(profiles_data) if isinstance(profiles_data, list) else 0

            if status == "preparing":
                try:
                    from datetime import datetime

                    state_data["status"] = "ready"
                    state_data["updated_at"] = datetime.now().isoformat()
                    store.write_json(simulation_id, "state", state_data)
                    logger.info(f"Auto update simulation status: {simulation_id} preparing -> ready")
                    status = "ready"
                except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
                    logger.warning(f"Failed to auto update status: {exc}")

            logger.info(
                f"Simulation {simulation_id} Detection result: HasPreparation complete (status={status}, config_generated={config_generated})"
            )
            return True, {
                "status": status,
                "entities_count": state_data.get("entities_count", 0),
                "profiles_count": profiles_count,
                "entity_types": state_data.get("entity_types", []),
                "config_generated": config_generated,
                "created_at": state_data.get("created_at"),
                "updated_at": state_data.get("updated_at"),
                "existing_files": existing_files,
            }

        logger.warning(
            f"Simulation {simulation_id} Detection result: Has notPreparation complete (status={status}, config_generated={config_generated})"
        )
        return False, {
            "reason": (
                "Status not in prepared list or config_generated is false: "
                f"status={status}, config_generated={config_generated}"
            ),
            "status": status,
            "config_generated": config_generated,
        }

    except Exception as exc:  # noqa: BLE001 — exc used in response payload
        return False, {"reason": f"Failed to read state file: {str(exc)}"}


@simulation_bp.route('/prepare', methods=['POST'])
@handle_api_errors(log_prefix="Failed to start preparation task")
def prepare_simulation():
    """Prepare a simulation environment as an async task."""
    from ..models.task import TaskManager, TaskStatus

    data = request.get_json() or {}

    simulation_id = data.get('simulation_id')
    if not simulation_id:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message="Please provide simulation_id",
        )

    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            status=400,
            message="Invalid simulation_id format",
        )

    manager = SimulationManager()
    state = manager.get_simulation(simulation_id)
    if not state:
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Simulation does not exist: {simulation_id}",
        )

    force_regenerate = data.get('force_regenerate', False)

    # Project einmalig laden — wird sowohl für den P5.3-Profil-Fallback als
    # auch für die Anforderungs-Validierung (simulation_requirement) und das
    # nachfolgende Lesen weiterer Felder benötigt (Gemini-MEDIUM auf PR #528:
    # vorher wurde derselbe Datensatz zwei Mal aus dem ProjectManager geholt).
    project = ProjectManager.get_project(state.project_id)
    if not project:
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Project does not exist: {state.project_id}",
        )

    # Profil-Routing (Issue #888). `llm_profile_id` ist eine Routing-Anweisung,
    # kein Fallback-Unterdrücker — analog graph.py / report.py, wo das Feld
    # ebenfalls echtes Routing auslöst.
    #
    # Vorher kehrte das Feld seine eigene Absicht um: ein mitgeschicktes
    # `llm_profile_id` übersprang den P5.3-Fallback, ohne selbst irgendetwas
    # aufzulösen (`expand_profile_in_data` reagiert nur auf ein `llm_model` mit
    # `profile:`-Präfix). Der Standardfall — Projekt hat ein Profil, User lässt
    # die Modellauswahl auf "default" — landete damit still im
    # Server-Default-Modell.
    #
    # `default` ist die UI-Platzhalterwahl (`useEnvForm.effectiveModel()` liefert
    # dafür `null`) und zählt deshalb nicht als explizite Modellwahl.
    _data_profile = (data.get('llm_profile_id') or '').strip() or None
    _data_model = (data.get('llm_model') or '').strip() or None
    explicit_model_override = bool(_data_model and _data_model.lower() != 'default')
    # Vor der Expansion festhalten: `expand_profile_in_data` schreibt einen
    # `llm_provider`-Block aus dem Profil (Provider/Key/Base-URL) und würde
    # `llm_runtime.enabled` sonst ununterscheidbar von einem echten
    # Client-Provider-Override machen.
    explicit_runtime_request = bool(data.get('llm_provider'))
    if not explicit_model_override:
        # Request-Profil schlägt Projekt-Profil (Single-Run-Override), beide
        # schlagen das Server-Default-Modell.
        _routed_profile = _data_profile or getattr(project, 'llm_profile_id', None)
        if _routed_profile:
            data['llm_model'] = f"profile:{_routed_profile}"
    # UI-Profile-Token in echtes Modell + Provider-Creds expandieren.
    from ..utils.llm_profile_resolver import expand_profile_in_data
    expand_profile_in_data(data)
    llm_model_override = (data.get('llm_model') or '').strip() or None
    try:
        llm_runtime = parse_runtime_llm_config(data)
    except ValueError as exc:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message=str(exc),
        )
    logger.info(
        f"Start processing /prepare Request: simulation_id={simulation_id}, force_regenerate={force_regenerate}",
        extra={'simulation_id': simulation_id},
    )

    # Der "bereits vorbereitet"-Kurzschluss hängt bewusst an der *expliziten*
    # Client-Wahl, nicht an `llm_model_override`/`llm_runtime.enabled` (Issue
    # #888). Seit dem Profil-Routing oben sind beide für jedes Projekt mit
    # hinterlegtem Profil gesetzt — an sie gebunden würde der Kurzschluss nie
    # mehr greifen und jedes Betreten von Step 2 eine vollständige
    # Neu-Vorbereitung samt Persona-Neugenerierung auslösen.
    client_requested_override = explicit_model_override or (
        llm_runtime.enabled and explicit_runtime_request
    )
    if not force_regenerate and not client_requested_override:
        logger.debug(f"Check simulation {simulation_id} Is preparation complete...")
        is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
        logger.debug(f"Check result: is_prepared={is_prepared}, prepare_info={prepare_info}")
        if is_prepared:
            logger.info(f"Simulation {simulation_id} has preparation complete, no need to regenerate")
            return json_success({
                "simulation_id": simulation_id,
                "status": "ready",
                "message": "Preparation already completed, no need to regenerate",
                "already_prepared": True,
                "prepare_info": prepare_info,
            })
        logger.info(f"Simulation {simulation_id} has no preparation complete, preparing now")

    simulation_requirement = project.simulation_requirement or ""
    if not simulation_requirement:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message="Project missing simulation requirement description (simulation_requirement)",
        )

    document_text = ProjectManager.get_extracted_text(state.project_id) or ""
    entity_types_list = data.get('entity_types')
    use_llm_for_profiles = data.get('use_llm_for_profiles', True)
    parallel_profile_count = data.get('parallel_profile_count') or None

    max_agents = _resolve_max_agents_with_floor(data.get("max_agents"))

    # Sub-Slice 20a: optional PersonaQuotaPlan aus Body. ValidationError →
    # HTTP 400 mit Pydantic-Fehlermessage; sonst wird der Plan an den
    # Service durchgereicht (Validierung post-generation, Erzwingung in 20b).
    # Sub-Slice 22 (Gemini-Followup): spezifische Exceptions statt blankem
    # ``except Exception``, damit echte 500er nicht als 400 maskiert werden.
    try:
        quota_plan = _parse_quota_plan(data)
    except (ValidationError, ValueError, TypeError) as exc:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message=f"Invalid quota_plan: {exc}",
        )

    agent_language_override = (data.get('language') or '').strip().lower() or None
    if agent_language_override and agent_language_override not in ('de', 'en'):
        agent_language_override = None

    storage = get_simulation_storage()

    try:
        logger.info(f"Synchronously get entity count: graph_id={state.graph_id}")
        reader = EntityReader(storage)
        filtered_preview = reader.filter_defined_entities(
            graph_id=state.graph_id,
            defined_entity_types=entity_types_list,
            enrich_with_edges=False,
        )
        preview_count = filtered_preview.filtered_count
        if max_agents is not None and max_agents > 0:
            preview_count = min(preview_count, max_agents)
        state.entities_count = preview_count
        state.entity_types = list(filtered_preview.entity_types)
        logger.info(
            f"Expected entity count: {filtered_preview.filtered_count}, [type][model]: {filtered_preview.entity_types}"
        )
    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning(f"Synchronously get entity countFailed（Will retry in background task）: {exc}")

    task_manager = TaskManager()
    run_record = run_registry.create_run(
        run_type="simulation_prepare",
        entity_id=simulation_id,
        status="pending",
        progress=0,
        message="Simulation preparation queued",
        linked_ids={
            "simulation_id": simulation_id,
            "project_id": state.project_id,
        },
        artifacts=_simulation_run_artifacts(simulation_id),
        resume_capability={"available": True, "action": "restart", "label": "Restart preparation"},
        branch_label=state.branch_name,
        metadata={
            "project_id": state.project_id,
            "graph_id": state.graph_id,
            "source_simulation_id": state.source_simulation_id,
            "root_simulation_id": state.root_simulation_id,
            "branch_name": state.branch_name,
            "branch_depth": state.branch_depth,
            "llm_model": llm_model_override,
            "llm_provider": llm_runtime.redacted_metadata() or None,
        },
    )
    task_id = task_manager.create_task(
        task_type="simulation_prepare",
        metadata={
            "simulation_id": simulation_id,
            "project_id": state.project_id,
            "run_id": run_record["run_id"],
        },
    )
    seed_run_stage_routing(
        run_record["run_id"],
        "persona_generation",
        llm_model_override=llm_model_override,
        llm_runtime=llm_runtime,
    )
    route_router = StageModelRouter(run_record["run_id"])
    resolved_route = route_router.resolve("persona_generation")
    route_router.lock_stage("persona_generation", resolved_route)
    resolved_api_key = resolve_route_api_key(resolved_route, llm_runtime)

    if resolved_api_key is None and not _is_local_endpoint(resolved_route.base_url_sanitized):
        guard_message = (
            f"provider_override: kein api_key im Payload und kein Key in der Settings-DB "
            f"für Provider '{resolved_route.provider_id}'. "
            "Bitte in Einstellungen → LLM-Anbieter einen Schlüssel speichern "
            "oder im Sitzungsfeld eingeben."
        )
        # Issue #841: run_record und task_id existieren an dieser Stelle
        # bereits (Zeilen 369/393) — ohne dieses Markieren bleibt der
        # Datensatz dauerhaft als "pending" in der Registry verwaist.
        # Reihenfolge ist bewusst: fail_task() setzt intern per sync_task()
        # eine generische Task-Message ("Task failed") auf den Run zurück —
        # der detaillierte update_run()-Aufruf muss deshalb zuletzt laufen,
        # sonst überschreibt sync_task() die provider_override-Meldung.
        task_manager.fail_task(task_id, guard_message)
        # Issue #844: update_run() liefert None, wenn das Run-Manifest
        # zwischenzeitlich verschwunden ist, oder es kann eine I/O-Exception
        # werfen (write_json_atomic ist ungeschützt). Beide Fälle dürfen
        # NICHT wie eine erfolgreich persistierte Ablehnung behandelt werden
        # — sonst bleibt der Run unbemerkt "pending" (siehe #841), obwohl der
        # Client bereits eine scheinbar abschließende 422-Antwort erhalten
        # hat. fail_task() selbst hat keine prüfbare Fehlersemantik (siehe
        # TaskManager.update_task) und bleibt daher best-effort.
        persistence_error: Optional[Exception] = None
        try:
            updated_run = run_registry.update_run(
                run_record["run_id"], status="failed", message=guard_message, error=guard_message
            )
        except Exception as exc:  # noqa: BLE001 — Persistenzfehler, unten geloggt
            updated_run = None
            persistence_error = exc

        if updated_run is None:
            logger.error(
                "Persistenzfehler beim Markieren von run_id=%s (task_id=%s) als "
                "failed im Provider-Key-Guard: %s",
                run_record["run_id"], task_id,
                persistence_error or "update_run() lieferte None (Run-Manifest existiert nicht mehr)",
            )
            return json_error(
                ApiErrorCode.INTERNAL_ERROR,
                status=500,
                message="Interner Fehler beim Markieren des Runs als fehlgeschlagen. Bitte erneut versuchen.",
            )
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=422,
            message=guard_message,
        )

    if resolved_api_key is None and _is_local_endpoint(resolved_route.base_url_sanitized):
        # Lokaler Endpoint ohne Key ist explizit freigegeben (siehe Guard oben) —
        # der Platzhalter ersetzt `None`, damit der Generator-Vertrag aus #778
        # (Key und Base-URL aus derselben Quelle) nicht faelschlich einen
        # ValueError wirft.
        resolved_api_key = LOCAL_NO_AUTH_API_KEY

    effective_llm_runtime = build_runtime_llm_config(resolved_route, resolved_api_key)

    manager._set_status(state, SimulationStatus.PREPARING)

    def run_prepare():
        try:
            task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=0,
                message="Start preparing simulation environment...",
            )

            stage_details = {}

            def progress_callback(stage, progress, message, **kwargs):
                stage_weights = {
                    "reading": (0, 20),
                    "generating_profiles": (20, 70),
                    "generating_config": (70, 90),
                    "copying_scripts": (90, 100),
                }

                start, end = stage_weights.get(stage, (0, 100))
                current_progress = int(start + (end - start) * progress / 100)

                stage_names = {
                    "reading": "Read knowledge graph entities",
                    "generating_profiles": "GenerateAgentpersona",
                    "generating_config": "Generate simulation configuration",
                    "copying_scripts": "Prepare simulation scripts",
                }

                stage_index = list(stage_weights.keys()).index(stage) + 1 if stage in stage_weights else 1
                total_stages = len(stage_weights)

                stage_details[stage] = {
                    "stage_name": stage_names.get(stage, stage),
                    "stage_progress": progress,
                    "current": kwargs.get("current", 0),
                    "total": kwargs.get("total", 0),
                    "item_name": kwargs.get("item_name", ""),
                }

                detail = stage_details[stage]
                progress_detail_data = {
                    "current_stage": stage,
                    "current_stage_name": stage_names.get(stage, stage),
                    "stage_index": stage_index,
                    "total_stages": total_stages,
                    "stage_progress": progress,
                    "current_item": detail["current"],
                    "total_items": detail["total"],
                    "item_description": message,
                }

                if detail["total"] > 0:
                    detailed_message = (
                        f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: "
                        f"{detail['current']}/{detail['total']} - {message}"
                    )
                else:
                    detailed_message = f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: {message}"

                task_manager.update_task(
                    task_id,
                    progress=current_progress,
                    message=detailed_message,
                    progress_detail=progress_detail_data,
                )

            result_state = manager.prepare_simulation(
                simulation_id=simulation_id,
                simulation_requirement=simulation_requirement,
                document_text=document_text,
                defined_entity_types=entity_types_list,
                use_llm_for_profiles=use_llm_for_profiles,
                progress_callback=progress_callback,
                parallel_profile_count=parallel_profile_count,
                storage=storage,
                llm_model=resolved_route.model,
                llm_runtime=effective_llm_runtime,
                language=agent_language_override,
                max_agents=max_agents,
                quota_plan=quota_plan,
            )

            task_manager.complete_task(task_id, result=result_state.to_simple_dict())

        except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
            logger.error(f"Failed to prepare simulation: {str(exc)}")
            task_manager.fail_task(task_id, str(exc))

            failed_state = manager.get_simulation(simulation_id)
            if failed_state:
                failed_state.error = str(exc)
                manager._set_status(failed_state, SimulationStatus.FAILED)

    # TODO(P0-queue): migrate to Redis-Queue (RQ) in Wave 2 — see app/jobs/__init__.py
    from ..jobs import enqueue
    enqueue("simulation_prepare", run_prepare)

    return json_success({
        "simulation_id": simulation_id,
        "task_id": task_id,
        "run_id": run_record["run_id"],
        "status": "preparing",
        "message": "Preparation task started; query progress via /api/simulation/prepare/status",
        "already_prepared": False,
        "expected_entities_count": state.entities_count,
        "entity_types": state.entity_types,
    })


@simulation_bp.route('/prepare/status', methods=['POST'])
@handle_api_errors(log_prefix="Failed to query task status")
def get_prepare_status():
    """Query preparation progress by task_id or simulation_id."""
    from ..models.task import TaskManager

    data = request.get_json() or {}
    task_id = data.get('task_id')
    simulation_id = data.get('simulation_id')

    if task_id and not validate_task_id(task_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            status=400,
            message="Invalid task_id format",
        )
    if simulation_id and not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            status=400,
            message="Invalid simulation_id format",
        )

    if simulation_id:
        is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
        if is_prepared:
            return json_success({
                "simulation_id": simulation_id,
                "status": "ready",
                "progress": 100,
                "message": "Preparation already completed",
                "already_prepared": True,
                "prepare_info": prepare_info,
            })

    if not task_id:
        if simulation_id:
            return json_success({
                "simulation_id": simulation_id,
                "status": "not_started",
                "progress": 0,
                "message": "Preparation not started yet, please call /api/simulation/prepare",
                "already_prepared": False,
            })
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message="Please provide task_id or simulation_id",
        )

    task_manager = TaskManager()
    task = task_manager.get_task(task_id)
    if not task:
        if simulation_id:
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
            if is_prepared:
                return json_success({
                    "simulation_id": simulation_id,
                    "task_id": task_id,
                    "status": "ready",
                    "progress": 100,
                    "message": "Task complete（PrepareWork already exists）",
                    "already_prepared": True,
                    "prepare_info": prepare_info,
                })

        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Task does not exist: {task_id}",
        )

    task_dict = task.to_dict()
    task_dict["already_prepared"] = False
    return json_success(task_dict)
