"""Tests für Workspace-Routing-Store."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.contracts.llm_routing_contract import StageLLMRoute
from app.contracts.workspace_routing_contract import WorkspaceLlmRoutingDefaults
from app.services.workspace_routing_store import (
    WorkspaceRoutingStore,
    get_workspace_routing_store,
    reset_singleton_for_tests,
)


@pytest.fixture
def store(tmp_path: Path):
    s = WorkspaceRoutingStore(data_dir=tmp_path)
    yield s


def test_load_empty_returns_defaults(store):
    defaults = store.load()
    assert isinstance(defaults, WorkspaceLlmRoutingDefaults)
    assert defaults.stage_overrides == {}


def test_save_and_load_roundtrip(store):
    payload = WorkspaceLlmRoutingDefaults(
        global_default=StageLLMRoute(provider_id="openai", model="gpt-4o-mini"),
        stage_overrides={
            "report_generation": StageLLMRoute(provider_id="openai", model="gpt-4o"),
        },
    )
    store.save(payload)
    loaded = store.load()
    assert loaded.global_default.model == "gpt-4o-mini"
    assert loaded.stage_overrides["report_generation"].model == "gpt-4o"
    assert loaded.updated_at is not None


def test_set_stage_override(store):
    route = StageLLMRoute(provider_id="google", model="gemini-1.5-pro")
    updated = store.set_stage_override("persona_generation", route)
    assert updated.stage_overrides["persona_generation"].model == "gemini-1.5-pro"


def test_clear_stage_override(store):
    route = StageLLMRoute(provider_id="google", model="gemini-1.5-pro")
    store.set_stage_override("persona_generation", route)
    cleared = store.set_stage_override("persona_generation", None)
    assert "persona_generation" not in cleared.stage_overrides


def test_set_global_default(store):
    route = StageLLMRoute(provider_id="openai", model="gpt-4o-mini")
    updated = store.set_global_default(route)
    assert updated.global_default.model == "gpt-4o-mini"


def test_singleton_uses_env_data_dir(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    reset_singleton_for_tests()
    s = get_workspace_routing_store()
    s.set_global_default(StageLLMRoute(provider_id="openai", model="gpt-4o"))
    assert (tmp_path / "workspace_llm_routing.json").exists()
    reset_singleton_for_tests()
