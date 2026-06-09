"""Issue #581 — WARNING log when _resolve_num_ctx hits the 8k legacy fallback.

Acceptance criteria (from issue):
1. New WARNING log fires exactly once per unknown model (lru_cache on the warner).
2. Pytest covers: known model (no warning), unknown model (warning fires),
   explicit env override (no warning).

Note: ``agora.llm_client`` uses ``propagate=False`` (setup_logger sets this to avoid
duplicate output), so pytest's ``caplog`` fixture cannot intercept the log records.
We patch ``logger.warning`` directly on the module's logger object instead.
"""

from __future__ import annotations

from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clear_warning_cache() -> None:
    """Clear the lru_cache on _warn_legacy_fallback_once between tests."""
    from app.utils.llm_client import _warn_legacy_fallback_once

    _warn_legacy_fallback_once.cache_clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestResolveNumCtxWarning:
    """WARNING-log behaviour on the legacy 8k fallback path."""

    def setup_method(self) -> None:
        _clear_warning_cache()

    def test_known_model_no_warning(self, monkeypatch):
        """Known heuristic model must NOT produce a WARNING."""
        from app.utils import llm_client

        monkeypatch.delenv("LLM_MODEL_CONTEXT_LIMITS_JSON", raising=False)
        monkeypatch.delenv("LLM_CONTEXT_LIMIT", raising=False)
        monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)

        with patch.object(llm_client.logger, "warning") as mock_warn:
            result = llm_client._resolve_num_ctx(
                model_name="gemini-3-pro:cloud",
                provider_options_num_ctx=None,
            )

        assert result == 1_048_576
        mock_warn.assert_not_called()

    def test_unknown_model_emits_warning(self, monkeypatch):
        """Unknown model hitting legacy fallback must emit exactly one WARNING."""
        from app.utils import llm_client

        monkeypatch.delenv("LLM_MODEL_CONTEXT_LIMITS_JSON", raising=False)
        monkeypatch.delenv("LLM_CONTEXT_LIMIT", raising=False)
        monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)

        with patch.object(llm_client.logger, "warning") as mock_warn:
            result = llm_client._resolve_num_ctx(
                model_name="brand-new-mystery-model:latest",
                provider_options_num_ctx=None,
            )

        assert result == 8192
        mock_warn.assert_called_once()
        call_args = mock_warn.call_args
        # Format string + positional args from logger.warning(fmt, model, fallback)
        assert "brand-new-mystery-model:latest" in str(call_args)
        assert "LLM_MODEL_CONTEXT_LIMITS_JSON" in str(call_args)

    def test_unknown_model_warning_fires_only_once_via_cache(self, monkeypatch):
        """lru_cache must suppress repeated warnings for the same unknown model."""
        from app.utils import llm_client

        monkeypatch.delenv("LLM_MODEL_CONTEXT_LIMITS_JSON", raising=False)
        monkeypatch.delenv("LLM_CONTEXT_LIMIT", raising=False)
        monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)

        with patch.object(llm_client.logger, "warning") as mock_warn:
            llm_client._resolve_num_ctx(
                model_name="mystery-model:v2",
                provider_options_num_ctx=None,
            )
            llm_client._resolve_num_ctx(
                model_name="mystery-model:v2",
                provider_options_num_ctx=None,
            )
            llm_client._resolve_num_ctx(
                model_name="mystery-model:v2",
                provider_options_num_ctx=None,
            )

        assert mock_warn.call_count == 1, (
            f"lru_cache should suppress repeated warnings; got {mock_warn.call_count}"
        )

    def test_explicit_env_override_no_warning(self, monkeypatch):
        """LLM_MODEL_CONTEXT_LIMITS_JSON per-model override must not trigger WARNING."""
        from app.utils import llm_client

        monkeypatch.setenv(
            "LLM_MODEL_CONTEXT_LIMITS_JSON",
            '{"brand-new-mystery-model:latest": 65536}',
        )
        monkeypatch.delenv("LLM_CONTEXT_LIMIT", raising=False)
        monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)

        with patch.object(llm_client.logger, "warning") as mock_warn:
            result = llm_client._resolve_num_ctx(
                model_name="brand-new-mystery-model:latest",
                provider_options_num_ctx=None,
            )

        assert result == 65536
        mock_warn.assert_not_called()

    def test_ollama_num_ctx_env_still_warns(self, monkeypatch):
        """OLLAMA_NUM_CTX is still the legacy fallback path — WARNING fires even
        when the env differs from 8192, since no heuristic matched.
        """
        from app.utils import llm_client

        monkeypatch.delenv("LLM_MODEL_CONTEXT_LIMITS_JSON", raising=False)
        monkeypatch.delenv("LLM_CONTEXT_LIMIT", raising=False)
        monkeypatch.setenv("OLLAMA_NUM_CTX", "16384")

        with patch.object(llm_client.logger, "warning") as mock_warn:
            result = llm_client._resolve_num_ctx(
                model_name="niche-model:7b",
                provider_options_num_ctx=None,
            )

        assert result == 16384
        mock_warn.assert_called_once()

    def test_provider_options_explicit_no_warning(self, monkeypatch):
        """Explicit provider_options.num_ctx must not trigger WARNING."""
        from app.utils import llm_client

        monkeypatch.delenv("LLM_MODEL_CONTEXT_LIMITS_JSON", raising=False)
        monkeypatch.delenv("LLM_CONTEXT_LIMIT", raising=False)
        monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)

        with patch.object(llm_client.logger, "warning") as mock_warn:
            result = llm_client._resolve_num_ctx(
                model_name="brand-new-mystery-model:latest",
                provider_options_num_ctx=32768,
            )

        assert result == 32768
        mock_warn.assert_not_called()

    def test_warning_contains_fallback_value(self, monkeypatch):
        """WARNING message must include the fallback value."""
        from app.utils import llm_client

        monkeypatch.delenv("LLM_MODEL_CONTEXT_LIMITS_JSON", raising=False)
        monkeypatch.delenv("LLM_CONTEXT_LIMIT", raising=False)
        monkeypatch.setenv("OLLAMA_NUM_CTX", "8192")

        with patch.object(llm_client.logger, "warning") as mock_warn:
            llm_client._resolve_num_ctx(
                model_name="totally-unknown-model:x",
                provider_options_num_ctx=None,
            )

        mock_warn.assert_called_once()
        # The warning args include the fallback value as a positional arg
        call_args = mock_warn.call_args
        assert 8192 in call_args.args or "8192" in str(call_args)

    def test_empty_model_name_no_warning(self, monkeypatch):
        """Empty or None model_name must NOT emit a WARNING (unactionable log noise)."""
        from app.utils import llm_client

        monkeypatch.delenv("LLM_MODEL_CONTEXT_LIMITS_JSON", raising=False)
        monkeypatch.delenv("LLM_CONTEXT_LIMIT", raising=False)
        monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)

        with patch.object(llm_client.logger, "warning") as mock_warn:
            result_empty = llm_client._resolve_num_ctx(
                model_name="",
                provider_options_num_ctx=None,
            )
            result_none = llm_client._resolve_num_ctx(
                model_name=None,
                provider_options_num_ctx=None,
            )

        assert result_empty == 8192
        assert result_none == 8192
        mock_warn.assert_not_called()
