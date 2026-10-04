"""Paritaets- und Delegationstests fuer ``app.llm.model_capabilities`` (#1766).

Die Wahrheitstabelle unten wurde VOR dem Refactoring durch Ausfuehren des
damaligen Codes beider Seiten ermittelt (App-Pfad ``providers/openai.py`` und
Simulations-Pfad ``scripts/_sim_common.py``) und ist feste Erwartung. Sie
belegt, dass die Zusammenfuehrung kein beobachtbares Verhalten aendert --
einschliesslich der zwei bewusst erhaltenen Abweichungen (``o1.5-turbo``,
``o3.1``: App ``True``, Simulation ``False``).
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import _sim_common  # noqa: E402

from app.llm import model_capabilities as caps  # noqa: E402
from app.llm.client import LLMClient  # noqa: E402
from app.llm.providers import openai as app_openai  # noqa: E402

# (Modellname, App: Reasoning-Familie, Sim: max_completion_tokens, Sim: reasoning_effort "none")
#
# "App: Reasoning-Familie" gilt identisch fuer uses_max_completion_tokens,
# omits_temperature und reasoning_effort_kwargs(provider="openai").
TRUTH_TABLE: list[tuple[str, bool, bool, bool]] = [
    ("", False, False, False),
    (" gpt-6-luna ", True, True, True),
    ("GPT-5", True, True, False),
    ("GPT-6-Luna", True, True, True),
    ("O1-MINI", True, True, False),
    ("claude-opus-5", False, False, False),
    ("deepseek-chat", False, False, False),
    ("gpt-10", False, False, False),
    ("gpt-4-turbo", False, False, False),
    ("gpt-4.1", False, False, False),
    ("gpt-4o", False, False, False),
    ("gpt-5", True, True, False),
    ("gpt-5-mini", True, True, False),
    ("gpt-5.0", True, True, False),
    ("gpt-5.0-x", True, True, False),
    ("gpt-5.1", True, True, True),
    ("gpt-5.1-mini", True, True, True),
    ("gpt-5.10", True, True, True),
    ("gpt-5.6-luna", True, True, True),
    ("gpt-5.x", True, True, False),
    ("gpt-500", False, False, False),
    ("gpt-6", True, True, True),
    ("gpt-6-astra", True, True, True),
    ("gpt-6-luna", True, True, True),
    ("gpt-6-sol", True, True, True),
    ("gpt-6.1", True, True, True),
    ("gpt-6.1-sol", True, True, True),
    ("gpt-60", False, False, False),
    ("gpt-6o", False, False, False),
    ("gpt-7", True, True, True),
    ("gpt-9-x", True, True, True),
    ("gpt-oss:cloud", False, False, False),
    ("o1", True, True, False),
    ("o1-mini", True, True, False),
    # Bewusst erhaltene Divergenz: App akzeptiert die ``.``-Grenze, Simulation nicht.
    ("o1.5-turbo", True, False, False),
    ("o1preview", False, False, False),
    ("o3-mini", True, True, False),
    ("o3.1", True, False, False),
    ("o4-mini", True, True, False),
    ("oasis-model", False, False, False),
    ("qwen3", False, False, False),
]

DIVERGENT_MODELS = [m for m, app, sim, _ in TRUTH_TABLE if app != sim]


def test_truth_table_documents_exactly_the_known_divergences() -> None:
    assert sorted(DIVERGENT_MODELS) == ["o1.5-turbo", "o3.1"]


@pytest.mark.parametrize(("model", "family", "sim_max_completion", "sim_none"), TRUTH_TABLE)
class TestSharedModuleMatchesPreRefactorBehavior:
    def test_shared_module(
        self, model: str, family: bool, sim_max_completion: bool, sim_none: bool
    ) -> None:
        assert caps.is_reasoning_family(model) is family
        assert caps.uses_max_completion_tokens(model) is family
        assert caps.omits_temperature(model) is family
        assert caps.uses_max_completion_tokens_hyphen_boundary(model) is sim_max_completion
        assert caps.supports_reasoning_effort_none(model) is sim_none

    def test_app_entry_points(
        self, model: str, family: bool, sim_max_completion: bool, sim_none: bool
    ) -> None:
        assert app_openai._is_reasoning_family(model) is family
        assert app_openai.uses_max_completion_tokens(model) is family
        assert app_openai.omits_temperature(model) is family
        assert LLMClient._uses_max_completion_tokens(model) is family

        def kwargs(provider: str, **extra: Any) -> dict[str, Any]:
            return app_openai.reasoning_effort_kwargs(
                provider=provider, model=model, **extra
            )

        assert kwargs("openai", effort=None) == (
            {"reasoning_effort": "none"} if family else {}
        )
        assert kwargs("openai", effort="high") == (
            {"reasoning_effort": "high"} if family else {}
        )
        assert kwargs("openai", effort="high", force_no_thinking=True) == (
            {"reasoning_effort": "none"} if family else {}
        )
        # Provider-Bedingung bleibt: nur "openai" bekommt den Parameter.
        assert kwargs("ollama", effort=None) == {}
        assert kwargs("", effort="high") == {}

    def test_simulation_entry_points(
        self, model: str, family: bool, sim_max_completion: bool, sim_none: bool
    ) -> None:
        assert _sim_common.uses_max_completion_tokens(model) is sim_max_completion
        assert _sim_common.supports_reasoning_effort_none(model) is sim_none

        expected: dict[str, Any] = {
            ("max_completion_tokens" if sim_max_completion else "max_tokens"): 7
        }
        if sim_none:
            expected["reasoning_effort"] = "none"
        assert (
            _sim_common.build_camel_completion_params(model=model, completion_max_tokens=7)
            == expected
        )


@pytest.mark.parametrize(
    "fn",
    [
        caps.is_reasoning_family,
        caps.uses_max_completion_tokens,
        caps.omits_temperature,
        caps.uses_max_completion_tokens_hyphen_boundary,
        caps.supports_reasoning_effort_none,
    ],
)
def test_none_is_never_a_capable_model(fn: Any) -> None:
    # Der App-Pfad reichte schon vorher ``self.model or ""`` bzw. tolerierte None;
    # die Simulations-Funktionen warfen AttributeError. Jetzt einheitlich False.
    assert fn(None) is False


# ----------------------------------------------------------------------
# Delegation: beide Pfade lesen dieselbe Definition
# ----------------------------------------------------------------------


def test_simulation_wrappers_delegate_to_shared_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def fake_max(model: str | None) -> bool:
        calls.append(("max", str(model)))
        return "sentinel-max"  # type: ignore[return-value]

    def fake_none(model: str | None) -> bool:
        calls.append(("none", str(model)))
        return "sentinel-none"  # type: ignore[return-value]

    monkeypatch.setattr(caps, "uses_max_completion_tokens_hyphen_boundary", fake_max)
    monkeypatch.setattr(caps, "supports_reasoning_effort_none", fake_none)

    assert _sim_common.uses_max_completion_tokens("x") == "sentinel-max"
    assert _sim_common.supports_reasoning_effort_none("y") == "sentinel-none"
    assert calls == [("max", "x"), ("none", "y")]


def test_app_wrappers_delegate_to_shared_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(caps, "is_reasoning_family", lambda model: model == "sentinel")

    assert app_openai._is_reasoning_family("sentinel") is True
    assert app_openai.uses_max_completion_tokens("sentinel") is True
    assert app_openai.omits_temperature("sentinel") is True
    assert app_openai.reasoning_effort_kwargs(
        provider="openai", model="sentinel", effort=None
    ) == {"reasoning_effort": "none"}
    assert app_openai.uses_max_completion_tokens("gpt-6") is False


def test_no_duplicate_model_name_regex_outside_shared_module() -> None:
    """Die Doppelung darf nicht zurueckkehren: keine ``gpt-N``-Regex in den Wrappern."""
    for path in (
        _BACKEND_DIR / "app" / "llm" / "providers" / "openai.py",
        _SCRIPTS_DIR / "_sim_common.py",
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and "gpt-[" in node.value
        ]
        assert offenders == [], f"{path.name} definiert Modellnamen-Regex neu: {offenders}"


# ----------------------------------------------------------------------
# Seiteneffektfreier Import
# ----------------------------------------------------------------------


def test_module_imports_only_stdlib() -> None:
    path = _BACKEND_DIR / "app" / "llm" / "model_capabilities.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "re"}


def test_module_loads_without_flask_or_pydantic() -> None:
    """Dateipfad-Import (ohne ``app/__init__``) zieht weder Flask noch Pydantic.

    Hinweis: ``import app.llm.model_capabilities`` fuehrt ``app/__init__.py``
    aus (Flask, Config); der Simulations-Subprozess importiert ``app`` ohnehin
    (``run_parallel_simulation`` -> ``app.config``). Die Eigenschaft hier gilt
    fuer das Modul selbst.
    """
    path = _BACKEND_DIR / "app" / "llm" / "model_capabilities.py"
    code = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('mc', {str(path)!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "sys.modules['mc'] = mod\n"
        "spec.loader.exec_module(mod)\n"
        "assert mod.supports_reasoning_effort_none('gpt-6') is True\n"
        "loaded = sorted(m for m in ('flask', 'pydantic', 'app') if m in sys.modules)\n"
        "print(','.join(loaded))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == ""
