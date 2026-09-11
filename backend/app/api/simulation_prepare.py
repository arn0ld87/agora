"""
Preparation-related simulation API routes split from the main module.
"""

import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Iterator

from flask import request

from . import simulation_bp
from ..models.project import ProjectManager as ProjectManager
from ..services.entity_reader import EntityReader
from ..services.llm_provider_registry import LlmProviderRegistry
from ..services.llm_routing_seed import (
    build_runtime_llm_config,
    resolve_route_api_key,
    seed_run_stage_routing,
)
from ..services.persona_eligibility import filter_eligible_entities
from ..services.prepare_service import compute_persona_target
from ..services.report_agent import MIN_SIMULATION_AGENTS as MIN_SIMULATION_AGENTS
from ..services.run_lifecycle import RunLifecycle, RunPersistenceError
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.stage_model_router import StageModelRouter
from ..utils.validation import validate_simulation_id, validate_task_id
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import handle_api_errors, json_success, json_error
from ..utils.artifact_locator import ArtifactLocator
from .simulation_common import (
    get_simulation_storage,
    logger,
    run_registry,
    simulation_run_artifacts as _simulation_run_artifacts,
)


from ..utils.endpoints import LOCAL_NO_AUTH_API_KEY, is_local_endpoint

if TYPE_CHECKING:  # pragma: no cover — nur für Typprüfung
    from ..contracts.ai_provider_contract import AiModelRef


from .simulation_prepare_contracts import (
    ClientChoice,
    PrepareInputs as _PrepareInputs,
    PrepareRejected as _PrepareRejected,
    PrepareRequest as _PrepareRequest,
    PrepareRouting as _PrepareRouting,
    _collect_prepare_inputs as _collect_prepare_inputs,
    _load_prepare_project as _load_prepare_project,
    _parse_prepare_budget as _parse_prepare_budget,
    _parse_prepare_identity as _parse_prepare_identity,
    _parse_quota_plan as _parse_quota_plan,
    _read_client_choice as _read_client_choice,
    _resolve_max_agents_with_floor as _resolve_max_agents_with_floor,
    _resolve_prepare_routing as _resolve_prepare_routing,
)
from .simulation_prepare_jobs import (
    build_progress_callback as _build_progress_callback,
    make_prepare_job as _make_prepare_job_impl,
)
from .simulation_prepare_state import (
    check_simulation_prepared as _check_simulation_prepared,
)

_ClientChoice = ClientChoice

@dataclass
class _PrepareStartLockEntry:
    lock: threading.Lock
    users: int = 0


_prepare_start_locks: dict[str, _PrepareStartLockEntry] = {}
_prepare_start_locks_guard = threading.Lock()
_active_prepare_jobs: set[str] = set()


@contextmanager
def _prepare_start_lock(simulation_id: str) -> Iterator[None]:
    """Thread-sicherer Context-Manager für vorbereitungsspezifische Locks.

    Verhindert parallele Prepare-Jobs für dieselbe Simulation-ID durch
    einsetzbaren Lock-Mechanismus mit Referenzzählung.
    """
    with _prepare_start_locks_guard:
        entry = _prepare_start_locks.setdefault(
            simulation_id,
            _PrepareStartLockEntry(lock=threading.Lock()),
        )
        entry.users += 1
    try:
        with entry.lock:
            yield
    finally:
        with _prepare_start_locks_guard:
            entry.users -= 1
            if entry.users == 0 and _prepare_start_locks.get(simulation_id) is entry:
                del _prepare_start_locks[simulation_id]










def _ensure_prepare_startable(
    state: Any,
    simulation_id: str,
) -> None:
    """Verhindert zwei schreibende Prepare-Jobs fuer dieselbe Simulation."""
    if state.status != SimulationStatus.PREPARING:
        return
    with _prepare_start_locks_guard:
        active_job_exists = simulation_id in _active_prepare_jobs
    if not active_job_exists:
        return
    raise _PrepareRejected(
        json_error(
            ApiErrorCode.SIMULATION_PREPARE_IN_PROGRESS,
            status=409,
            message="Simulation preparation is already in progress",
        )
    )




















def _already_prepared_response(simulation_id: str):
    """Phase 3 — Kurzschluss, wenn alle Vorbereitungs-Artefakte schon liegen.

    Gibt ``None`` zurück, wenn regulär vorbereitet werden muss.
    """
    logger.debug(f"Check simulation {simulation_id} Is preparation complete...")
    is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
    logger.debug(f"Check result: is_prepared={is_prepared}, prepare_info={prepare_info}")
    if not is_prepared:
        logger.info(f"Simulation {simulation_id} has no preparation complete, preparing now")
        return None

    logger.info(f"Simulation {simulation_id} has preparation complete, no need to regenerate")
    return json_success({
        "simulation_id": simulation_id,
        "status": "ready",
        "message": "Preparation already completed, no need to regenerate",
        "already_prepared": True,
        "prepare_info": prepare_info,
    })




def _preview_entity_counts(state, storage, inputs: _PrepareInputs) -> None:
    """Phase 5 — Entitätenzahl für die Antwort vorab schätzen (best effort).

    Fehler sind hier bewusst nicht fatal: der Hintergrund-Task liest dieselbe
    Menge erneut.
    """
    try:
        logger.info(f"Synchronously get entity count: graph_id={state.graph_id}")
        reader = EntityReader(storage)
        filtered_preview = reader.filter_defined_entities(
            graph_id=state.graph_id,
            defined_entity_types=inputs.entity_types,
            enrich_with_edges=False,
        )
        # Issue #1034: derselbe Eignungsfilter wie im Laufpfad
        # (_phase_read_entities) — sonst zeigt der Preview-Nenner eine
        # Menge, die die eigentliche Generierung so nie erzeugt.
        # Bewusst ohne Sammler: diese Vorschau hat kein Task-Ergebnis, in
        # das ein Befund fließen könnte. Gemeldet wird im Laufpfad, der
        # dieselbe Menge erneut filtert. Ein Sammler an dieser Stelle
        # sähe nach Absicherung aus und wäre folgenlos.
        eligibility_preview = filter_eligible_entities(
            filtered_preview.entities,
            degradations=None,
        )
        if eligibility_preview.exclusions:
            filtered_preview.entities = eligibility_preview.eligible
            filtered_preview.filtered_count = len(filtered_preview.entities)
            filtered_preview.entity_types = {
                entity.get_entity_type() or "Entity"
                for entity in filtered_preview.entities
            }
        # Issue #1177: derselbe Dedup wie im Laufpfad. Ohne ihn zeigte die
        # Vorschau die Zahl vor der Bereinigung und damit mehr Personas, als
        # die Generierung anschliessend erzeugt — der Nutzer saehe eine Zahl,
        # die nie eintritt. Der Kommentar oben nennt genau diese Gefahr
        # bereits fuer den Eignungsfilter.
        from ..services.prepare_service import _dedupe_entities

        deduped_preview, duplicate_count = _dedupe_entities(filtered_preview.entities)
        if duplicate_count:
            filtered_preview.entities = deduped_preview
            filtered_preview.filtered_count = len(deduped_preview)
            filtered_preview.entity_types = {
                entity.get_entity_type() or "Entity" for entity in deduped_preview
            }

        preview_count = filtered_preview.filtered_count
        if inputs.max_agents is not None and inputs.max_agents > 0:
            preview_count = min(preview_count, inputs.max_agents)
        state.entities_count = preview_count
        state.entity_types = list(filtered_preview.entity_types)
        logger.info(
            "Expected entity count: %s, entity types: %s",
            filtered_preview.filtered_count,
            filtered_preview.entity_types,
        )
    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning(
            "Synchronous entity count failed (will retry in the background task): %s", exc
        )


def _precheck_prepare_ai_model_ref(ai_model_ref: "AiModelRef | None") -> None:
    """Phase 6a — Connection der expliziten ``AiModelRef`` vorab prüfen."""
    if ai_model_ref is None:
        return

    from ..services.llm_routing_seed import prevalidate_ai_model_ref

    try:
        prevalidate_ai_model_ref(ai_model_ref)
    except ValueError as exc:
        raise _PrepareRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message=str(exc),
            )
        ) from exc


def _begin_prepare_run(
    req: _PrepareRequest, state, routing: _PrepareRouting
) -> RunLifecycle:
    """Phase 6b — Lifecycle für den Run-Record des Vorbereitungslaufs bauen."""
    return RunLifecycle.begin(
        run_registry,
        "simulation_prepare",
        req.simulation_id,
        failure_message="Simulation preparation failed: {exc_type}",
        progress=0,
        message="Simulation preparation queued",
        linked_ids={
            "simulation_id": req.simulation_id,
            "project_id": state.project_id,
        },
        artifacts=_simulation_run_artifacts(req.simulation_id),
        resume_capability={"available": True, "action": "restart", "label": "Restart preparation"},
        branch_label=state.branch_name,
        metadata={
            "project_id": state.project_id,
            "graph_id": state.graph_id,
            "source_simulation_id": state.source_simulation_id,
            "root_simulation_id": state.root_simulation_id,
            "branch_name": state.branch_name,
            "branch_depth": state.branch_depth,
            "llm_model": routing.llm_model_override,
            "llm_provider": routing.llm_runtime.redacted_metadata() or None,
            # Budget-Config (Issue #764) — nur Limits, keine Secrets
            **({"budget": req.budget_config.model_dump(mode="json")} if req.budget_config else {}),
        },
    )


def _seed_prepare_routing(
    run_record: "dict[str, Any]",
    routing: _PrepareRouting,
    ai_model_ref: "AiModelRef | None",
) -> None:
    """Phase 7 — Stage-Routing für ``persona_generation`` seeden."""
    if ai_model_ref is None:
        seed_run_stage_routing(
            run_record["run_id"],
            "persona_generation",
            llm_model_override=routing.llm_model_override,
            llm_runtime=routing.llm_runtime,
            llm_profile_id=routing.routed_profile_id,
        )
        return

    try:
        seed_run_stage_routing(
            run_record["run_id"],
            "persona_generation",
            llm_model_override=routing.llm_model_override,
            llm_runtime=routing.llm_runtime,
            llm_profile_id=routing.routed_profile_id,
            ai_model_ref=ai_model_ref,
        )
    except ValueError as exc:
        raise _PrepareRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message=str(exc),
            ),
            run_failure_message=str(exc),
        ) from exc


def _resolve_prepare_route(run_record: "dict[str, Any]", llm_runtime):
    """Phase 8 — Stage-Route auflösen, sperren und den API-Key bestimmen."""
    route_router = StageModelRouter(run_record["run_id"])
    resolved_route = route_router.resolve("persona_generation")
    route_router.lock_stage("persona_generation", resolved_route)
    definition = LlmProviderRegistry.connection_definition(resolved_route.provider_id)
    if definition is not None and definition.transport == "cli":
        # CLI-Provider nutzen ihre lokale Anmeldung, keinen HTTP-API-Key.
        # Die Registry entscheidet; eine fehlende URL allein ist keine Freigabe.
        return resolved_route, None
    resolved_api_key = resolve_route_api_key(resolved_route, llm_runtime)

    if resolved_api_key is None and not is_local_endpoint(resolved_route.base_url_sanitized):
        guard_message = (
            f"provider_override: kein api_key im Payload und kein Key in der Settings-DB "
            f"für Provider '{resolved_route.provider_id}'. "
            "Bitte in Einstellungen → LLM-Anbieter einen Schlüssel speichern "
            "oder im Sitzungsfeld eingeben."
        )
        raise _PrepareRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=422,
                message=guard_message,
            ),
            run_failure_message=guard_message,
        )

    if resolved_api_key is None and is_local_endpoint(resolved_route.base_url_sanitized):
        # Lokaler Endpoint ohne Key ist explizit freigegeben (siehe Guard oben) —
        # der Platzhalter ersetzt `None`, damit der Generator-Vertrag aus #778
        # (Key und Base-URL aus derselben Quelle) nicht faelschlich einen
        # ValueError wirft.
        resolved_api_key = LOCAL_NO_AUTH_API_KEY

    return resolved_route, resolved_api_key




def _finish_cancelled_prepare_run(run_id: str, *, simulation_id: str) -> None:
    """Setzt den Abbruch-Endzustand eines per ``/cancel`` gestoppten Prepare-Laufs.

    Issue B2. Spiegelt bewusst ``services/report_generation.py::finish_cancelled_run``:
    ``stopped`` + ``termination_reason="user_cancel"``, Teilergebnisse bleiben
    als Artefakt erhalten. Anders als beim Report gibt es hier kein separates
    ``report_id`` — die einzigen Prepare-Artefakte hängen an ``simulation_id``
    (u. a. die Profildatei, die ``_phase_generate_profiles`` laufend speichert,
    nicht erst am Phasenende). Das Flag wird danach gelöscht, damit ein
    erneuter Prepare-Versuch (neue ``run_id``) nicht sofort wieder abbricht.
    """
    from ..services.sim.cancel_flag import clear_cancel

    run_registry.update_run(
        run_id,
        status="stopped",
        termination_reason="user_cancel",
        message=(
            "Vom Nutzer abgebrochen — bereits generierte Personas bleiben "
            "als Teilergebnis erhalten"
        ),
        event_type="user_cancel",
        artifacts=ArtifactLocator.existing_paths({
            "simulation": ArtifactLocator.simulation_artifacts(simulation_id),
        }),
        resume_capability={
            "available": True,
            "action": "restart",
            "label": "Restart simulation preparation",
        },
    )
    clear_cancel(run_id)




def _make_prepare_job(
    *,
    manager,
    task_manager,
    task_id: str,
    simulation_id: str,
    inputs: _PrepareInputs,
    storage,
    llm_model: str,
    effective_llm_runtime,
    run_record: "dict[str, Any]",
) -> "Callable[[], None]":
    """Compatibility wrapper around the extracted background-job builder."""
    return _make_prepare_job_impl(
        manager=manager,
        task_manager=task_manager,
        task_id=task_id,
        simulation_id=simulation_id,
        inputs=inputs,
        storage=storage,
        llm_model=llm_model,
        effective_llm_runtime=effective_llm_runtime,
        run_record=run_record,
        progress_callback_factory=_build_progress_callback,
        finish_cancelled_prepare_run=_finish_cancelled_prepare_run,
    )


def _track_active_prepare_job(
    simulation_id: str,
    target: "Callable[[], None]",
) -> "Callable[[], None]":
    """Wrapt den Hintergrund-Job, damit er sich in ``_active_prepare_jobs`` trägt.

    Der Eintrag wird garantiert im ``finally`` wieder entfernt — auch bei
    Exceptions im Job. Consumer (z.B. Cancel) prüfen darüber, ob ein
    Prepare-Job für die Simulation läuft.
    """
    with _prepare_start_locks_guard:
        _active_prepare_jobs.add(simulation_id)

    def tracked() -> None:
        try:
            target()
        finally:
            with _prepare_start_locks_guard:
                _active_prepare_jobs.discard(simulation_id)

    return tracked


def _discard_active_prepare_job(simulation_id: str) -> None:
    """Entfernt den Active-Job-Eintrag idempotent (Discard statt Remove)."""
    with _prepare_start_locks_guard:
        _active_prepare_jobs.discard(simulation_id)


def _build_prepare_response(
    simulation_id: str,
    task_id: str,
    run_record: "dict[str, Any]",
    state,
    inputs: _PrepareInputs,
) -> "dict[str, Any]":
    """Phase 10 — Antwort-Payload des angestoßenen Vorbereitungslaufs."""
    return {
        "simulation_id": simulation_id,
        "task_id": task_id,
        "run_id": run_record["run_id"],
        "status": "preparing",
        "message": "Preparation task started; query progress via /api/simulation/prepare/status",
        "already_prepared": False,
        "expected_entities_count": state.entities_count,
        "entity_types": state.entity_types,
        # Issue #1034: Der Fortschrittszähler zählt Personas, nicht
        # Entitäten. `expected_entities_count` bleibt die Entitätenzahl;
        # den Nenner liefert `persona_target` aus derselben Funktion, die
        # auch `_phase_generate_profiles` im Laufpfad verwendet.
        "persona_target": compute_persona_target(
            state.entities_count,
            max_agents=inputs.max_agents,
            quota_plan=inputs.quota_plan,
        ).model_dump(mode="json"),
    }


def _prepare_simulation_under_start_lock(
    data: "dict[str, Any]",
    simulation_id: str,
    ai_model_ref: "AiModelRef | None",
):
    """Prüft und startet Prepare innerhalb des simulationsbezogenen Locks."""
    from ..models.task import TaskManager

    try:
        manager = SimulationManager()
        task_manager = TaskManager()
        state = manager.get_simulation(simulation_id)
        if not state:
            raise _PrepareRejected(
                json_error(
                    ApiErrorCode.NOT_FOUND,
                    status=404,
                    message=f"Simulation does not exist: {simulation_id}",
                )
            )

        _ensure_prepare_startable(state, simulation_id)

        req = _PrepareRequest(
            simulation_id=simulation_id,
            ai_model_ref=ai_model_ref,
            budget_config=_parse_prepare_budget(data),
            force_regenerate=data.get('force_regenerate', False),
        )
        project = _load_prepare_project(state)
        routing = _resolve_prepare_routing(data, project, ai_model_ref)

        logger.info(
            f"Start processing /prepare Request: simulation_id={simulation_id}, "
            f"force_regenerate={req.force_regenerate}",
            extra={'simulation_id': simulation_id},
        )

        if not req.force_regenerate and not routing.client_requested_override:
            already_prepared = _already_prepared_response(simulation_id)
            if already_prepared is not None:
                return already_prepared

        inputs = _collect_prepare_inputs(data, project, state)
        storage = get_simulation_storage()
        _preview_entity_counts(state, storage, inputs)

        _precheck_prepare_ai_model_ref(ai_model_ref)
    except _PrepareRejected as rejected:
        # Vor der Run-Registrierung — es gibt noch keinen Record, der
        # verwaisen könnte.
        return rejected.response

    # Issue #841/#1183: Ab der Registrierung existiert ein Run-Record mit
    # status="pending". Task-Kopplung (#841-Reihenfolge), BaseException-Netz
    # und strikte Persistenzsemantik (#844) liegen im RunLifecycle. Auch
    # Statuswechsel und Enqueue laufen innerhalb des Fensters — ihr Scheitern
    # hinterließ vorher einen pending-Phantom.
    try:
        with _begin_prepare_run(req, state, routing) as run:
            run_record = run.record
            task_id = task_manager.create_task(
                task_type="simulation_prepare",
                metadata={
                    "simulation_id": req.simulation_id,
                    "project_id": state.project_id,
                    "run_id": run_record["run_id"],
                },
            )
            run.attach_task(task_manager, task_id)
            _seed_prepare_routing(run_record, routing, ai_model_ref)
            resolved_route, resolved_api_key = _resolve_prepare_route(
                run_record, routing.llm_runtime
            )

            effective_llm_runtime = build_runtime_llm_config(resolved_route, resolved_api_key)

            manager._set_status(state, SimulationStatus.PREPARING)

            # TODO(P0-queue): migrate to Redis-Queue (RQ) in Wave 2 — see app/jobs/__init__.py
            from ..jobs import enqueue
            tracked_job = _track_active_prepare_job(
                simulation_id,
                _make_prepare_job(
                    manager=manager,
                    task_manager=task_manager,
                    task_id=task_id,
                    simulation_id=simulation_id,
                    inputs=inputs,
                    storage=storage,
                    llm_model=resolved_route.model,
                    effective_llm_runtime=effective_llm_runtime,
                    run_record=run_record,
                ),
            )
            try:
                enqueue("simulation_prepare", tracked_job)
            except BaseException:
                _discard_active_prepare_job(simulation_id)
                raise
    except RunPersistenceError:
        # #844: Die failed-Markierung wurde nicht persistiert — das darf nicht
        # wie eine sauber abgeschlossene Ablehnung aussehen.
        return json_error(
            ApiErrorCode.INTERNAL_ERROR,
            status=500,
            message=(
                "Interner Fehler beim Markieren des Runs als fehlgeschlagen. "
                "Bitte erneut versuchen."
            ),
        )
    except _PrepareRejected as rejected:
        return rejected.response

    return json_success(_build_prepare_response(simulation_id, task_id, run_record, state, inputs))


@simulation_bp.route('/prepare', methods=['POST'])
@handle_api_errors(log_prefix="Failed to start preparation task")
def prepare_simulation():
    """Prepare a simulation environment as an async task."""
    data = request.get_json() or {}
    try:
        simulation_id, ai_model_ref = _parse_prepare_identity(data)
    except _PrepareRejected as rejected:
        return rejected.response

    with _prepare_start_lock(simulation_id):
        return _prepare_simulation_under_start_lock(data, simulation_id, ai_model_ref)


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
                    "message": "Task complete (PrepareWork already exists)",
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
