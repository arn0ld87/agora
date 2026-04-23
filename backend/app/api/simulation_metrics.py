"""Polarization / network metrics endpoint (Issue #12).

``GET /api/simulation/<simulation_id>/metrics`` runs the
:class:`NetworkAnalyticsService` against the actions currently logged for
the simulation and returns a :class:`PolarizationMetrics` payload. The
handler is stateless — no background worker today, the networkx run is
fast enough on realistic simulation sizes (< ~10k interactions) that
on-demand computation is fine.
"""

from __future__ import annotations

from flask import request

from . import simulation_bp
from ..container import get_container
from ..services.simulation_runner import SimulationRunner
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.validation import validate_simulation_id


@simulation_bp.route('/<simulation_id>/metrics', methods=['GET'])
@handle_api_errors
def get_simulation_metrics(simulation_id: str):
    """Compute polarization metrics for the given simulation.

    Query params:

    * ``window_size_rounds`` (optional, int > 0) — restrict analysis to
      the last N rounds. Omitted or 0 → full history.
    * ``platform`` (optional: twitter | reddit) — filter the action stream.
    """
    if not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format", status=400)

    try:
        window_raw = request.args.get('window_size_rounds')
        window = int(window_raw) if window_raw is not None and window_raw != '' else None
    except (TypeError, ValueError):
        return json_error("window_size_rounds must be an integer", status=400)

    platform = request.args.get('platform')
    if platform and platform not in ('twitter', 'reddit'):
        return json_error("platform must be 'twitter' or 'reddit'", status=400)

    actions = SimulationRunner.get_all_actions(simulation_id, platform=platform)
    action_dicts = [a.to_dict() for a in actions]

    service = get_container().network_analytics()
    metrics = service.compute_metrics(
        action_dicts,
        simulation_id=simulation_id,
        window_size_rounds=window,
    )
    return json_success(metrics.to_dict())
