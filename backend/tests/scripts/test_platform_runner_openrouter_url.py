"""Der Einzelplattform-Runner reicht die Basis-URL an die Completion-Parameter weiter.

Regression (Review #1779): ``platform_runner.py`` rief
``build_camel_completion_params`` ohne ``base_url`` auf. Der Helper erkannte
OpenRouter deshalb nicht und sendete kein ``reasoning_effort``; der
Parallel-Runner tat es.
"""
from __future__ import annotations

import ast
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _completion_param_calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "build_camel_completion_params"
    ]


def test_both_runners_pass_the_base_url_to_the_completion_params() -> None:
    for name in ("sim_runtime/platform_runner.py", "run_parallel_simulation.py"):
        calls = _completion_param_calls(_SCRIPTS / name)
        assert calls, name
        for call in calls:
            assert "base_url" in {keyword.arg for keyword in call.keywords}, name
