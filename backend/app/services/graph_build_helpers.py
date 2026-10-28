"""Worker-Helfer fuer ``app.services.graph_build`` (Build- und Resume-Tasks)."""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .graph_build_checkpoint import GraphBuildCheckpoint


def _finish_cancelled_build(
    *, project_id: str, project: Any, run_record: dict[str, Any], task_id: str,
    task_manager: Any, builder: Any, graph_id: str | None, degradations: Any,
    checkpoint_holder: list[GraphBuildCheckpoint | None],
    cancelled_episode_uuids: list[str], build_logger: Any,
) -> None:
    """Issue B2: Endzustand eines per ``/cancel`` gestoppten Graph-Builds.

    Spiegelt bewusst ``services/report_generation.py::finish_cancelled_run``:
    ``stopped`` + ``termination_reason="user_cancel"``, Reihenfolge
    ``complete_task()`` zuerst (``sync_task`` würde sonst generisch
    "completed" setzen), dann der detaillierte Run-Update. Der Graph
    wird NICHT gelöscht und NICHT zurückgerollt — bereits committete
    Episoden/Entities/Relations bleiben stehen (Plan B2, bewusste
    Entscheidung); er gilt nur als unvollständig.

    Review-Finding (PR #1371, Befund 3): diese Funktion läuft
    INNERHALB des äußeren try-Blocks von ``build_task``. Ohne
    eigene Fehlerbehandlung würde ein Aussetzer hier selbst
    (Neo4j-Schreibfehler in ``mark_graph_incomplete``,
    ``ProjectManager.save_project``, ein Registry-Schreibfehler
    in ``run_registry.update_run``) ins äußere
    ``except Exception`` durchschlagen — und DAS löscht per
    ``builder.delete_graph(graph_id)`` genau den Teilgraphen,
    den dieser Cancel-Pfad ausdrücklich erhalten soll, während
    ``complete_task()`` bereits ``cancelled: True`` gemeldet
    hätte. Jeder Schritt läuft deshalb einzeln best-effort:
    ein Fehschlag wird geloggt, aber weder hier noch nach
    außen erneut geworfen. Der wichtigste Schritt — der
    Run-Registry-Update auf ``status="stopped"`` — läuft
    zuletzt und unabhängig davon, ob die vorherigen Schritte
    geglückt sind, damit der Nutzer den Abbruch so oder so
    sieht.
    """
    from . import graph_build as _gb
    from ..services.sim.cancel_flag import clear_cancel

    build_logger.info(
        "Graph build cancelled by user [project_id=%s, run_id=%s, "
        "graph_id=%s, episodes=%d]",
        project_id, run_record["run_id"], graph_id, len(cancelled_episode_uuids),
    )

    # ``builder``/``graph_id`` sind zu diesem Zeitpunkt immer
    # gesetzt — beide Aufrufstellen liegen im try-Block nach
    # ``builder = container.graph_builder()`` und
    # ``graph_id = builder.create_graph(...)``. Die Prüfung
    # bleibt trotzdem stehen: eine geschlossene Funktion kann
    # ihre Closure-Variablen nicht flow-sensitiv typisieren,
    # und ein späteres Refactoring darf hier nicht auf ein
    # AttributeError statt eines sauberen Log-Eintrags laufen.
    if builder is not None and graph_id is not None:
        try:
            builder.mark_graph_incomplete(graph_id, reason="user_cancel")
        except Exception as exc:  # noqa: BLE001 — best effort; siehe Docstring
            build_logger.warning(
                "graph_build: mark_graph_incomplete fehlgeschlagen "
                "[project_id=%s, run_id=%s, graph_id=%s]: %r",
                project_id, run_record["run_id"], graph_id, exc,
            )
    else:
        build_logger.warning(
            "Graph build cancelled before builder/graph_id existed "
            "[project_id=%s, run_id=%s] — nichts zu markieren",
            project_id, run_record["run_id"],
        )

    try:
        project.graph_id = graph_id
        project.status = _gb.ProjectStatus.GRAPH_INCOMPLETE
        _gb.ProjectManager.save_project(project)
    except Exception as exc:  # noqa: BLE001 — best effort; siehe Docstring
        build_logger.warning(
            "graph_build: save_project (GRAPH_INCOMPLETE) fehlgeschlagen "
            "[project_id=%s, run_id=%s]: %r",
            project_id, run_record["run_id"], exc,
        )

    try:
        task_manager.complete_task(
            task_id,
            result={
                "project_id": project_id,
                "graph_id": graph_id,
                "episode_count": len(cancelled_episode_uuids),
                "cancelled": True,
                "degradations": degradations.report().model_dump(mode="json"),
            },
        )
    except Exception as exc:  # noqa: BLE001 — best effort; siehe Docstring
        build_logger.warning(
            "graph_build: complete_task (cancel) fehlgeschlagen "
            "[project_id=%s, run_id=%s, task_id=%s]: %r",
            project_id, run_record["run_id"], task_id, exc,
        )

    # Wichtigster Schritt — läuft unabhängig vom Erfolg der
    # vorherigen, sonst bliebe der Run für den Nutzer
    # unsichtbar auf "processing" hängen.
    try:
        _gb.run_registry.update_run(
            run_record["run_id"],
            status="stopped",
            termination_reason="user_cancel",
            message=(
                "Vom Nutzer abgebrochen — bereits geschriebene Entitäten "
                "und Relationen bleiben im Graphen erhalten, der Graph "
                "gilt als unvollständig"
            ),
            artifacts=_gb.ArtifactLocator.existing_paths({
                "project_dir": _gb.ProjectManager._get_project_dir(project_id),
            }),
            # Issue #1472b: "resume" nur, wenn der Checkpoint
            # tatsächlich mindestens einen fertigen Chunk
            # trägt — sonst bleibt es beim ehrlichen "restart".
            resume_capability=_gb.resume_capability_for_checkpoint(
                checkpoint_holder[0]
            ),
        )
    except Exception as exc:  # noqa: BLE001 — best effort; siehe Docstring
        build_logger.error(
            "graph_build: run_registry.update_run (cancel) fehlgeschlagen "
            "[project_id=%s, run_id=%s] — Run bleibt evtl. auf 'processing' "
            "haengen: %r",
            project_id, run_record["run_id"], exc,
        )

    try:
        clear_cancel(run_record["run_id"])
    except Exception as exc:  # noqa: BLE001 — best effort; siehe Docstring
        build_logger.debug(
            "graph_build: clear_cancel fehlgeschlagen [run_id=%s]: %r",
            run_record["run_id"], exc,
        )


def _handle_build_graph_failure(
    *, exc: Exception, project_id: str, project: Any, run_record: dict[str, Any],
    task_id: str, task_manager: Any, builder: Any, graph_id: str | None,
    checkpoint_holder: list[GraphBuildCheckpoint | None], build_logger: Any,
) -> None:
    """Fehlerpfad fuer ``_execute_build_graph_task``."""
    from . import graph_build as _gb

    build_logger.exception("Graph build failed [project_id=%s, run_id=%s]", project_id, run_record["run_id"])
    # ``builder`` kann None sein, wenn die Exception vor
    # ``builder = container.graph_builder()`` auftrat (z. B.
    # im allerersten ``task_manager.update_task``) — dann gibt
    # es auch keinen ``graph_id`` und nichts aufzuräumen.
    if graph_id is not None and builder is not None:
        try:
            builder.delete_graph(graph_id)
        except Exception:  # noqa: BLE001 — best-effort cleanup; primary exception already propagated
            try:
                builder.mark_graph_failed(graph_id, reason=str(exc))
            except Exception as err:  # noqa: BLE001 — best-effort cleanup; primary exception already propagated
                _gb.logger.debug("graph_build: mark_graph_failed also failed, ignoring: %s", err)

    # P1-1 (PR #1535 Review): delete_graph raeumt den
    # Graph-Knoten weg, aber ein liegen gebliebener
    # Checkpoint wuerde ``resume_capability`` unten trotzdem
    # "resume" melden — der Resume-Pfad arbeitet nur mit
    # ``MATCH`` (kein ``create_graph``) und liefe ins Leere.
    # Ein angebotenes Resume, das nicht funktioniert, ist
    # schlimmer als keins: Checkpoint mit loeschen, nur
    # "restart" bleibt eine ehrliche Option.
    if checkpoint_holder[0] is not None:
        _gb.clear_checkpoint(project_id)
        checkpoint_holder[0] = None

    project.status = _gb.ProjectStatus.FAILED
    project.error = str(exc)
    _gb.ProjectManager.save_project(project)

    task_manager.update_task(
        task_id, status=_gb.TaskStatus.FAILED, message=f"Build failed: {str(exc)}", error=traceback.format_exc()
    )
    _gb.run_registry.update_run(
        run_record["run_id"],
        status="failed",
        message=str(exc),
        error=str(exc),
        # Issue #1472b/P1-1: "resume" nur, wenn ein Checkpoint
        # UND der Graph, auf den er zeigt, noch existieren —
        # nach dem obigen delete_graph ist das nie der Fall,
        # checkpoint_holder[0] ist an dieser Stelle immer
        # None, also immer "restart".
        resume_capability=_gb.resume_capability_for_checkpoint(checkpoint_holder[0]),
    )


def _execute_build_graph_task(
    *, cls: Any, project_id: str, project: Any, text: str, ontology: dict[str, Any],
    graph_name: str, chunk_size: int, chunk_overlap: int, task_id: str,
    task_manager: Any, run_record: dict[str, Any], container: Any, ner_override: Any,
) -> None:
    """
    Builds the project's graph and records its completion or failure state.

    On failure, marks the project, task, and run as failed and attempts to clean up any
    partially created graph.
    """
    from . import graph_build as _gb

    build_logger = _gb.get_logger("agora.build")
    graph_id = None
    # Defensiv vorinitialisiert wie ``graph_id`` oben: falls eine
    # Exception schon vor ``builder = container.graph_builder()``
    # unten auftritt (z. B. im ersten ``task_manager.update_task``),
    # greift der except-Zweig sonst auf eine ungebundene lokale
    # Variable zu (statische Analyse, Review-Finding) — genau der
    # Fall, in dem ein sauberer Fehlschlag am wichtigsten wäre.
    builder = None
    # Issue #1029: Dies ist der produktive Build-Pfad (Endpunkt
    # ``/api/graph/build``). ``GraphBuilderService._build_graph_worker``
    # trägt dieselbe Verdrahtung, wird von hier aber nicht benutzt —
    # beide Pfade müssen sie haben, sonst ist das Gate genau dort
    # blind, wo es zählt.
    degradations = _gb.DegradationCollector()
    extraction_tally = _gb.ChunkExtractionTally()
    # Issue #1472b: haelt den jeweils aktuellsten, bereits auf
    # Platte geschriebenen Checkpoint — eine Ein-Element-Liste
    # statt einer einfachen Variable, damit sowohl der innere
    # Callback als auch ``_finish_cancelled_build`` (weiter unten
    # definiert, per Closure) denselben veraenderlichen Zustand
    # sehen, ohne ``nonlocal`` ueber mehrere Funktionsgrenzen
    # hinweg zu brauchen.
    checkpoint_holder: list[GraphBuildCheckpoint | None] = [None]

    try:
        task_manager.update_task(task_id, status=_gb.TaskStatus.PROCESSING, message="Initializing graph build service...")
        builder = container.graph_builder()

        # Issue #1472b: ein frischer Build (erster Versuch ODER
        # ``force``-Restart) startet ohne verwertbaren Checkpoint
        # — ein liegen gebliebener Checkpoint eines VORHERIGEN,
        # anderen Graphen darf hier nicht fälschlich anschlagen.
        # Der eigentliche Resume-Pfad läuft nie über
        # ``build_task``, sondern über
        # ``api/runs.py::_resume_graph_build``.
        _gb.clear_checkpoint(project_id)

        task_manager.update_task(task_id, message="Chunking text...", progress=5)
        # Issue #1152 Slice 1, Teil B / #1472b: dieselbe
        # Chunk-Zerlegung wie ein späterer Resume-Versuch
        # (``chunk_project_text``) — beide Pfade teilen sich
        # denselben Code, damit Chunk-Indizes über einen Resume
        # hinweg stabil bleiben.
        chunks, document_ids, chunk_ids, manifest_anchored = cls.chunk_project_text(
            project_id, text, chunk_size, chunk_overlap
        )

        task_manager.update_task(task_id, message="Creating graph...", progress=10)
        graph_id = builder.create_graph(name=graph_name)

        _gb.run_registry.update_run(
            run_record["run_id"],
            entity_id=project_id,
            linked_ids={"graph_id": graph_id, "project_id": project_id, "task_id": task_id},
            message=f"Graph created: {graph_id}",
        )

        task_manager.update_task(task_id, message="Setting ontology definition...", progress=15)
        builder.set_ontology(graph_id, ontology)

        def add_progress_callback(msg, progress_ratio, completed, total):
            progress = 15 + int(progress_ratio * 40)
            task_manager.update_task(
                task_id, message=msg, progress=progress,
                progress_detail={"batch_count": completed, "total_batches": total, "batch_at": _gb.time.time()}
            )

        def record_checkpoint(idx: int, episode_uuid: str) -> None:
            """Issue #1472b: schreibt nach jedem committeten Chunk

            einen aktualisierten Checkpoint. Läuft ausschließlich im
            Hauptthread der ``as_completed``-Schleife in
            ``add_text_batches`` (kein Lock nötig). Ein
            Schreibfehler propagiert unverändert — siehe
            Docstring von ``checkpoint_callback`` in
            ``add_text_batches`` und
            ``graph_build_checkpoint.save_checkpoint``.
            """
            current = checkpoint_holder[0]
            if current is None:
                current = _gb.GraphBuildCheckpoint(
                    graph_id=graph_id,
                    total_chunks=len(chunks),
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    manifest_anchored=manifest_anchored,
                    updated_at=_gb.datetime.now(_gb.UTC),
                )
            updated = current.with_completed_chunk(idx, episode_uuid)
            _gb.save_checkpoint(project_id, updated)
            checkpoint_holder[0] = updated

        # Checkpoint (Issue B2): zwischen Ontologie-Setzen und dem
        # eigentlichen (potenziell langen) Chunk-Durchlauf. Noch
        # keine Episode geschrieben — der Cancel-Pfad bekommt eine
        # leere Liste.
        from ..services.sim.cancel_flag import is_cancel_requested
        if is_cancel_requested(run_record["run_id"]):
            _finish_cancelled_build(
                project_id=project_id, project=project, run_record=run_record,
                task_id=task_id, task_manager=task_manager, builder=builder,
                graph_id=graph_id, degradations=degradations,
                checkpoint_holder=checkpoint_holder, cancelled_episode_uuids=[],
                build_logger=build_logger,
            )
            return

        from .graph_builder import GraphBuildCancelled
        try:
            builder.add_text_batches(
                graph_id, chunks, batch_size=3,
                progress_callback=add_progress_callback,
                ner_extractor=ner_override,
                degradations=degradations,
                extraction_tally=extraction_tally,
                document_ids=document_ids,
                chunk_ids=chunk_ids,
                run_id=run_record["run_id"],
                checkpoint_callback=record_checkpoint,
                chunk_contexts=_gb.build_chunk_contexts(chunks, document_ids),
            )
        except GraphBuildCancelled as cancel_exc:
            _finish_cancelled_build(
                project_id=project_id, project=project, run_record=run_record,
                task_id=task_id, task_manager=task_manager, builder=builder,
                graph_id=graph_id, degradations=degradations,
                checkpoint_holder=checkpoint_holder,
                cancelled_episode_uuids=cancel_exc.episode_uuids,
                build_logger=build_logger,
            )
            return

        task_manager.update_task(task_id, message="Retrieving graph data...", progress=95)
        graph_data = builder.get_graph_data(graph_id)

        # Issue #1029: Qualitätsgate vor dem Abschluss. Bis hierher
        # meldete der Build "completed", auch wenn der Graph keine
        # einzige Beziehung trug — der Report scheiterte Minuten
        # später an fehlender Evidenz.
        builder.assess_graph_quality_from_counts(
            node_count=graph_data.get("node_count", 0),
            edge_count=graph_data.get("edge_count", 0),
            extraction_tally=extraction_tally,
            degradations=degradations,
        )
        degradation_payload = degradations.report().model_dump(mode="json")

        builder.mark_graph_completed(graph_id)
        project.graph_id = graph_id
        project.status = _gb.ProjectStatus.GRAPH_COMPLETED
        _gb.ProjectManager.save_project(project)
        # Issue #1472b: ein abgeschlossener Graph hat nichts mehr
        # zum Fortsetzen — ein stehen gebliebener Checkpoint
        # würde nur einen künftigen, unverwandten Build-Versuch
        # verwirren.
        _gb.clear_checkpoint(project_id)

        task_manager.update_task(
            task_id, status=_gb.TaskStatus.COMPLETED, message="Graph build completed", progress=100,
            result={
                "project_id": project_id,
                "graph_id": graph_id,
                "node_count": graph_data.get("node_count", 0),
                "edge_count": graph_data.get("edge_count", 0),
                # Leere Liste heißt „nichts ist still ausgefallen“.
                "degradations": degradation_payload,
            }
        )
        _gb.run_registry.update_run(run_record["run_id"], status="completed", progress=100, message="Graph build completed")

    except Exception as exc:  # noqa: BLE001 — exception reported to task/run registry
        _handle_build_graph_failure(
            exc=exc, project_id=project_id, project=project, run_record=run_record,
            task_id=task_id, task_manager=task_manager, builder=builder,
            graph_id=graph_id, checkpoint_holder=checkpoint_holder, build_logger=build_logger,
        )
    finally:
        # Review-Finding (PR #1371, Befund 7): ohne diesen
        # finally-Block räumte nur der GraphBuildCancelled-Zweig
        # (über _finish_cancelled_build) das Flag auf. Kommt die
        # Cancel-Anfrage NACH dem letzten Checkpoint (z. B.
        # während der Qualitätsbewertung nach add_text_batches),
        # läuft der Build normal zu Ende und das
        # threading.Event bliebe für die restliche
        # Prozesslaufzeit im globalen Dict von cancel_flag.py
        # liegen. ``clear_cancel`` ist idempotent, ein zweiter
        # Aufruf im Cancel-Zweig oben ist folgenlos.
        from ..services.sim.cancel_flag import clear_cancel, is_cancel_requested

        if is_cancel_requested(run_record["run_id"]):
            build_logger.info(
                "Graph build: Cancel-Flag war gesetzt, aber der "
                "letzte Checkpoint war bereits passiert "
                "[project_id=%s, run_id=%s] — Abbruch kam zu "
                "spät, Endzustand bleibt wie oben bestimmt.",
                project_id, run_record["run_id"],
            )
        clear_cancel(run_record["run_id"])


def _finish_cancelled_resume(
    *, project_id: str, project: Any, new_run: dict[str, Any], task_id: str,
    task_manager: Any, container: Any, graph_id: str,
    checkpoint_holder: list[GraphBuildCheckpoint], episode_uuids: list[str],
) -> None:
    """Endzustand eines per ``/cancel`` gestoppten Graph-Build-Resumes."""
    from . import graph_build as _gb

    build_logger = _gb.logger
    build_logger.info(
        "Graph build resume cancelled by user [project_id=%s, run_id=%s, "
        "graph_id=%s, episodes=%d]",
        project_id, new_run["run_id"], graph_id, len(episode_uuids),
    )
    builder = container.graph_builder()
    try:
        builder.mark_graph_incomplete(graph_id, reason="user_cancel")
    except Exception as exc:  # noqa: BLE001 — best effort, siehe build_graph._finish_cancelled_build
        build_logger.warning(
            "graph_build resume: mark_graph_incomplete fehlgeschlagen "
            "[project_id=%s, run_id=%s, graph_id=%s]: %r",
            project_id, new_run["run_id"], graph_id, exc,
        )
    try:
        project.graph_id = graph_id
        project.status = _gb.ProjectStatus.GRAPH_INCOMPLETE
        _gb.ProjectManager.save_project(project)
    except Exception as exc:  # noqa: BLE001 — best effort
        build_logger.warning(
            "graph_build resume: save_project (GRAPH_INCOMPLETE) fehlgeschlagen "
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
    except Exception as exc:  # noqa: BLE001 — best effort
        build_logger.warning(
            "graph_build resume: complete_task (cancel) fehlgeschlagen "
            "[project_id=%s, run_id=%s, task_id=%s]: %r",
            project_id, new_run["run_id"], task_id, exc,
        )
    try:
        _gb.run_registry.update_run(
            new_run["run_id"],
            status="stopped",
            termination_reason="user_cancel",
            message=(
                "Vom Nutzer abgebrochen — bereits geschriebene Entitäten "
                "und Relationen bleiben im Graphen erhalten, der Graph "
                "gilt als unvollständig"
            ),
            artifacts=_gb.ArtifactLocator.existing_paths({
                "project_dir": _gb.ProjectManager._get_project_dir(project_id),
            }),
            resume_capability=_gb.resume_capability_for_checkpoint(checkpoint_holder[0]),
        )
    except Exception as exc:  # noqa: BLE001 — best effort
        build_logger.error(
            "graph_build resume: run_registry.update_run (cancel) fehlgeschlagen "
            "[project_id=%s, run_id=%s]: %r",
            project_id, new_run["run_id"], exc,
        )
    try:
        from .sim.cancel_flag import clear_cancel
        clear_cancel(new_run["run_id"])
    except Exception as exc:  # noqa: BLE001 — best effort
        build_logger.debug(
            "graph_build resume: clear_cancel fehlgeschlagen [run_id=%s]: %r",
            new_run["run_id"], exc,
        )


def _execute_resume_graph_build_task(
    *, project_id: str, project: Any, ontology: dict[str, Any], graph_id: str,
    checkpoint: GraphBuildCheckpoint, chunks: list[str],
    remaining_original_indices: list[int], remaining_chunks: list[str],
    remaining_document_ids: list[str | None] | None,
    remaining_chunk_ids: list[int | None] | None,
    remaining_chunk_contexts: list[str | None], new_run: dict[str, Any],
    task_id: str, task_manager: Any, container: Any,
) -> None:
    """Worker-Funktion fuer ``GraphBuildService.resume_graph_build``."""
    from . import graph_build as _gb

    checkpoint_holder = [checkpoint]

    def record_checkpoint(local_idx: int, episode_uuid: str) -> None:
        original_idx = remaining_original_indices[local_idx]
        updated = checkpoint_holder[0].with_completed_chunk(original_idx, episode_uuid)
        _gb.save_checkpoint(project_id, updated)
        checkpoint_holder[0] = updated

    try:
        task_manager.update_task(task_id, status=_gb.TaskStatus.PROCESSING, message="Resuming graph build...")
        builder = container.graph_builder()
        builder.set_ontology(graph_id, ontology)

        def add_progress_callback(msg, progress_ratio, completed, total):
            # ``completed``/``total`` beziehen sich nur auf die in
            # DIESEM Versuch verbleibenden Chunks — der bereits vor
            # dem Resume abgeschlossene Anteil fließt separat in
            # den Startwert von ``progress`` bei
            # ``RunLifecycle.begin`` ein.
            done_before = len(checkpoint.completed_chunk_indices)
            overall_ratio = (done_before + completed) / len(chunks) if chunks else 1.0
            task_manager.update_task(
                task_id, message=msg, progress=int(overall_ratio * 100)
            )

        if remaining_chunks:
            from .sim.cancel_flag import is_cancel_requested
            if is_cancel_requested(new_run["run_id"]):
                _finish_cancelled_resume(
                    project_id=project_id, project=project, new_run=new_run,
                    task_id=task_id, task_manager=task_manager, container=container,
                    graph_id=graph_id, checkpoint_holder=checkpoint_holder, episode_uuids=[],
                )
                return

            from .graph_builder import GraphBuildCancelled
            try:
                builder.add_text_batches(
                    graph_id, remaining_chunks, batch_size=3,
                    progress_callback=add_progress_callback,
                    document_ids=remaining_document_ids,
                    chunk_ids=remaining_chunk_ids,
                    run_id=new_run["run_id"],
                    checkpoint_callback=record_checkpoint,
                    chunk_contexts=remaining_chunk_contexts,
                )
            except GraphBuildCancelled as cancel_exc:
                _finish_cancelled_resume(
                    project_id=project_id, project=project, new_run=new_run,
                    task_id=task_id, task_manager=task_manager, container=container,
                    graph_id=graph_id, checkpoint_holder=checkpoint_holder,
                    episode_uuids=cancel_exc.episode_uuids,
                )
                return
        # else: der komplette Rest war bereits vor diesem
        # Resume-Versuch fertig — direkt zum Qualitätsgate.

        task_manager.update_task(task_id, message="Retrieving graph data...", progress=95)
        graph_data = builder.get_graph_data(graph_id)

        # P1-3 (PR #1535 Review): derselbe Qualitaetsgate wie im
        # Original-Build (siehe ``build_graph.build_task``) —
        # ohne ihn faehrt ein resumeter Graph mit zu wenigen
        # Relationen als "fertig" durch, weil sein Task-Ergebnis
        # keine ``degradations`` traegt. Ein frischer Collector
        # genuegt: der Resume-Pfad wiring bewusst keine
        # NER-Degradationen durch (Docstring oben), die
        # Chunk-Erfolgsquote bleibt bei ``extraction_tally.total
        # == 0`` deshalb ungeprueft — nur die Node-/Edge-Zahlen
        # zaehlen hier, wie beim Original-Build.
        degradations = _gb.DegradationCollector()
        extraction_tally = _gb.ChunkExtractionTally()
        builder.assess_graph_quality_from_counts(
            node_count=graph_data.get("node_count", 0),
            edge_count=graph_data.get("edge_count", 0),
            extraction_tally=extraction_tally,
            degradations=degradations,
        )
        degradation_payload = degradations.report().model_dump(mode="json")

        builder.mark_graph_completed(graph_id)
        project.status = _gb.ProjectStatus.GRAPH_COMPLETED
        project.graph_id = graph_id
        _gb.ProjectManager.save_project(project)
        # Issue #1472b: fertig — kein Checkpoint mehr zum Fortsetzen.
        _gb.clear_checkpoint(project_id)

        task_manager.update_task(
            task_id,
            status=_gb.TaskStatus.COMPLETED,
            message="Graph build completed",
            progress=100,
            result={
                "project_id": project_id,
                "graph_id": graph_id,
                "node_count": graph_data.get("node_count", 0),
                "edge_count": graph_data.get("edge_count", 0),
                "chunk_count": len(chunks),
                "resumed_chunk_count": len(checkpoint.completed_chunk_indices),
                # Leere Liste heißt „nichts ist still ausgefallen“
                # — spiegelt den Original-Build (P1-3).
                "degradations": degradation_payload,
            },
        )
        _gb.run_registry.update_run(
            new_run["run_id"],
            status="completed",
            progress=100,
            message="Graph build completed",
            artifacts=_gb.ArtifactLocator.existing_paths({
                "project_dir": _gb.ProjectManager._get_project_dir(project_id),
            }),
        )
    except Exception as exc:  # noqa: BLE001 — exception reported to task/run registry
        project.status = _gb.ProjectStatus.FAILED
        project.error = str(exc)
        _gb.ProjectManager.save_project(project)
        task_manager.update_task(
            task_id,
            status=_gb.TaskStatus.FAILED,
            message=f"Build failed: {exc}",
            error=traceback.format_exc(),
        )
        _gb.run_registry.update_run(
            new_run["run_id"],
            status="failed",
            message=str(exc),
            error=str(exc),
            resume_capability=_gb.resume_capability_for_checkpoint(checkpoint_holder[0]),
        )


def build_graph(
    cls: Any,
    project_id: str,
    graph_name: str,
    llm_model_override: Any = None,
    llm_runtime: Any = None,
    llm_profile_id: Any = None,
    force: bool = False,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    container: Any = None,
    ai_model_ref: Any = None,
) -> tuple[str, str]:
    """Queue a graph build for a project using its extracted text and ontology."""
    from . import graph_build as _gb

    project = _gb.ProjectManager.get_project(project_id)
    if not project:
        raise ValueError(_gb.ApiErrorCode.NOT_FOUND)

    # State check
    if project.status == _gb.ProjectStatus.CREATED:
        raise ValueError(_gb.ApiErrorCode.ONTOLOGY_MISSING)

    if project.status == _gb.ProjectStatus.GRAPH_BUILDING and not force:
        raise RuntimeError(_gb.ApiErrorCode.GRAPH_BUILD_IN_PROGRESS)

    if force:
        project.status = _gb.ProjectStatus.ONTOLOGY_GENERATED
        project.graph_id = None
        project.graph_build_task_id = None
        project.error = None

    # Resume-Pfad: hat der Request keine eigene Route und trägt das Projekt
    # eine beim Ontology-Generate persistierte AiModelRef, ist diese die
    # kanonische Bindung — analog zum llm_profile_id-Default darunter (#900).
    if (
        ai_model_ref is None
        and project.ai_model_ref
        and not llm_model_override
        and (llm_runtime is None or not llm_runtime.enabled)
        and not llm_profile_id
    ):
        try:
            ai_model_ref = _gb.AiModelRef.model_validate(project.ai_model_ref)
        except Exception:  # noqa: BLE001 — defekte Persistenz darf den Legacy-Pfad nicht blockieren
            _gb.logger.warning(
                "Persistierte ai_model_ref des Projekts ist ungültig, "
                "Legacy-Routing wird verwendet [project_id=%s]",
                project_id,
            )

    effective_model_override = None if ai_model_ref is not None else llm_model_override
    effective_llm_runtime = None if ai_model_ref is not None else llm_runtime
    effective_profile_id = (
        None if ai_model_ref is not None else llm_profile_id or project.llm_profile_id
    )
    if ai_model_ref is None and llm_profile_id is not None:
        project.llm_profile_id = llm_profile_id

    # Inputs
    chunk_size = chunk_size or project.chunk_size or _gb.Config.DEFAULT_CHUNK_SIZE
    chunk_overlap = chunk_overlap or project.chunk_overlap or _gb.Config.DEFAULT_CHUNK_OVERLAP
    project.chunk_size = chunk_size
    project.chunk_overlap = chunk_overlap

    text = _gb.ProjectManager.get_extracted_text(project_id)
    if not text:
        raise ValueError("Extracted text not found")

    ontology = project.ontology
    if not ontology:
        raise ValueError("Ontology definition not found")

    task_manager = _gb.TaskManager()
    run_record = _gb.run_registry.create_run(
        run_type="graph_build",
        entity_id=project_id,
        status="pending",
        progress=0,
        message="Graph build queued",
        linked_ids={"project_id": project_id},
        artifacts=_gb.ArtifactLocator.existing_paths({
            "project_dir": _gb.ProjectManager._get_project_dir(project_id),
        }),
        resume_capability={"available": True, "action": "restart", "label": "Restart graph build"},
        metadata={"graph_name": graph_name, **_gb.workspace_credential_metadata()},
    )
    task_id: str | None = None
    with _gb._terminalize_ai_model_ref_sync_failure(
        ai_model_ref=ai_model_ref,
        project=project,
        run_id=run_record["run_id"],
        phase="graph_build_enqueue",
        task_manager=task_manager,
        task_id_getter=lambda: task_id,
    ):
        task_id = task_manager.create_task(
            f"Build graph: {graph_name}",
            metadata={"project_id": project_id, "run_id": run_record["run_id"]},
        )
        project.status = _gb.ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        _gb.ProjectManager.save_project(project)

        with _gb._classify_ai_model_ref_seed_error(ai_model_ref):
            _gb.seed_run_stage_routing(
                run_record["run_id"],
                "graph_build",
                llm_model_override=effective_model_override,
                llm_runtime=effective_llm_runtime,
                llm_profile_id=effective_profile_id,
                ai_model_ref=ai_model_ref,
            )
        route_router = _gb.StageModelRouter(run_record["run_id"])
        resolved_route = route_router.resolve("graph_build")
        route_router.lock_stage("graph_build", resolved_route)

        # The locked route is authoritative; legacy profile IDs must not replace it.
        ner_llm_client = _gb.LLMClient.from_route(
            resolved_route,
            secret_resolver=_gb.SecretResolver(),
            api_key_override=_gb.resolve_route_api_key(resolved_route, effective_llm_runtime),
            run_id=run_record["run_id"],
        )
        _gb.logger.info(
            "Build-Pfad nutzt Route-Snapshot: model=%s provider=%s [project_id=%s, run_id=%s]",
            ner_llm_client.model,
            resolved_route.provider_id,
            project_id,
            run_record["run_id"],
        )
        ner_override = _gb.NERExtractor(llm_client=ner_llm_client)

        def build_task():
            _execute_build_graph_task(
                cls=cls,
                project_id=project_id,
                project=project,
                text=text,
                ontology=ontology,
                graph_name=graph_name,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                task_id=task_id,
                task_manager=task_manager,
                run_record=run_record,
                container=container,
                ner_override=ner_override,
            )

        from ..jobs import enqueue
        def scoped_build_task():
            with _gb.workspace_credential_context_for_run(run_record["run_id"]):
                build_task()

        enqueue("graph_build", scoped_build_task, run_id=run_record["run_id"])
    return task_id, run_record["run_id"]


def resume_graph_build(
    cls: Any,
    *,
    project_id: str,
    parent_run_id: str,
    checkpoint: Any,
    chunks: list[str],
    document_ids: list[str | None] | None,
    chunk_ids: list[int | None] | None,
    container: Any,
) -> dict:
    """Setzt einen unterbrochenen graph_build anhand eines Checkpoints fort."""
    from . import graph_build as _gb
    from .run_lifecycle import RunLifecycle

    project = _gb.ProjectManager.get_project(project_id)
    if not project:
        raise ValueError(_gb.ApiErrorCode.NOT_FOUND)
    ontology = project.ontology
    if not ontology:
        raise ValueError("Ontology definition not found")

    graph_id = checkpoint.graph_id
    completed_indices = set(checkpoint.completed_chunk_indices)
    remaining_original_indices = [
        idx for idx in range(len(chunks)) if idx not in completed_indices
    ]
    remaining_chunks = [chunks[idx] for idx in remaining_original_indices]
    remaining_document_ids = (
        [document_ids[idx] for idx in remaining_original_indices]
        if document_ids is not None
        else None
    )
    remaining_chunk_ids = (
        [chunk_ids[idx] for idx in remaining_original_indices]
        if chunk_ids is not None
        else None
    )
    _all_contexts = _gb.build_chunk_contexts(chunks, document_ids)
    remaining_chunk_contexts = [_all_contexts[idx] for idx in remaining_original_indices]

    with RunLifecycle.begin(
        _gb.run_registry,
        "graph_build",
        project_id,
        parent_run_id=parent_run_id,
        failure_message="Graph build resume failed: {exc_type}",
        progress=int(100 * len(completed_indices) / len(chunks)) if chunks else 0,
        message="Graph build resume queued",
        linked_ids={"project_id": project_id, "graph_id": graph_id},
        artifacts=_gb.ArtifactLocator.existing_paths({
            "project_dir": _gb.ProjectManager._get_project_dir(project_id),
        }),
        resume_capability={"available": True, "action": "resume", "label": "Resume graph build"},
        metadata={"graph_name": project.name or "Agora Graph", **_gb.workspace_credential_metadata()},
    ) as lifecycle:
        new_run = lifecycle.record
        task_manager = _gb.TaskManager()
        task_id = task_manager.create_task(
            f"Resume graph build: {project.name or graph_id}",
            metadata={"project_id": project_id, "run_id": new_run["run_id"]},
        )
        lifecycle.attach_task(task_manager, task_id)
        project.status = _gb.ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        _gb.ProjectManager.save_project(project)

        def build_task():
            _execute_resume_graph_build_task(
                project_id=project_id,
                project=project,
                ontology=ontology,
                graph_id=graph_id,
                checkpoint=checkpoint,
                chunks=chunks,
                remaining_original_indices=remaining_original_indices,
                remaining_chunks=remaining_chunks,
                remaining_document_ids=remaining_document_ids,
                remaining_chunk_ids=remaining_chunk_ids,
                remaining_chunk_contexts=remaining_chunk_contexts,
                new_run=new_run,
                task_id=task_id,
                task_manager=task_manager,
                container=container,
            )

        from ..jobs import enqueue
        def scoped_build_task():
            with _gb.workspace_credential_context_for_run(new_run["run_id"]):
                build_task()

        enqueue("graph_build", scoped_build_task, run_id=new_run["run_id"])

    return {"run_id": new_run["run_id"], "task_id": task_id, "status": "processing"}
