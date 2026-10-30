"""Tests for CLI session preflight and writability checks (Issue #1834).

Verifies that:
1. Writable and non-writable session mounts are properly distinguished.
2. `session_dir_not_writable` reports accurate details (UID, path).
3. `AGORA_CODEX_HOME` is respected as fallback when `CODEX_HOME` is not set.
4. Preflight fails fast with `LlmProviderError` (provider_unavailable) on unready sessions.
5. `LLMClient.from_route` logs route source and stage diagnostics.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from app.contracts.ai_provider_contract import AiRoute
from app.contracts.llm_routing_contract import ResolvedRoute
from app.llm.errors import LlmProviderError
from app.llm.providers import codex_cli as codex_cli_mod
from app.llm.providers.codex_cli import (
    CodexCliReadiness,
    codex_cli_credential_state,
    codex_cli_home,
    verify_codex_cli_session_ready,
)
from app.services.preflight_cli_session import (
    verify_cli_session_preflight,
    verify_route_cli_preflight,
)
from app.services.stage_model_router import StageModelRouter


class TestCodexCliSessionWritability:
    def test_writable_session_dir_is_ok(self, tmp_path):
        home = tmp_path / "codex_home"
        home.mkdir()
        (home / "session.json").write_text("{}")
        assert codex_cli_credential_state(home) == "ok"

    def test_writable_sessions_subdir_is_ok(self, tmp_path):
        home = tmp_path / "codex_home"
        sessions = home / "sessions"
        sessions.mkdir(parents=True)
        (sessions / "state.json").write_text("{}")
        assert codex_cli_credential_state(home) == "ok"

    def test_non_writable_home_is_detected_as_session_dir_not_writable(
        self, tmp_path, monkeypatch
    ):
        home = tmp_path / "codex_home"
        home.mkdir()
        (home / "session.json").write_text("{}")

        # Mock _check_directory_writable to simulate root-owned unwritable dir for non-root users
        monkeypatch.setattr(
            codex_cli_mod, "_check_directory_writable", lambda directory: False
        )
        assert codex_cli_credential_state(home) == "session_dir_not_writable"

    def test_readiness_status_message_includes_uid_and_hint_when_not_writable(
        self, tmp_path, monkeypatch
    ):
        readiness = CodexCliReadiness(
            binary_present=True,
            home=tmp_path,
            credentials="session_dir_not_writable",
        )
        assert readiness.ready is False
        msg = readiness.status_message or ""
        assert "nicht beschreibbar" in msg
        assert "uid=" in msg
        assert "AGORA_CODEX_HOME" in msg

    def test_verify_session_ready_raises_llm_provider_error_when_not_writable(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(codex_cli_mod, "is_codex_cli_available", lambda: True)
        monkeypatch.setattr(codex_cli_mod, "codex_cli_home", lambda: tmp_path)
        monkeypatch.setattr(
            codex_cli_mod,
            "codex_cli_credential_state",
            lambda home=None: "session_dir_not_writable",
        )

        with pytest.raises(LlmProviderError) as exc_info:
            verify_codex_cli_session_ready()

        assert exc_info.value.normalized.provider == "codex_cli"
        assert exc_info.value.normalized.code == "provider_unavailable"
        assert "nicht beschreibbar" in exc_info.value.normalized.message

    def test_home_prioritizes_codex_home_then_agora_codex_home(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.delenv(codex_cli_mod.CODEX_HOME_ENV, raising=False)
        monkeypatch.delenv(codex_cli_mod.AGORA_CODEX_HOME_ENV, raising=False)

        # 1. Fallback to ~/.codex
        monkeypatch.setenv("HOME", str(tmp_path))
        assert codex_cli_home() == tmp_path / ".codex"

        # 2. AGORA_CODEX_HOME
        agora_dir = tmp_path / "agora_codex"
        monkeypatch.setenv(codex_cli_mod.AGORA_CODEX_HOME_ENV, str(agora_dir))
        assert codex_cli_home() == agora_dir

        # 3. CODEX_HOME takes precedence over AGORA_CODEX_HOME
        codex_dir = tmp_path / "explicit_codex"
        monkeypatch.setenv(codex_cli_mod.CODEX_HOME_ENV, str(codex_dir))
        assert codex_cli_home() == codex_dir


class TestPreflightCliSessionService:
    def test_verify_cli_session_preflight_noop_for_non_cli_provider(self):
        # Should not raise for standard providers
        verify_cli_session_preflight("openai", stage="report_generation")
        verify_cli_session_preflight("ollama", stage="simulation_rounds")

    def test_verify_cli_session_preflight_checks_codex_cli(self, monkeypatch):
        mock_verify = MagicMock()
        monkeypatch.setattr(
            "app.services.preflight_cli_session.verify_codex_cli_session_ready",
            mock_verify,
        )

        verify_cli_session_preflight(
            "codex_cli", stage="report_generation", run_id="run-123"
        )
        mock_verify.assert_called_once()

    def test_verify_route_cli_preflight_delegates_to_provider_check(self, monkeypatch):
        mock_verify = MagicMock()
        monkeypatch.setattr(
            "app.services.preflight_cli_session.verify_cli_session_preflight",
            mock_verify,
        )

        route = ResolvedRoute(
            stage="report_generation",
            provider_id="codex_cli",
            model="gpt-5-codex",
            base_url_sanitized=None,
            reasoning_effort="none",
            routing_version=1,
            provider_options={"source": "stage_override"},
            started_at="2026-10-30T00:00:00Z",
        )

        verify_route_cli_preflight(route, run_id="run-456")
        mock_verify.assert_called_once_with(
            "codex_cli", stage="report_generation", run_id="run-456"
        )


class TestClientRouteTransparency:
    def test_resolved_route_from_ai_route_preserves_source_and_fallback_reason(self):
        router = StageModelRouter(run_id="run-test")
        ai_route = AiRoute(
            stage="report_generation",
            provider_connection_id="codex_cli",
            model_id="gpt-5-codex",
            source="stage_override",
            fallback_reason=None,
            provider_options={},
            routing_version=1,
        )

        resolved = router._resolved_route_from_ai_route("report_generation", ai_route, 1)
        assert resolved.provider_options.get("source") == "stage_override"
        assert resolved.provider_id == "codex_cli"
        assert resolved.model == "gpt-5-codex"

    def test_from_route_logs_source_diagnostics(self, monkeypatch, caplog):
        from app.llm.client import LLMClient

        route = ResolvedRoute(
            stage="report_generation",
            provider_id="codex_cli",
            model="codex-cli-default",
            base_url_sanitized=None,
            reasoning_effort="none",
            routing_version=1,
            provider_options={"source": "stage_override"},
            started_at="2026-10-30T00:00:00Z",
        )

        # Mock codex readiness so LLMClient can initialize without real codex
        monkeypatch.setattr(codex_cli_mod, "is_codex_cli_available", lambda: True)
        monkeypatch.setattr(
            codex_cli_mod, "codex_cli_credential_state", lambda home=None: "ok"
        )

        with caplog.at_level(logging.INFO):
            client = LLMClient.from_route(route, run_id="run-789")

        assert client._codex_cli_active is True
        assert any(
            "LLMClient.from_route: stage=report_generation provider_id=codex_cli model=codex-cli-default source=stage_override run_id=run-789"
            in record.message
            for record in caplog.records
        )
