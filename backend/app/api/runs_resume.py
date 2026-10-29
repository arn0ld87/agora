"""
Simulation-run and report-generation resume/restart helpers for runs API.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..utils.llm_client import LLMClient


def _runs_module():
    from . import runs
    return runs


def _reject_if_route_api_key_missing(resolved_route, resolved_api_key):
    """Fail-closed guard mirroring ``simulation_run._resolve_start_route``.

    A workspace-scoped run without a resolvable key must never fall through
    to an operator-configured route. Session-auth (CLI) providers and local
    endpoints do not require a key and are exempt, exactly like the initial
    start path. Returns a ready ``json_error(...)`` response, or ``None``.
    """
    _runs_mod = _runs_module()
    from ..services.llm_provider_registry import LlmProviderRegistry

    is_session_auth = LlmProviderRegistry.uses_session_auth(resolved_route.provider_id)
    if (
        resolved_api_key is None
        and not is_session_auth
        and not _runs_mod.is_local_endpoint(resolved_route.base_url_sanitized)
    ):
        return _runs_mod.json_error(
            f"provider_override: kein api_key im Payload und kein Key in der Settings-DB "
            f"für Provider '{resolved_route.provider_id}'. "
            "Bitte in Einstellungen → LLM-Anbieter einen Schlüssel speichern "
            "oder im Sitzungsfeld eingeben.",
            status=422,
            code="provider_api_key_missing",
        )
    return None


def _original_run_is_workspace_scoped(original_run: dict) -> bool:
    """Whether the ORIGINAL run (not the requester, not the replacement run
    the restart is about to create) is workspace-scoped — a plain metadata
    read, deliberately not ``workspace_credential_id_for_run`` (#1688 item
    4): that helper cross-checks ownership against the workspace store and
    default-denies a run with no explicit persisted scope on a demo
    instance — the right behaviour when resolving a credential to *use*, but
    it would turn "decide whether the demo cap applies to a restart" into a
    hard failure for any pre-#1688 legacy run. The actual key resolution
    still goes through that fail-closed path via
    ``resolve_route_api_key(..., run_id=run["run_id"])`` below.
    """
    return (original_run.get("metadata") or {}).get("credential_scope") == "workspace"


def _inherited_credential_scope_metadata(original_run: dict) -> dict:
    """Copy the ORIGINAL run's persisted credential-scope metadata onto a
    restart's replacement run record (#1688 item 3, follow-up to Finding H2).

    ``workspace_credential_metadata()`` reflects the REQUESTING principal —
    correct for a fresh start, wrong for a restart: an operator restarting a
    workspace-owned run must not silently reclassify that run as
    ``credential_scope="operator"``. ``build_route_subprocess_env`` /
    ``workspace_credential_id_for_run`` read exactly this persisted metadata
    (by the NEW run's id) to decide whether the resolved key goes through the
    workspace secret-FD path or lands in the subprocess env as plaintext —
    whoever clicks "restart", the new run must keep following its original
    owner's scope.
    """
    _runs_mod = _runs_module()
    metadata = original_run.get("metadata") or {}
    scope = metadata.get("credential_scope")
    if scope == "workspace" and metadata.get("credential_workspace_id"):
        return {
            "credential_scope": "workspace",
            "credential_workspace_id": metadata["credential_workspace_id"],
        }
    if scope == "operator":
        return {"credential_scope": "operator"}
    # Legacy run with no explicit persisted scope (pre-#1688): fall back to
    # the requesting principal, exactly like a fresh start would.
    return _runs_mod.workspace_credential_metadata()


def _resolve_simulation_platform(run: dict, config: dict | None, state) -> str:
    """Bestimmt die Plattform für den Resume/Restart-Lauf.

    Reihenfolge:
    1. Run-Manifest / Run-Metadaten (falls dort persistiert)
    2. Simulation-Config (config['platform'])
    3. Simulation-State (state.platform falls vorhanden)
    4. Fallback auf 'parallel'
    """
    metadata = run.get("metadata") or {}
    if metadata.get("platform"):
        return str(metadata["platform"])
    if config and config.get("platform"):
        return str(config["platform"])
    if getattr(state, "platform", None):
        return str(state.platform)
    return "parallel"


def _capture_resume_manifest_draft(
    run_id: str,
    simulation_id: str,
    state,
    resolved_route,
    platform: str,
    max_rounds: int | None,
    enable_graph_memory_update: bool,
    memory_update_graph_id: str | None,
) -> None:
    """Draft-Manifest für einen Simulation-Resume/Restart schreiben (Finding 4.1)."""
    _runs_mod = _runs_module()
    try:
        from .. import __version__
        from ..contracts.run_manifest_contract import ai_route_snapshot_from_ai_route
        from ..services.manifest_capture import ManifestCapture
        from ..services.runtime_run_config import RuntimeRunConfig

        config = _runs_mod.SimulationManager().get_simulation_config(simulation_id)
        config_hash = ManifestCapture.simulation_config_hash(config)

        seed_document_hash, seed_document_filename = ManifestCapture.seed_document_snapshot(
            state.project_id
        )

        canonical_route = RuntimeRunConfig(run_id).load_ai_route_snapshot("simulation_rounds")
        ai_route_snapshot = (
            ai_route_snapshot_from_ai_route(canonical_route).model_dump(mode="json")
            if canonical_route is not None
            else None
        )

        ManifestCapture.capture_draft_best_effort(
            run_id=run_id,
            run_dir=_runs_mod.ArtifactLocator.run_dir(run_id),
            seed_document_hash=seed_document_hash,
            seed_document_filename=seed_document_filename,
            simulation_config_hash=config_hash,
            graph_id=state.graph_id or "unknown",
            agora_version=__version__,
            schema_version="1.0.0",
            random_seed=None,
            simulation_id_seed=simulation_id,
            routing={
                "simulation_rounds": {
                    "model": resolved_route.model,
                    "provider": resolved_route.provider_id,
                    "base_url": resolved_route.base_url_sanitized or "",
                    "ai_route_snapshot": ai_route_snapshot,
                }
            },
            prompts=ManifestCapture.oasis_prompt_snapshots(),
            platform=platform,
            max_rounds=max_rounds,
            enable_graph_memory_update=enable_graph_memory_update,
            memory_update_graph_id=memory_update_graph_id,
        )
    except Exception:  # noqa: BLE001 — best-effort
        _runs_mod.logger.warning(
            "Draft-Manifest-Vorbereitung für resume run_id=%s fehlgeschlagen", run_id, exc_info=True
        )


def _try_soft_resume_paused_process(_runs_mod, simulation_id: str, run_id: str) -> dict | None:
    existing_run_state = _runs_mod.SimulationRunner.get_run_state(simulation_id)
    if existing_run_state and existing_run_state.runner_status == _runs_mod.RunnerStatus.PAUSED:
        from ..services.sim.process_manager import is_process_alive

        if is_process_alive(existing_run_state.process_pid):
            from ..services.simulation_ipc import set_pause_state

            set_pause_state(_runs_mod.ArtifactLocator.simulation_dir(simulation_id), False)
            _runs_mod.run_registry.update_run(
                run_id,
                status="processing",
                message="Simulation resumed",
                message_key="run.simulation_resumed",
                artifacts=_runs_mod._simulation_artifacts(simulation_id),
                resume_capability={"available": True, "action": "resume", "label": "Resume run"},
            )
            return {"run_id": run_id, "status": "processing", "message": "Simulation resumed"}
    return None


def _resolve_resume_limits_and_budget(_runs_mod, run: dict, config: dict, state):
    from ..services.run_budget import get_run_budget_config as _get_run_budget_config

    original_is_workspace_scoped = _runs_mod._original_run_is_workspace_scoped(run)
    original_budget_config = _get_run_budget_config(run["run_id"])
    configured_max_rounds = (
        (run.get("metadata") or {}).get("max_rounds")
        or config.get("max_rounds")
        or getattr(state, "max_rounds", None)
    )
    return _runs_mod.apply_demo_run_limits(
        configured_max_rounds, original_budget_config, demo_scoped=original_is_workspace_scoped
    )


def _resolve_graph_memory_settings(_runs_mod, run: dict, config: dict, state) -> tuple[bool, str | None]:
    enable_graph_memory_update = bool(
        (run.get("metadata") or {}).get("enable_graph_memory_update")
        or config.get("enable_graph_memory_update")
        or getattr(state, "enable_graph_memory_update", False)
    )
    memory_update_graph_id = (
        (run.get("metadata") or {}).get("memory_update_graph_id")
        or state.graph_id
    )
    if not memory_update_graph_id and state.project_id:
        project = _runs_mod.ProjectManager.get_project(state.project_id)
        if project:
            memory_update_graph_id = project.graph_id
    return enable_graph_memory_update, memory_update_graph_id


def _resume_or_restart_simulation_run(run: dict):
    _runs_mod = _runs_module()
    simulation_id = _runs_mod._linked_or_entity_id(run, "simulation_id", "simulation_id")
    manager = _runs_mod.SimulationManager()
    state = manager.get_simulation(simulation_id)
    if not state:
        raise ValueError(f"Simulation does not exist: {simulation_id}")

    soft_resume_res = _try_soft_resume_paused_process(_runs_mod, simulation_id, run["run_id"])
    if soft_resume_res is not None:
        return soft_resume_res

    config = manager.get_simulation_config(simulation_id) or {}
    platform = _resolve_simulation_platform(run, config, state)

    # Finding H2 (#1688): a restart previously called
    # ``SimulationRunner.start_simulation`` bare — no route, no
    # ``runtime_env``, no demo round/budget cap. It inherited the OASIS
    # subprocess's whitelisted backend env instead of a workspace-scoped
    # key, i.e. a JWT visitor's restart could run on operator credentials.
    # Resolve the same locked stage route the original run used
    # (``StageModelRouter(run_id)`` returns the snapshot ``lock_stage``
    # persisted at start — no re-seeding needed), resolve its API key with
    # the same fail-closed guard as ``/simulation/start``, and cap
    # max_rounds/budget for a demo JWT visitor exactly like a fresh start.
    route_router = _runs_mod.StageModelRouter(run["run_id"])
    resolved_route = route_router.resolve("simulation_rounds")
    resolved_api_key = _runs_mod.resolve_route_api_key(resolved_route, None, run_id=run["run_id"])
    key_error = _runs_mod._reject_if_route_api_key_missing(resolved_route, resolved_api_key)
    if key_error is not None:
        return key_error

    # Finding #1688 item 4: carry over the ORIGINAL run's persisted budget
    # instead of unconditionally recomputing from (None, None) — that always
    # handed ``_apply_budget_to_simulation`` a ``None`` config for an
    # operator restart, whose else-branch deletes budget_config.json /
    # budget_abort.json outright, wiping ANY run's budget cap on restart.
    # Whether the demo cap itself applies is likewise decided from the
    # ORIGINAL run's persisted owner, not the live requester — an operator
    # restarting a demo-capped workspace run must not lift that cap just by
    # being the one clicking "restart".
    try:
        max_rounds, budget_config = _resolve_resume_limits_and_budget(_runs_mod, run, config, state)
    except _runs_mod.DemoLimitExceededError as exc:
        return _runs_mod.json_error(exc.message, status=400, code="demo_limit_exceeded")

    enable_graph_memory_update, memory_update_graph_id = _resolve_graph_memory_settings(
        _runs_mod, run, config, state
    )

    # Issue #1183: Der Run-Record entsteht VOR dem Prozessstart im
    # Lifecycle-Fenster — schlägt der Start fehl, existiert ein failed-Record
    # statt gar keinem (vorher: create_run erst nach start_simulation).
    with _runs_mod.RunLifecycle.begin(
        _runs_mod.run_registry,
        "simulation_run",
        simulation_id,
        parent_run_id=run["run_id"],
        failure_message="Simulation restart failed: {exc_type}",
        progress=0,
        message="Simulation restart queued",
        message_key="run.simulation_restart_queued",
        linked_ids={"simulation_id": simulation_id, "project_id": state.project_id},
        artifacts=_runs_mod._simulation_artifacts(simulation_id),
        resume_capability={"available": True, "action": "resume", "label": "Resume run"},
        branch_label=state.branch_name,
        metadata={
            "graph_id": state.graph_id,
            "branch_name": state.branch_name,
            "platform": platform,
            "max_rounds": max_rounds,
            "enable_graph_memory_update": enable_graph_memory_update,
            "memory_update_graph_id": memory_update_graph_id if enable_graph_memory_update else None,
            **_runs_mod._inherited_credential_scope_metadata(run),
        },
    ) as lifecycle:
        new_run = lifecycle.record
        from ..services.manifest_capture import ManifestCapture
        from ..services.run_budget import set_run_budget_config as _set_run_budget_config
        from .simulation_run import _apply_budget_to_simulation

        _apply_budget_to_simulation(
            simulation_id, new_run["run_id"], budget_config, _set_run_budget_config
        )

        _capture_resume_manifest_draft(
            run_id=new_run["run_id"],
            simulation_id=simulation_id,
            state=state,
            resolved_route=resolved_route,
            platform=platform,
            max_rounds=max_rounds,
            enable_graph_memory_update=enable_graph_memory_update,
            memory_update_graph_id=memory_update_graph_id if enable_graph_memory_update else None,
        )

        # Finding F1 (Codex-Review Runde 3, PR #1476): requested_run_id ist
        # run["run_id"] — der urspruenglich angefragte, hier zu resumierende
        # (moeglicherweise verwaiste) Run, NICHT das gerade eben angelegte
        # Replacement-Manifest (new_run["run_id"]). Ohne diese gezielte
        # Weitergabe koennte die Stale-Korrektur bei mehreren historischen
        # "processing"-Manifesten einen falschen, neueren Run treffen.
        try:
            new_run_state = _runs_mod.SimulationRunner.start_simulation(
                simulation_id=simulation_id,
                platform=platform,
                max_rounds=max_rounds,
                enable_graph_memory_update=enable_graph_memory_update,
                graph_id=memory_update_graph_id if enable_graph_memory_update else None,
                requested_run_id=run["run_id"],
                runtime_env=_runs_mod.build_route_subprocess_env(
                    resolved_route, resolved_api_key, new_run["run_id"]
                ),
            )
        except Exception:
            ManifestCapture.discard_draft_best_effort(
                run_id=new_run["run_id"],
                run_dir=_runs_mod.ArtifactLocator.run_dir(new_run["run_id"]),
            )
            raise
        state.status = _runs_mod.SimulationStatus.RUNNING
        manager._save_simulation_state(state)
        lifecycle.succeed(status="processing", message="Simulation restarted", message_key="run.simulation_restarted")
    return {"run_id": new_run["run_id"], "status": new_run_state.runner_status.value, "message": "Simulation restarted"}


def _resume_report_generate(run: dict):
    _runs_mod = _runs_module()
    report_id = run.get("linked_ids", {}).get("report_id") or run.get("entity_id")
    simulation_id = run.get("linked_ids", {}).get("simulation_id")
    if not simulation_id:
        raise ValueError("Run is missing simulation_id linkage")

    # Recover the model override that was active when the run was originally started.
    # The original /api/report/generate call stores llm_model_override in the run
    # metadata; we honour it on resume so the same model is used throughout.
    llm_model_override = (run.get("metadata") or {}).get("llm_model") or None
    # Wenn der originale Request ein UI-Profile-Token war (`profile:<id>`),
    # expandieren wir es jetzt — sonst landet der Pseudo-Modellname als Modell
    # beim LLM (Ollama 404, kein Entity-Output).
    if isinstance(llm_model_override, str) and llm_model_override.startswith("profile:"):
        from ..utils.llm_profile_resolver import expand_profile_in_data
        _expand_buf = {"llm_model": llm_model_override}
        expand_profile_in_data(_expand_buf)
        llm_model_override = (_expand_buf.get("llm_model") or "").strip() or None

    manager = _runs_mod.SimulationManager()
    state = manager.get_simulation(simulation_id)
    if not state:
        raise ValueError(f"Simulation does not exist: {simulation_id}")
    project = _runs_mod.ProjectManager.get_project(state.project_id)
    if not project:
        raise ValueError(f"Project does not exist: {state.project_id}")
    graph_id = state.graph_id or project.graph_id
    if not graph_id:
        # Reiner Persona-Lauf ohne Graphen (Block B4).
        raise ValueError(
            "Dieser Lauf hat keinen Wissensgraphen — Berichte stuetzen sich auf Belege aus dem Graphen und sind fuer reine Persona-Laeufe deshalb noch nicht moeglich. Die Simulation selbst laeuft und ist auswertbar."
        )
    storage = _runs_mod.current_app.extensions.get("neo4j_storage")
    if not storage:
        raise ValueError("GraphStorage not initialized")
    # Budget-Enforcement + Routing-SSoT (#984): Der Resume-Client entsteht aus
    # der beim Original-Start gelockten Stage-Route MIT run_id — das frühere
    # LLMClient(model=...) ohne run_id lieferte keinen Budget-Enforcer, ein
    # fortgesetzter Report lief ohne jede Budgetdurchsetzung.
    # StageModelRouter.resolve() gibt den gelockten Snapshot zurück; nur für
    # Alt-Runs ohne Snapshot entscheidet der kanonische Resolver. Keine zweite
    # Client-Bauweise neben der Route (SSoT aus #817).
    from ..services.ai_route_resolver import NoAiRouteCandidateError
    from ..services.secret_resolver import SecretResolver

    try:
        route_router = _runs_mod.StageModelRouter(run["run_id"])
        resolved_route = route_router.resolve("report_generation")
        shared_llm_client: Optional[LLMClient] = _runs_mod.LLMClient.from_route(
            resolved_route,
            secret_resolver=SecretResolver(),
            run_id=run["run_id"],
        )
    except (ValueError, NoAiRouteCandidateError) as exc:
        # Kein API-Key konfiguriert → kein sinnvoller Resume-Pfad möglich.
        # Synchron mit 422 antworten statt still None zu setzen und im
        # Worker-Thread beim ersten LLM-Call zu sterben (Copilot PR #466).
        _runs_mod.logger.warning(
            "LLMClient für Resume-Report nicht verfügbar — synchrones 422: %s",
            exc,
        )
        return _runs_mod.json_error(
            f"LLM-Provider nicht verfügbar: {exc}. "
            "Konfiguriere einen API-Key, bevor der Report fortgesetzt wird.",
            status=422,
            code="llm_client_unavailable",
        )
    graph_tools = _runs_mod.GraphToolsService(storage=storage, llm_client=shared_llm_client)

    task_manager = _runs_mod.TaskManager()
    task_id = task_manager.create_task(
        "report_generate",
        metadata={"simulation_id": simulation_id, "graph_id": graph_id, "report_id": report_id, "run_id": run["run_id"]},
    )

    from ..services.run_budget import BudgetExceededError, mark_budget_abort

    def run_generate():
        try:
            task_manager.update_task(
                task_id,
                status=_runs_mod.TaskStatus.PROCESSING,
                progress=0,
                message="Initializing Report Agent...",
                message_key="run.report_initializing",
            )
            agent = _runs_mod.ReportAgent(
                graph_id=graph_id,
                simulation_id=simulation_id,
                simulation_requirement=project.simulation_requirement or "",
                graph_tools=graph_tools,
                llm_client=shared_llm_client,
                model_name=llm_model_override,
                # Issue #1240: Szenario-/Erwartungstext stützt keinen Claim.
                document_roles=_runs_mod.load_document_roles(project.project_id),
            )

            def progress_callback(stage, progress, message):
                task_manager.update_task(task_id, progress=progress, message=f"[{stage}] {message}")

            # Issue #1243: auch der Resume-Pfad muss abbrechbar sein — ohne
            # cancel_run_id liest generate_report das Flag nie.
            report = agent.generate_report(
                progress_callback=progress_callback,
                report_id=report_id,
                cancel_run_id=run["run_id"],
            )
            _runs_mod.ReportManager.save_report(report)
            if _runs_mod.was_run_cancelled(run["run_id"]):
                # Teilreport nach Nutzerabbruch traegt status=COMPLETED; ohne
                # diesen Zweig waere er von einem vollstaendigen Lauf nicht zu
                # unterscheiden.
                # Reihenfolge bindend (#978): complete_task spiegelt sich per
                # sync_task auf den Run zurueck und wuerde "stopped" wieder
                # ueberschreiben. Der Run-Update laeuft zuletzt.
                task_manager.complete_task(
                    task_id,
                    result={
                        "report_id": report_id,
                        "simulation_id": simulation_id,
                        "cancelled": True,
                    },
                )
                _runs_mod.finish_cancelled_run(
                    run["run_id"], report_id=report_id, simulation_id=simulation_id
                )
            elif _runs_mod.is_deliverable_report_status(report.status):
                # Issue #1479: ein INCOMPLETE-Report ist ein ehrliches
                # Teilergebnis, kein Fehlschlag — die alte Gleichheitsprüfung
                # gegen COMPLETED schickte ihn in den else-Zweig und meldete
                # den Resume faelschlich als "failed".
                _runs_mod.finish_completed_run(
                    run["run_id"],
                    report_id=report_id,
                    simulation_id=simulation_id,
                    report_status=report.status.value,
                )
                task_manager.complete_task(
                    task_id,
                    result={"report_id": report_id, "simulation_id": simulation_id, "status": report.status.value},
                )
            else:
                _runs_mod.run_registry.update_run(
                    run["run_id"],
                    status="failed",
                    message=report.error or "Report generation failed",
                    error=report.error,
                )
                task_manager.fail_task(task_id, report.error or "Report generation failed")
        except BudgetExceededError as exc:
            # Budgetabbruch (#984): Teilresultate bleiben erhalten, Status
            # "stopped" + termination_reason statt technischem "failed".
            # Reihenfolge bindend (#978, gleiche Falle wie #841): fail_task()
            # zuerst — sync_task setzt generisch "failed" —, der detaillierte
            # mark_budget_abort() zuletzt (setzt stopped + termination_reason).
            _runs_mod.logger.warning(
                "Resume report budget-aborted (run_id=%s, report_id=%s): %s",
                run["run_id"], report_id, exc,
            )
            task_manager.fail_task(task_id, str(exc))
            mark_budget_abort(run["run_id"], exc.dimension, exc.observed, exc.threshold)
        except Exception as exc:  # noqa: BLE001 — exception reported to task/run registry
            _runs_mod.run_registry.update_run(run["run_id"], status="failed", message=str(exc), error=str(exc))
            task_manager.fail_task(task_id, str(exc))

    _runs_mod.run_registry.update_run(
        run["run_id"], status="processing", progress=0, message="Report generation resumed", message_key="run.report_resumed"
    )

    def scoped_run_generate():
        with _runs_mod.workspace_credential_context_for_run(run["run_id"]):
            run_generate()

    threading.Thread(target=scoped_run_generate, daemon=True).start()
    return {"run_id": run["run_id"], "task_id": task_id, "status": "processing"}
