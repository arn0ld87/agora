"""
Graph API: Project management endpoints.
"""

from flask import request
from . import graph_bp
from ..models.project import ProjectManager, ProjectStatus
from ..utils.validation import validate_project_id
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import handle_api_errors, json_success, json_error
from ..utils.scopes import require_scope

@graph_bp.route('/project/<project_id>', methods=['GET'])
@handle_api_errors
def get_project(project_id: str):
    """Get project details"""
    if not validate_project_id(project_id):
        return json_error(ApiErrorCode.INVALID_ID, status=400)

    project = ProjectManager.get_project(project_id)
    if not project:
        return json_error(ApiErrorCode.NOT_FOUND, status=404, message=f"Project does not exist: {project_id}")

    return json_success(project.to_dict())

@graph_bp.route('/project/list', methods=['GET'])
@handle_api_errors
def list_projects():
    """List all projects"""
    limit = request.args.get('limit', 50, type=int)
    projects = ProjectManager.list_projects(limit=limit)
    return json_success([p.to_dict() for p in projects], count=len(projects))

@graph_bp.route('/project/<project_id>', methods=['DELETE'])
@require_scope("graph:write")
@handle_api_errors
def delete_project(project_id: str):
    """Delete project"""
    if not validate_project_id(project_id):
        return json_error(ApiErrorCode.INVALID_ID, status=400)

    success = ProjectManager.delete_project(project_id)
    if not success:
        return json_error(ApiErrorCode.NOT_FOUND, status=404, message=f"Project does not exist or deletion failed: {project_id}")

    return json_success(message=f"Project deleted: {project_id}")

@graph_bp.route('/project/<project_id>/reset', methods=['POST'])
@require_scope("graph:write")
@handle_api_errors
def reset_project(project_id: str):
    """Reset project status (for rebuilding graph)"""
    if not validate_project_id(project_id):
        return json_error(ApiErrorCode.INVALID_ID, status=400)

    project = ProjectManager.get_project(project_id)
    if not project:
        return json_error(ApiErrorCode.NOT_FOUND, status=404, message=f"Project does not exist: {project_id}")

    # Reset to ontology generated state
    if project.ontology:
        project.status = ProjectStatus.ONTOLOGY_GENERATED
    else:
        project.status = ProjectStatus.CREATED

    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    ProjectManager.save_project(project)

    return json_success(project.to_dict(), message=f"Project reset: {project_id}")
