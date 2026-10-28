"""
Start-phase validation, prechecks, routing, and manifest helpers for simulation runs.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from flask import request

from ..contracts.auth_contract import AuthType
from ..services.llm_runtime import RuntimeLlmConfig
from ..services.run_lifecycle import RunLifecycle
from ..services.simulation_manager import SimulationStatus
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import json_error
from .simulation_common import (
    simulation_run_artifacts as _simulation_run_artifacts,
)

if TYPE_CHECKING:  # pragma: no cover — nur für Typprüfung
    from ..contracts.ai_provider_contract import AiModelRef
    from ..contracts.llm_routing_contract import ResolvedRoute
    from ..contracts.run_budget_contract import RunBudgetConfig


def _sim_mod():
    from . import simulation_run
    return simulation_run


def _evaluate_persona_review_gate(simulation_id: str):
    """Return a 409 response when PERSONA_REVIEW_ENABLED blocks the start.

    Returns None when the gate is open. The gate is silent while the global
    ``PERSONA_REVIEW_ENABLED`` flag is off so existing behaviour is unchanged
    until an operator explicitly opts in.
    """
    mod = _sim_mod()
    if not mod.Config.PERSONA_REVIEW_ENABLED:
        return None
    review = mod.PersonaReviewService(mod.get_artifact_store()).evaluate_start_gate(
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
    return _sim_mod().ArtifactLocator.simulation_dir(simulation_id)


def _apply_budget_to_simulation(simulation_id, run_id, budget_config, set_config_fn) -> None:
    """Budget-Config am Run verankern und Subprozess-Artefakte pflegen (#764).

    - Mit Budget: metadata.budget im Manifest + budget_config.json im Sim-Dir
      (vom Subprozess-Guard gelesen).
    - Ohne Budget: Alt-Artefakte entfernen (budget_config.json /
      budget_abort.json eines früheren Runs darf nicht weiterwirken).
    Keine Secrets: die Config enthält nur Limits, Enforcement und Währung.
    """
    import os as _os

    mod = _sim_mod()
    sim_dir = mod._simulation_dir(simulation_id)
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
                    mod.logger.warning("Konnte veraltetes Budget-Artefakt nicht löschen: %s", stale)


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


def _effective_start_budget(
    user_budget: "RunBudgetConfig | None", run_id: str
) -> "RunBudgetConfig | None":
    """Wirksames Budget eines frischen Simulationsstarts (Issue #1772).

    Ein vom Nutzer (oder dem Demo-Limit) gesetztes Budget gewinnt immer und
    wird nicht ergaenzt -- auch dann nicht, wenn es keinen Tokendeckel enthaelt.
    Ohne Nutzerbudget gilt das Standardbudget aus den Einstellungen
    (``resolve_default_run_budget``: Tokens, Kosten, Laufzeit, Aufrufe; ``0`` =
    kein Limit, alles auf 0 -> ``None``). Nur der
    Startpfad ruft das auf: Replay, Neustart und Branch geben das Budget des
    Ursprungslaufs weiter und bekommen keinen nachtraeglichen Deckel.
    """
    if user_budget is not None:
        return user_budget
    from ..services.run_budget import default_simulation_budget

    default_budget = default_simulation_budget()
    if default_budget is not None:
        _sim_mod().logger.info(
            "Standardbudget %s fuer %s gesetzt (kein Nutzerbudget)",
            default_budget.model_dump(mode="json", exclude_none=True), run_id,
        )
    return default_budget


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


def _apply_demo_start_limits(
    max_rounds: int | None, budget_config: "RunBudgetConfig | None"
) -> tuple[int | None, "RunBudgetConfig | None"]:
    """Enforce bounded JWT runs only on an explicitly enabled demo instance.

    Finding M1: the round/budget cap itself now lives in
    ``simulation_common.apply_demo_run_limits`` so the replay/resume paths in
    ``runs.py`` enforce the identical limit — this wrapper only translates
    the shared ``DemoLimitExceededError`` into the ``_StartRejected``
    response shape this endpoint's callers expect.
    """
    from .simulation_common import DemoLimitExceededError, apply_demo_run_limits

    try:
        return apply_demo_run_limits(max_rounds, budget_config)
    except DemoLimitExceededError as exc:
        raise _StartRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                status=400,
                message=exc.message,
            )
        ) from exc


def _parse_start_request(data: "dict[str, Any]") -> _StartRequest:
    """Phase 1 — Request-Payload validieren und in einen Container überführen.

    Die Prüfreihenfolge ist Teil des API-Verhaltens: bei mehreren fehlerhaften
    Feldern entscheidet sie, welche Meldung der Aufrufer sieht.
    """
    mod = _sim_mod()
    simulation_id = data.get('simulation_id')
    if not simulation_id:
        raise _StartRejected(
            json_error(
                ApiErrorCode.VALIDATION_FAILED,
                message="Please provide simulation_id",
            )
        )
    if not mod.validate_simulation_id(simulation_id):
        raise _StartRejected(
            json_error(
                ApiErrorCode.INVALID_ID,
                message="Invalid simulation_id format",
            )
        )
    principal = mod.current_principal()
    if (
        data.get('enable_graph_memory_update')
        and principal is not None
        and principal.auth_type == AuthType.JWT
    ):
        raise _StartRejected(
            json_error(
                ApiErrorCode.AUTH_FORBIDDEN,
                status=403,
                message="Graph memory update is unavailable for workspace simulations",
            )
        )

    platform = data.get('platform', 'parallel')
    llm_model_override = (data.get('llm_model') or '').strip() or None
    try:
        llm_runtime = mod.parse_runtime_llm_config(data)
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
        llm_runtime = mod.parse_runtime_llm_config({})

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

    max_rounds, budget_config = _apply_demo_start_limits(max_rounds, budget_config)

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
    mod = _sim_mod()
    run_state = mod.SimulationRunner.get_run_state(simulation_id)
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
    mod.logger.info(f"Force mode: stopping running simulation {simulation_id}")
    try:
        mod.SimulationRunner.stop_simulation(simulation_id)
    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        mod.logger.warning(f"Warning when stopping simulation: {exc}")


def _ensure_startable_state(manager, state, req: _StartRequest) -> bool:
    """Phase 2 — sicherstellen, dass die Simulation startbar ist.

    Gibt zurück, ob dafür ein Force-Restart nötig war (``force_restarted``).
    """
    mod = _sim_mod()
    if state.status == SimulationStatus.READY:
        return False

    is_prepared, _prepare_info = mod._check_simulation_prepared(req.simulation_id)
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
        mod.logger.info(f"Force mode: cleaning simulation runtime files for {req.simulation_id}")
        cleanup_result = mod.SimulationRunner.cleanup_simulation_logs(req.simulation_id)
        if not cleanup_result.get("success"):
            mod.logger.warning(f"Warning when cleaning logs: {cleanup_result.get('errors')}")
        force_restarted = True

    manager._reset_to_ready(
        state,
        reason=f"force start_run after status={state.status.value}",
    )
    return force_restarted


def _resolve_graph_memory_id(state, req: _StartRequest) -> "str | None":
    """Phase 3 — Graph-ID für das Knowledge-Graph-Memory-Update auflösen."""
    mod = _sim_mod()
    if not req.enable_graph_memory_update:
        return None

    graph_id = state.graph_id
    if not graph_id:
        project = mod.ProjectManager.get_project(state.project_id)
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
    mod.logger.info(
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
    from ..services.llm_routing_seed import workspace_credential_id_for_run
    from ..services.workspace_provider_credentials_store import WorkspaceProviderCredentialsStore
    from ..services.llm_provider_registry import LlmProviderRegistry
    provider_id_preview = map_runtime_provider_to_route_provider(llm_runtime.provider)
    if not provider_id_preview:
        return

    registry = LlmProviderRegistry()
    descriptor = next((p for p in registry.get_providers() if p.id == provider_id_preview), None)
    p_type = descriptor.type if descriptor else "openai_compatible"
    workspace_id = workspace_credential_id_for_run(None)
    stored_key = (
        WorkspaceProviderCredentialsStore().get_plaintext(workspace_id, provider_id_preview)
        if workspace_id is not None
        else SecretResolver().get_api_key(provider_id_preview, p_type)
    )
    if not stored_key and not _sim_mod().is_local_endpoint(
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
    mod = _sim_mod()
    return RunLifecycle.begin(
        mod.run_registry,
        "simulation_run",
        req.simulation_id,
        failure_message="Simulation start failed: {exc_type}",
        progress=0,
        message="Simulation run queued",
        message_key="run.simulation_run_queued",
        linked_ids={"simulation_id": req.simulation_id, "project_id": state.project_id},
        artifacts=getattr(mod, "_simulation_run_artifacts", _simulation_run_artifacts)(req.simulation_id),
        resume_capability=mod._simulation_resume_capability(req.simulation_id, state),
        branch_label=state.branch_name,
        metadata={
            **mod.workspace_credential_metadata(),
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
    mod = _sim_mod()
    route_router = mod.StageModelRouter(run_id)
    resolved_route = route_router.resolve("simulation_rounds")
    route_router.lock_stage("simulation_rounds", resolved_route)
    resolved_api_key = mod.resolve_route_api_key(resolved_route, llm_runtime)

    # Issue #1423: Ein Session-Provider (codex_cli, auth_mode="session") hat
    # per Definition keinen api_key — er authentifiziert über die lokale
    # ``codex login``-Session. ``is_local_endpoint(None)`` ist ``False``,
    # deshalb hätte der Guard darunter jeden codex_cli-Start mit 422
    # abgelehnt, bevor der Subprozess überhaupt startet.
    #
    # Die Ausnahme hängt am ``auth_mode``, nicht am ``transport``: ``claude_cli``
    # ist ebenfalls ``transport="cli"``, braucht aber einen echten Token. Für
    # ihn muss der Guard greifen, sonst startet der Lauf ohne Anmeldung und
    # scheitert erst im Subprozess.
    from ..services.llm_provider_registry import LlmProviderRegistry

    is_session_auth = LlmProviderRegistry.uses_session_auth(resolved_route.provider_id)

    if (
        resolved_api_key is None
        and not is_session_auth
        and not mod.is_local_endpoint(resolved_route.base_url_sanitized)
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

    store = _sim_mod().get_artifact_store()
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
    if req.llm_runtime.enabled or req.ai_model_ref is not None:
        if resolved_route.base_url_sanitized:
            config["llm_base_url"] = resolved_route.base_url_sanitized
        else:
            # Die Route gibt keinen Endpoint vor (cli-Route oder HTTP-Route ohne
            # eigene URL): eine aus dem Prepare (anderer Provider) stehengebliebene
            # Basis-URL würde neben dem neuen Modell stehen und es über den
            # falschen Endpoint rufen. Keine .env-URL als Ersatz einsetzen.
            config["llm_base_url"] = ""
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
    run_id: str,
    req: "_StartRequest",
    state,
    resolved_route: "ResolvedRoute",
    memory_update_graph_id: "str | None",
) -> None:
    """Issue #763/#1274 (Ticket 9, Punkte 1/2/3/5/6): Draft-Manifest beim Run-Start schreiben.

    Vollständig best-effort — inklusive der Datenaufbereitung, nicht nur des
    Schreibvorgangs. Ein Fehler hier (z. B. beim Config-Read oder Hashing)
    darf den bereits erfolgreich gestarteten Run nicht mehr gefährden. Läuft
    seit #1686 VOR ``SimulationRunner.start_simulation`` (siehe
    ``start_simulation()``), nicht mehr danach — sonst konnte ein sofort
    beendeter Monitor-Thread das Manifest finalisieren wollen, bevor der
    Draft überhaupt existierte, und der Run blieb dauerhaft im Status
    ``draft`` hängen.

    ``random_seed`` bleibt ``None`` — es existiert kein echtes RNG-Seed-
    Konzept im System (kein ``np.random.seed`` o.ä.); ein aus der
    ``simulation_id`` abgeleiteter Platzhalter-Hash würde Reproduzierbarkeit
    vortäuschen, die nicht besteht (#1274 Punkt 1).
    """
    mod = _sim_mod()
    try:
        from .. import __version__
        from ..contracts.run_manifest_contract import ai_route_snapshot_from_ai_route
        from ..services.runtime_run_config import RuntimeRunConfig

        config = mod.SimulationManager().get_simulation_config(req.simulation_id)
        config_hash = mod.ManifestCapture.simulation_config_hash(config)

        seed_document_hash, seed_document_filename = mod.ManifestCapture.seed_document_snapshot(
            state.project_id
        )

        # Der kanonische AiRoute-Snapshot wurde bereits von
        # ``route_router.lock_stage(...)`` in ``_resolve_start_route``
        # persistiert (#1274 Punkt 2) — hier nur noch für den strikten
        # Manifest-Snapshot einlesen, nicht neu auflösen.
        canonical_route = RuntimeRunConfig(run_id).load_ai_route_snapshot("simulation_rounds")
        ai_route_snapshot = (
            ai_route_snapshot_from_ai_route(canonical_route).model_dump(mode="json")
            if canonical_route is not None
            else None
        )

        mod.ManifestCapture.capture_draft_best_effort(
            run_id=run_id,
            run_dir=mod.ArtifactLocator.run_dir(run_id),
            seed_document_hash=seed_document_hash,
            seed_document_filename=seed_document_filename,
            simulation_config_hash=config_hash,
            graph_id=state.graph_id or "unknown",
            agora_version=__version__,
            schema_version="1.0.0",
            random_seed=None,
            simulation_id_seed=req.simulation_id,
            routing={
                "simulation_rounds": {
                    "model": resolved_route.model,
                    "provider": resolved_route.provider_id,
                    "base_url": resolved_route.base_url_sanitized or "",
                    "ai_route_snapshot": ai_route_snapshot,
                }
            },
            prompts=mod.ManifestCapture.oasis_prompt_snapshots(),
            platform=req.platform,
            max_rounds=req.max_rounds,
            enable_graph_memory_update=req.enable_graph_memory_update,
            memory_update_graph_id=memory_update_graph_id,
        )
    except Exception:  # noqa: BLE001 — best-effort, siehe Docstring
        mod.logger.warning(
            "Draft-Manifest-Vorbereitung für run_id=%s fehlgeschlagen", run_id, exc_info=True
        )


def execute_start_simulation():
    """Start running a prepared simulation."""
    mod = _sim_mod()
    try:
        req = getattr(mod, '_parse_start_request', _parse_start_request)(request.get_json() or {})

        manager = mod.SimulationManager()
        state = manager.get_simulation(req.simulation_id)
        if not state:
            raise _StartRejected(
                mod.json_error(
                    mod.ApiErrorCode.NOT_FOUND,
                    status=404,
                    message=f"Simulation does not exist: {req.simulation_id}",
                )
            )

        gate_response = getattr(mod, '_evaluate_persona_review_gate', _evaluate_persona_review_gate)(req.simulation_id)
        if gate_response is not None:
            return gate_response

        force_restarted = getattr(mod, '_ensure_startable_state', _ensure_startable_state)(manager, state, req)
        graph_id = getattr(mod, '_resolve_graph_memory_id', _resolve_graph_memory_id)(state, req)
        getattr(mod, '_precheck_runtime_provider_key', _precheck_runtime_provider_key)(req.llm_runtime)
        getattr(mod, '_precheck_ai_model_ref', _precheck_ai_model_ref)(req.ai_model_ref)

    except _StartRejected as rejected:
        return rejected.response

    try:
        with getattr(mod, '_begin_start_run', _begin_start_run)(req, state) as run:
            run_id = run.run_id
            mod.seed_run_stage_routing(
                run_id,
                "simulation_rounds",
                llm_model_override=req.llm_model_override,
                llm_runtime=req.llm_runtime,
                ai_model_ref=req.ai_model_ref,
            )
            from ..services.run_budget import set_run_budget_config as _set_run_budget_config
            effective_budget = getattr(mod, '_effective_start_budget', _effective_start_budget)(req.budget_config, run_id)
            getattr(mod, '_apply_budget_to_simulation', _apply_budget_to_simulation)(
                req.simulation_id, run_id, effective_budget, _set_run_budget_config
            )

            resolved_route, resolved_api_key = getattr(mod, '_resolve_start_route', _resolve_start_route)(run_id, req.llm_runtime)
            getattr(mod, '_apply_route_to_simulation_config', _apply_route_to_simulation_config)(req, resolved_route, run_id)

            getattr(mod, '_capture_start_manifest_draft', _capture_start_manifest_draft)(run_id, req, state, resolved_route, graph_id)

            try:
                run_state = mod.SimulationRunner.start_simulation(
                    simulation_id=req.simulation_id,
                    platform=req.platform,
                    max_rounds=req.max_rounds,
                    enable_graph_memory_update=req.enable_graph_memory_update,
                    graph_id=graph_id,
                    runtime_env=mod.build_route_subprocess_env(
                        resolved_route,
                        resolved_api_key,
                        run_id,
                    ),
                )
            except Exception:
                mod.ManifestCapture.discard_draft_best_effort(
                    run_id=run_id, run_dir=mod.ArtifactLocator.run_dir(run_id)
                )
                raise

            manager._set_status(state, mod.SimulationStatus.RUNNING)
            run.succeed(
                status="processing",
                progress=0,
                message="Simulation run started",
                message_key="run.simulation_run_started",
                resume_capability=mod._simulation_resume_capability(req.simulation_id, state),
            )
    except mod.RunPersistenceError:
        return mod.json_error(
            mod.ApiErrorCode.INTERNAL_ERROR,
            status=500,
            message=(
                "Interner Fehler beim Persistieren des Run-Status. "
                "Bitte erneut versuchen."
            ),
        )
    except _StartRejected as rejected:
        return rejected.response

    return mod.json_success(
        _build_start_response(req, run_state, run_id, graph_id, force_restarted)
    )

