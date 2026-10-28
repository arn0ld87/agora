"""
Service for building graphs and generating ontologies.
"""

from collections.abc import Callable, Iterator  # noqa: F401
from contextlib import contextmanager  # noqa: F401
from datetime import UTC, datetime  # noqa: F401
import time  # noqa: F401

from ..config import Config  # noqa: F401
from ..contracts.ai_provider_contract import AiModelRef
from ..models.project import Project, ProjectManager, ProjectStatus  # noqa: F401
from ..models.task import TaskManager, TaskStatus  # noqa: F401
from ..services.degradation_collector import (
    ChunkExtractionTally,  # noqa: F401
    DegradationCollector,  # noqa: F401
)
from ..services.graph_build_checkpoint import (
    GraphBuildCheckpoint,
    clear_checkpoint,  # noqa: F401
    resume_capability_for_checkpoint,  # noqa: F401
    save_checkpoint,  # noqa: F401
)
from ..services.llm_routing_seed import (
    resolve_route_api_key,  # noqa: F401
    seed_run_stage_routing,  # noqa: F401
    workspace_credential_context_for_run,  # noqa: F401
    workspace_credential_metadata,  # noqa: F401
)
from ..services.ontology_generator import OntologyGenerator  # noqa: F401
from ..services.run_registry import RunRegistry
from ..services.secret_resolver import SecretResolver  # noqa: F401
from ..services.stage_model_router import StageModelRouter  # noqa: F401
from ..services.text_processor import TextProcessor  # noqa: F401
from ..storage.ner_chunk_context import build_chunk_contexts  # noqa: F401
from ..storage.ner_extractor import NERExtractor  # noqa: F401
from ..utils.api_errors import ApiErrorCode  # noqa: F401
from ..utils.artifact_locator import ArtifactLocator  # noqa: F401
from ..utils.file_parser import split_text_into_chunks_with_documents  # noqa: F401
from ..utils.llm_client import LLMClient  # noqa: F401
from ..utils.logger import get_logger
from .graph_build_ontology import (
    AiModelRefPostValidationError,  # noqa: F401
    AiModelRefRoutingInputError,  # noqa: F401
    _classify_ai_model_ref_seed_error,  # noqa: F401
    _ontology_completion_message,  # noqa: F401
    _terminalize_ai_model_ref_sync_failure,  # noqa: F401
    chunk_project_text as _chunk_project_text,
    generate_ontology as _generate_ontology,
)

logger = get_logger('agora.graph_build_service')
run_registry = RunRegistry()
AI_MODEL_REF_ROUTING_FAILURE_MESSAGE = "ai_model_ref routing could not be finalized"
AI_MODEL_REF_GENERATION_FAILURE_MESSAGE = "ontology generation could not be completed"


class GraphBuildService:
    @staticmethod
    def chunk_project_text(
        project_id: str,
        text: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> tuple[list[str], list[str | None] | None, list[int | None] | None, bool]:
        """Zerlegt den extrahierten Text eines Projekts deterministisch in Chunks."""
        return _chunk_project_text(
            project_id=project_id,
            text=text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

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
        """Generate an ontology for a project from its documents and simulation requirements."""
        return _generate_ontology(
            project_id=project_id,
            simulation_requirement=simulation_requirement,
            document_texts=document_texts,
            llm_model_override=llm_model_override,
            llm_runtime=llm_runtime,
            llm_profile_id=llm_profile_id,
            additional_context=additional_context,
            ai_model_ref=ai_model_ref,
        )

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
        """Queue a graph build for a project using its extracted text and ontology."""
        from .graph_build_helpers import build_graph as _build_graph

        return _build_graph(
            cls=cls,
            project_id=project_id,
            graph_name=graph_name,
            llm_model_override=llm_model_override,
            llm_runtime=llm_runtime,
            llm_profile_id=llm_profile_id,
            force=force,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            container=container,
            ai_model_ref=ai_model_ref,
        )

    @classmethod
    def resume_graph_build(
        cls,
        *,
        project_id: str,
        parent_run_id: str,
        checkpoint: GraphBuildCheckpoint,
        chunks: list[str],
        document_ids: list[str | None] | None,
        chunk_ids: list[int | None] | None,
        container,
    ) -> dict:
        """Setzt einen unterbrochenen graph_build anhand eines Checkpoints fort."""
        from .graph_build_helpers import resume_graph_build as _resume_graph_build

        return _resume_graph_build(
            cls=cls,
            project_id=project_id,
            parent_run_id=parent_run_id,
            checkpoint=checkpoint,
            chunks=chunks,
            document_ids=document_ids,
            chunk_ids=chunk_ids,
            container=container,
        )
