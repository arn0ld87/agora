from __future__ import annotations

import ast
import builtins
import copy
import io
import re
import textwrap
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE_DIR = ROOT / "backend" / "app" / "services"
OASIS_PATH = SERVICE_DIR / "oasis_profile_generator.py"
CONFIG_PATH = SERVICE_DIR / "simulation_config_generator.py"

MODEL_NAMES = [
    "PersonaProfileSchema",
    "PersonaIneligible",
    "CollectivePersonaSchema",
    "OasisAgentProfile",
    "PersonaDemographicSlot",
]

GROUPS: dict[str, tuple[str, list[str]]] = {
    "oasis_profile_core.py": (
        "_oasis_profile_core",
        ["generate_profile_from_entity", "_generate_username"],
    ),
    "oasis_profile_demographics.py": (
        "_oasis_profile_demographics",
        [
            "_pick_dach_name",
            "_last_name",
            "_pick_individual_gender",
            "_largest_remainder_counts",
            "_build_weighted_slots",
            "_build_age_slots",
            "_build_demographic_slots",
            "_build_demographic_slot_prompt_block",
        ],
    ),
    "oasis_profile_context.py": (
        "_oasis_profile_context",
        [
            "_search_graph_for_entity",
            "_build_entity_context",
            "_align_persona_identity",
            "_profession_after_coherence_check",
            "_is_individual_entity",
            "_is_group_entity",
            "_build_eligibility_prompt_block",
        ],
    ),
    "oasis_profile_llm.py": (
        "_oasis_profile_llm",
        ["_generate_profile_with_llm", "_validate_profile_metadata", "_try_fix_json"],
    ),
    "oasis_profile_prompts.py": (
        "_oasis_profile_prompts",
        ["_get_system_prompt", "_build_individual_persona_prompt", "_build_group_persona_prompt"],
    ),
    "oasis_profile_rule_based.py": (
        "_oasis_profile_rule_based",
        [
            "_rule_based_voice_register",
            "_report_persona_degradation",
            "_generate_profile_rule_based",
            "_build_collective_payload",
            "_build_rule_based_payload",
            "_build_generic_person_payload",
        ],
    ),
    "oasis_profile_batch_results.py": (
        "_oasis_profile_batch_results",
        [
            "_backfill_rejected_slots",
            "_consume_gevent_results",
            "_consume_thread_results",
            "_cancel_checkpoint",
        ],
    ),
    "oasis_profile_batch.py": (
        "_oasis_profile_batch",
        ["generate_profiles_from_entities"],
    ),
    "oasis_profile_persistence.py": (
        "_oasis_profile_persistence",
        [
            "_print_generated_profile",
            "save_profiles",
            "_save_twitter_csv",
            "_normalize_gender",
            "_save_reddit_json",
            "save_profiles_to_json",
        ],
    ),
}

# These names are patched by existing tests at the legacy module path.
# Helper modules resolve them dynamically instead of capturing a copy at import time.
DYNAMIC_LEGACY_NAMES = {
    "logger",
    "_resolve_persona_detail_level",
    "_try_repair_truncated_json",
}


def _repair_config_syntax() -> None:
    text = CONFIG_PATH.read_text(encoding="utf-8")
    old = "except json.JSONDecodeError, ValueError:"
    count = text.count(old)
    if count != 2:
        raise SystemExit(f"expected exactly two invalid exception clauses, found {count}")
    text = text.replace(old, "except (json.JSONDecodeError, ValueError):")
    CONFIG_PATH.write_text(text, encoding="utf-8")
    ast.parse(text)


def _node_start(node: ast.AST) -> int:
    decorators = getattr(node, "decorator_list", [])
    return min([node.lineno, *[decorator.lineno for decorator in decorators]])


def _local_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    args = node.args
    for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
        names.add(arg.arg)
    if args.vararg:
        names.add(args.vararg.arg)
    if args.kwarg:
        names.add(args.kwarg.arg)

    # Python function scope is flat for assignments in this function, but nested
    # function/class bodies have their own scopes and must not pollute this set.
    class LocalVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, child: ast.FunctionDef) -> None:
            if child is node:
                self.generic_visit(child)
            else:
                names.add(child.name)

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, child: ast.ClassDef) -> None:
            names.add(child.name)

        def visit_Name(self, child: ast.Name) -> None:
            if isinstance(child.ctx, (ast.Store, ast.Del)):
                names.add(child.id)

        def visit_Import(self, child: ast.Import) -> None:
            for alias in child.names:
                names.add(alias.asname or alias.name.split(".")[0])

        def visit_ImportFrom(self, child: ast.ImportFrom) -> None:
            for alias in child.names:
                names.add(alias.asname or alias.name)

        def visit_ExceptHandler(self, child: ast.ExceptHandler) -> None:
            if child.name:
                names.add(child.name)
            self.generic_visit(child)

    LocalVisitor().visit(node)
    return names


def _global_load_names(nodes: list[ast.FunctionDef | ast.AsyncFunctionDef]) -> set[str]:
    builtins_set = set(dir(builtins)) | {"self", "cls"}
    result: set[str] = set()
    for node in nodes:
        local = _local_names(node)

        class LoadVisitor(ast.NodeVisitor):
            def visit_FunctionDef(self, child: ast.FunctionDef) -> None:
                if child is node:
                    self.generic_visit(child)
                else:
                    # Nested function code is moved together with the parent. Its
                    # true globals are captured separately by walking its body.
                    nested_local = _local_names(child)
                    for nested in ast.walk(child):
                        if (
                            isinstance(nested, ast.Name)
                            and isinstance(nested.ctx, ast.Load)
                            and nested.id not in nested_local
                            and nested.id not in builtins_set
                        ):
                            result.add(nested.id)

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Name(self, child: ast.Name) -> None:
                if (
                    isinstance(child.ctx, ast.Load)
                    and child.id not in local
                    and child.id not in builtins_set
                ):
                    result.add(child.id)

        LoadVisitor().visit(node)
    return result


def _rewrite_dynamic_legacy_names(text: str) -> str:
    output: list[tuple[int, str]] = []
    previous_significant: tuple[int, str] | None = None
    ignored = {tokenize.ENCODING, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT}

    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        token_pair = (token.type, token.string)
        if (
            token.type == tokenize.NAME
            and token.string in DYNAMIC_LEGACY_NAMES
            and previous_significant != (tokenize.OP, ".")
        ):
            output.extend(
                [
                    (tokenize.NAME, "_legacy"),
                    (tokenize.OP, "."),
                    (tokenize.NAME, token.string),
                ]
            )
        else:
            output.append(token_pair)
        if token.type not in ignored:
            previous_significant = token_pair

    return tokenize.untokenize(output)


def _helper_source(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    lines: list[str],
) -> str:
    # Start at `def`, deliberately excluding @staticmethod/@classmethod. The
    # compatibility wrapper on OasisProfileGenerator retains those decorators.
    raw = "".join(lines[node.lineno - 1 : node.end_lineno])
    raw = textwrap.dedent(raw)
    raw = _rewrite_dynamic_legacy_names(raw)

    positional = [*node.args.posonlyargs, *node.args.args]
    if positional and positional[0].arg in {"self", "cls"}:
        first = positional[0].arg
        pattern = rf"((?:async\s+)?def\s+{re.escape(node.name)}\s*\(\s*){first}(?=\s*[,\)])"
        raw, count = re.subn(pattern, rf"\1{first}: Any", raw, count=1, flags=re.S)
        if count != 1:
            raise SystemExit(f"could not annotate first argument for {node.name}")

    return raw.rstrip() + "\n"


def _wrapper_source(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    module_alias: str,
) -> str:
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
    replacement.body = [
        ast.Return(value=ast.Await(value=call))
        if isinstance(node, ast.AsyncFunctionDef)
        else ast.Return(value=call)
    ]
    ast.fix_missing_locations(replacement)
    return textwrap.indent(ast.unparse(replacement), "    ") + "\n"


def _write_models(
    model_nodes: dict[str, ast.ClassDef],
    lines: list[str],
) -> None:
    body = [
        '"""Data contracts for OASIS persona generation.\n\n',
        "Extracted from oasis_profile_generator to keep the public generator facade focused.\n",
        '"""\n\n',
        "from __future__ import annotations\n\n",
        "from dataclasses import dataclass, field\n",
        "from datetime import datetime\n",
        "from typing import Any, Dict, List, Optional\n\n",
        "from pydantic import BaseModel, Field\n\n",
    ]
    for name in MODEL_NAMES:
        node = model_nodes[name]
        body.append("".join(lines[_node_start(node) - 1 : node.end_lineno]).rstrip())
        body.append("\n\n\n")
    (SERVICE_DIR / "oasis_profile_models.py").write_text("".join(body).rstrip() + "\n", encoding="utf-8")


def _split_oasis_generator() -> None:
    source = OASIS_PATH.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    tree = ast.parse(source)

    model_nodes = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in MODEL_NAMES
    }
    missing_models = sorted(set(MODEL_NAMES) - model_nodes.keys())
    if missing_models:
        raise SystemExit(f"missing model classes: {missing_models}")
    _write_models(model_nodes, lines)

    generator = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "OasisProfileGenerator"
    )
    methods = {
        node.name: node
        for node in generator.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    expected_methods = {
        name
        for _filename, (_module_alias, names) in GROUPS.items()
        for name in names
    }
    missing_methods = sorted(expected_methods - methods.keys())
    if missing_methods:
        raise SystemExit(f"missing generator methods: {missing_methods}")

    replacements: dict[int, tuple[int, str]] = {}

    model_import = (
        "from .oasis_profile_models import (\n"
        "    CollectivePersonaSchema,\n"
        "    OasisAgentProfile,\n"
        "    PersonaDemographicSlot,\n"
        "    PersonaIneligible,\n"
        "    PersonaProfileSchema,\n"
        ")\n"
    )
    first_model = model_nodes[MODEL_NAMES[0]]
    replacements[_node_start(first_model)] = (first_model.end_lineno, model_import)
    for name in MODEL_NAMES[1:]:
        node = model_nodes[name]
        replacements[_node_start(node)] = (node.end_lineno, "")

    helper_imports: list[str] = []
    for filename, (module_alias, names) in GROUPS.items():
        nodes = [methods[name] for name in names]
        dependencies = sorted(_global_load_names(nodes) - DYNAMIC_LEGACY_NAMES)
        if "OasisProfileGenerator" in dependencies:
            raise SystemExit(f"{filename} unexpectedly depends on OasisProfileGenerator")

        module = [
            '"""Implementation helpers extracted from OasisProfileGenerator.\n\n',
            "The public compatibility surface remains app.services.oasis_profile_generator.\n",
            '"""\n\n',
            "from __future__ import annotations\n\n",
            "from typing import Any\n\n",
            "from . import oasis_profile_generator as _legacy\n",
        ]
        if dependencies:
            module.append("from .oasis_profile_generator import (\n")
            module.extend(f"    {name},\n" for name in dependencies)
            module.append(")\n")
        module.append("\n")
        for node in nodes:
            module.append(_helper_source(node, lines))
            module.append("\n\n")
        (SERVICE_DIR / filename).write_text("".join(module).rstrip() + "\n", encoding="utf-8")

        helper_imports.append(f"from . import {filename[:-3]} as {module_alias}\n")
        for node in nodes:
            replacements[_node_start(node)] = (
                node.end_lineno,
                _wrapper_source(node, module_alias),
            )

    # Helper modules are imported immediately before the public facade class.
    # At that point all legacy module globals and model re-exports already exist.
    replacements[generator.lineno] = (
        generator.lineno - 1,
        "\n" + "".join(helper_imports) + "\n",
    )

    output: list[str] = []
    line_number = 1
    while line_number <= len(lines):
        if line_number in replacements:
            end, replacement = replacements[line_number]
            output.append(replacement)
            if end < line_number:
                # insertion-only replacement
                del replacements[line_number]
            else:
                line_number = end + 1
                continue
        output.append(lines[line_number - 1])
        line_number += 1

    new_source = "".join(output)
    OASIS_PATH.write_text(new_source, encoding="utf-8")
    ast.parse(new_source)

    loc = len(new_source.splitlines())
    if loc >= 800:
        raise SystemExit(f"oasis_profile_generator.py still P0 after split: {loc} LOC")


def main() -> None:
    _repair_config_syntax()
    _split_oasis_generator()

    generated = [
        OASIS_PATH,
        CONFIG_PATH,
        SERVICE_DIR / "oasis_profile_models.py",
        *[SERVICE_DIR / filename for filename in GROUPS],
    ]
    for path in generated:
        ast.parse(path.read_text(encoding="utf-8"))

    print("Python refactor generated successfully")
    for path in generated:
        print(f"{len(path.read_text(encoding='utf-8').splitlines()):5d} {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
