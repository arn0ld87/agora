"""Regression gate: every scope used in @allow_ticket_auth must be covered
by auth._ALLOWED_SCOPE_PREFIXES.

Uses AST introspection so it catches *all* decorated endpoints without
relying on the application being fully importable (avoids heavy fixture
setup) and without regex approximations.

Callable scopes that compute at runtime (non-literal, non-name lambda
bodies) are skipped with an explanatory comment — those require
integration-level tests.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Generator


def _extract_module_constants(tree: ast.Module) -> dict[str, str]:
    """Return a mapping of top-level string constant assignments, e.g.
    ``_TICKET_SCOPE = "llm-stream"`` → ``{"_TICKET_SCOPE": "llm-stream"}``.
    """
    constants: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                    if isinstance(node.value.value, str):
                        constants[target.id] = node.value.value
    return constants


def _scope_prefix_from_lambda(
    lambda_node: ast.Lambda,
    module_constants: dict[str, str],
) -> str | None:
    """Extract the literal scope prefix from a ``lambda`` AST node.

    Handled forms:
    - ``lambda: "literal"``         → returns ``"literal"``
    - ``lambda: NAME``              → resolves NAME from module constants
    - ``lambda param: f"prefix:{param}"``  → returns the static prefix
      (everything before the first ``{``)

    Returns ``None`` for anything that requires runtime evaluation —
    those get an explicit skip in the caller.
    """
    body = lambda_node.body

    # Case 1: plain string constant — lambda: "literal"
    if isinstance(body, ast.Constant) and isinstance(body.value, str):
        return body.value

    # Case 2: bare name resolved via module-level constant — lambda: _TICKET_SCOPE
    if isinstance(body, ast.Name):
        return module_constants.get(body.id)

    # Case 3: f-string — lambda param: f"prefix:{param}"
    # ast.JoinedStr represents an f-string.  We take the leading
    # Constant part (the static prefix) — it must start the f-string.
    if isinstance(body, ast.JoinedStr) and body.values:
        first = body.values[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value  # e.g. "download:report:"

    # Anything else (concat, call, …) is a runtime value — caller skips it.
    return None


def _collect_scopes(
    api_dir: pathlib.Path,
) -> Generator[tuple[pathlib.Path, str]]:
    """Yield ``(source_file, scope_or_prefix)`` for every
    ``@allow_ticket_auth(...)`` decoration found via AST walk.

    Yields the *literal* scope or the static prefix of an f-string template.
    Runtime-computed scopes are skipped (commented out below).
    """
    for py_file in sorted(api_dir.glob("*.py")):
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        constants = _extract_module_constants(tree)

        for node in ast.walk(tree):
            # We look for decorated function/async-function definitions.
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            for decorator in node.decorator_list:
                # Decorator must be a Call node.
                if not isinstance(decorator, ast.Call):
                    continue

                # The callable part must be the name "allow_ticket_auth".
                func = decorator.func
                if not (isinstance(func, ast.Name) and func.id == "allow_ticket_auth"):
                    continue

                # First positional argument must be the scope lambda.
                if not decorator.args:
                    continue
                first_arg = decorator.args[0]
                if not isinstance(first_arg, ast.Lambda):
                    # Callable scope that isn't a lambda — skip, runtime-only.
                    continue

                prefix = _scope_prefix_from_lambda(first_arg, constants)
                if prefix is None:
                    # Runtime-computed scope: cannot be statically verified.
                    # Add an explicit integration test for this endpoint instead.
                    continue

                yield py_file, prefix


def test_every_allow_ticket_auth_scope_is_whitelisted() -> None:
    """Every literal scope passed to @allow_ticket_auth(...) must be allowed
    by auth._ALLOWED_SCOPE_PREFIXES. Prevents regressions like #558."""

    from app.api.auth import _ALLOWED_SCOPE_PREFIXES  # noqa: PLC0415

    api_dir = pathlib.Path(__file__).parents[2] / "app" / "api"
    assert api_dir.is_dir(), f"API directory not found: {api_dir}"

    literal_scopes: list[tuple[pathlib.Path, str]] = list(_collect_scopes(api_dir))

    # Sanity-check: we must have discovered *some* scopes.  If this assertion
    # fires after a structural refactor, update the collection logic above.
    assert literal_scopes, (
        "No @allow_ticket_auth scopes were discovered — "
        "check that the AST walker still matches the decorator form."
    )

    failures: list[str] = []
    for path, scope in literal_scopes:
        # Scopes that end with ":" are prefixes (f-string templates like
        # "download:report:").  Append a dummy segment to test them as full
        # scope strings against _scope_is_allowed logic.
        test_scope = scope + "dummy" if scope.endswith(":") else scope
        allowed = any(test_scope.startswith(p) for p in _ALLOWED_SCOPE_PREFIXES)
        if not allowed:
            failures.append(
                f"  {path.name}: scope {test_scope!r} (from prefix {scope!r}) "
                f"not covered by _ALLOWED_SCOPE_PREFIXES"
            )

    assert not failures, (
        "The following scopes are used in @allow_ticket_auth but NOT whitelisted "
        "in backend/app/api/auth.py _ALLOWED_SCOPE_PREFIXES:\n"
        + "\n".join(failures)
    )
