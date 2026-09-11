from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SIM_DIR = ROOT / "backend" / "app" / "services" / "sim"
TARGET = SIM_DIR / "process_manager.py"

ENV_FUNCS = [
    "_resolve_child_path",
    "_build_subprocess_env",
    "_compute_oasis_db_path",
    "_inject_oasis_db_env",
]
CANCEL_FUNCS = ["_read_cancel_abort", "_write_cancel_abort", "_clear_cancel_abort"]
TERMINATION_FUNCS = [
    "terminate_process",
    "stop_simulation",
    "cleanup_all_simulations",
    "terminate_run",
]


def start_line(node: ast.AST) -> int:
    decorators = getattr(node, "decorator_list", [])
    return min([node.lineno, *[item.lineno for item in decorators]])


def raw(node: ast.AST, lines: list[str]) -> str:
    return "".join(lines[start_line(node) - 1 : node.end_lineno]).rstrip() + "\n"


def write_environment(functions: dict[str, ast.FunctionDef], lines: list[str]) -> None:
    parts = [
        '"""Subprocess environment, path and OASIS database helpers.\n\n',
        'Extracted from process_manager; no lifecycle state is owned here.\n',
        '"""\n\n',
        'from __future__ import annotations\n\n',
        'import os\n',
        'from pathlib import Path\n',
        'from typing import Any, Dict, Optional\n\n',
        'from ...llm.providers.codex_cli import CLI_TRANSPORT_VALUE, TRANSPORT_ENV_KEY\n\n',
        'SAFE_ENV_KEYS: frozenset[str] = frozenset(\n',
        '    {\n',
        '        "PATH", "PYTHONPATH", "PYTHONUTF8", "PYTHONIOENCODING", "TZ",\n',
        '        "LLM_BASE_URL", "LLM_MODEL_NAME", "LLM_MAX_OUTPUT_TOKENS",\n',
        '        "OLLAMA_THINKING", "REDIS_URL", "HF_TOKEN",\n',
        '        "AGORA_CODEX_CLI_BIN", "AGORA_CODEX_CLI_TIMEOUT_SECONDS",\n',
        '    }\n',
        ')\n\n',
        '_OASIS_DB_DIR_NAME = "oasis_db"\n',
        '_OASIS_DB_FILE_NAME = "social_media.db"\n\n',
    ]
    for name in ENV_FUNCS:
        parts.append(raw(functions[name], lines))
        parts.append("\n\n")
    (SIM_DIR / "process_environment.py").write_text("".join(parts).rstrip() + "\n", encoding="utf-8")


def write_cancel(functions: dict[str, ast.FunctionDef], lines: list[str]) -> None:
    parts = [
        '"""Persistent cancel-marker handling for simulation subprocesses."""\n\n',
        'from __future__ import annotations\n\n',
        'import os\n',
        'from typing import Any, Dict, Optional\n\n',
        'from ...utils.logger import get_logger\n\n',
        'logger = get_logger("agora.process_manager")\n\n',
        'CANCEL_ABORT_FILENAME = "cancel_abort.json"\n\n',
    ]
    for name in CANCEL_FUNCS:
        parts.append(raw(functions[name], lines))
        parts.append("\n\n")
    (SIM_DIR / "process_cancel.py").write_text("".join(parts).rstrip() + "\n", encoding="utf-8")


def write_termination(functions: dict[str, ast.FunctionDef], lines: list[str]) -> None:
    parts = [
        '"""Process termination and cleanup operations for simulation subprocesses."""\n\n',
        'from __future__ import annotations\n\n',
        'import os\n',
        'import signal\n',
        'import subprocess\n',
        'import sys\n',
        'import time\n',
        'from datetime import datetime\n',
        'from typing import Any, Callable, Dict, List, Optional\n\n',
        'from ...utils.logger import get_logger\n',
        'from .process_cancel import _write_cancel_abort\n',
        'from .process_environment import _resolve_child_path\n',
        'from .run_state_store import RunnerStatus, SimulationRunState\n\n',
        'logger = get_logger("agora.process_manager")\n',
        'IS_WINDOWS = sys.platform == "win32"\n\n',
    ]
    for name in TERMINATION_FUNCS:
        parts.append(raw(functions[name], lines))
        parts.append("\n\n")
    (SIM_DIR / "process_termination.py").write_text("".join(parts).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    source = TARGET.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }
    expected = set(ENV_FUNCS + CANCEL_FUNCS + TERMINATION_FUNCS)
    missing = sorted(expected - functions.keys())
    if missing:
        raise SystemExit(f"missing process_manager functions: {missing}")

    write_environment(functions, lines)
    write_cancel(functions, lines)
    write_termination(functions, lines)

    replacements: dict[int, tuple[int, str]] = {}
    for name in expected:
        node = functions[name]
        replacements[start_line(node)] = (node.end_lineno, "")

    # Remove constants that are now owned by focused modules. The facade
    # re-exports them below, keeping all existing import paths stable.
    assignments: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assignments[node.target.id] = node
    for name in ["CANCEL_ABORT_FILENAME", "SAFE_ENV_KEYS", "IS_WINDOWS", "_OASIS_DB_DIR_NAME", "_OASIS_DB_FILE_NAME"]:
        node = assignments.get(name)
        if node is None:
            raise SystemExit(f"missing process_manager constant: {name}")
        replacements[start_line(node)] = (node.end_lineno, "")

    imports = '''from .process_cancel import (
    CANCEL_ABORT_FILENAME as CANCEL_ABORT_FILENAME,
    _clear_cancel_abort as _clear_cancel_abort,
    _read_cancel_abort as _read_cancel_abort,
    _write_cancel_abort as _write_cancel_abort,
)
from .process_environment import (
    SAFE_ENV_KEYS as SAFE_ENV_KEYS,
    _build_subprocess_env as _build_subprocess_env,
    _compute_oasis_db_path as _compute_oasis_db_path,
    _inject_oasis_db_env as _inject_oasis_db_env,
    _resolve_child_path as _resolve_child_path,
)
from .process_termination import (
    IS_WINDOWS as IS_WINDOWS,
    cleanup_all_simulations as cleanup_all_simulations,
    stop_simulation as stop_simulation,
    terminate_process as terminate_process,
    terminate_run as terminate_run,
)
'''
    marker = "from .run_state_store import RunnerStatus, SimulationRunState\n"
    if marker not in source:
        raise SystemExit("run_state_store import marker not found")

    output: list[str] = []
    inserted = False
    line_no = 1
    while line_no <= len(lines):
        replacement = replacements.get(line_no)
        if replacement is not None:
            end, text = replacement
            output.append(text)
            line_no = end + 1
            continue
        output.append(lines[line_no - 1])
        if not inserted and lines[line_no - 1] == marker:
            output.append(imports + "\n")
            inserted = True
        line_no += 1

    new_source = "".join(output)
    TARGET.write_text(new_source, encoding="utf-8")

    generated = [
        TARGET,
        SIM_DIR / "process_environment.py",
        SIM_DIR / "process_cancel.py",
        SIM_DIR / "process_termination.py",
    ]
    for path in generated:
        ast.parse(path.read_text(encoding="utf-8"))
        print(f"{path.name}: {len(path.read_text(encoding='utf-8').splitlines())} LOC")

    if len(new_source.splitlines()) >= 800:
        raise SystemExit("process_manager.py remains >=800 LOC after split")


if __name__ == "__main__":
    main()
