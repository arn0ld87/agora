"""
Compatibility shim for the Graph API.

The routes live in the split blueprints ``graph_projects``, ``graph_build``,
and ``graph_data``. Production code should import from those modules
(or from the corresponding ``app.services.graph_*`` services) directly.

This module exists only so that existing tests can keep patching
``app.api.graph.<Symbol>`` for class-level mocks (``ProjectManager.method``,
``RunRegistry.method``, …) without needing migration in the same PR.

Two important notes for test authors:

1. Patching *class* attributes (e.g. ``ProjectManager.get_project``) propagates
   through every instance and still works as before.
2. Patching *function* names (e.g. ``seed_run_stage_routing``) on this module
   does NOT affect the service code, because the services import these
   symbols directly from their source module. Migrate such patches to the
   service module path (``app.services.graph_build.<symbol>``).

The ``run_registry`` instance is intentionally re-exported from
``app.services.graph_build`` so that ``patch("app.api.graph.run_registry...")``
still reaches the actual instance used by the build pipeline.
"""

from .graph_build import (  # noqa: F401  -- re-exported for backwards compatibility
    allowed_file,
    build_graph,
    generate_ontology,
)
from .graph_data import (  # noqa: F401  -- re-exported for backwards compatibility
    delete_graph,
    export_graph,
    get_graph_data,
    get_graph_diff,
    get_graph_snapshot,
    get_task,
    list_tasks,
)
from .graph_projects import (  # noqa: F401  -- re-exported for backwards compatibility
    delete_project,
    get_project,
    list_projects,
    reset_project,
)

# Symbols frequently patched at ``app.api.graph.<name>`` by the existing test
# suite. Class-attribute patches (``X.method``) propagate through every
# instance, so re-exporting the classes is sufficient.
from ..container import get_container  # noqa: F401
from ..models.project import ProjectManager  # noqa: F401
from ..models.task import TaskManager  # noqa: F401
from ..services.llm_routing_seed import (  # noqa: F401
    resolve_route_api_key,
    seed_run_stage_routing,
)
from ..services.ontology_generator import OntologyGenerator  # noqa: F401
from ..services.run_registry import RunRegistry  # noqa: F401
from ..services.secret_resolver import SecretResolver  # noqa: F401
from ..services.stage_model_router import StageModelRouter  # noqa: F401
from ..services.text_processor import TextProcessor  # noqa: F401
from ..storage.ner_extractor import NERExtractor  # noqa: F401
from ..utils.artifact_locator import ArtifactLocator  # noqa: F401
from ..utils.file_parser import FileParser  # noqa: F401
from ..utils.llm_client import LLMClient  # noqa: F401

# Share the SAME registry instance the build pipeline uses, so monkeypatching
# ``app.api.graph.run_registry.<method>`` reaches the actual call sites.
from ..services.graph_build import run_registry  # noqa: F401
