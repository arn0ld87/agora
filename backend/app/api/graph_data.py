"""
Graph API: Data retrieval, snapshot, diff, and export endpoints.
"""

import io
from flask import Response, request
from . import graph_bp
from ..container import get_container
from ..models.graph import GraphDataDTO
from ..models.task import TaskManager
from ..utils.validation import validate_graph_id, validate_task_id
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import handle_api_errors, json_success, json_error
from ..utils.graph_diff_helpers import build_pydantic_graph_diff
from ..utils.scopes import require_scope
from ..services.graph_export import GraphExportService

@graph_bp.route('/task/<task_id>', methods=['GET'])
@handle_api_errors
def get_task(task_id: str):
    """Query task status"""
    if not validate_task_id(task_id):
        return json_error(ApiErrorCode.INVALID_ID, status=400)

    task = TaskManager().get_task(task_id)
    if not task:
        return json_error(ApiErrorCode.NOT_FOUND, status=404, message=f"Task does not exist: {task_id}")

    return json_success(task.to_dict())

@graph_bp.route('/tasks', methods=['GET'])
@handle_api_errors
def list_tasks():
    """List all tasks"""
    tasks = TaskManager().list_tasks()
    return json_success([t.to_dict() for t in tasks], count=len(tasks))

@graph_bp.route('/data/<graph_id>', methods=['GET'])
@require_scope("graph:read")
@handle_api_errors
def get_graph_data(graph_id: str):
    """Get graph data (nodes and edges)."""
    if not validate_graph_id(graph_id):
        return json_error(ApiErrorCode.INVALID_ID, status=400)

    builder = get_container().graph_builder()
    graph_data = builder.get_graph_data(graph_id)
    dto = GraphDataDTO.from_storage_dict(graph_data)
    return json_success(dto.to_dict())

@graph_bp.route('/snapshot/<graph_id>/<int:round_num>', methods=['GET'])
@require_scope("graph:read")
@handle_api_errors
def get_graph_snapshot(graph_id: str, round_num: int):
    """Return the set of RELATION edges valid at round_num."""
    if not validate_graph_id(graph_id):
        return json_error(ApiErrorCode.INVALID_ID, status=400)
    if round_num < 0:
        return json_error(ApiErrorCode.VALIDATION_FAILED, status=400, message="round_num must be >= 0")

    service = get_container().temporal_graph()
    snapshot = service.get_snapshot(graph_id, round_num)
    return json_success(snapshot.to_dict())

@graph_bp.route('/<graph_id>/diff', methods=['GET'])
@require_scope("graph:read")
@handle_api_errors
def get_graph_diff(graph_id: str):
    """Return added / removed / reinforced edges between two rounds."""
    if not validate_graph_id(graph_id):
        return json_error(ApiErrorCode.INVALID_ID, status=400)

    raw_start = request.args.get('start_round')
    raw_end = request.args.get('end_round')

    if raw_start is None or raw_end is None:
        return json_error(ApiErrorCode.VALIDATION_FAILED, status=400, message="Required parameters: start_round and end_round (int)")

    try:
        start_round = int(raw_start)
        end_round = int(raw_end)
    except (TypeError, ValueError):
        return json_error(ApiErrorCode.VALIDATION_FAILED, status=400, message="start_round and end_round must be integers")

    if start_round < 0 or end_round < 0:
        return json_error(ApiErrorCode.VALIDATION_FAILED, status=400, message="start_round und end_round müssen >= 0 sein")
        return json_error(ApiErrorCode.VALIDATION_FAILED, status=400, message="start_round and end_round must be >= 0")
    if end_round < start_round:
        return json_error(ApiErrorCode.VALIDATION_FAILED, status=400, message="end_round must be >= start_round")

    svc = get_container().temporal_graph()
    service_diff = svc.compute_diff(graph_id, start_round, end_round)
    snap_a = svc.get_snapshot(graph_id, start_round)
    snap_b = svc.get_snapshot(graph_id, end_round)

    graph_diff = build_pydantic_graph_diff(
        service_diff=service_diff,
        snap_a=snap_a,
        snap_b=snap_b,
        graph_id=graph_id,
        start_round=start_round,
        end_round=end_round,
    )
    return json_success(graph_diff.model_dump(mode="json"))

@graph_bp.route('/<graph_id>/export', methods=['GET'])
@require_scope("graph:read")
@handle_api_errors
def export_graph(graph_id: str):
    """Export the full graph as GraphML for downstream graph tooling."""
    if not validate_graph_id(graph_id):
        return json_error(ApiErrorCode.INVALID_ID, status=400)

    fmt = (request.args.get('format') or 'graphml').strip().lower()
    if fmt != 'graphml':
        return json_error(ApiErrorCode.UNSUPPORTED_FORMAT, status=400, message="format must be 'graphml'")

    builder = get_container().graph_builder()
    graph_data = builder.get_graph_data(graph_id)
    if not graph_data or (not graph_data.get("nodes") and not graph_data.get("edges")):
        return json_error(ApiErrorCode.NOT_FOUND, status=404, message=f"Graph not found or empty: {graph_id}")

    body = GraphExportService.export_graphml(graph_data)
    response = Response(body, mimetype='application/xml; charset=utf-8')
    response.headers['Content-Disposition'] = f'attachment; filename="agora-graph-{graph_id}.graphml"'
    return response

@graph_bp.route('/delete/<graph_id>', methods=['DELETE'])
@require_scope("graph:write")
@handle_api_errors
def delete_graph(graph_id: str):
    """Delete graph"""
    if not validate_graph_id(graph_id):
        return json_error(ApiErrorCode.INVALID_ID, status=400)

    builder = get_container().graph_builder()
    builder.delete_graph(graph_id)
    return json_success(message=f"Graph deleted: {graph_id}")
