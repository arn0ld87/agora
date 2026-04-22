"""
API Routes Module
"""

from flask import Blueprint

graph_bp = Blueprint('graph', __name__)
simulation_bp = Blueprint('simulation', __name__)
report_bp = Blueprint('report', __name__)
runs_bp = Blueprint('runs', __name__)
status_bp = Blueprint('status', __name__)

from . import graph  # noqa: E402, F401
from . import simulation_common  # noqa: E402, F401
from . import simulation_lifecycle  # noqa: E402, F401
from . import simulation_entities  # noqa: E402, F401
from . import simulation_prepare  # noqa: E402, F401
from . import simulation  # noqa: E402, F401
from . import report  # noqa: E402, F401
from . import runs  # noqa: E402, F401
from . import status  # noqa: E402, F401
