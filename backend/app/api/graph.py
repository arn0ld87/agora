"""
Compatibility layer for Graph API.
Redirects to submodules graph_projects, graph_build, and graph_data.
"""

from .graph_projects import *
from .graph_build import *
from .graph_data import *

# For tests that patch these specifically on app.api.graph
from ..models.project import ProjectManager
from ..models.task import TaskManager
from ..services.run_registry import RunRegistry
run_registry = RunRegistry()
from ..services.ontology_generator import OntologyGenerator
from ..utils.artifact_locator import ArtifactLocator
from ..services.llm_routing_seed import seed_run_stage_routing
from ..services.stage_model_router import StageModelRouter
from ..services.secret_resolver import SecretResolver
from ..utils.llm_client import LLMClient
from ..storage.ner_extractor import NERExtractor
from ..utils.file_parser import FileParser
from ..services.text_processor import TextProcessor

# Private helpers for tests that patch them
def _make_ner_override(*args, **kwargs):
    from ..storage.ner_extractor import NERExtractor
    from ..utils.llm_client import LLMClient, build_client_from_profile
    from ..services.secret_resolver import SecretResolver
    from ..services.llm_routing_seed import resolve_route_api_key

    run_id = args[0]
    resolved_route = args[1]
    llm_runtime = args[2]
    resolved_profile = kwargs.get("resolved_profile")

    if resolved_profile is not None:
        ner_llm_client = build_client_from_profile(resolved_profile, run_id=run_id)
    else:
        ner_llm_client = LLMClient.from_route(
            resolved_route,
            secret_resolver=SecretResolver(),
            api_key_override=resolve_route_api_key(resolved_route, llm_runtime),
            run_id=run_id,
        )
    return NERExtractor(llm_client=ner_llm_client)
