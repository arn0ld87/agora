from __future__ import annotations

import ast
from pathlib import Path

SOURCE = Path("backend/app/api/simulation_prepare.py")
CONTRACTS = Path("backend/app/api/simulation_prepare_contracts.py")
STATE = Path("backend/app/api/simulation_prepare_state.py")
JOBS = Path("backend/app/api/simulation_prepare_jobs.py")

source = SOURCE.read_text(encoding="utf-8")
lines = source.splitlines(keepends=True)
tree = ast.parse(source)
nodes = {
    node.name: node
    for node in tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
}


def span(name: str) -> tuple[int, int]:
    node = nodes[name]
    starts = [node.lineno]
    starts.extend(dec.lineno for dec in getattr(node, "decorator_list", []))
    return min(starts) - 1, node.end_lineno


def segment(name: str) -> str:
    start, end = span(name)
    return "".join(lines[start:end]).rstrip() + "\n"


contract_names = [
    "_parse_quota_plan",
    "_resolve_max_agents_with_floor",
    "_PrepareRejected",
    "_PrepareRequest",
    "_PrepareRouting",
    "_PrepareInputs",
    "_parse_prepare_identity",
    "_parse_prepare_budget",
    "_load_prepare_project",
    "_ClientChoice",
    "_read_client_choice",
    "_resolve_prepare_routing",
    "_collect_prepare_inputs",
]
state_names = ["_check_simulation_prepared"]
job_names = ["_build_progress_callback", "_make_prepare_job"]
remove_names = set(contract_names + state_names + job_names)

contracts_body = "\n\n".join(segment(name).rstrip() for name in contract_names) + "\n"
for old, new in {
    "_PrepareRejected": "PrepareRejected",
    "_PrepareRequest": "PrepareRequest",
    "_PrepareRouting": "PrepareRouting",
    "_PrepareInputs": "PrepareInputs",
    "_ClientChoice": "ClientChoice",
}.items():
    contracts_body = contracts_body.replace(old, new)

contracts_header = '''"""Request contracts and input/routing parsing for simulation preparation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from pydantic import ValidationError

from ..contracts import PersonaQuotaPlan
from ..models.project import ProjectManager
from ..services.llm_runtime import parse_runtime_llm_config
from ..services.report_agent import MIN_SIMULATION_AGENTS
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import json_error
from ..utils.validation import validate_simulation_id
from .simulation_common import logger

if TYPE_CHECKING:
    from ..contracts.ai_provider_contract import AiModelRef
    from ..contracts.run_budget_contract import RunBudgetConfig
    from ..services.llm_runtime import RuntimeLlmConfig

'''
CONTRACTS.write_text(contracts_header + contracts_body, encoding="utf-8")

state_body = segment("_check_simulation_prepared").replace(
    "def _check_simulation_prepared(", "def check_simulation_prepared(", 1
)
state_header = '''"""Prepared-state and artifact inspection for simulation preparation."""

from __future__ import annotations

import os

from ..config import Config
from .simulation_common import get_artifact_store, logger

'''
STATE.write_text(state_header + state_body, encoding="utf-8")

progress_body = segment("_build_progress_callback").replace(
    "def _build_progress_callback(", "def build_progress_callback(", 1
)
job_body = segment("_make_prepare_job")
job_body = job_body.replace("def _make_prepare_job(", "def make_prepare_job(", 1)
job_body = job_body.replace("inputs: _PrepareInputs", "inputs: PrepareInputs")
job_body = job_body.replace(
    '    run_record: "dict[str, Any]",\n) -> "Callable[[], None]":',
    '    run_record: "dict[str, Any]",\n'
    '    progress_callback_factory: "Callable[..., Callable[..., None]]",\n'
    '    finish_cancelled_prepare_run: "Callable[..., None]",\n'
    ') -> "Callable[[], None]":',
)
job_body = job_body.replace(
    "_build_progress_callback(task_manager, task_id)",
    "progress_callback_factory(task_manager, task_id)",
)
job_body = job_body.replace(
    "_finish_cancelled_prepare_run(\n",
    "finish_cancelled_prepare_run(\n",
)

jobs_header = '''"""Background-job helpers for simulation preparation."""

from __future__ import annotations

from typing import Any, Callable

from ..services.degradation_collector import DegradationCollector
from ..services.simulation_manager import SimulationStatus
from .simulation_common import logger
from .simulation_prepare_contracts import PrepareInputs

'''
JOBS.write_text(jobs_header + progress_body + "\n\n" + job_body, encoding="utf-8")

# Remove the extracted top-level nodes from the facade while preserving all
# surrounding comments and the route/orchestrator code.
remove_lines: set[int] = set()
for name in remove_names:
    start, end = span(name)
    remove_lines.update(range(start, end))

facade = "".join(line for idx, line in enumerate(lines) if idx not in remove_lines)

# Preserve monkeypatch/import compatibility intentionally. Explicit same-name
# aliases tell Ruff these are public re-exports rather than dead imports.
facade = facade.replace(
    "from ..models.project import ProjectManager\n",
    "from ..models.project import ProjectManager as ProjectManager\n",
)
facade = facade.replace(
    "from ..services.report_agent import MIN_SIMULATION_AGENTS\n",
    "from ..services.report_agent import MIN_SIMULATION_AGENTS as MIN_SIMULATION_AGENTS\n",
)

compat_imports = '''from .simulation_prepare_contracts import (
    ClientChoice as _ClientChoice,
    PrepareInputs as _PrepareInputs,
    PrepareRejected as _PrepareRejected,
    PrepareRequest as _PrepareRequest,
    PrepareRouting as _PrepareRouting,
    _collect_prepare_inputs as _collect_prepare_inputs,
    _load_prepare_project as _load_prepare_project,
    _parse_prepare_budget as _parse_prepare_budget,
    _parse_prepare_identity as _parse_prepare_identity,
    _parse_quota_plan as _parse_quota_plan,
    _read_client_choice as _read_client_choice,
    _resolve_max_agents_with_floor as _resolve_max_agents_with_floor,
    _resolve_prepare_routing as _resolve_prepare_routing,
)
from .simulation_prepare_jobs import (
    build_progress_callback as _build_progress_callback,
    make_prepare_job as _make_prepare_job_impl,
)
from .simulation_prepare_state import (
    check_simulation_prepared as _check_simulation_prepared,
)

'''
marker = "@dataclass\nclass _PrepareStartLockEntry:"
if marker not in facade:
    raise RuntimeError("compatibility import insertion marker not found")
facade = facade.replace(marker, compat_imports + marker, 1)

make_wrapper = '''def _make_prepare_job(
    *,
    manager,
    task_manager,
    task_id: str,
    simulation_id: str,
    inputs: _PrepareInputs,
    storage,
    llm_model: str,
    effective_llm_runtime,
    run_record: "dict[str, Any]",
) -> "Callable[[], None]":
    """Compatibility wrapper around the extracted background-job builder."""
    return _make_prepare_job_impl(
        manager=manager,
        task_manager=task_manager,
        task_id=task_id,
        simulation_id=simulation_id,
        inputs=inputs,
        storage=storage,
        llm_model=llm_model,
        effective_llm_runtime=effective_llm_runtime,
        run_record=run_record,
        progress_callback_factory=_build_progress_callback,
        finish_cancelled_prepare_run=_finish_cancelled_prepare_run,
    )


'''
wrapper_marker = "def _track_active_prepare_job("
if wrapper_marker not in facade:
    raise RuntimeError("job wrapper insertion marker not found")
facade = facade.replace(wrapper_marker, make_wrapper + wrapper_marker, 1)

SOURCE.write_text(facade, encoding="utf-8")

print(f"simulation_prepare.py: {len(facade.splitlines())} LOC")
print(f"simulation_prepare_contracts.py: {len((contracts_header + contracts_body).splitlines())} LOC")
print(f"simulation_prepare_state.py: {len((state_header + state_body).splitlines())} LOC")
print(f"simulation_prepare_jobs.py: {len((jobs_header + progress_body + chr(10) + chr(10) + job_body).splitlines())} LOC")
