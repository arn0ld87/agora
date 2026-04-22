import re

# Standard identifier regex: prefix_ followed by 12 hex characters
# Based on uuid4().hex[:12] usage in the codebase
PROJ_ID_PATTERN = re.compile(r'^proj_[a-f0-9]{12}$')
SIM_ID_PATTERN = re.compile(r'^sim_[a-f0-9]{12}$')
REPORT_ID_PATTERN = re.compile(r'^report_[a-f0-9]{12}$')
RUN_ID_PATTERN = re.compile(r'^run_[a-f0-9]{12}$')

# Graph IDs in Neo4j are UUIDs
UUID_PATTERN = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$|'
                          r'^[a-f0-9]{32}$')

# Task-IDs sind bare UUIDs — TaskManager.create_task() nutzt str(uuid.uuid4()),
# kein "task_"-Prefix. Security-Review f5dd63b hatte hier fälschlich ^task_[a-f0-9]+$
# erzwungen, wodurch jeder /api/graph/task/<id>-Poll mit 400 abstürzte.
TASK_ID_PATTERN = UUID_PATTERN

def validate_project_id(project_id: str) -> bool:
    """Validate project_id format"""
    if not project_id:
        return False
    return bool(PROJ_ID_PATTERN.match(project_id))

def validate_simulation_id(simulation_id: str) -> bool:
    """Validate simulation_id format"""
    if not simulation_id:
        return False
    return bool(SIM_ID_PATTERN.match(simulation_id))

def validate_report_id(report_id: str) -> bool:
    """Validate report_id format"""
    if not report_id:
        return False
    return bool(REPORT_ID_PATTERN.match(report_id))

def validate_graph_id(graph_id: str) -> bool:
    """Validate graph_id format (UUID)"""
    if not graph_id:
        return False
    return bool(UUID_PATTERN.match(graph_id))

def validate_run_id(run_id: str) -> bool:
    """Validate run_id format"""
    if not run_id:
        return False
    return bool(RUN_ID_PATTERN.match(run_id))

def validate_task_id(task_id: str) -> bool:
    """Validate task_id format"""
    if not task_id:
        return False
    return bool(TASK_ID_PATTERN.match(task_id))
