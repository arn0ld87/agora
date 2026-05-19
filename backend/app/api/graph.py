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
