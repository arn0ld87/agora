from __future__ import annotations

import ast
import copy
import io
import re
import textwrap
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE_DIR = ROOT / "backend" / "app" / "services"
TARGET = SERVICE_DIR / "prepare_service.py"

GROUPS: dict[str, list[str]] = {
    "prepare_llm.py": ["_resolve_llm_connection"],
    "prepare_entities.py": [
        "_strip_leading_article",
        "_normalize_adjective_endings",
        "_entity_identity_key",
        "_dedupe_entities",
        "_cap_entities_across_types",
        "_phase_read_entities",
    ],
    "prepare_quota.py": [
        "_expand_entities_for_quota",
        "_apply_persona_floor_to_entities",
        "_apply_persona_floor_to_quota_plan",
        "compute_persona_target",
        "_validate_persona_quota",
    ],
}

ALIASES = {
    "prepare_llm.py": "_prepare_llm",
    "prepare_entities.py": "_prepare_entities",
    "prepare_quota.py": "_prepare_quota",
}

ENTITY_DYNAMIC_NAMES = {
    "_LEADING_ARTICLES",
    "_ADJECTIVE_SUFFIXES",
    "_MIN_ADJECTIVE_STEM_LENGTH",
    "EntityReader",
    "filter_eligible_entities",
    "logger",
}


def start_line(node: ast.AST) -> int:
    decorators = getattr(node, "decorator_list", [])
    return min([node.lineno, *[item.lineno for item in decorators]])


def raw_function(node: ast.FunctionDef | ast.AsyncFunctionDef, lines: list[str]) -> str:
    return "".join(lines[start_line(node) - 1 : node.end_lineno]).rstrip() + "\n"


def rewrite_names(text: str, names: set[str], prefix: str) -> str:
    output: list[tuple[int, str]] = []
    previous_significant: tuple[int, str] | None = None
    ignored = {
        tokenize.ENCODING,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.COMMENT,
    }
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        pair = (token.type, token.string)
        if (
            token.type == tokenize.NAME
            and token.string in names
            and previous_significant != (tokenize.OP, ".")
        ):
            output.extend(
                [
                    (tokenize.NAME, prefix),
                    (tokenize.OP, "."),
                    (tokenize.NAME, token.string),
                ]
            )
        else:
            output.append(pair)
        if token.type not in ignored:
            previous_significant = pair
    return tokenize.untokenize(output)


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
    returned: ast.expr = ast.Await(call) if isinstance(node, ast.AsyncFunctionDef) else call
    replacement.body = [ast.Return(returned)]
    replacement.decorator_list = copy.deepcopy(node.decorator_list)
    ast.fix_missing_locations(replacement)
    return ast.unparse(replacement).rstrip() + "\n"


def prelude(filename: str) -> str:
    if filename == "prepare_llm.py":
        return '''"""LLM route resolution for simulation preparation."""

from __future__ import annotations

from typing import Optional

from ..contracts.llm_routing_contract import ResolvedRoute
from ..contracts.provider_types import PROVIDER_CODEX_CLI
from .llm_routing_seed import resolve_route_api_key
from .llm_runtime import RuntimeLlmConfig

LlmRuntimeInput = RuntimeLlmConfig | ResolvedRoute

'''
    if filename == "prepare_entities.py":
        return '''"""Entity selection and graph-read phase for simulation preparation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, List, Optional

from . import prepare_service as _legacy
from .degradation_collector import DegradationCollector

if TYPE_CHECKING:
    from .entity_reader import EntityNode
    from .simulation_manager import SimulationState

'''
    if filename == "prepare_quota.py":
        return '''"""Persona quota, floor and target calculations for simulation preparation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..contracts import PersonaQuotaActual, PersonaQuotaPlan, PersonaTargetContract
from ..utils.logger import get_logger
from .oasis_profile_generator import OasisAgentProfile
from .report_agent import MIN_PERSONA_TABLE_ROWS

logger = get_logger("agora.prepare")

'''
    raise AssertionError(filename)


def main() -> None:
    source = TARGET.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    expected = {name for names in GROUPS.values() for name in names}
    missing = sorted(expected - functions.keys())
    if missing:
        raise SystemExit(f"Missing prepare_service functions: {missing}")

    replacements: dict[int, tuple[int, str]] = {}
    for filename, names in GROUPS.items():
        alias = ALIASES[filename]
        parts = [prelude(filename)]
        for name in names:
            node = functions[name]
            implementation = raw_function(node, lines)
            if filename == "prepare_entities.py":
                implementation = rewrite_names(
                    implementation,
                    ENTITY_DYNAMIC_NAMES,
                    "_legacy",
                )
            parts.append(implementation)
            parts.append("\n\n")
            replacements[start_line(node)] = (node.end_lineno, wrapper_source(node, alias))
        (SERVICE_DIR / filename).write_text("".join(parts).rstrip() + "\n", encoding="utf-8")

    helper_imports = "".join(
        f"from . import {filename[:-3]} as {ALIASES[filename]}\n"
        for filename in GROUPS
    )
    marker = 'logger = get_logger("agora.prepare")\n'
    if marker not in source:
        raise SystemExit("prepare logger marker not found")

    output: list[str] = []
    line_no = 1
    inserted_imports = False
    while line_no <= len(lines):
        replacement = replacements.get(line_no)
        if replacement is not None:
            end, text = replacement
            output.append(text)
            line_no = end + 1
            continue
        output.append(lines[line_no - 1])
        if not inserted_imports and lines[line_no - 1] == marker:
            output.append("\n" + helper_imports)
            inserted_imports = True
        line_no += 1

    new_source = "".join(output)
    # EntityReader/filter_eligible_entities are a compatibility seam: existing
    # tests monkeypatch them on prepare_service. Explicit self-aliases keep Ruff
    # from deleting the facade attributes while prepare_entities resolves them
    # dynamically through _legacy.
    new_source = new_source.replace(
        "from .entity_reader import EntityReader\n",
        "from .entity_reader import EntityReader as EntityReader\n",
        1,
    )
    new_source = new_source.replace(
        "from .persona_eligibility import filter_eligible_entities\n",
        "from .persona_eligibility import filter_eligible_entities as filter_eligible_entities\n",
        1,
    )

    TARGET.write_text(new_source, encoding="utf-8")
    ast.parse(new_source)
    for filename in GROUPS:
        ast.parse((SERVICE_DIR / filename).read_text(encoding="utf-8"))

    loc = len(new_source.splitlines())
    print(f"prepare_service.py: {loc} LOC")
    for filename in GROUPS:
        path = SERVICE_DIR / filename
        print(f"{filename}: {len(path.read_text(encoding='utf-8').splitlines())} LOC")
    if loc >= 800:
        raise SystemExit(f"prepare_service.py remains too large after split: {loc} LOC")


if __name__ == "__main__":
    main()
