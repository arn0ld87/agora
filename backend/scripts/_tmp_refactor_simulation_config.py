from __future__ import annotations

import ast
import copy
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE_DIR = ROOT / "backend" / "app" / "services"
TARGET = SERVICE_DIR / "simulation_config_generator.py"

MODEL_NAMES = [
    "AgentActivityConfig",
    "TimeSimulationConfig",
    "EventConfig",
    "PlatformConfig",
    "SimulationParameters",
]

KEEP_METHODS = {"__init__", "_resolve_agents_per_batch", "generate_config"}


def node_start(node: ast.AST) -> int:
    decorators = getattr(node, "decorator_list", [])
    return min([node.lineno, *[item.lineno for item in decorators]])


def helper_group(name: str) -> str | None:
    if name in KEEP_METHODS:
        return None
    if name in {"_build_context", "_summarize_entities"}:
        return "context"
    if name in {"_call_llm_with_retry", "_fix_truncated_json", "_try_fix_config_json"}:
        return "llm"
    if "time_config" in name or name in {"_coerce_int", "_coerce_int_list"}:
        return "time"
    if name in {"_generate_event_config", "_parse_event_config", "_assign_initial_post_agents"}:
        return "events"
    if name.startswith("_generate_agent_config") or name == "_ensure_skeptic_quota":
        return "agents"
    raise SystemExit(f"Unclassified SimulationConfigGenerator method: {name}")


def helper_prelude(group: str) -> str:
    common = '''"""Implementation helpers extracted from SimulationConfigGenerator.

The public compatibility surface remains app.services.simulation_config_generator.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, ValidationError as PydanticValidationError

from ..config import Config
from ..utils.logger import get_logger
from .entity_reader import EntityNode
from .simulation_config_models import (
    AgentActivityConfig,
    EventConfig,
    PlatformConfig,
    SimulationParameters,
    TimeSimulationConfig,
)
from .simulation_config_schemas import (
    AgentConfigsResponse,
    EventConfigResponse,
    get_time_config_schema,
)

logger = get_logger("agora.simulation_config")
'''
    return common + f"\n# Responsibility group: {group}\n\n"


def helper_source(node: ast.FunctionDef | ast.AsyncFunctionDef, lines: list[str]) -> str:
    # Deliberately omit class-level decorators. The compatibility wrapper retains
    # @staticmethod/@classmethod while the implementation helper is a plain function.
    raw = "".join(lines[node.lineno - 1 : node.end_lineno])
    return textwrap.dedent(raw).rstrip() + "\n"


def wrapper_source(node: ast.FunctionDef | ast.AsyncFunctionDef, module_alias: str) -> str:
    replacement = copy.deepcopy(node)
    positional = [*node.args.posonlyargs, *node.args.args]
    args: list[ast.expr] = [ast.Name(id=arg.arg, ctx=ast.Load()) for arg in positional]
    if node.args.vararg:
        args.append(ast.Starred(value=ast.Name(id=node.args.vararg.arg, ctx=ast.Load()), ctx=ast.Load()))
    keywords = [
        ast.keyword(arg=arg.arg, value=ast.Name(id=arg.arg, ctx=ast.Load()))
        for arg in node.args.kwonlyargs
    ]
    if node.args.kwarg:
        keywords.append(ast.keyword(arg=None, value=ast.Name(id=node.args.kwarg.arg, ctx=ast.Load())))

    call = ast.Call(
        func=ast.Attribute(
            value=ast.Name(id=module_alias, ctx=ast.Load()),
            attr=node.name,
            ctx=ast.Load(),
        ),
        args=args,
        keywords=keywords,
    )
    returned: ast.expr = ast.Await(value=call) if isinstance(node, ast.AsyncFunctionDef) else call
    replacement.body = [ast.Return(value=returned)]
    ast.fix_missing_locations(replacement)
    return textwrap.indent(ast.unparse(replacement), "    ") + "\n"


def write_models(model_nodes: dict[str, ast.ClassDef], lines: list[str]) -> None:
    parts = [
        '"""Data contracts for simulation configuration generation.\n\n',
        'Extracted from simulation_config_generator so the generator can stay an orchestration facade.\n',
        '"""\n\n',
        'from __future__ import annotations\n\n',
        'import json\n',
        'from dataclasses import asdict, dataclass, field\n',
        'from datetime import datetime\n',
        'from typing import Any, Dict, List, Optional\n\n',
    ]
    for name in MODEL_NAMES:
        node = model_nodes[name]
        parts.append("".join(lines[node_start(node) - 1 : node.end_lineno]).rstrip())
        parts.append("\n\n\n")
    (SERVICE_DIR / "simulation_config_models.py").write_text(
        "".join(parts).rstrip() + "\n", encoding="utf-8"
    )


def main() -> None:
    source = TARGET.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    tree = ast.parse(source)

    model_nodes = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in MODEL_NAMES
    }
    missing_models = sorted(set(MODEL_NAMES) - model_nodes.keys())
    if missing_models:
        raise SystemExit(f"Missing simulation config model classes: {missing_models}")
    write_models(model_nodes, lines)

    generator = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SimulationConfigGenerator"
    )
    methods = {
        node.name: node
        for node in generator.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    groups: dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]] = {
        "context": [],
        "llm": [],
        "time": [],
        "events": [],
        "agents": [],
    }
    for name, node in methods.items():
        group = helper_group(name)
        if group is not None:
            groups[group].append(node)

    if any(not nodes for nodes in groups.values()):
        empty = [group for group, nodes in groups.items() if not nodes]
        raise SystemExit(f"Expected non-empty helper groups, empty: {empty}")

    replacements: dict[int, tuple[int, str]] = {}

    first_model = model_nodes[MODEL_NAMES[0]]
    model_reexports = (
        "from .simulation_config_models import (\n"
        "    AgentActivityConfig as AgentActivityConfig,\n"
        "    EventConfig as EventConfig,\n"
        "    PlatformConfig as PlatformConfig,\n"
        "    SimulationParameters as SimulationParameters,\n"
        "    TimeSimulationConfig as TimeSimulationConfig,\n"
        ")\n"
    )
    replacements[node_start(first_model)] = (first_model.end_lineno, model_reexports)
    for name in MODEL_NAMES[1:]:
        node = model_nodes[name]
        replacements[node_start(node)] = (node.end_lineno, "")

    helper_imports: list[str] = []
    for group, nodes in groups.items():
        filename = f"simulation_config_{group}.py"
        alias = f"_simulation_config_{group}"
        parts = [helper_prelude(group)]
        for node in nodes:
            parts.append(helper_source(node, lines))
            parts.append("\n\n")
        (SERVICE_DIR / filename).write_text("".join(parts).rstrip() + "\n", encoding="utf-8")
        helper_imports.append(f"from . import simulation_config_{group} as {alias}\n")
        for node in nodes:
            replacements[node_start(node)] = (node.end_lineno, wrapper_source(node, alias))

    output: list[str] = []
    line_no = 1
    while line_no <= len(lines):
        if line_no == generator.lineno:
            output.append("\n")
            output.extend(helper_imports)
            output.append("\n")
        replacement = replacements.get(line_no)
        if replacement is not None:
            end, text = replacement
            output.append(text)
            line_no = end + 1
            continue
        output.append(lines[line_no - 1])
        line_no += 1

    new_source = "".join(output)
    TARGET.write_text(new_source, encoding="utf-8")
    ast.parse(new_source)

    generated = [
        TARGET,
        SERVICE_DIR / "simulation_config_models.py",
        *[SERVICE_DIR / f"simulation_config_{group}.py" for group in groups],
    ]
    for path in generated:
        ast.parse(path.read_text(encoding="utf-8"))

    main_loc = len(new_source.splitlines())
    print(f"simulation_config_generator.py: {main_loc} LOC")
    for path in generated[1:]:
        print(f"{path.name}: {len(path.read_text(encoding='utf-8').splitlines())} LOC")
    if main_loc >= 700:
        raise SystemExit(f"simulation_config_generator.py still too large after split: {main_loc} LOC")


if __name__ == "__main__":
    main()
