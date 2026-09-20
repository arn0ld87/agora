"""
Service for building graphs and generating ontologies.
"""

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from ..config import Config
from ..contracts.ai_provider_contract import AiModelRef
from ..services.degradation_collector import ChunkExtractionTally, DegradationCollector
from ..services.graph_build_checkpoint import (
    GraphBuildCheckpoint,
    clear_checkpoint,
    resume_capability_for_checkpoint,
    save_checkpoint,
)
from ..services.ontology_generator import OntologyGenerator
from ..services.llm_routing_seed import resolve_route_api_key, seed_run_stage_routing
from ..services.stage_model_router import StageModelRouter
from ..services.text_processor import TextProcessor
from ..storage.ner_extractor import NERExtractor
from ..utils.artifact_locator import ArtifactLocator
from ..utils.file_parser import split_text_into_chunks_with_documents
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from ..models.task import TaskManager, TaskStatus
from ..models.project import Project, ProjectManager, ProjectStatus
from ..services.run_registry import RunRegistry
from ..services.secret_resolver import SecretResolver
from ..utils.api_errors import ApiErrorCode

logger = get_logger('agora.graph_build_service')
run_registry = RunRegistry()
AI_MODEL_REF_ROUTING_FAILURE_MESSAGE = "ai_model_ref routing could not be finalized"
AI_MODEL_REF_GENERATION_FAILURE_MESSAGE = "ontology generation could not be completed"


class AiModelRefPostValidationError(RuntimeError):
    """Safe boundary error for synchronous AiModelRef operational failures."""


class AiModelRefRoutingInputError(ValueError):
    """Identify ValueErrors raised directly by AiModelRef route seeding.

    Public boundary type: the API layer maps *only* this subtype to the
    ai_model_ref routing validation response (400). Every other ``ValueError``
    keeps its semantic error code, so unrelated failures such as
    ``ONTOLOGY_MISSING`` or ``NOT_FOUND`` are no longer mislabeled as routing
    problems.
    """


@contextmanager
def _classify_ai_model_ref_seed_error(
    ai_model_ref: AiModelRef | None,
) -> Iterator[None]:
    try:
        yield
    except ValueError:
        if ai_model_ref is not None:
            raise AiModelRefRoutingInputError from None
        raise


@contextmanager
def _terminalize_ai_model_ref_sync_failure(
    *,
    ai_model_ref: AiModelRef | None,
    project: Project,
    run_id: str,
    phase: str,
    failure_message: str = AI_MODEL_REF_ROUTING_FAILURE_MESSAGE,
    task_manager: TaskManager | None = None,
    task_id_getter: Callable[[], str | None] | None = None,
) -> Iterator[None]:
    try:
        yield
    except Exception as exc:
        if ai_model_ref is not None:
            task_id = task_id_getter() if task_id_getter is not None else None
            logger.warning(
                "AiModelRef synchronous graph operation failed "
                "[project_id=%s, run_id=%s, task_id=%s, phase=%s, error_type=%s]",
                project.project_id,
                run_id,
                task_id,
                phase,
                type(exc).__name__,
            )
            if task_id is not None and task_manager is not None:
                task_manager.fail_task(task_id, failure_message)
            project.status = ProjectStatus.FAILED
            project.error = failure_message
            # Projektstatus zuerst persistieren: schlägt das Registry-I/O fehl,
            # darf der FAILED-Zustand nicht nur im Speicher stehen, während auf
            # Platte weiterhin GRAPH_BUILDING/CREATED klebt.
            ProjectManager.save_project(project)
            try:
                run_registry.update_run(
                    run_id,
                    status="failed",
                    message=failure_message,
                    error=failure_message,
                )
            except Exception:  # noqa: BLE001 — Terminalisierung darf nicht am Registry-I/O scheitern
                logger.exception(
                    "run_registry.update_run failed during terminalization [run_id=%s]",
                    run_id,
                )
            if isinstance(exc, TimeoutError):
                raise TimeoutError from None
            if not isinstance(exc, AiModelRefRoutingInputError):
                raise AiModelRefPostValidationError from None
        raise


class GraphBuildService:
    @staticmethod
    def chunk_project_text(
        project_id: str,
        text: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> tuple[list[str], list[str | None] | None, list[int | None] | None, bool]:
        """Zerlegt den extrahierten Text eines Projekts deterministisch in Chunks.

        Ausgelagert aus ``build_task`` (Issue #1472b): ein Resume-Versuch
        (``api/runs.py::_resume_graph_build``) muss GENAU dieselbe
        Chunk-Zerlegung reproduzieren wie der Original-Lauf, dessen
        Checkpoint er fortsetzt — sonst zeigt ein Chunk-Index nach einem
        Resume auf ein anderes Textstück als beim Original-Lauf. Eine
        zweite, unabhängig gepflegte Kopie dieser Verzweigung wäre genau
        die Drift-Quelle, die das verhindern soll.

        Projekte mit Dokument-Manifest-Sidecar (Issue #1152) chunken über
        den dokument-verankerten Pfad (liefert ``document_ids``/
        ``chunk_ids``); Altprojekte ohne Sidecar nehmen den bisherigen
        Pfad — beides unverändert gegenüber dem vorherigen Inline-Code.

        Returns:
            ``(chunks, document_ids, chunk_ids, manifest_anchored)``.
        """
        manifest = ProjectManager.get_document_manifest(project_id)
        if manifest is not None:
            anchored_chunks = split_text_into_chunks_with_documents(
                text, manifest, chunk_size=chunk_size, overlap=chunk_overlap
            )
            chunks = [c.text for c in anchored_chunks]
            document_ids = [c.document_id for c in anchored_chunks]
            chunk_ids = [c.chunk_id for c in anchored_chunks]
            return chunks, document_ids, chunk_ids, True

        chunks = TextProcessor.split_text(text, chunk_size=chunk_size, overlap=chunk_overlap)
        # Bewusst ``None`` (nicht ``[None] * len(chunks)``) — identisch zum
        # vorherigen Inline-Code, byte-genau dasselbe Argument, mit dem
        # ``add_text_batches`` schon immer für Altprojekte ohne Sidecar
        # aufgerufen wurde. ``resume_graph_build`` normalisiert diesen Fall
        # selbst auf eine indexierbare Liste, wo es das für den Chunk-Skip
        # braucht — kein Grund, den etablierten Aufruf-Vertrag hier zu
        # ändern.
        return chunks, None, None, False

    @classmethod
    def generate_ontology(
        cls,
        project_id,
        simulation_requirement,
        document_texts,
        llm_model_override=None,
        llm_runtime=None,
        llm_profile_id=None,
        additional_context=None,
        ai_model_ref: AiModelRef | None = None,
    ):
        """
        Generate an ontology for a project from its documents and simulation requirements.
        
        Parameters:
            project_id: Identifier of the project to update.
            simulation_requirement: Requirements that guide ontology generation.
            document_texts: Source documents used to generate the ontology.
            llm_model_override: Optional model override for the generation run.
            llm_runtime: Optional runtime configuration for the language model.
            llm_profile_id: Optional language model profile identifier recorded on the project.
            additional_context: Optional context supplied to the ontology generator.
            ai_model_ref: Canonical (provider connection, model) reference chosen in
                the UI. When set it is authoritative and suppresses every legacy
                override (``llm_model_override``, ``llm_runtime``, ``llm_profile_id``
                are forced to ``None``); it is persisted on the project so a resumed
                graph build keeps the binding.

        Returns:
            The project updated with the generated ontology and analysis summary.

        Raises:
            ValueError: If the project does not exist.
            AiModelRefRoutingInputError: If route seeding rejects the ``ai_model_ref``
                (unknown/disabled connection, model not in the catalog).
            AiModelRefPostValidationError: If a non-routing failure occurs after the
                route was sealed; project and run are terminalized first and the raw
                error is not propagated.
            TimeoutError: If a synchronous step times out; states are terminalized
                before the timeout is re-raised.
        """
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(ApiErrorCode.NOT_FOUND)

        effective_model_override = None if ai_model_ref is not None else llm_model_override
        effective_llm_runtime = None if ai_model_ref is not None else llm_runtime
        effective_profile_id = None if ai_model_ref is not None else llm_profile_id

        run_record = run_registry.create_run(
            run_type="ontology_generate",
            entity_id=project.project_id,
            status="processing",
            progress=0,
            message="Ontology generation started",
            linked_ids={"project_id": project.project_id},
        )
        run_id = run_record["run_id"]
        # Routing-Phase: nur hier ist ein Fehler tatsächlich ein
        # ai_model_ref-Routingproblem und darf als solches terminalisiert und
        # nach außen als 400 klassifiziert werden.
        with _terminalize_ai_model_ref_sync_failure(
            ai_model_ref=ai_model_ref,
            project=project,
            run_id=run_id,
            phase="ontology_routing",
        ):
            for stage_id in ("document_ingest", "ontology_generation"):
                with _classify_ai_model_ref_seed_error(ai_model_ref):
                    seed_run_stage_routing(
                        run_id,
                        stage_id,
                        llm_model_override=effective_model_override,
                        llm_runtime=effective_llm_runtime,
                        llm_profile_id=effective_profile_id,
                        ai_model_ref=ai_model_ref,
                    )
            route_router = StageModelRouter(run_id)
            ingest_route = route_router.resolve("document_ingest")
            route_router.lock_stage("document_ingest", ingest_route)
            ontology_route = route_router.resolve("ontology_generation")
            route_router.lock_stage("ontology_generation", ontology_route)

        # Generierungs-/Persistenzphase: Fehler werden weiterhin terminalisiert
        # und sanitisiert, tragen aber eine eigene, nicht-routingbezogene
        # Meldung, damit Routingfehler unterscheidbar bleiben.
        with _terminalize_ai_model_ref_sync_failure(
            ai_model_ref=ai_model_ref,
            project=project,
            run_id=run_id,
            phase="ontology_generation",
            failure_message=AI_MODEL_REF_GENERATION_FAILURE_MESSAGE,
        ):
            # The locked ontology route is authoritative; profile IDs are metadata only.
            llm_client = LLMClient.from_route(
                ontology_route,
                secret_resolver=SecretResolver(),
                api_key_override=resolve_route_api_key(ontology_route, effective_llm_runtime),
                run_id=run_id,
            )
            logger.info(
                "Calling LLM to generate ontology definition (model=%s, provider=%s) [project_id=%s, run_id=%s]",
                llm_client.model,
                ontology_route.provider_id,
                project_id,
                run_id
            )

            generator = OntologyGenerator(llm_client=llm_client)
            ontology = generator.generate(
                document_texts=document_texts,
                simulation_requirement=simulation_requirement,
                additional_context=additional_context
            )

            project.ontology = {
                "entity_types": ontology.get("entity_types", []),
                "edge_types": ontology.get("edge_types", [])
            }
            project.analysis_summary = ontology.get("analysis_summary", "")
            project.status = ProjectStatus.ONTOLOGY_GENERATED
            project.llm_model = effective_model_override
            project.llm_provider = effective_llm_runtime.redacted_metadata() if effective_llm_runtime else None
            project.llm_profile_id = effective_profile_id
            # Kanonische Referenz persistieren: auf dem ai_model_ref-Pfad sind
            # alle Legacy-Felder None, ein wiederaufgenommener Build hätte sonst
            # keinerlei Modell-/Connection-Bindung mehr (#900).
            project.ai_model_ref = (
                ai_model_ref.model_dump(mode="json") if ai_model_ref is not None else None
            )
            ProjectManager.save_project(project)

            run_registry.update_run(
                run_id,
                status="completed",
                progress=100,
                message="Ontology generation completed",
                linked_ids={"project_id": project.project_id},
            )
        return project

    @classmethod
    def build_graph(
        cls,
        project_id,
        graph_name,
        llm_model_override=None,
        llm_runtime=None,
        llm_profile_id=None,
        force=False,
        chunk_size=None,
        chunk_overlap=None,
        container=None,
        ai_model_ref: AiModelRef | None = None,
    ):
        """
        Queue a graph build for a project using its extracted text and ontology.
        
        Parameters:
            project_id: Identifier of the project to build.
            graph_name: Name assigned to the new graph.
            llm_model_override: Optional model override for graph processing.
            llm_runtime: Optional runtime configuration for the language model.
            llm_profile_id: Optional language model profile identifier.
            force: Whether to restart a graph build already in progress.
            chunk_size: Optional text chunk size.
            chunk_overlap: Optional overlap between consecutive text chunks.
            container: Service container used to create the graph builder.
            ai_model_ref: Canonical (provider connection, model) reference. When set
                it is authoritative and suppresses every legacy override. When absent
                and the request carries no legacy route either, a reference persisted
                on the project by the ontology run is used instead.

        Returns:
            A tuple containing the task identifier and run identifier.

        Raises:
            ValueError: If the project, extracted text, or ontology is missing, or if
                the project has not completed ontology generation.
            RuntimeError: If a graph build is already in progress and `force` is false.
            AiModelRefRoutingInputError: If route seeding rejects the ``ai_model_ref``.
            AiModelRefPostValidationError: If a non-routing failure occurs after the
                route was sealed; project, run and task are terminalized first and the
                raw error is not propagated.
            TimeoutError: If a synchronous step times out; states are terminalized
                before the timeout is re-raised.
        """
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(ApiErrorCode.NOT_FOUND)

        # State check
        if project.status == ProjectStatus.CREATED:
            raise ValueError(ApiErrorCode.ONTOLOGY_MISSING)

        if project.status == ProjectStatus.GRAPH_BUILDING and not force:
            raise RuntimeError(ApiErrorCode.GRAPH_BUILD_IN_PROGRESS)

        if force:
            project.status = ProjectStatus.ONTOLOGY_GENERATED
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
                ai_model_ref = AiModelRef.model_validate(project.ai_model_ref)
            except Exception:  # noqa: BLE001 — defekte Persistenz darf den Legacy-Pfad nicht blockieren
                logger.warning(
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
        chunk_size = chunk_size or project.chunk_size or Config.DEFAULT_CHUNK_SIZE
        chunk_overlap = chunk_overlap or project.chunk_overlap or Config.DEFAULT_CHUNK_OVERLAP
        project.chunk_size = chunk_size
        project.chunk_overlap = chunk_overlap

        text = ProjectManager.get_extracted_text(project_id)
        if not text:
            raise ValueError("Extracted text not found")

        ontology = project.ontology
        if not ontology:
            raise ValueError("Ontology definition not found")

        task_manager = TaskManager()
        run_record = run_registry.create_run(
            run_type="graph_build",
            entity_id=project_id,
            status="pending",
            progress=0,
            message="Graph build queued",
            linked_ids={"project_id": project_id},
            artifacts=ArtifactLocator.existing_paths({
                "project_dir": ProjectManager._get_project_dir(project_id),
            }),
            resume_capability={"available": True, "action": "restart", "label": "Restart graph build"},
            metadata={"graph_name": graph_name},
        )
        task_id: str | None = None
        with _terminalize_ai_model_ref_sync_failure(
            ai_model_ref=ai_model_ref,
            project=project,
            run_id=run_record["run_id"],
            phase="graph_build_enqueue",
            task_manager=task_manager,
            task_id_getter=lambda: task_id,
        ):
            task_id = task_manager.create_task(
                f"Build graph: {graph_name}",
                metadata={"project_id": project_id, "run_id": run_record["run_id"]}
            )
            project.status = ProjectStatus.GRAPH_BUILDING
            project.graph_build_task_id = task_id
            ProjectManager.save_project(project)

            with _classify_ai_model_ref_seed_error(ai_model_ref):
                seed_run_stage_routing(
                    run_record["run_id"],
                    "graph_build",
                    llm_model_override=effective_model_override,
                    llm_runtime=effective_llm_runtime,
                    llm_profile_id=effective_profile_id,
                    ai_model_ref=ai_model_ref,
                )
            route_router = StageModelRouter(run_record["run_id"])
            resolved_route = route_router.resolve("graph_build")
            route_router.lock_stage("graph_build", resolved_route)

            # The locked route is authoritative; legacy profile IDs must not replace it.
            ner_llm_client = LLMClient.from_route(
                resolved_route,
                secret_resolver=SecretResolver(),
                api_key_override=resolve_route_api_key(resolved_route, effective_llm_runtime),
                run_id=run_record["run_id"],
            )
            logger.info(
                "Build-Pfad nutzt Route-Snapshot: model=%s provider=%s [project_id=%s, run_id=%s]",
                ner_llm_client.model,
                resolved_route.provider_id,
                project_id,
                run_record["run_id"]
            )
            ner_override = NERExtractor(llm_client=ner_llm_client)

            def build_task():
                """
                Builds the project's graph and records its completion or failure state.

                On failure, marks the project, task, and run as failed and attempts to clean up any
                partially created graph.
                """
                build_logger = get_logger('agora.build')
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
                degradations = DegradationCollector()
                extraction_tally = ChunkExtractionTally()
                # Issue #1472b: haelt den jeweils aktuellsten, bereits auf
                # Platte geschriebenen Checkpoint — eine Ein-Element-Liste
                # statt einer einfachen Variable, damit sowohl der innere
                # Callback als auch ``_finish_cancelled_build`` (weiter unten
                # definiert, per Closure) denselben veraenderlichen Zustand
                # sehen, ohne ``nonlocal`` ueber mehrere Funktionsgrenzen
                # hinweg zu brauchen.
                checkpoint_holder: "list[GraphBuildCheckpoint | None]" = [None]

                def _finish_cancelled_build(cancelled_episode_uuids: "list[str]") -> None:
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
                        project.status = ProjectStatus.GRAPH_INCOMPLETE
                        ProjectManager.save_project(project)
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
                        run_registry.update_run(
                            run_record["run_id"],
                            status="stopped",
                            termination_reason="user_cancel",
                            message=(
                                "Vom Nutzer abgebrochen — bereits geschriebene Entitäten "
                                "und Relationen bleiben im Graphen erhalten, der Graph "
                                "gilt als unvollständig"
                            ),
                            artifacts=ArtifactLocator.existing_paths({
                                "project_dir": ProjectManager._get_project_dir(project_id),
                            }),
                            # Issue #1472b: "resume" nur, wenn der Checkpoint
                            # tatsächlich mindestens einen fertigen Chunk
                            # trägt — sonst bleibt es beim ehrlichen "restart".
                            resume_capability=resume_capability_for_checkpoint(
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

                try:
                    task_manager.update_task(task_id, status=TaskStatus.PROCESSING, message="Initializing graph build service...")
                    builder = container.graph_builder()

                    # Issue #1472b: ein frischer Build (erster Versuch ODER
                    # ``force``-Restart) startet ohne verwertbaren Checkpoint
                    # — ein liegen gebliebener Checkpoint eines VORHERIGEN,
                    # anderen Graphen darf hier nicht fälschlich anschlagen.
                    # Der eigentliche Resume-Pfad läuft nie über
                    # ``build_task``, sondern über
                    # ``api/runs.py::_resume_graph_build``.
                    clear_checkpoint(project_id)

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

                    run_registry.update_run(
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
                            progress_detail={"batch_count": completed, "total_batches": total, "batch_at": time.time()}
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
                            current = GraphBuildCheckpoint(
                                graph_id=graph_id,
                                total_chunks=len(chunks),
                                chunk_size=chunk_size,
                                chunk_overlap=chunk_overlap,
                                manifest_anchored=manifest_anchored,
                                updated_at=datetime.now(UTC),
                            )
                        updated = current.with_completed_chunk(idx, episode_uuid)
                        save_checkpoint(project_id, updated)
                        checkpoint_holder[0] = updated

                    # Checkpoint (Issue B2): zwischen Ontologie-Setzen und dem
                    # eigentlichen (potenziell langen) Chunk-Durchlauf. Noch
                    # keine Episode geschrieben — der Cancel-Pfad bekommt eine
                    # leere Liste.
                    from ..services.sim.cancel_flag import is_cancel_requested
                    if is_cancel_requested(run_record["run_id"]):
                        _finish_cancelled_build([])
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
                        )
                    except GraphBuildCancelled as cancel_exc:
                        _finish_cancelled_build(cancel_exc.episode_uuids)
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
                    project.status = ProjectStatus.GRAPH_COMPLETED
                    ProjectManager.save_project(project)
                    # Issue #1472b: ein abgeschlossener Graph hat nichts mehr
                    # zum Fortsetzen — ein stehen gebliebener Checkpoint
                    # würde nur einen künftigen, unverwandten Build-Versuch
                    # verwirren.
                    clear_checkpoint(project_id)

                    task_manager.update_task(
                        task_id, status=TaskStatus.COMPLETED, message="Graph build completed", progress=100,
                        result={
                            "project_id": project_id,
                            "graph_id": graph_id,
                            "node_count": graph_data.get("node_count", 0),
                            "edge_count": graph_data.get("edge_count", 0),
                            # Leere Liste heißt „nichts ist still ausgefallen“.
                            "degradations": degradation_payload,
                        }
                    )
                    run_registry.update_run(run_record["run_id"], status="completed", progress=100, message="Graph build completed")

                except Exception as exc:
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
                                logger.debug("graph_build: mark_graph_failed also failed, ignoring: %s", err)

                    project.status = ProjectStatus.FAILED
                    project.error = str(exc)
                    ProjectManager.save_project(project)

                    import traceback
                    task_manager.update_task(task_id, status=TaskStatus.FAILED, message=f"Build failed: {str(exc)}", error=traceback.format_exc())
                    run_registry.update_run(
                        run_record["run_id"],
                        status="failed",
                        message=str(exc),
                        error=str(exc),
                        # Issue #1472b: "resume" nur, wenn der Checkpoint bis
                        # zum Fehlschlag mindestens einen Chunk verzeichnet
                        # hat — sonst bleibt der sticky Default aus der
                        # Run-Anlage ("restart") stehen.
                        resume_capability=resume_capability_for_checkpoint(checkpoint_holder[0]),
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

            from ..jobs import enqueue
            # run_id: Issue #1472 — siehe simulation_prepare.
            enqueue("graph_build", build_task, run_id=run_record["run_id"])
        return task_id, run_record["run_id"]

    @classmethod
    def resume_graph_build(
        cls,
        *,
        project_id: str,
        parent_run_id: str,
        checkpoint: GraphBuildCheckpoint,
        chunks: list[str],
        # Wie in ``GraphBuilderService.add_text_batches``: beide Listen sind
        # optional, und ihre Elemente duerfen einzeln ``None`` sein (ein
        # Chunk ohne Dokument-/Chunk-Provenance).
        document_ids: list[str | None] | None,
        chunk_ids: list[int | None] | None,
        container,
    ) -> dict:
        """Setzt einen unterbrochenen ``graph_build`` anhand eines Checkpoints fort
        (Issue #1472b).

        Verarbeitet ausschließlich die Chunks, deren Index NICHT in
        ``checkpoint.completed_chunk_indices`` steht — bereits committete
        Episoden/Entities/Relations werden nicht erneut geschrieben (Neo4j
        MERGEt Episode- und Relation-Knoten über eine je Aufruf frisch
        generierte UUID; ein erneuter Durchlauf bereits fertiger Chunks
        würde also Dubletten erzeugen statt sie zu deduplizieren — siehe
        ``storage/neo4j_write.py``).

        Bewusst kein ``builder.create_graph(...)`` — der Checkpoint trägt
        den ``graph_id`` des unterbrochenen Versuchs, in den
        weitergeschrieben wird. Wie ``api/runs.py::_restart_graph_build``
        bewusst ohne Route-Locking, NER-Override und
        Degradation-Sammlung (dieselbe Vereinfachung, die der bestehende
        Restart-Pfad bereits trägt) — kein Feature-Ausbau in diesem Slice.

        Aufrufer (``api/runs.py::_resume_graph_build``) validiert
        Projekt/Ontologie/Container-Verfügbarkeit bereits vor dem Aufruf
        und übergibt die für DIESEN Checkpoint passende Chunk-Zerlegung
        (``chunk_project_text`` — dieselbe Methode wie beim
        Original-Build).
        """
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(ApiErrorCode.NOT_FOUND)
        ontology = project.ontology
        if not ontology:
            raise ValueError("Ontology definition not found")

        graph_id = checkpoint.graph_id
        completed_indices = set(checkpoint.completed_chunk_indices)
        # Reihenfolge stabil halten (nicht die Set-Iterationsreihenfolge) —
        # ``remaining_original_indices[local_idx]`` übersetzt die Position
        # innerhalb der REDUZIERTEN Liste zurück auf den ursprünglichen,
        # checkpoint-relevanten Chunk-Index.
        remaining_original_indices = [
            idx for idx in range(len(chunks)) if idx not in completed_indices
        ]
        remaining_chunks = [chunks[idx] for idx in remaining_original_indices]
        # ``document_ids``/``chunk_ids`` sind optional (ein Lauf ohne
        # Provenance uebergibt ``None``, siehe ``add_text_batches``). Ohne
        # diese Fallunterscheidung waere ein Resume genau dort mit einem
        # TypeError gestorben, wo er am noetigsten ist.
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

        from .run_lifecycle import RunLifecycle

        # Issue #1183: Anlage-Fenster hinter RunLifecycle — jeder Abbruch bis
        # zum Job-Start markiert den Run als failed statt ihn pending zu
        # verwaisen (dieselbe Invariante wie ``build_graph``/``_restart_graph_build``).
        with RunLifecycle.begin(
            run_registry,
            "graph_build",
            project_id,
            parent_run_id=parent_run_id,
            failure_message="Graph build resume failed: {exc_type}",
            progress=int(100 * len(completed_indices) / len(chunks)) if chunks else 0,
            message="Graph build resume queued",
            linked_ids={"project_id": project_id, "graph_id": graph_id},
            artifacts=ArtifactLocator.existing_paths({
                "project_dir": ProjectManager._get_project_dir(project_id),
            }),
            resume_capability={"available": True, "action": "resume", "label": "Resume graph build"},
            metadata={"graph_name": project.name or "Agora Graph"},
        ) as lifecycle:
            new_run = lifecycle.record
            task_manager = TaskManager()
            task_id = task_manager.create_task(
                f"Resume graph build: {project.name or graph_id}",
                metadata={"project_id": project_id, "run_id": new_run["run_id"]},
            )
            lifecycle.attach_task(task_manager, task_id)
            project.status = ProjectStatus.GRAPH_BUILDING
            project.graph_build_task_id = task_id
            ProjectManager.save_project(project)

            checkpoint_holder = [checkpoint]

            def record_checkpoint(local_idx: int, episode_uuid: str) -> None:
                original_idx = remaining_original_indices[local_idx]
                updated = checkpoint_holder[0].with_completed_chunk(original_idx, episode_uuid)
                save_checkpoint(project_id, updated)
                checkpoint_holder[0] = updated

            def _finish_cancelled_resume(episode_uuids: list) -> None:
                build_logger = logger
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
                    project.status = ProjectStatus.GRAPH_INCOMPLETE
                    ProjectManager.save_project(project)
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
                    run_registry.update_run(
                        new_run["run_id"],
                        status="stopped",
                        termination_reason="user_cancel",
                        message=(
                            "Vom Nutzer abgebrochen — bereits geschriebene Entitäten "
                            "und Relationen bleiben im Graphen erhalten, der Graph "
                            "gilt als unvollständig"
                        ),
                        artifacts=ArtifactLocator.existing_paths({
                            "project_dir": ProjectManager._get_project_dir(project_id),
                        }),
                        resume_capability=resume_capability_for_checkpoint(checkpoint_holder[0]),
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

            def build_task():
                builder = None
                try:
                    task_manager.update_task(task_id, status=TaskStatus.PROCESSING, message="Resuming graph build...")
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
                            _finish_cancelled_resume([])
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
                            )
                        except GraphBuildCancelled as cancel_exc:
                            _finish_cancelled_resume(cancel_exc.episode_uuids)
                            return
                    # else: der komplette Rest war bereits vor diesem
                    # Resume-Versuch fertig — direkt zum Qualitätsgate.

                    task_manager.update_task(task_id, message="Retrieving graph data...", progress=95)
                    graph_data = builder.get_graph_data(graph_id)
                    builder.mark_graph_completed(graph_id)
                    project.status = ProjectStatus.GRAPH_COMPLETED
                    project.graph_id = graph_id
                    ProjectManager.save_project(project)
                    # Issue #1472b: fertig — kein Checkpoint mehr zum Fortsetzen.
                    clear_checkpoint(project_id)

                    task_manager.update_task(
                        task_id,
                        status=TaskStatus.COMPLETED,
                        message="Graph build completed",
                        progress=100,
                        result={
                            "project_id": project_id,
                            "graph_id": graph_id,
                            "node_count": graph_data.get("node_count", 0),
                            "edge_count": graph_data.get("edge_count", 0),
                            "chunk_count": len(chunks),
                            "resumed_chunk_count": len(checkpoint.completed_chunk_indices),
                        },
                    )
                    run_registry.update_run(
                        new_run["run_id"],
                        status="completed",
                        progress=100,
                        message="Graph build completed",
                        artifacts=ArtifactLocator.existing_paths({
                            "project_dir": ProjectManager._get_project_dir(project_id),
                        }),
                    )
                except Exception as exc:  # noqa: BLE001 — exception reported to task/run registry
                    project.status = ProjectStatus.FAILED
                    project.error = str(exc)
                    ProjectManager.save_project(project)
                    import traceback
                    task_manager.update_task(
                        task_id,
                        status=TaskStatus.FAILED,
                        message=f"Build failed: {exc}",
                        error=traceback.format_exc(),
                    )
                    run_registry.update_run(
                        new_run["run_id"],
                        status="failed",
                        message=str(exc),
                        error=str(exc),
                        resume_capability=resume_capability_for_checkpoint(checkpoint_holder[0]),
                    )

            from ..jobs import enqueue
            enqueue("graph_build", build_task, run_id=new_run["run_id"])

        return {"run_id": new_run["run_id"], "task_id": task_id, "status": "processing"}
