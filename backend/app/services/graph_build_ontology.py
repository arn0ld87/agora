"""
Ontology generation and text chunking helpers for graph build service.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from ..contracts.ai_provider_contract import AiModelRef
from ..utils.api_errors import ApiErrorCode

if TYPE_CHECKING:
    from ..models.project import Project
    from ..models.task import TaskManager


def _ontology_completion_message(generator: object) -> str:
    """Abschlussmeldung der Ontologie-Generierung samt sichtbaren Warnungen.

    Issue #1759 (B1): Deklariert der Generator keinen Streitgegenstand-Typ,
    steht das in der Run-Meldung statt still zu verschwinden.
    """
    from . import graph_build as _gb

    base = "Ontology generation completed"
    degradations = getattr(generator, "degradations", None)
    if not isinstance(degradations, _gb.DegradationCollector) or not degradations:
        return base
    details = "; ".join(event.detail for event in degradations.report().events)
    return f"{base} (Warnung: {details})"


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
    failure_message: str | None = None,
    task_manager: TaskManager | None = None,
    task_id_getter: Callable[[], str | None] | None = None,
) -> Iterator[None]:
    from . import graph_build as _gb

    effective_failure_message = (
        failure_message or _gb.AI_MODEL_REF_ROUTING_FAILURE_MESSAGE
    )

    try:
        yield
    except Exception as exc:
        if ai_model_ref is not None:
            task_id = task_id_getter() if task_id_getter is not None else None
            _gb.logger.warning(
                "AiModelRef synchronous graph operation failed "
                "[project_id=%s, run_id=%s, task_id=%s, phase=%s, error_type=%s]",
                project.project_id,
                run_id,
                task_id,
                phase,
                type(exc).__name__,
            )
            if task_id is not None and task_manager is not None:
                task_manager.fail_task(task_id, effective_failure_message)
            project.status = _gb.ProjectStatus.FAILED
            project.error = effective_failure_message
            # Projektstatus zuerst persistieren: schlägt das Registry-I/O fehl,
            # darf der FAILED-Zustand nicht nur im Speicher stehen, während auf
            # Platte weiterhin GRAPH_BUILDING/CREATED klebt.
            _gb.ProjectManager.save_project(project)
            try:
                _gb.run_registry.update_run(
                    run_id,
                    status="failed",
                    message=effective_failure_message,
                    error=effective_failure_message,
                )
            except Exception:  # noqa: BLE001 — Terminalisierung darf nicht am Registry-I/O scheitern
                _gb.logger.exception(
                    "run_registry.update_run failed during terminalization [run_id=%s]",
                    run_id,
                )
            if isinstance(exc, TimeoutError):
                raise TimeoutError from None
            if not isinstance(exc, AiModelRefRoutingInputError):
                raise AiModelRefPostValidationError from None
        raise


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
    from . import graph_build as _gb

    manifest = _gb.ProjectManager.get_document_manifest(project_id)
    if manifest is not None:
        anchored_chunks = _gb.split_text_into_chunks_with_documents(
            text, manifest, chunk_size=chunk_size, overlap=chunk_overlap
        )
        chunks = [c.text for c in anchored_chunks]
        document_ids = [c.document_id for c in anchored_chunks]
        chunk_ids = [c.chunk_id for c in anchored_chunks]
        return chunks, document_ids, chunk_ids, True

    chunks = _gb.TextProcessor.split_text(text, chunk_size=chunk_size, overlap=chunk_overlap)
    return chunks, None, None, False


def generate_ontology(
    project_id: str,
    simulation_requirement: Any,
    document_texts: Any,
    llm_model_override: Any = None,
    llm_runtime: Any = None,
    llm_profile_id: Any = None,
    additional_context: Any = None,
    ai_model_ref: AiModelRef | None = None,
) -> Any:
    """Generate an ontology for a project from its documents and simulation requirements."""
    from . import graph_build as _gb

    project = _gb.ProjectManager.get_project(project_id)
    if not project:
        raise ValueError(ApiErrorCode.NOT_FOUND)

    effective_model_override = None if ai_model_ref is not None else llm_model_override
    effective_llm_runtime = None if ai_model_ref is not None else llm_runtime
    effective_profile_id = None if ai_model_ref is not None else llm_profile_id

    run_record = _gb.run_registry.create_run(
        run_type="ontology_generate",
        entity_id=project.project_id,
        status="processing",
        progress=0,
        message="Ontology generation started",
        linked_ids={"project_id": project.project_id},
        metadata=_gb.workspace_credential_metadata(),
    )
    run_id = run_record["run_id"]
    with _terminalize_ai_model_ref_sync_failure(
        ai_model_ref=ai_model_ref,
        project=project,
        run_id=run_id,
        phase="ontology_routing",
    ):
        for stage_id in ("document_ingest", "ontology_generation"):
            with _classify_ai_model_ref_seed_error(ai_model_ref):
                _gb.seed_run_stage_routing(
                    run_id,
                    stage_id,
                    llm_model_override=effective_model_override,
                    llm_runtime=effective_llm_runtime,
                    llm_profile_id=effective_profile_id,
                    ai_model_ref=ai_model_ref,
                )
        route_router = _gb.StageModelRouter(run_id)
        ingest_route = route_router.resolve("document_ingest")
        route_router.lock_stage("document_ingest", ingest_route)
        ontology_route = route_router.resolve("ontology_generation")
        route_router.lock_stage("ontology_generation", ontology_route)

    with _terminalize_ai_model_ref_sync_failure(
        ai_model_ref=ai_model_ref,
        project=project,
        run_id=run_id,
        phase="ontology_generation",
        failure_message=_gb.AI_MODEL_REF_GENERATION_FAILURE_MESSAGE,
    ):
        llm_client = _gb.LLMClient.from_route(
            ontology_route,
            secret_resolver=_gb.SecretResolver(),
            api_key_override=_gb.resolve_route_api_key(ontology_route, effective_llm_runtime),
            run_id=run_id,
        )
        _gb.logger.info(
            "Calling LLM to generate ontology definition (model=%s, provider=%s) [project_id=%s, run_id=%s]",
            llm_client.model,
            ontology_route.provider_id,
            project_id,
            run_id,
        )

        generator = _gb.OntologyGenerator(llm_client=llm_client)
        ontology = generator.generate(
            document_texts=document_texts,
            simulation_requirement=simulation_requirement,
            additional_context=additional_context,
        )

        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", []),
        }
        project.analysis_summary = ontology.get("analysis_summary", "")
        project.status = _gb.ProjectStatus.ONTOLOGY_GENERATED
        project.llm_model = effective_model_override
        project.llm_provider = effective_llm_runtime.redacted_metadata() if effective_llm_runtime else None
        project.llm_profile_id = effective_profile_id
        project.ai_model_ref = (
            ai_model_ref.model_dump(mode="json") if ai_model_ref is not None else None
        )
        _gb.ProjectManager.save_project(project)

        _gb.run_registry.update_run(
            run_id,
            status="completed",
            progress=100,
            message=_ontology_completion_message(generator),
            linked_ids={"project_id": project.project_id},
        )
    return project
