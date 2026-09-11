from pathlib import Path

path = Path("backend/scripts/_tmp_refactor_simulation_config.py")
text = path.read_text(encoding="utf-8")
old = '''def helper_source(node: ast.FunctionDef | ast.AsyncFunctionDef, lines: list[str]) -> str:\n    # Deliberately omit class-level decorators. The compatibility wrapper retains\n    # @staticmethod/@classmethod while the implementation helper is a plain function.\n    raw = "".join(lines[node.lineno - 1 : node.end_lineno])\n    return textwrap.dedent(raw).rstrip() + "\\n"\n'''
new = '''def helper_source(node: ast.FunctionDef | ast.AsyncFunctionDef, lines: list[str]) -> str:\n    # Render the method as a module-level function through the AST. This avoids\n    # corrupting indentation inside multiline prompt strings while deliberately\n    # dropping class-only decorators such as @staticmethod.\n    helper = copy.deepcopy(node)\n    helper.decorator_list = []\n    ast.fix_missing_locations(helper)\n    return ast.unparse(helper).rstrip() + "\\n"\n'''
if old not in text:
    raise SystemExit("expected helper_source implementation not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
