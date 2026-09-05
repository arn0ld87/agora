"""
Run-control and live-status routes split from the main simulation API module.
"""

import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from flask import jsonify, request

from . import simulation_bp
from ..config import Config
from ..models.project import ProjectManager
from ..services.persona_review_service import PersonaReviewService
from ..services.llm_routing_seed import (
    build_route_subprocess_env,
    resolve_route_api_key,
    seed_run_stage_routing,
)
from ..utils.endpoints import is_local_endpoint
from ..services.llm_runtime import RuntimeLlmConfig, parse_runtime_llm_config
from ..services.manifest_capture import ManifestCapture
from ..services.run_lifecycle import RunLifecycle, RunPersistenceError
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner
from ..services.stage_model_router import StageModelRouter
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.artifact_locator import ArtifactLocator
from ..utils.pagination import clamp_int, DEFAULT_LIMIT, MAX_LIMIT
from ..utils.scopes import require_scope
from ..utils.validation import validate_simulation_id
from .simulation_common import (
    get_artifact_store,
    logger,
    run_registry,
    simulation_resume_capability as _simulation_resume_capability,
    simulation_run_artifacts as _simulation_run_artifacts,
)
from .simulation_prepare import _check_simulation_prepared

if TYPE_CHECKING:  # pragma: no cover — nur für Typprüfung
    from ..contracts.ai_provider_contract import AiModelRef
    from ..contracts.llm_routing_contract import ResolvedRoute
    from ..contracts.run_budget_contract import RunBudgetConfig


def _evaluate_persona_review_gate(simulation_id: str):
    """Return a 409 response when PERSONA_REVIEW_ENABLED blocks the start.

    Returns None when the gate is open. The gate is silent while the global
    ``PERSONA_REVIEW_ENABLED`` flag is off so existing behaviour is unchanged
    until an operator explicitly opts in.
    """
    if not Config.PERSONA_REVIEW_ENABLED:
        return None
    review = PersonaReviewService(get_artifact_store()).evaluate_start_gate(
        simulation_id
    )
    if review["allowed"]:
        return None
    return json_error(
        ApiErrorCode.PERSONA_REVIEW_REQUIRED,
        status=409,
        message="Persona review pending. Approve all personas before starting the simulation.",
        extra={"review": review},
    )


def _simulation_dir(simulation_id: str) -> str:
    return ArtifactLocator.simulation_dir(simulation_id)


def _apply_budget_to_simulation(simulation_id, run_id, budget_config, set_config_fn) -> None:
    """Budget-Config am Run verankern und Subprozess-Artefakte pflegen (#764).

    - Mit Budget: metadata.budget im Manifest + budget_config.json im Sim-Dir
      (vom Subprozess-Guard gelesen).
    - Ohne Budget: Alt-Artefakte entfernen (budget_config.json /
      budget_abort.json eines früheren Runs darf nicht weiterwirken).
    Keine Secrets: die Config enthält nur Limits, Enforcement und Währung.
    """
    import os as _os

    sim_dir = _simulation_dir(simulation_id)
    config_path = _os.path.join(sim_dir, "budget_config.json")
    abort_path = _os.path.join(sim_dir, "budget_abort.json")

    if budget_config is not None:
        set_config_fn(run_id, budget_config)
        _os.makedirs(sim_dir, exist_ok=True)
        tmp_path = f"{config_path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            handle.write(budget_config.model_dump_json(indent=2))
            handle.write("\n")
        _os.replace(tmp_path, config_path)
        if _os.path.exists(abort_path):
            _os.remove(abort_path)
    else:
        for stale in (config_path, abort_path):
            if _os.path.exists(stale):
                try:
                    _os.remove(stale)
                except OSError:
                    logger.warning("Konnte veraltetes Budget-Artefakt nicht löschen: %s", stale)


class _StartRejected(Exception):
    """Bricht eine Start-Phase mit einer fertig gebauten Fehler-Response ab.

    Die Phasen unterhalb von :func:`start_simulation` sind einzeln testbar und
    müssen ihren Ablehnungsfall deshalb selbst formulieren können. Sie tragen
    die bereits gebaute ``json_error``-Response, damit Status-Code, Fehlercode
    und Meldung wortgleich das bleiben, was der monolithische Handler vorher
    zurückgegeben hat (#1079).
    """

    #: Failed-Meldung für einen bereits registrierten Run (RunLifecycle).
    run_failure_message = "Simulation start rejected before launch"

    def __init__(self, response: Any) -> None:
        super().__init__("simulation start rejected")
        self.response = response


@dataclass(frozen=True)
class _StartRequest:
    """Validierte Eingaben eines ``POST /api/simulation/start``.

    Interner Parameter-Container zwischen den Start-Phasen, **kein**
    API-Vertrag: die Wire-Validierung bleibt feldweise in
    :func:`_parse_start_request`, und nichts an dieser Klasse wird serialisiert.
    """

    simulation_id: str
    platform: str
    max_rounds: "int | None"
    simulation_days: "int | None"
    llm_model_override: "str | None"
    llm_runtime: RuntimeLlmConfig
    ai_model_ref: "AiModelRef | None"
    budget_config: "RunBudgetConfig | None"
    enable_graph_memory_update: bool
    force: bool


def _parse_bounded_int(
    raw: Any,
    *,
    minimum: int,
    maximum: "int | None",
    range_message: str,
    type_message: str,
) -> int:
    """Ganzzahl mit Grenzen parsen; wirft :class:`_StartRejected` bei Verstoß."""
    try:
        value = int(raw)
    except (ValueError, TypeError):
        raise _StartRejected(
            json_error(ApiErrorCode.VALIDATION_FAILED, message=type_message)
        ) from None
    if value < minimum or (maximum is not None and value > maximum):
        raise _StartRejected(
            json_error(ApiErrorCode.VALIDATION_FAILED, message=range_message)
        )
    return value


def _parse_ai_model_ref(data: "dict[str, Any]") -> "AiModelRef | None":
    """Explizite UI-Auswahl (``AiModelRef``) lesen und gegen Legacy-Felder sperren.

    Die AiModelRef ist die autoritative Sim-Route und darf nicht still mit
    Legacy-Feldern kombiniert werden (Issue #817, analog /api/report/generate).
    Wenn gesetzt, wird die ProviderConnection zur Single Source of Truth für
    Modell, Base-URL und gebundenen Key — kein .env-Fallback. Root Cause des
    OASIS-404 ``model MiniMax-M3 not found``: der Legacy-Pfad reichte nur den
    nackten Modellnamen weiter und produzierte eine Route ohne Base-URL +
    Default-Provider-Key → CAMEL traf den OpenAI-Default-Endpoint. Der
    ai_model_ref-Pfad bindet Connection-URL und -Secret atomar
    (connection_only=True).
    """
    raw_ref = data.get('ai_model_ref')
    if raw_ref is None:
        return None

    from pydantic import ValidationError as _ValidationError

    from ..contracts.ai_provider_contract import AiModelRef as _AiModelRef
    try:
        ai_model_ref = _AiModelRef.model_validate(raw_ref)
    except _ValidationError:
        raise _StartRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message="ai_model_ref ist ungültig",
            )
        ) from None
    # Nur die Legacy-Felder prüfen, die dieser Handler auch ausliest und
    # weiterreicht (llm_model → llm_model_override, llm_provider →
    # llm_runtime). llm_profile_id wird im Sim-Start nicht unterstützt und
    # daher nicht als Konfliktgrund geführt — ein Profilpfad ist hier nicht
    # implementiert (CodeRabbit PR #852).
    conflicting = [
        key for key in ('llm_model', 'llm_provider')
        if data.get(key)
    ]
    if conflicting:
        raise _StartRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message=(
                    f"ai_model_ref darf nicht mit {', '.join(conflicting)} "
                    "kombiniert werden"
                ),
            )
        )
    return ai_model_ref


def _parse_budget_config(data: "dict[str, Any]") -> "RunBudgetConfig | None":
    """Run-Budget (Issue #764): optionale Token-/Kosten-/Zeit-/Aufruflimits."""
    raw_budget = data.get('budget')
    if raw_budget is None:
        return None

    from pydantic import ValidationError as _BudgetValidationError

    from ..contracts.run_budget_contract import RunBudgetConfig as _RunBudgetConfig
    try:
        return _RunBudgetConfig.model_validate(raw_budget)
    except _BudgetValidationError as exc:
        raise _StartRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message=f"budget ist ungültig: {exc.errors()[0].get('msg', 'validation error')}",
            )
        ) from exc


def _parse_start_request(data: "dict[str, Any]") -> _StartRequest:
    """Phase 1 — Request-Payload validieren und in einen Container überführen.

    Die Prüfreihenfolge ist Teil des API-Verhaltens: bei mehreren fehlerhaften
    Feldern entscheidet sie, welche Meldung der Aufrufer sieht.
    """
    simulation_id = data.get('simulation_id')
    if not simulation_id:
        raise _StartRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                message="Please provide simulation_id",
            )
        )
    if not validate_simulation_id(simulation_id):
        raise _StartRejected(
            json_error(
                ApiErrorCode.INVALID_ID,
                message="Invalid simulation_id format",
            )
        )

    platform = data.get('platform', 'parallel')
    llm_model_override = (data.get('llm_model') or '').strip() or None
    try:
        llm_runtime = parse_runtime_llm_config(data)
    except ValueError as exc:
        raise _StartRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message=str(exc),
            )
        ) from exc

    ai_model_ref = _parse_ai_model_ref(data)
    if ai_model_ref is not None:
        # Legacy-Override stummschalten: die Connection ist maßgeblich.
        llm_model_override = None
        llm_runtime = parse_runtime_llm_config({})

    budget_config = _parse_budget_config(data)

    raw_max_rounds = data.get('max_rounds')
    max_rounds = None if raw_max_rounds is None else _parse_bounded_int(
        raw_max_rounds,
        minimum=1,
        maximum=None,
        range_message="max_rounds must be a positive integer",
        type_message="max_rounds must be a valid integer",
    )

    raw_simulation_days = data.get('simulation_days')
    simulation_days = None if raw_simulation_days is None else _parse_bounded_int(
        raw_simulation_days,
        minimum=1,
        maximum=365,
        range_message="simulation_days must be between 1 and 365",
        type_message="simulation_days must be a valid integer",
    )

    if platform not in ['twitter', 'reddit', 'parallel']:
        raise _StartRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                message=f"Invalid platform type: {platform}. Allowed: twitter/reddit/parallel",
            )
        )

    return _StartRequest(
        simulation_id=simulation_id,
        platform=platform,
        max_rounds=max_rounds,
        simulation_days=simulation_days,
        llm_model_override=llm_model_override,
        llm_runtime=llm_runtime,
        ai_model_ref=ai_model_ref,
        budget_config=budget_config,
        enable_graph_memory_update=data.get('enable_graph_memory_update', False),
        force=data.get('force', False),
    )


def _stop_running_simulation(simulation_id: str, force: bool) -> None:
    """Laufenden Sim-Prozess für einen Force-Restart beenden.

    Ohne ``force`` ist ein laufender Run ein 409 — der Aufrufer muss erst
    ``/stop`` rufen.
    """
    run_state = SimulationRunner.get_run_state(simulation_id)
    if not (run_state and run_state.runner_status.value == 'running'):
        return
    if not force:
        raise _StartRejected(
            json_error(
                ApiErrorCode.SIMULATION_ALREADY_RUNNING,
                status=409,
                message=(
                    "Simulation is running. Please call /stop first or use force=true to force restart."
                ),
            )
        )
    logger.info(f"Force mode: stopping running simulation {simulation_id}")
    try:
        SimulationRunner.stop_simulation(simulation_id)
    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning(f"Warning when stopping simulation: {exc}")


def _ensure_startable_state(manager, state, req: _StartRequest) -> bool:
    """Phase 2 — sicherstellen, dass die Simulation startbar ist.

    Gibt zurück, ob dafür ein Force-Restart nötig war (``force_restarted``).
    """
    if state.status == SimulationStatus.READY:
        return False

    is_prepared, _prepare_info = _check_simulation_prepared(req.simulation_id)
    if not is_prepared:
        raise _StartRejected(
            json_error(
                ApiErrorCode.SIMULATION_NOT_PREPARED,
                status=409,
                message=(
                    f"Simulation not ready. Current status: {state.status.value}. "
                    "Please call /prepare first"
                ),
            )
        )

    if state.status == SimulationStatus.RUNNING:
        _stop_running_simulation(req.simulation_id, req.force)

    force_restarted = False
    if req.force:
        logger.info(f"Force mode: cleaning simulation runtime files for {req.simulation_id}")
        cleanup_result = SimulationRunner.cleanup_simulation_logs(req.simulation_id)
        if not cleanup_result.get("success"):
            logger.warning(f"Warning when cleaning logs: {cleanup_result.get('errors')}")
        force_restarted = True

    manager._reset_to_ready(
        state,
        reason=f"force start_run after status={state.status.value}",
    )
    return force_restarted


def _resolve_graph_memory_id(state, req: _StartRequest) -> "str | None":
    """Phase 3 — Graph-ID für das Knowledge-Graph-Memory-Update auflösen."""
    if not req.enable_graph_memory_update:
        return None

    graph_id = state.graph_id
    if not graph_id:
        project = ProjectManager.get_project(state.project_id)
        if project:
            graph_id = project.graph_id
    if not graph_id:
        raise _StartRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                message=(
                    "Enable knowledge graph memory update requires valid graph_id. "
                    "Please ensure project graph is built."
                ),
            )
        )
    logger.info(
        f"Enable knowledge graph memory update: simulation_id={req.simulation_id}, graph_id={graph_id}",
        extra={'simulation_id': req.simulation_id},
    )
    return graph_id


def _precheck_runtime_provider_key(llm_runtime: RuntimeLlmConfig) -> None:
    """Phase 4a — Key-Verfügbarkeit für einen Legacy-Provider-Override prüfen.

    Pre-Check VOR der Run-Record-Creation, damit kein orphaned Run entsteht
    (Copilot PR #466, simulation_run.py:247). Dafür simulieren wir die
    Stage-Auflösung ohne Persistenz: ein leerer Routing-Stub reicht für die
    Provider/Key-Bestimmung, weil ``seed_run_stage_routing`` nichts anderes
    tut als Workspace-Default + Override zusammenzuführen.
    """
    if not (llm_runtime.enabled and not llm_runtime.api_key):
        return

    from ..services.llm_routing_seed import map_runtime_provider_to_route_provider
    from ..services.secret_resolver import SecretResolver
    from ..services.llm_provider_registry import LlmProviderRegistry
    provider_id_preview = map_runtime_provider_to_route_provider(llm_runtime.provider)
    if not provider_id_preview:
        return

    registry = LlmProviderRegistry()
    descriptor = next((p for p in registry.get_providers() if p.id == provider_id_preview), None)
    p_type = descriptor.type if descriptor else "openai_compatible"
    stored_key = SecretResolver().get_api_key(provider_id_preview, p_type)
    if not stored_key and not is_local_endpoint(
        (descriptor.base_url if descriptor else None) or llm_runtime.base_url
    ):
        raise _StartRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=422,
                message=(
                    f"provider_override: kein api_key im Payload und kein Key in der Settings-DB "
                    f"für Provider '{provider_id_preview}'. "
                    "Bitte in Einstellungen → LLM-Anbieter einen Schlüssel speichern "
                    "oder im Sitzungsfeld eingeben."
                ),
            )
        )


def _precheck_ai_model_ref(ai_model_ref: "AiModelRef | None") -> None:
    """Phase 4b — Connection der expliziten ``AiModelRef`` vorab prüfen.

    Pre-Check VOR der Run-Record-Creation: die Connection muss existieren,
    aktiviert sein und (für api_key-Connections) ein gebundenes Secret tragen —
    sonst kein .env-Fallback, sondern 422 (analog dem Legacy-Pre-Check, kein
    orphaned Run). Die volle Model-Discovery (Connection/Model-Mismatch, Issue
    #819) läuft später in ``seed_run_stage_routing``; deren ValueError wird am
    Endpunkt zu 4xx.
    """
    if ai_model_ref is None:
        return

    from ..services.llm_routing_seed import prevalidate_ai_model_ref
    try:
        prevalidate_ai_model_ref(ai_model_ref)
    except ValueError as exc:
        raise _StartRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=422,
                message=str(exc),
            )
        ) from exc


def _begin_start_run(req: _StartRequest, state) -> RunLifecycle:
    """Phase 5 — Lifecycle für den Run-Record des Startlaufs bauen."""
    return RunLifecycle.begin(
        run_registry,
        "simulation_run",
        req.simulation_id,
        failure_message="Simulation start failed: {exc_type}",
        progress=0,
        message="Simulation run queued",
        linked_ids={"simulation_id": req.simulation_id, "project_id": state.project_id},
        artifacts=_simulation_run_artifacts(req.simulation_id),
        resume_capability=_simulation_resume_capability(req.simulation_id, state),
        branch_label=state.branch_name,
        metadata={
            "graph_id": state.graph_id,
            "platform": req.platform,
            "source_simulation_id": state.source_simulation_id,
            "root_simulation_id": state.root_simulation_id,
            "branch_name": state.branch_name,
            "branch_depth": state.branch_depth,
            "llm_model": req.llm_model_override,
            "llm_provider": req.llm_runtime.redacted_metadata() or None,
        },
    )


def _resolve_start_route(run_id: str, llm_runtime: RuntimeLlmConfig):
    """Phase 6 — Stage-Route auflösen, sperren und den API-Key bestimmen."""
    route_router = StageModelRouter(run_id)
    resolved_route = route_router.resolve("simulation_rounds")
    route_router.lock_stage("simulation_rounds", resolved_route)
    resolved_api_key = resolve_route_api_key(resolved_route, llm_runtime)

    # Issue #1423: Ein CLI-Provider (codex_cli, transport="cli") hat per
    # Definition keinen api_key — er authentifiziert über die lokale
    # ``codex login``-Session. ``is_local_endpoint(None)`` ist ``False``,
    # deshalb hätte der Guard darunter jeden codex_cli-Start mit 422
    # abgelehnt, bevor der Subprozess überhaupt startet.
    from ..services.llm_provider_registry import LlmProviderRegistry

    definition = LlmProviderRegistry.connection_definition(resolved_route.provider_id)
    is_cli_transport = definition is not None and definition.transport == "cli"

    if (
        resolved_api_key is None
        and not is_cli_transport
        and not is_local_endpoint(resolved_route.base_url_sanitized)
    ):
        # Fallback-422 für Workspace-Default-Fälle (kein Frontend-Override).
        # Issue #1176: Die Markierung als ``failed`` steht nicht mehr hier,
        # sondern im Netz um den gesamten Startabschnitt — sonst gäbe es zwei
        # Stellen mit derselben Verantwortung, und nur eine davon würde bei
        # einem neuen Abbruchpfad mitgezogen.
        raise _StartRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=422,
                message=(
                    f"provider_override: kein api_key im Payload und kein Key in der Settings-DB "
                    f"für Provider '{resolved_route.provider_id}'. "
                    "Bitte in Einstellungen → LLM-Anbieter einen Schlüssel speichern "
                    "oder im Sitzungsfeld eingeben."
                ),
            )
        )
    return resolved_route, resolved_api_key


def _has_config_overrides(req: _StartRequest) -> bool:
    """Ob der Request die persistierte Sim-Config überhaupt anfasst."""
    return bool(
        req.simulation_days is not None
        or req.llm_model_override
        or req.llm_runtime.enabled
        or req.ai_model_ref is not None
    )


def _apply_route_to_simulation_config(
    req: _StartRequest, resolved_route: "ResolvedRoute", run_id: str
) -> None:
    """Phase 7 — Laufzeit-Overrides in die persistierte Sim-Config schreiben."""
    if not _has_config_overrides(req):
        return

    store = get_artifact_store()
    config = store.read_json(req.simulation_id, "simulation_config", default=None)
    if not config:
        # Der Run wurde in Phase 5 bereits registriert — die failed-Markierung
        # übernimmt der RunLifecycle um den Startabschnitt (#1094, #1183).
        raise _StartRejected(
            json_error(
                ApiErrorCode.SIMULATION_NOT_PREPARED,
                status=404,
                message="Simulation configuration does not exist. Please call /prepare first",
            )
        )
    if req.simulation_days is not None:
        time_config = dict(config.get("time_config") or {})
        time_config["total_simulation_hours"] = req.simulation_days * 24
        config["time_config"] = time_config
    if req.llm_model_override or req.ai_model_ref is not None:
        config["llm_model"] = resolved_route.model
    if (req.llm_runtime.enabled or req.ai_model_ref is not None) and resolved_route.base_url_sanitized:
        config["llm_base_url"] = resolved_route.base_url_sanitized
    store.write_json(req.simulation_id, "simulation_config", config)


def _build_start_response(
    req: _StartRequest,
    run_state,
    run_id: str,
    graph_id: "str | None",
    force_restarted: bool,
) -> "dict[str, Any]":
    """Phase 8 — Antwort-Payload aus Runner-State und Request-Overrides bauen."""
    response_data = run_state.to_dict()
    if req.max_rounds:
        response_data['max_rounds_applied'] = req.max_rounds
    if req.simulation_days:
        response_data['simulation_days_applied'] = req.simulation_days
    response_data['graph_memory_update_enabled'] = req.enable_graph_memory_update
    response_data['force_restarted'] = force_restarted
    response_data['run_id'] = run_id
    if req.enable_graph_memory_update:
        response_data['graph_id'] = graph_id
    return response_data


def _capture_start_manifest_draft(
    run_id: str, req: "_StartRequest", state, resolved_route: "ResolvedRoute"
) -> None:
    """Issue #763 (Ticket 9): Draft-Manifest beim Run-Start schreiben.

    Vollständig best-effort — inklusive der Datenaufbereitung, nicht nur des
    Schreibvorgangs. Ein Fehler hier (z. B. beim Config-Read oder Hashing)
    darf den bereits erfolgreich gestarteten Run nicht mehr gefährden; die
    Route hat an dieser Stelle bereits ``run.succeed()`` aufgerufen. Es
    existiert kein echtes RNG-Seed-Konzept im System (kein
    ``np.random.seed`` o.ä.); ``random_seed`` ist daher ein deterministischer
    Platzhalter aus der ``simulation_id``, nicht ein tatsächlich verwendeter
    Zufalls-Seed.
    """
    try:
        import hashlib

        from .. import __version__

        config = SimulationManager().get_simulation_config(req.simulation_id) or {}
        config_hash = hashlib.sha256(
            json.dumps(config, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        seed_placeholder = int.from_bytes(
            hashlib.sha256(req.simulation_id.encode("utf-8")).digest()[:4], "big"
        )

        ManifestCapture.capture_draft_best_effort(
            run_id=run_id,
            run_dir=ArtifactLocator.run_dir(run_id),
            seed_document_hash="unknown",
            seed_document_filename="unknown",
            simulation_config_hash=f"sha256:{config_hash}",
            graph_id=state.graph_id or "unknown",
            agora_version=__version__,
            schema_version="1.0.0",
            random_seed=seed_placeholder,
            simulation_id_seed=req.simulation_id,
            routing={
                "simulation_rounds": {
                    "model": resolved_route.model,
                    "provider": resolved_route.provider_id,
                    "base_url": resolved_route.base_url_sanitized or "",
                }
            },
        )
    except Exception:  # noqa: BLE001 — best-effort, siehe Docstring
        logger.warning(
            "Draft-Manifest-Vorbereitung für run_id=%s fehlgeschlagen", run_id, exc_info=True
        )


@simulation_bp.route('/start', methods=['POST'])
@require_scope("simulation:control")
@handle_api_errors(logger=logger, log_prefix="Failed to start simulation")
def start_simulation():
    """Start running a prepared simulation.

    Der Handler orchestriert nur noch die Phasen: Validierung → Startbarkeit →
    Graph-Memory → Provider-Prechecks → Run-Registrierung → Routen-Auflösung →
    Config-Overrides → Prozessstart (#1079). Jede Phase lehnt über
    :class:`_StartRejected` mit einer fertigen Fehler-Response ab.
    """
    try:
        req = _parse_start_request(request.get_json() or {})

        manager = SimulationManager()
        state = manager.get_simulation(req.simulation_id)
        if not state:
            raise _StartRejected(
                json_error(
                    ApiErrorCode.NOT_FOUND,
                    status=404,
                    message=f"Simulation does not exist: {req.simulation_id}",
                )
            )

        gate_response = _evaluate_persona_review_gate(req.simulation_id)
        if gate_response is not None:
            return gate_response

        force_restarted = _ensure_startable_state(manager, state, req)
        graph_id = _resolve_graph_memory_id(state, req)
        _precheck_runtime_provider_key(req.llm_runtime)
        _precheck_ai_model_ref(req.ai_model_ref)

    except _StartRejected as rejected:
        # Vor der Run-Registrierung — es gibt noch keinen Run-Record, der
        # verwaisen koennte.
        return rejected.response

    # Issue #1176/#1183: Ab der Registrierung existiert ein Run-Record mit
    # status="pending". Jeder Ausgang, der ihn nicht auf einen Endzustand
    # bringt, hinterlaesst einen Phantom-Run. Das BaseException-Netz und die
    # strikte Persistenzsemantik (#844) liegen im RunLifecycle — hier steht
    # nur noch, was start-spezifisch ist. Routing-Seed und Budget-Anker
    # laufen bewusst innerhalb des Fensters: auch ihr Scheitern darf keinen
    # pending-Run hinterlassen.
    try:
        with _begin_start_run(req, state) as run:
            run_id = run.run_id
            seed_run_stage_routing(
                run_id,
                "simulation_rounds",
                llm_model_override=req.llm_model_override,
                llm_runtime=req.llm_runtime,
                ai_model_ref=req.ai_model_ref,
            )
            # Budget am Run verankern + Subprozess-Config schreiben (#764).
            # Alt-Artefakte (budget_abort.json eines früheren Runs) werden
            # entfernt, damit ein Neustart nicht sofort wieder abbricht.
            from ..services.run_budget import set_run_budget_config as _set_run_budget_config
            _apply_budget_to_simulation(
                req.simulation_id, run_id, req.budget_config, _set_run_budget_config
            )

            resolved_route, resolved_api_key = _resolve_start_route(run_id, req.llm_runtime)
            _apply_route_to_simulation_config(req, resolved_route, run_id)

            run_state = SimulationRunner.start_simulation(
                simulation_id=req.simulation_id,
                platform=req.platform,
                max_rounds=req.max_rounds,
                enable_graph_memory_update=req.enable_graph_memory_update,
                graph_id=graph_id,
                runtime_env=build_route_subprocess_env(
                    resolved_route,
                    resolved_api_key,
                    run_id,
                ),
            )

            manager._set_status(state, SimulationStatus.RUNNING)
            run.succeed(
                status="processing",
                progress=0,
                message="Simulation run started",
                resume_capability=_simulation_resume_capability(req.simulation_id, state),
            )

            # Issue #763 (Ticket 9): Draft-Manifest beim Run-Start. Best-Effort —
            # ein Manifest-Fehler darf den bereits erfolgreich gestarteten Run
            # nicht mehr gefährden.
            _capture_start_manifest_draft(run_id, req, state, resolved_route)
    except RunPersistenceError:
        # #844: Die failed-/processing-Markierung wurde nicht persistiert —
        # das darf nicht wie ein sauber abgeschlossener Vorgang aussehen.
        return json_error(
            ApiErrorCode.INTERNAL_ERROR,
            status=500,
            message=(
                "Interner Fehler beim Persistieren des Run-Status. "
                "Bitte erneut versuchen."
            ),
        )
    except _StartRejected as rejected:
        return rejected.response

    return json_success(
        _build_start_response(req, run_state, run_id, graph_id, force_restarted)
    )


@simulation_bp.route('/stop', methods=['POST'])
@require_scope("simulation:control")
@handle_api_errors(logger=logger, log_prefix="Failed to stop simulation")
def stop_simulation():
    """Stop a running simulation."""
    data = request.get_json() or {}
    simulation_id = data.get('simulation_id')
    if not simulation_id:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            message="Please provide simulation_id",
        )
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    run_state = SimulationRunner.stop_simulation(simulation_id)
    manager = SimulationManager()
    state = manager.get_simulation(simulation_id)
    if state:
        manager._set_status(state, SimulationStatus.PAUSED)
        run = run_registry.get_latest_by_linked_id("simulation_id", simulation_id, run_type="simulation_run")
        if run:
            run_registry.update_run(
                run["run_id"],
                status="stopped",
                progress=run_state.to_dict().get("progress_percent", 0),
                message="Simulation stopped",
                artifacts=_simulation_run_artifacts(simulation_id),
                resume_capability=_simulation_resume_capability(simulation_id, state),
            )
    return json_success(run_state.to_dict())


@simulation_bp.route('/<simulation_id>/pause', methods=['POST'])
@require_scope("simulation:control")
@handle_api_errors(logger=logger, log_prefix="Failed to pause simulation")
def pause_simulation(simulation_id: str):
    """Set the soft-pause flag so the simulation halts after the current round."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    from ..services.simulation_ipc import set_pause_state

    sim_dir = _simulation_dir(simulation_id)
    if not os.path.isdir(sim_dir):
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Simulation does not exist: {simulation_id}",
        )

    state = set_pause_state(sim_dir, True)
    logger.info(f"Pause requested for {simulation_id}")
    run = run_registry.get_latest_by_linked_id("simulation_id", simulation_id, run_type="simulation_run")
    if run:
        sim_state = SimulationManager().get_simulation(simulation_id)
        run_registry.update_run(
            run["run_id"],
            status="paused",
            message="Pause requested",
            artifacts=_simulation_run_artifacts(simulation_id),
            resume_capability=_simulation_resume_capability(simulation_id, sim_state),
        )
    return json_success({"simulation_id": simulation_id, "control_state": state})


@simulation_bp.route('/<simulation_id>/resume', methods=['POST'])
@require_scope("simulation:control")
@handle_api_errors(logger=logger, log_prefix="Failed to resume simulation")
def resume_simulation(simulation_id: str):
    """Clear the pause flag so the simulation continues."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    from ..services.simulation_ipc import set_pause_state

    sim_dir = _simulation_dir(simulation_id)
    if not os.path.isdir(sim_dir):
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=f"Simulation does not exist: {simulation_id}",
        )

    state = set_pause_state(sim_dir, False)
    logger.info(f"Resume requested for {simulation_id}")
    run = run_registry.get_latest_by_linked_id("simulation_id", simulation_id, run_type="simulation_run")
    if run:
        sim_state = SimulationManager().get_simulation(simulation_id)
        run_registry.update_run(
            run["run_id"],
            status="processing",
            message="Run resumed",
            artifacts=_simulation_run_artifacts(simulation_id),
            resume_capability=_simulation_resume_capability(simulation_id, sim_state),
        )
    return json_success({"simulation_id": simulation_id, "control_state": state})


@simulation_bp.route('/<simulation_id>/console-log', methods=['GET'])
# TODO(scope-rollout): explicit @require_scope("simulation:read") after grace period — Code-Review 2026-05-17 §3.3
@handle_api_errors(logger=logger, log_prefix="Failed to read simulation console log")
def get_simulation_console_log(simulation_id: str):
    """Read incremental subprocess console logs for a simulation."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )
    from_line = request.args.get('from_line', 0, type=int)
    data = SimulationRunner.get_console_log(simulation_id, from_line=from_line)
    return json_success(data)


@simulation_bp.route('/<simulation_id>/run-status', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get running status")
def get_run_status(simulation_id: str):
    """Get lightweight real-time run status for frontend polling."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    from ..services.simulation_ipc import read_control_state

    run_state = SimulationRunner.get_run_state(simulation_id)
    control = read_control_state(_simulation_dir(simulation_id))
    if not run_state:
        return json_success({
            "simulation_id": simulation_id,
            "runner_status": "idle",
            "current_round": 0,
            "total_rounds": 0,
            "progress_percent": 0,
            "twitter_actions_count": 0,
            "reddit_actions_count": 0,
            "total_actions_count": 0,
            "paused": bool(control.get("paused")),
        })

    data = run_state.to_dict()
    data["paused"] = bool(control.get("paused"))
    return json_success(data)


@simulation_bp.route('/<simulation_id>/run-status/detail', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get detailed status")
def get_run_status_detail(simulation_id: str):
    """
    Liefert den detaillierten Laufstatus mit aggregierten Aktionszahlen und paginierten Aktionen.

    Parameters:
        simulation_id (str): ID der Simulation.

    Returns:
        Response: JSON-Antwort mit Laufstatus, Aktionszahlen, paginierten Aktionen und aktuellen Rundenaktionen.
    """
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    run_state = SimulationRunner.get_run_state(simulation_id)
    platform_filter = request.args.get('platform')
    if not run_state:
        return json_success({
            "simulation_id": simulation_id,
            "runner_status": "idle",
            "actions_total": 0,
            "actions": [],
            "all_actions": [],
            "twitter_actions": [],
            "reddit_actions": [],
        })

    # Pagination-Parameter für actions-Subquery
    limit = clamp_int(
        request.args.get('limit', type=int),
        default=DEFAULT_LIMIT,
        minimum=1,
        maximum=MAX_LIMIT,
    )
    offset = max(request.args.get('offset', 0, type=int), 0)

    all_actions = SimulationRunner.get_all_actions(simulation_id=simulation_id, platform=platform_filter)
    twitter_actions = SimulationRunner.get_all_actions(
        simulation_id=simulation_id, platform="twitter"
    ) if not platform_filter or platform_filter == "twitter" else []
    reddit_actions = SimulationRunner.get_all_actions(
        simulation_id=simulation_id, platform="reddit"
    ) if not platform_filter or platform_filter == "reddit" else []
    current_round = run_state.current_round
    recent_actions = SimulationRunner.get_all_actions(
        simulation_id=simulation_id,
        platform=platform_filter,
        round_num=current_round,
    ) if current_round > 0 else []

    # Paginierte actions-Subquery (Aggregat-Felder bleiben im Top-Level)
    paginated_actions = SimulationRunner.get_actions(
        simulation_id=simulation_id,
        limit=limit,
        offset=offset,
        platform=platform_filter,
    )

    result = run_state.to_dict()
    # Aggregate + Counts statt redundanter Full-Lists (Gemini-Review PR #526).
    # Detail-Daten holt der Client über die paginierte `actions`-Subquery
    # bzw. /actions?platform=... — das Pagination-Ziel wäre sonst untergraben.
    result["actions_total"] = len(all_actions)
    result["actions"] = [action.to_dict() for action in paginated_actions]
    result["twitter_actions_count"] = len(twitter_actions)
    result["reddit_actions_count"] = len(reddit_actions)
    result["rounds_count"] = len(run_state.rounds)
    result["recent_actions"] = [action.to_dict() for action in recent_actions]
    return json_success(result)


@simulation_bp.route('/<simulation_id>/actions', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get action history")
def get_simulation_actions(simulation_id: str):
    """Get paginated action history for a simulation."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    limit = clamp_int(
        request.args.get('limit', type=int),
        default=DEFAULT_LIMIT,
        minimum=1,
        maximum=MAX_LIMIT,
    )
    offset = max(request.args.get('offset', 0, type=int), 0)
    platform = request.args.get('platform')
    agent_id = request.args.get('agent_id', type=int)
    round_num = request.args.get('round_num', type=int)
    actions = SimulationRunner.get_actions(
        simulation_id=simulation_id,
        limit=limit,
        offset=offset,
        platform=platform,
        agent_id=agent_id,
        round_num=round_num,
    )
    return json_success({
        "count": len(actions),
        "actions": [action.to_dict() for action in actions],
    })


@simulation_bp.route('/<simulation_id>/timeline', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get timeline")
def get_simulation_timeline(simulation_id: str):
    """Get round-level timeline summaries for a simulation."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    start_round = request.args.get('start_round', 0, type=int)
    end_round = request.args.get('end_round', type=int)
    timeline = SimulationRunner.get_timeline(
        simulation_id=simulation_id,
        start_round=start_round,
        end_round=end_round,
    )
    return json_success({"rounds_count": len(timeline), "timeline": timeline})


@simulation_bp.route('/<simulation_id>/agent-stats', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get agent statistics")
def get_agent_stats(simulation_id: str):
    """Get aggregated per-agent statistics."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    stats = SimulationRunner.get_agent_stats(simulation_id)
    return json_success({"agents_count": len(stats), "stats": stats})


@simulation_bp.route('/env-status', methods=['POST'])
@handle_api_errors(logger=logger, log_prefix="Failed to get environment status")
def get_env_status():
    """Get current simulation environment availability."""
    data = request.get_json() or {}
    simulation_id = data.get('simulation_id')
    if not simulation_id:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            message="Please provide simulation_id",
        )
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    env_alive = SimulationRunner.check_env_alive(simulation_id)
    env_status = SimulationRunner.get_env_status_detail(simulation_id)
    message = (
        "Environment running, ready to receive interview requests"
        if env_alive
        else "Environment not running or closed"
    )
    return json_success({
        "simulation_id": simulation_id,
        "env_alive": env_alive,
        "twitter_available": env_status.get("twitter_available", False),
        "reddit_available": env_status.get("reddit_available", False),
        "message": message,
    })


@simulation_bp.route('/close-env', methods=['POST'])
@handle_api_errors(logger=logger, log_prefix="Failed to close environment")
def close_simulation_env():
    """Gracefully close a simulation environment and update simulation status."""
    data = request.get_json() or {}
    simulation_id = data.get('simulation_id')
    if simulation_id and not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )
    timeout = data.get('timeout', 30)
    if not simulation_id:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            message="Please provide simulation_id",
        )

    result = SimulationRunner.close_simulation_env(simulation_id=simulation_id, timeout=timeout)
    manager = SimulationManager()
    state = manager.get_simulation(simulation_id)
    if state:
        manager._set_status(state, SimulationStatus.COMPLETED)

    # Preserve legacy envelope: outer ``success`` mirrors runner's inner success flag.
    return jsonify({"success": result.get("success", False), "data": result})
