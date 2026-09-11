from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE_DIR = ROOT / "backend" / "app" / "services"
GENERATOR = SERVICE_DIR / "oasis_profile_generator.py"

MODEL_NAMES = {
    "CollectivePersonaSchema",
    "OasisAgentProfile",
    "PersonaDemographicSlot",
    "PersonaIneligible",
    "PersonaProfileSchema",
}


def _binding_map(tree: ast.Module) -> dict[str, tuple[str, object]]:
    mapping: dict[str, tuple[str, object]] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                binding = alias.asname or alias.name.split(".")[0]
                mapping[binding] = ("import", alias)
        elif isinstance(node, ast.ImportFrom):
            # Do not map the model re-export back through the facade.
            if node.level == 1 and node.module == "oasis_profile_models":
                continue
            for alias in node.names:
                binding = alias.asname or alias.name
                mapping[binding] = ("from", (node.level, node.module, alias))
    return mapping


def _render_direct_imports(names: list[str], mapping: dict[str, tuple[str, object]]) -> str:
    plain_imports: list[ast.alias] = []
    from_groups: dict[tuple[int, str | None], list[ast.alias]] = defaultdict(list)
    facade_names: list[str] = []

    for name in names:
        if name in MODEL_NAMES:
            from_groups[(1, "oasis_profile_models")].append(ast.alias(name=name))
            continue
        entry = mapping.get(name)
        if entry is None:
            # Constants/functions genuinely owned by the compatibility facade.
            facade_names.append(name)
            continue
        kind, payload = entry
        if kind == "import":
            alias = payload
            assert isinstance(alias, ast.alias)
            plain_imports.append(ast.alias(name=alias.name, asname=alias.asname))
        else:
            level, module, alias = payload
            assert isinstance(alias, ast.alias)
            from_groups[(level, module)].append(ast.alias(name=alias.name, asname=alias.asname))

    nodes: list[ast.stmt] = []
    if plain_imports:
        nodes.append(ast.Import(names=plain_imports))
    for (level, module), aliases in sorted(from_groups.items(), key=lambda item: (item[0][0], item[0][1] or "")):
        nodes.append(ast.ImportFrom(module=module, names=aliases, level=level))
    if facade_names:
        nodes.append(
            ast.ImportFrom(
                module="oasis_profile_generator",
                names=[ast.alias(name=name) for name in sorted(facade_names)],
                level=1,
            )
        )

    for node in nodes:
        ast.fix_missing_locations(node)
    return "\n".join(ast.unparse(node) for node in nodes) + ("\n" if nodes else "")


def _rewire_helper(path: Path, mapping: dict[str, tuple[str, object]]) -> None:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    target = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.level == 1
            and node.module == "oasis_profile_generator"
        ),
        None,
    )
    if target is None:
        return

    names = [alias.asname or alias.name for alias in target.names]
    replacement = _render_direct_imports(names, mapping)
    lines = source.splitlines(keepends=True)
    new_source = "".join(lines[: target.lineno - 1]) + replacement + "".join(lines[target.end_lineno :])
    path.write_text(new_source, encoding="utf-8")
    ast.parse(new_source)


def main() -> None:
    source = GENERATOR.read_text(encoding="utf-8")
    tree = ast.parse(source)
    mapping = _binding_map(tree)

    for path in sorted(SERVICE_DIR.glob("oasis_profile_*.py")):
        if path.name in {"oasis_profile_generator.py", "oasis_profile_models.py"}:
            continue
        _rewire_helper(path, mapping)

    # Existing tests patch this symbol on the legacy module. Mark the import as
    # an explicit compatibility re-export so Ruff does not delete it.
    source = GENERATOR.read_text(encoding="utf-8")
    old = "from ..llm.json_mode import _try_repair_truncated_json\n"
    new = "from ..llm.json_mode import _try_repair_truncated_json as _try_repair_truncated_json\n"
    if old in source:
        source = source.replace(old, new, 1)
    GENERATOR.write_text(source, encoding="utf-8")
    ast.parse(source)


if __name__ == "__main__":
    main()
