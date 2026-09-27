"""#1688 (Security-Review 2026-09-26), Items 1 + 2: a workspace-scoped
(JWT/BYOK) run must never gain access to the operator's ``.env`` or to
Tavily-backed agent tools through ``scripts/agent_tools.py``.

Item 1 — ``agent_tools.py`` calls ``load_dotenv(<project_root>/.env)``
unconditionally at import time. ``run_*_simulation.py`` already skip loading
``.env`` for a workspace-scoped run via ``_sim_common.load_project_env``
*before* importing this module, but ``agent_tools`` is also imported lazily
elsewhere in the same runners (``_heuristic_context_limit``,
``enforce_memory_token_limit``) — an ungated module-level ``load_dotenv``
here would repopulate ``LLM_API_KEY``/``LLM_BOOST_*`` from the operator's
``.env`` regardless of that earlier skip.

Item 2 — ``build_camel_function_tools`` attaches ``web_search`` (Tavily),
``web_fetch`` and ``search_graph`` as native CAMEL FunctionTools. For a
workspace-scoped run this must return no tools at all: the operator's
``TAVILY_API_KEY`` must never be reachable through a visitor's simulation.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

# backend/scripts auf sys.path, wie zur Laufzeit des OASIS-Subprozesses.
_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

agent_tools = importlib.import_module("agent_tools")

_SENTINEL_KEY = "AGORA_TEST_DOTENV_SENTINEL_1688"


def _fake_load_dotenv(*_args, **_kwargs):
    """Stand-in for ``dotenv.load_dotenv`` — simulates a `.env` that would
    hand the operator's credential to whoever loads it."""
    os.environ[_SENTINEL_KEY] = "leaked-from-operator-env"


@pytest.fixture(autouse=True)
def _cleanup(monkeypatch):
    os.environ.pop(_SENTINEL_KEY, None)
    yield
    os.environ.pop(_SENTINEL_KEY, None)
    # Restore a clean module state for any test collected after this file —
    # reloaded with the real dotenv/os.path (monkeypatch already undid the
    # patches at this point).
    importlib.reload(agent_tools)


def test_workspace_scope_skips_module_level_dotenv_load(monkeypatch):
    """RED before the fix: import-time ``load_dotenv`` ran unconditionally
    and would have set the sentinel regardless of workspace scope."""
    monkeypatch.setattr(os.path, "exists", lambda _path: True)
    monkeypatch.setattr("dotenv.load_dotenv", _fake_load_dotenv)
    monkeypatch.setenv("AGORA_CREDENTIAL_SCOPE", "workspace")

    importlib.reload(agent_tools)

    assert _SENTINEL_KEY not in os.environ


def test_operator_scope_still_loads_dotenv(monkeypatch):
    """Guard for the guard: an operator run (no workspace-scope signal)
    keeps the legacy behaviour and still loads `.env`."""
    monkeypatch.setattr(os.path, "exists", lambda _path: True)
    monkeypatch.setattr("dotenv.load_dotenv", _fake_load_dotenv)
    monkeypatch.delenv("AGORA_CREDENTIAL_SCOPE", raising=False)

    importlib.reload(agent_tools)

    assert os.environ[_SENTINEL_KEY] == "leaked-from-operator-env"


def test_build_camel_function_tools_empty_for_workspace_scope(monkeypatch):
    """RED before the fix: workspace-scoped simulations still got
    web_search/web_fetch/search_graph FunctionTools attached, i.e. a Tavily
    call reachable via the operator's TAVILY_API_KEY."""
    monkeypatch.setenv("AGORA_CREDENTIAL_SCOPE", "workspace")

    tools = agent_tools.build_camel_function_tools({})

    assert tools == []


def test_build_camel_function_tools_nonempty_for_operator_scope(monkeypatch):
    """Guard for the guard: an operator run still gets its FunctionTools."""
    monkeypatch.delenv("AGORA_CREDENTIAL_SCOPE", raising=False)

    tools = agent_tools.build_camel_function_tools({})

    assert len(tools) >= 2  # web_search + web_fetch at minimum
