"""
Restart and resume handlers for Run registry API.
"""

from __future__ import annotations

import threading
import traceback
from typing import Optional

from ..services.graph_build_checkpoint import GraphBuildCheckpoint


def _runs_module():
    from . import runs as _runs_mod

    return _runs_mod


def _resume_or_restart_graph_build(run: dict):
    """Entscheidet zwischen Resume (Checkpoint vorhanden und passend) und
    vollem Restart — dieselbe Route (Issue #1472b), analog
    ``_resume_or_restart_simulation_run``.

    Die Prüfung rechnet die Chunk-Zerlegung EINMAL hier synchron nach
    (``GraphBuildService.chunk_project_text``) und validiert den
    Checkpoint dagegen (``checkpoint_is_resumable``). Passt er nicht mehr
    (Chunk-Parameter geändert, anderer Graph, kein einziger Chunk fertig),
    fällt die Route sauber auf ``_restart_graph_build`` zurück — ein
    angebotenes Resume, das doch bei null beginnt, ist schlimmer als keins.
    """
    _runs_mod = _runs_module()
    project_id = _runs_mod._linked_or_entity_id(run, "project_id", "project_id")
    project = _runs_mod.ProjectManager.get_project(project_id)
    if not project:
        raise ValueError(f"Project does not exist: {project_id}")

    text = _runs_mod.ProjectManager.get_extracted_text(project_id)
    graph_id = (run.get("linked_ids") or {}).get("graph_id")

    # ``text and graph_id`` als Bedingung UM den ganzen Block (statt separat
    # in einer Inline-Ternary vor ``if checkpoint is not None``) narrowt
    # ``text`` innerhalb des Blocks strukturell auf ``str`` — mypy kann die
    # Beziehung zwischen zwei unabhängigen Variablen sonst nicht verfolgen.
    if text and graph_id:
        checkpoint = _runs_mod.load_checkpoint(project_id)
        if checkpoint is not None:
            chunk_size = project.chunk_size or _runs_mod.Config.DEFAULT_CHUNK_SIZE
            chunk_overlap = project.chunk_overlap or _runs_mod.Config.DEFAULT_CHUNK_OVERLAP
            chunks, document_ids, chunk_ids, manifest_anchored = _runs_mod.GraphBuildService.chunk_project_text(
                project_id, text, chunk_size, chunk_overlap
            )
            if _runs_mod.checkpoint_is_resumable(
                checkpoint,
                graph_id=graph_id,
                total_chunks=len(chunks),
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                manifest_anchored=manifest_anchored,
            ):
                return _runs_mod._resume_graph_build(
                    run,
                    checkpoint,
                    chunks=chunks,
                    document_ids=document_ids,
                    chunk_ids=chunk_ids,
                    manifest_anchored=manifest_anchored,
                )

    return _runs_mod._restart_graph_build(run)


def _resume_graph_build(
    run: dict,
    checkpoint: GraphBuildCheckpoint,
    *,
    chunks: list[str],
    # Wie in ``GraphBuilderService.add_text_batches``: beide Listen sind
    # optional, und ihre Elemente duerfen einzeln ``None`` sein (ein Chunk
    # ohne Dokument-/Chunk-Provenance). Ein blankes ``list`` verdeckte das.
    document_ids: list[str | None] | None,
    chunk_ids: list[int | None] | None,
    manifest_anchored: bool,
):
    """Reine Routing-Schicht (Issue #1472b): löst Projekt/Container auf und
    delegiert die eigentliche Build-Logik an
    ``GraphBuildService.resume_graph_build`` — dieselbe Stelle wie der
    Original-Build (``build_graph``), damit Chunking,
    Checkpoint-Fortschreibung und Endzustände an EINER Stelle gepflegt
    werden statt in einer zweiten, unabhängig driftenden Kopie in der
    API-Schicht.
    """
    _runs_mod = _runs_module()
    project_id = _runs_mod._linked_or_entity_id(run, "project_id", "project_id")
    project = _runs_mod.ProjectManager.get_project(project_id)
    if not project:
        raise ValueError(f"Project does not exist: {project_id}")
    if not project.ontology:
        raise ValueError("Ontology definition not found")

    container = _runs_mod.get_container()
    if container.neo4j_storage is None:
        raise ValueError("GraphStorage not initialized")

    return _runs_mod.GraphBuildService.resume_graph_build(
        project_id=project_id,
        parent_run_id=run["run_id"],
        checkpoint=checkpoint,
        chunks=chunks,
        document_ids=document_ids,
        chunk_ids=chunk_ids,
        container=container,
    )


def _restart_graph_build(run: dict):
    _runs_mod = _runs_module()
    project_id = _runs_mod._linked_or_entity_id(run, "project_id", "project_id")
    project = _runs_mod.ProjectManager.get_project(project_id)
    if not project:
        raise ValueError(f"Project does not exist: {project_id}")

    text = _runs_mod.ProjectManager.get_extracted_text(project_id)
    if not text:
        raise ValueError("Extracted text not found")
    ontology = project.ontology
    if not ontology:
        raise ValueError("Ontology definition not found")

    container = _runs_mod.get_container()
    if container.neo4j_storage is None:
        raise ValueError("GraphStorage not initialized")

    graph_name = project.name or "Agora Graph"
    chunk_size = project.chunk_size or _runs_mod.Config.DEFAULT_CHUNK_SIZE
    chunk_overlap = project.chunk_overlap or _runs_mod.Config.DEFAULT_CHUNK_OVERLAP

    # Issue #1183: Anlage-Fenster hinter RunLifecycle — jeder Abbruch bis zum
    # Thread-Start markiert den Run als failed statt ihn pending zu verwaisen.
    with _runs_mod.RunLifecycle.begin(
        _runs_mod.run_registry,
        "graph_build",
        project_id,
        parent_run_id=run["run_id"],
        failure_message="Graph build restart failed: {exc_type}",
        progress=0,
        message="Graph build restart queued",
        message_key="run.graph_build_restart_queued",
        linked_ids={"project_id": project_id},
        artifacts=_runs_mod.ArtifactLocator.existing_paths(
            {"project_dir": _runs_mod.ProjectManager._get_project_dir(project_id)}
        ),
        resume_capability={"available": True, "action": "restart", "label": "Restart graph build"},
        metadata={"graph_name": graph_name, **_runs_mod.workspace_credential_metadata()},
    ) as lifecycle:
        new_run = lifecycle.record
        task_manager = _runs_mod.TaskManager()
        task_id = task_manager.create_task(
            f"Build graph: {graph_name}",
            metadata={"project_id": project_id, "run_id": new_run["run_id"]},
        )
        lifecycle.attach_task(task_manager, task_id)
        project.status = _runs_mod.ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        _runs_mod.ProjectManager.save_project(project)

        def _finish_cancelled_restart(graph_id, episode_uuids, builder):
            """Review-Finding PR #1371, Befund 4 (MITTEL): der Restart-Pfad

            baute ``add_text_batches`` bisher ganz ohne ``run_id`` auf —
            das Cancel-Flag konnte hier nie ankommen. Ein Nutzer, der einen
            gerade erst neu gestarteten Graph-Build sofort wieder abbricht,
            bekam 202 (Flag gesetzt), aber der Build lief unbeirrt zu Ende.
            Diese Funktion spiegelt ``services/graph_build.py::_finish_cancelled_build``
            so nah wie möglich (gleiche Endzustände, gleiches
            Best-Effort-pro-Schritt-Muster nach Befund 3), bewusst nicht
            importiert — sie hängt an einer anderen Closure (kein
            ``degradations``-Collector, kein ``extraction_tally`` in diesem
            schlankeren Restart-Pfad).
            """
            build_logger = _runs_mod.logger
            build_logger.info(
                "Graph build restart cancelled by user [project_id=%s, run_id=%s, "
                "graph_id=%s, episodes=%d]",
                project_id, new_run["run_id"], graph_id, len(episode_uuids),
            )
            if builder is not None and graph_id is not None:
                try:
                    builder.mark_graph_incomplete(graph_id, reason="user_cancel")
                except Exception as exc:  # noqa: BLE001 — best effort, siehe Befund 3
                    build_logger.warning(
                        "graph_build restart: mark_graph_incomplete fehlgeschlagen "
                        "[project_id=%s, run_id=%s, graph_id=%s]: %r",
                        project_id, new_run["run_id"], graph_id, exc,
                    )
            try:
                project.graph_id = graph_id
                project.status = _runs_mod.ProjectStatus.GRAPH_INCOMPLETE
                _runs_mod.ProjectManager.save_project(project)
            except Exception as exc:  # noqa: BLE001 — best effort, siehe Befund 3
                build_logger.warning(
                    "graph_build restart: save_project (GRAPH_INCOMPLETE) fehlgeschlagen "
                    "[project_id=%s, run_id=%s]: %r",
                    project_id, new_run["run_id"], exc,
                )
            try:
                task_manager.complete_task(
                    task_id,
                    result={
                        "project_id": project_id,
                        "graph_id": graph_id,
                        "episode_count": len(episode_uuids),
                        "cancelled": True,
                    },
                )
            except Exception as exc:  # noqa: BLE001 — best effort, siehe Befund 3
                build_logger.warning(
                    "graph_build restart: complete_task (cancel) fehlgeschlagen "
                    "[project_id=%s, run_id=%s, task_id=%s]: %r",
                    project_id, new_run["run_id"], task_id, exc,
                )
            try:
                _runs_mod.run_registry.update_run(
                    new_run["run_id"],
                    status="stopped",
                    termination_reason="user_cancel",
                    message=(
                        "Vom Nutzer abgebrochen — bereits geschriebene Entitäten "
                        "und Relationen bleiben im Graphen erhalten, der Graph "
                        "gilt als unvollständig"
                    ),
                    message_key="run.graph_build_cancelled",
                    artifacts=_runs_mod.ArtifactLocator.existing_paths(
                        {"project_dir": _runs_mod.ProjectManager._get_project_dir(project_id)}
                    ),
                    resume_capability={"available": True, "action": "restart", "label": "Restart graph build"},
                )
            except Exception as exc:  # noqa: BLE001 — best effort, siehe Befund 3
                build_logger.error(
                    "graph_build restart: run_registry.update_run (cancel) fehlgeschlagen "
                    "[project_id=%s, run_id=%s]: %r",
                    project_id, new_run["run_id"], exc,
                )
            try:
                from ..services.sim.cancel_flag import clear_cancel
                clear_cancel(new_run["run_id"])
            except Exception as exc:  # noqa: BLE001 — best effort, siehe Befund 3
                build_logger.debug(
                    "graph_build restart: clear_cancel fehlgeschlagen [run_id=%s]: %r",
                    new_run["run_id"], exc,
                )

        def build_task():
            builder = None
            graph_id = None
            try:
                task_manager.update_task(
                    task_id,
                    status=_runs_mod.TaskStatus.PROCESSING,
                    message="Initializing graph build service...",
                    message_key="run.graph_build_initializing",
                )
                builder = container.graph_builder()
                task_manager.update_task(
                    task_id,
                    message="Chunking text...",
                    message_key="run.graph_build_chunking",
                    progress=5,
                )
                from ..services.text_processor import TextProcessor
                chunks = TextProcessor.split_text(text, chunk_size=chunk_size, overlap=chunk_overlap)
                total_chunks = len(chunks)
                task_manager.update_task(
                    task_id,
                    message="Creating graph...",
                    message_key="run.graph_build_creating_graph",
                    progress=10,
                )
                graph_id = builder.create_graph(name=graph_name)
                project.graph_id = graph_id
                _runs_mod.ProjectManager.save_project(project)
                _runs_mod.run_registry.update_run(
                    new_run["run_id"], linked_ids={"graph_id": graph_id}, entity_id=graph_id
                )
                task_manager.update_task(
                    task_id,
                    message="Setting ontology definition...",
                    message_key="run.graph_build_setting_ontology",
                    progress=15,
                )
                builder.set_ontology(graph_id, ontology)

                def add_progress_callback(msg, progress_ratio):
                    progress = 15 + int(progress_ratio * 40)
                    task_manager.update_task(task_id, message=msg, progress=progress)

                # Checkpoint (Issue B2, Review-Finding Befund 4): derselbe
                # kooperative Abbruch wie im produktiven Build-Pfad
                # (services/graph_build.py) — ohne run_id konnte das
                # Cancel-Flag hier vorher nie ankommen.
                from ..services.sim.cancel_flag import is_cancel_requested
                if is_cancel_requested(new_run["run_id"]):
                    _finish_cancelled_restart(graph_id, [], builder)
                    return

                from ..services.graph_builder import GraphBuildCancelled
                try:
                    episodes = builder.add_text_batches(
                        graph_id, chunks, batch_size=3,
                        progress_callback=add_progress_callback,
                        run_id=new_run["run_id"],
                        # Issue #1470 (Codex-Review PR #1620): derselbe
                        # NER-Kontext wie im Erst- und im Resume-Build.
                        chunk_contexts=_runs_mod.build_chunk_contexts(chunks),
                    )
                except GraphBuildCancelled as cancel_exc:
                    _finish_cancelled_restart(graph_id, cancel_exc.episode_uuids, builder)
                    return

                task_manager.update_task(
                    task_id,
                    message="Retrieving graph data...",
                    message_key="run.graph_build_retrieving",
                    progress=95,
                )
                graph_data = builder.get_graph_data(graph_id)
                project.status = _runs_mod.ProjectStatus.GRAPH_COMPLETED
                _runs_mod.ProjectManager.save_project(project)
                task_manager.update_task(
                    task_id,
                    status=_runs_mod.TaskStatus.COMPLETED,
                    message="Graph build completed",
                    message_key="run.graph_build_completed",
                    progress=100,
                    result={
                        "project_id": project_id,
                        "graph_id": graph_id,
                        "node_count": graph_data.get("node_count", 0),
                        "edge_count": graph_data.get("edge_count", 0),
                        "chunk_count": total_chunks,
                        "episode_count": len(episodes),
                    },
                )
                _runs_mod.run_registry.update_run(
                    new_run["run_id"],
                    status="completed",
                    progress=100,
                    message="Graph build completed",
                    message_key="run.graph_build_completed",
                    artifacts=_runs_mod.ArtifactLocator.existing_paths(
                        {"project_dir": _runs_mod.ProjectManager._get_project_dir(project_id)}
                    ),
                )
            except Exception as exc:  # noqa: BLE001 — exception reported to task/run registry
                project.status = _runs_mod.ProjectStatus.FAILED
                project.error = str(exc)
                _runs_mod.ProjectManager.save_project(project)
                task_manager.update_task(
                    task_id,
                    status=_runs_mod.TaskStatus.FAILED,
                    message=f"Build failed: {exc}",
                    error=traceback.format_exc(),
                )
                _runs_mod.run_registry.update_run(
                    new_run["run_id"], status="failed", message=str(exc), error=str(exc)
                )

        def scoped_build_task():
            with _runs_mod.workspace_credential_context_for_run(new_run["run_id"]):
                build_task()

        threading.Thread(target=scoped_build_task, daemon=True).start()

    return {"run_id": new_run["run_id"], "task_id": task_id, "status": "processing"}


def _restart_contested_question(run: dict, config: dict) -> Optional[str]:
    """Die Streitfrage, die der Nutzer für diese Vorbereitung vorgegeben hat (#1778).

    Der Restart hat keinen Request-Payload. Zuerst gilt der Vermerk am
    Ursprungs-Run: er existiert auch dann, wenn die Vorbereitung vor der
    Konfiguration scheiterte. Sonst gilt die gespeicherte Konfiguration, aber
    nur mit ``origin="user"`` — einen Vorschlag des Assistenten leitet der
    Restart wie jede Vorbereitung neu ab.
    """
    from_run = (run.get("metadata") or {}).get("contested_question")
    if isinstance(from_run, str) and from_run.strip():
        return from_run.strip()

    persisted = config.get("contested_question")
    if isinstance(persisted, dict) and persisted.get("origin") == "user":
        statement = persisted.get("statement")
        if isinstance(statement, str) and statement.strip():
            return statement.strip()
    return None


def _restart_activity_mode(run: dict, config: dict) -> Optional[str]:
    """Der Aktivitätsmodus der ursprünglichen Vorbereitung (#1779).

    Zuerst der Vermerk am Ursprungs-Run, sonst der Modus der gespeicherten
    Konfiguration. ``None``, wenn keiner bekannt ist (Einstellung/Standard).
    """
    from_run = (run.get("metadata") or {}).get("activity_mode")
    if isinstance(from_run, str) and from_run.strip():
        return from_run.strip()
    time_config = config.get("time_config")
    model = time_config.get("activity_model") if isinstance(time_config, dict) else None
    persisted = model.get("mode") if isinstance(model, dict) else None
    return persisted if isinstance(persisted, str) and persisted.strip() else None


def _restart_simulation_prepare(run: dict):
    _runs_mod = _runs_module()
    simulation_id = _runs_mod._linked_or_entity_id(run, "simulation_id", "simulation_id")
    manager = _runs_mod.SimulationManager()
    state = manager.get_simulation(simulation_id)
    if not state:
        raise ValueError(f"Simulation does not exist: {simulation_id}")

    project = _runs_mod.ProjectManager.get_project(state.project_id)
    if not project:
        raise ValueError(f"Project does not exist: {state.project_id}")

    simulation_requirement = project.simulation_requirement or ""
    document_text = _runs_mod.ProjectManager.get_extracted_text(state.project_id) or ""
    storage = _runs_mod.current_app.extensions.get("neo4j_storage")
    if not storage:
        raise ValueError("GraphStorage not initialized")

    config = manager.get_simulation_config(simulation_id) or {}
    contested_question = _runs_mod._restart_contested_question(run, config)
    activity_mode = _runs_mod._restart_activity_mode(run, config)
    # Issue #841/#844/#1183: Anlage-Fenster hinter RunLifecycle — Markierung,
    # Task-Reihenfolge und strikte Persistenzsemantik liegen im Kontextmanager.
    with _runs_mod.RunLifecycle.begin(
        _runs_mod.run_registry,
        "simulation_prepare",
        simulation_id,
        parent_run_id=run["run_id"],
        failure_message="Simulation preparation restart failed: {exc_type}",
        progress=0,
        message="Simulation preparation restart queued",
        message_key="run.prepare_restart_queued",
        linked_ids={"simulation_id": simulation_id, "project_id": state.project_id},
        artifacts=_runs_mod._simulation_artifacts(simulation_id),
        resume_capability={"available": True, "action": "restart", "label": "Restart preparation"},
        branch_label=state.branch_name,
        metadata={
            "graph_id": state.graph_id,
            "branch_name": state.branch_name,
            **_runs_mod._inherited_credential_scope_metadata(run),
            # #1778: weitertragen, damit auch ein zweiter Restart sie kennt.
            **({"contested_question": contested_question} if contested_question else {}),
            # #1779: Aktivitätsmodus ebenso weitertragen.
            **({"activity_mode": activity_mode} if activity_mode else {}),
        },
    ) as lifecycle:
        new_run = lifecycle.record
        run_id = new_run["run_id"]

        # Restart hat keinen Request-Payload — llm_runtime=None, damit das
        # Resolving ausschließlich über die persistierte Route bzw. den in der
        # Settings-DB hinterlegten Store-Key läuft und nicht still auf
        # Config.LLM_API_KEY/LLM_BASE_URL aus der lokalen .env zurückfällt (#798,
        # Opus-Review-Folgebefund zu #778). Exakt derselbe Resolver-Pfad wie
        # simulation_prepare.py::prepare_simulation.
        from ..utils.endpoints import LOCAL_NO_AUTH_API_KEY
        from ..services.llm_provider_registry import LlmProviderRegistry

        _runs_mod.seed_run_stage_routing(
            run_id,
            "persona_generation",
            llm_model_override=config.get("llm_model"),
            llm_runtime=None,
        )
        route_router = _runs_mod.StageModelRouter(run_id)
        resolved_route = route_router.resolve("persona_generation")
        route_router.lock_stage("persona_generation", resolved_route)

        if LlmProviderRegistry.uses_session_auth(resolved_route.provider_id):
            resolved_api_key = None
        else:
            resolved_api_key = _runs_mod.resolve_route_api_key(resolved_route, None)

            if resolved_api_key is None and not _runs_mod.is_local_endpoint(resolved_route.base_url_sanitized):
                guard_message = (
                    f"provider_override: kein api_key im Payload und kein Key in der Settings-DB "
                    f"für Provider '{resolved_route.provider_id}'. "
                    "Bitte in Einstellungen → LLM-Anbieter einen Schlüssel speichern "
                    "oder im Sitzungsfeld eingeben."
                )
                guard_error = ValueError(guard_message)
                # RunLifecycle liest die failed-Meldung über dieses Attribut (#841).
                guard_error.run_failure_message = guard_message  # type: ignore[attr-defined]
                raise guard_error

            if resolved_api_key is None and _runs_mod.is_local_endpoint(resolved_route.base_url_sanitized):
                resolved_api_key = LOCAL_NO_AUTH_API_KEY

        effective_llm_runtime = _runs_mod.build_runtime_llm_config(resolved_route, resolved_api_key)

        task_manager = _runs_mod.TaskManager()
        task_id = task_manager.create_task(
            "simulation_prepare",
            metadata={"simulation_id": simulation_id, "project_id": state.project_id, "run_id": new_run["run_id"]},
        )
        lifecycle.attach_task(task_manager, task_id)
        state.status = _runs_mod.SimulationStatus.PREPARING
        manager._save_simulation_state(state)

        def run_prepare():
            # Review-Finding PR #1371, Befund 4 (MITTEL): ohne run_id konnte
            # das Cancel-Flag hier nie ankommen — ein neu gestarteter Restart
            # war trotz "Restart"-Angebot im Endzustand nicht abbrechbar.
            from ..services.prepare_service import PrepareCancelledError
            from ..services.sim.cancel_flag import clear_cancel

            try:
                task_manager.update_task(
                    task_id,
                    status=_runs_mod.TaskStatus.PROCESSING,
                    progress=0,
                    message="Start preparing simulation environment...",
                    message_key="run.prepare_starting",
                )

                def progress_callback(stage, progress, message, **kwargs):
                    stage_weights = {
                        "reading": (0, 20),
                        "generating_profiles": (20, 70),
                        "generating_config": (70, 90),
                        "copying_scripts": (90, 100),
                    }
                    start, end = stage_weights.get(stage, (0, 100))
                    current_progress = int(start + (end - start) * progress / 100)
                    task_manager.update_task(task_id, progress=current_progress, message=f"[{stage}] {message}")

                # Sub-Slice 20a: quota_plan aus persistierter Run-Config wieder
                # aufnehmen, damit Restart denselben Soll-Plan nutzt wie der
                # ursprüngliche Prepare-Run. Inkonsistenter Plan im persisted
                # Config-Snapshot würde im Service-Layer als ValidationError
                # propagieren und den Restart als FAILED markieren — das ist
                # gewollt (kein silent-Fallback auf "ohne Plan").
                from ..api.simulation_prepare import _parse_quota_plan
                quota_plan = _parse_quota_plan(config or {})

                result_state = manager.prepare_simulation(
                    simulation_id=simulation_id,
                    simulation_requirement=simulation_requirement,
                    document_text=document_text,
                    defined_entity_types=None,
                    use_llm_for_profiles=True,
                    progress_callback=progress_callback,
                    parallel_profile_count=None,
                    storage=storage,
                    llm_model=config.get("llm_model"),
                    llm_runtime=effective_llm_runtime,
                    language=config.get("language"),
                    max_agents=config.get("max_agents"),
                    quota_plan=quota_plan,
                    # #1778: Nutzervorgabe für die Streitfrage erneut
                    # durchreichen; None heißt, der Assistent schlägt eine vor.
                    contested_question_override=contested_question,
                    activity_mode=activity_mode,
                    run_id=run_id,
                )
                task_manager.complete_task(task_id, result=result_state.to_simple_dict())
                _runs_mod.run_registry.update_run(
                    new_run["run_id"],
                    status="completed",
                    progress=100,
                    message="Simulation preparation completed",
                    message_key="run.prepare_completed",
                    artifacts=_runs_mod._simulation_artifacts(simulation_id),
                    resume_capability={"available": True, "action": "restart", "label": "Restart preparation"},
                )
            except PrepareCancelledError:
                # Spiegelt api/simulation_prepare.py::_make_prepare_job — hier
                # bewusst wiederverwendet statt neu gebaut, damit beide Pfade
                # denselben Endzustand liefern (kein zweites Muster).
                _runs_mod.logger.info(
                    "Simulation prepare restart cancelled by user (run_id=%s, simulation_id=%s)",
                    new_run["run_id"], simulation_id,
                )
                task_manager.complete_task(
                    task_id,
                    result={
                        "simulation_id": simulation_id,
                        "status": "cancelled",
                        "cancelled": True,
                    },
                )
                from ..api.simulation_prepare import _finish_cancelled_prepare_run
                _finish_cancelled_prepare_run(new_run["run_id"], simulation_id=simulation_id)
            except Exception as exc:  # noqa: BLE001 — exception reported to task/run registry
                task_manager.fail_task(task_id, str(exc))
                _runs_mod.run_registry.update_run(
                    new_run["run_id"], status="failed", message=str(exc), error=str(exc)
                )
                failed_state = manager.get_simulation(simulation_id)
                if failed_state:
                    failed_state.error = str(exc)
                    try:
                        manager._set_status(failed_state, _runs_mod.SimulationStatus.FAILED)
                    except Exception:  # noqa: BLE001
                        failed_state.status = _runs_mod.SimulationStatus.FAILED
                        manager._save_simulation_state(failed_state)
            finally:
                clear_cancel(new_run["run_id"])

        def scoped_prepare_job():
            with _runs_mod.workspace_credential_context_for_run(new_run["run_id"]):
                run_prepare()

        from ..api.simulation_prepare import _track_active_prepare_job
        tracked_job = _track_active_prepare_job(simulation_id, scoped_prepare_job)
        threading.Thread(target=tracked_job, daemon=True).start()

    return {"run_id": new_run["run_id"], "task_id": task_id, "status": "processing"}

