"""
API Routes Module
"""

from flask import Blueprint

graph_bp = Blueprint('graph', __name__)
simulation_bp = Blueprint('simulation', __name__)
report_bp = Blueprint('report', __name__)
runs_bp = Blueprint('runs', __name__)
status_bp = Blueprint('status', __name__)
logs_bp = Blueprint('logs', __name__)
llm_bp = Blueprint('llm', __name__)  # Slice E.1 (#213): model-active SSE stream

from .auth import auth_bp  # noqa: E402, F401 -- P0.2b: signed-ticket endpoint
from .settings import settings_bp  # noqa: E402, F401 -- Issue #133: Settings-UI
from .api_keys import api_keys_bp  # noqa: E402, F401 -- Slice G2: API-Keys real
from . import graph           # noqa: E402, F401
from . import graph_projects  # noqa: E402, F401
from . import graph_build     # noqa: E402, F401
from . import graph_data      # noqa: E402, F401
from . import simulation_common  # noqa: E402, F401
from . import simulation_lifecycle  # noqa: E402, F401
from . import simulation_entities  # noqa: E402, F401
from . import simulation_prepare  # noqa: E402, F401
from . import simulation_profiles  # noqa: E402, F401
from . import simulation_run  # noqa: E402, F401
from . import simulation_interviews  # noqa: E402, F401
from . import simulation_history  # noqa: E402, F401
from . import simulation_stream  # noqa: E402, F401 -- Issue #9 Phase C: SSE bridge
from . import simulation_metrics  # noqa: E402, F401 -- Issue #12: polarization metrics
from . import simulation_compare  # noqa: E402, F401 -- Sub-Slice 24 (#66): Branch-Compare-API
from . import simulation  # noqa: E402, F401
from . import report  # noqa: E402, F401
from . import runs  # noqa: E402, F401
from . import llm_routing  # noqa: E402, F401
from . import status  # noqa: E402, F401
from . import logs  # noqa: E402, F401 -- Issue #132: Backend-Log-Viewer
from . import llm  # noqa: E402, F401 -- Slice E.1 (#213): model-active SSE stream
from . import llm_providers  # noqa: E402, F401
from . import llm_active  # noqa: E402, F401 -- Active provider/model selection
from .llm_profiles import llm_profiles_bp  # noqa: E402, F401 -- P5.2: LLM-Profile CRUD
