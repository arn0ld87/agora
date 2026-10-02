"""Regression: die aufgeloeste Modell-ID gehoert genau zu ihrer Completion.

``ClaudeCliModel`` liest pro Aufruf ``modelUsage`` aus dem CLI-Result. Frueher
lag die ID als Instanz-State vor — eine spaetere Antwort ohne ``modelUsage``
erbte dann das Modell des Vorgaengeraufrufs, und ueberlappende Aufrufer
ueberschrieben sich die Zuordnung gegenseitig.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

SLUG = "claude-cli-default"
MESSAGES = [{"role": "user", "content": "Hallo"}]


@pytest.fixture()
def module():
    from sim_runtime import claude_cli_model

    return claude_cli_model


@pytest.fixture()
def model(module, monkeypatch):
    monkeypatch.setattr(module, "_cli_semaphore", None)
    return module.ClaudeCliModel(model_type=SLUG)


def test_response_without_model_usage_falls_back_to_requested_slug(module, model, monkeypatch):
    replies = iter([("erste", "claude-opus-5-5"), ("zweite", None)])

    async def _once(_self, _prompt):
        return next(replies)

    monkeypatch.setattr(module.ClaudeCliModel, "_ainvoke_once", _once)

    first = asyncio.run(model._arun(MESSAGES))
    second = asyncio.run(model._arun(MESSAGES))

    assert first.model == "claude-opus-5-5"
    assert second.model == SLUG


def test_overlapping_calls_keep_their_own_model(module, model, monkeypatch):
    async def _once(_self, prompt):
        # Der zuerst gestartete Aufruf endet zuletzt.
        if "langsam" in prompt:
            await asyncio.sleep(0.05)
            return "langsam", "claude-opus-5-5"
        return "schnell", "claude-sonnet-5-5"

    monkeypatch.setattr(module.ClaudeCliModel, "_ainvoke_once", _once)

    async def _both():
        return await asyncio.gather(
            model._arun([{"role": "user", "content": "langsam"}]),
            model._arun([{"role": "user", "content": "schnell"}]),
        )

    slow, fast = asyncio.run(_both())

    assert slow.model == "claude-opus-5-5"
    assert fast.model == "claude-sonnet-5-5"


def test_sync_path_scopes_model_per_call(module, model, monkeypatch):
    from app.llm.providers import claude_cli

    replies = iter([("erste", "claude-haiku-4-5-20251001"), ("zweite", None)])
    monkeypatch.setattr(
        claude_cli, "_run_claude_cli_with_model", lambda *_a, **_k: next(replies)
    )

    assert model._run(MESSAGES).model == "claude-haiku-4-5-20251001"
    assert model._run(MESSAGES).model == SLUG
