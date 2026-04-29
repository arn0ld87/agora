"""Polarization / network metrics endpoint (Issue #12).

``GET /api/simulation/<simulation_id>/metrics`` runs the
:class:`NetworkAnalyticsService` against the actions currently logged for
the simulation and returns a :class:`PolarizationMetrics` payload. The
handler is stateless — no background worker today, the networkx run is
fast enough on realistic simulation sizes (< ~10k interactions) that
on-demand computation is fine.
"""

from __future__ import annotations

import csv
import io

from flask import Response, request

from . import simulation_bp
from ..container import get_container
from ..services.network_analytics import PolarizationMetrics
from ..services.simulation_runner import SimulationRunner
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.validation import validate_simulation_id


def _compute(simulation_id: str, *, window: int | None, platform: str | None) -> PolarizationMetrics:
    actions = SimulationRunner.get_all_actions(simulation_id, platform=platform)
    action_dicts = [a.to_dict() for a in actions]
    service = get_container().network_analytics()
    return service.compute_metrics(
        action_dicts,
        simulation_id=simulation_id,
        window_size_rounds=window,
    )


def _parse_window(raw: str | None) -> int | None:
    if raw is None or raw == '':
        return None
    return int(raw)


def _csv_response(rows: list[list[str]], *, filename: str) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator='\n')
    for row in rows:
        writer.writerow(row)
    response = Response(buf.getvalue(), mimetype='text/csv; charset=utf-8')
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


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
        window = _parse_window(request.args.get('window_size_rounds'))
    except (TypeError, ValueError):
        return json_error("window_size_rounds must be an integer", status=400)

    platform = request.args.get('platform')
    if platform and platform not in ('twitter', 'reddit'):
        return json_error("platform must be 'twitter' or 'reddit'", status=400)

    metrics = _compute(simulation_id, window=window, platform=platform)
    return json_success(metrics.to_dict())


@simulation_bp.route('/<simulation_id>/metrics/export', methods=['GET'])
@handle_api_errors
def export_simulation_metrics(simulation_id: str):
    """Flat CSV export of polarization metrics (Slice 5.2).

    Query params:

    * ``format`` — currently only ``csv``.
    * ``view`` — ``summary`` (default), ``clusters``, ``bridges``.
    * ``window_size_rounds``, ``platform`` — same semantics as the JSON endpoint.
    """
    if not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format", status=400)

    fmt = (request.args.get('format') or 'csv').strip().lower()
    if fmt != 'csv':
        return json_error("format must be 'csv'", status=400)

    view = (request.args.get('view') or 'summary').strip().lower()
    if view not in ('summary', 'clusters', 'bridges'):
        return json_error("view must be 'summary', 'clusters' or 'bridges'", status=400)

    try:
        window = _parse_window(request.args.get('window_size_rounds'))
    except (TypeError, ValueError):
        return json_error("window_size_rounds must be an integer", status=400)

    platform = request.args.get('platform')
    if platform and platform not in ('twitter', 'reddit'):
        return json_error("platform must be 'twitter' or 'reddit'", status=400)

    metrics = _compute(simulation_id, window=window, platform=platform)
    payload = metrics.to_dict()

    if view == 'summary':
        rows = [
            [
                "simulation_id",
                "window_size_rounds",
                "total_agents",
                "total_interactions",
                "echo_chamber_index",
                "cluster_count",
            ],
            [
                payload.get("simulation_id") or "",
                "" if payload.get("window_size_rounds") in (None, 0) else str(payload["window_size_rounds"]),
                str(payload.get("total_agents", 0)),
                str(payload.get("total_interactions", 0)),
                f"{payload.get('echo_chamber_index', 0.0):.4f}",
                str(payload.get("cluster_count", 0)),
            ],
        ]
        return _csv_response(rows, filename=f"agora-metrics-{simulation_id}-summary.csv")

    if view == 'clusters':
        rows = [["cluster_id", "size", "agent_ids"]]
        for cluster in payload.get("dominant_clusters", []):
            rows.append([
                str(cluster.get("cluster_id", "")),
                str(cluster.get("size", 0)),
                ";".join(str(a) for a in cluster.get("agent_ids", [])),
            ])
        return _csv_response(rows, filename=f"agora-metrics-{simulation_id}-clusters.csv")

    rows = [["rank", "agent_id"]]
    for rank, agent_id in enumerate(payload.get("bridge_agents", []), start=1):
        rows.append([str(rank), str(agent_id)])
    return _csv_response(rows, filename=f"agora-metrics-{simulation_id}-bridges.csv")
