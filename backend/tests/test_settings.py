"""
Unit-Tests für backend/app/settings.py (ADR-0003 PR 1).

Jede Test-Klasse ist isoliert via monkeypatch.setenv / monkeypatch.delenv;
kein Test berührt app.config.Config oder importiert es.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.services.settings_schema import field_by_key
from app.settings import AgoraSettings, get_settings, reload_settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build(**env_overrides: str) -> AgoraSettings:
    """Construct AgoraSettings with _env_file=None and given env values."""
    return AgoraSettings(_env_file=None, **env_overrides)


def _build_debug(monkeypatch, **extra: str) -> AgoraSettings:
    """
    Construct a debug-mode AgoraSettings without reading any .env file.

    Sets the minimum env vars required to pass all prod-guard validators
    in debug mode (only LLM_API_KEY is checked universally).
    """
    defaults = {
        "FLASK_DEBUG": "true",
        "LLM_API_KEY": "dummy",
    }
    defaults.update(extra)
    for k, v in defaults.items():
        monkeypatch.setenv(k, v)
    return AgoraSettings(_env_file=None)


# ---------------------------------------------------------------------------
# 1. Defaults
# ---------------------------------------------------------------------------

class TestDefaults:
    """AgoraSettings with _env_file=None returns hard-coded defaults."""

    @pytest.fixture(autouse=True)
    def _min_env(self, monkeypatch):
        """Minimum env so validators pass (debug=True, LLM_API_KEY set)."""
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.setenv("LLM_API_KEY", "dummy")

    def test_llm_base_url_default(self):
        s = AgoraSettings(_env_file=None)
        assert s.llm_base_url == field_by_key("LLM_BASE_URL").default

    def test_neo4j_uri_default(self):
        s = AgoraSettings(_env_file=None)
        assert s.neo4j_uri == field_by_key("NEO4J_URI").default

    def test_report_toolcall_mode_default(self):
        s = AgoraSettings(_env_file=None)
        assert s.report_toolcall_mode == "native"

    def test_vector_dim_default(self):
        # nomic-embed-text → 768
        s = AgoraSettings(_env_file=None)
        assert s.vector_dim == field_by_key("VECTOR_DIM").default

    def test_debug_default_false(self, monkeypatch):
        monkeypatch.delenv("FLASK_DEBUG", raising=False)
        # Need prod-mode min env to avoid ValidationError
        monkeypatch.setenv("SECRET_KEY", "PLACEHOLDER_NOT_A_REAL_SECRET_xxxx")  # noqa: S105 — pytest test fixture, ggignore
        monkeypatch.setenv("NEO4J_PASSWORD", "PLACEHOLDER_NOT_A_REAL_PW_xxxx")  # noqa: S105 — pytest test fixture, ggignore
        monkeypatch.setenv("AGORA_AUTH_TOKEN", "PLACEHOLDER_NOT_A_REAL_TOKEN_xx")  # noqa: S105 — pytest test fixture, ggignore
        s = AgoraSettings(_env_file=None)
        assert s.debug is False

    def test_llm_model_name_default(self):
        s = AgoraSettings(_env_file=None)
        assert s.llm_model_name == field_by_key("LLM_MODEL_NAME").default

    def test_llm_max_output_tokens_default(self):
        s = AgoraSettings(_env_file=None)
        assert s.llm_max_output_tokens == field_by_key("LLM_MAX_OUTPUT_TOKENS").default

    def test_llm_context_limit_default(self):
        s = AgoraSettings(_env_file=None)
        assert s.llm_context_limit == field_by_key("LLM_CONTEXT_LIMIT").default

    def test_embedding_model_default(self):
        s = AgoraSettings(_env_file=None)
        assert s.embedding_model == field_by_key("EMBEDDING_MODEL").default

    def test_ontology_mutation_mode_default(self):
        s = AgoraSettings(_env_file=None)
        assert s.ontology_mutation_mode == "disabled"

    def test_event_bus_backend_default(self):
        s = AgoraSettings(_env_file=None)
        assert s.event_bus_backend == "auto"

    def test_agora_log_format_default(self):
        s = AgoraSettings(_env_file=None)
        assert s.agora_log_format == "text"

    def test_persona_review_enabled_default(self):
        s = AgoraSettings(_env_file=None)
        assert s.persona_review_enabled is False

    def test_llm_model_context_limits_default_empty_dict(self):
        s = AgoraSettings(_env_file=None)
        assert s.llm_model_context_limits == {}

    def test_redis_url_default(self):
        s = AgoraSettings(_env_file=None)
        assert s.redis_url == field_by_key("REDIS_URL").default


# ---------------------------------------------------------------------------
# 2. Env Override
# ---------------------------------------------------------------------------

class TestEnvOverride:
    """monkeypatch.setenv overrides each field type correctly."""

    @pytest.fixture(autouse=True)
    def _debug_env(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.setenv("LLM_API_KEY", "dummy")

    def test_str_field_override(self, monkeypatch):
        monkeypatch.setenv("LLM_BASE_URL", "http://myhost:1234/v1")
        s = AgoraSettings(_env_file=None)
        assert s.llm_base_url == "http://myhost:1234/v1"

    def test_int_field_override(self, monkeypatch):
        monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "4096")
        s = AgoraSettings(_env_file=None)
        assert s.llm_max_output_tokens == 4096

    def test_float_field_override(self, monkeypatch):
        monkeypatch.setenv("HYBRID_SEARCH_VECTOR_WEIGHT", "0.5")
        s = AgoraSettings(_env_file=None)
        assert s.hybrid_search_vector_weight == pytest.approx(0.5)

    def test_bool_field_override_true(self, monkeypatch):
        monkeypatch.setenv("ENABLE_AGENT_TOOLS", "true")
        s = AgoraSettings(_env_file=None)
        assert s.enable_agent_tools is True

    def test_bool_field_override_false(self, monkeypatch):
        monkeypatch.setenv("ENABLE_AGENT_TOOLS", "false")
        s = AgoraSettings(_env_file=None)
        assert s.enable_agent_tools is False

    def test_secret_str_field_override(self, monkeypatch):
        monkeypatch.setenv("NEO4J_PASSWORD", "PLACEHOLDER_PW_FOR_TESTS")  # noqa: S105 — pytest test fixture, ggignore
        s = AgoraSettings(_env_file=None)
        assert s.neo4j_password.get_secret_value() == "PLACEHOLDER_PW_FOR_TESTS"

    def test_dict_field_override_via_json(self, monkeypatch):
        monkeypatch.setenv(
            "LLM_MODEL_CONTEXT_LIMITS_JSON", '{"gpt-4o": 128000}'
        )
        s = AgoraSettings(_env_file=None)
        assert s.llm_model_context_limits == {"gpt-4o": 128000}

    def test_alias_flask_debug_respected(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        s = AgoraSettings(_env_file=None)
        assert s.debug is True

    def test_agent_language_override(self, monkeypatch):
        monkeypatch.setenv("AGENT_LANGUAGE", "EN")
        s = AgoraSettings(_env_file=None)
        # normalised to lowercase
        assert s.agent_language == "en"


# ---------------------------------------------------------------------------
# 3. Validators
# ---------------------------------------------------------------------------

class TestValidators:
    """One positive + one (or more) negative case per validator."""

    # ---- report_toolcall_mode ----

    def test_report_toolcall_mode_native_unchanged(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.setenv("LLM_API_KEY", "dummy")
        monkeypatch.setenv("REPORT_TOOLCALL_MODE", "native")
        s = AgoraSettings(_env_file=None)
        assert s.report_toolcall_mode == "native"

    def test_report_toolcall_mode_xml_uppercase_normalised(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.setenv("LLM_API_KEY", "dummy")
        monkeypatch.setenv("REPORT_TOOLCALL_MODE", "XML")
        s = AgoraSettings(_env_file=None)
        assert s.report_toolcall_mode == "xml"

    def test_report_toolcall_mode_garbage_falls_back_to_xml(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.setenv("LLM_API_KEY", "dummy")
        monkeypatch.setenv("REPORT_TOOLCALL_MODE", "Garbage")
        s = AgoraSettings(_env_file=None)
        assert s.report_toolcall_mode == "xml"

    # ---- llm_model_context_limits_json ----

    def test_llm_model_context_limits_invalid_json_returns_empty_dict(
        self, monkeypatch
    ):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.setenv("LLM_API_KEY", "dummy")
        monkeypatch.setenv("LLM_MODEL_CONTEXT_LIMITS_JSON", "NOT_JSON{{{")
        s = AgoraSettings(_env_file=None)
        assert s.llm_model_context_limits == {}

    def test_llm_model_context_limits_valid_json_parsed(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.setenv("LLM_API_KEY", "dummy")
        monkeypatch.setenv(
            "LLM_MODEL_CONTEXT_LIMITS_JSON", '{"qwen3:32b": 131072}'
        )
        s = AgoraSettings(_env_file=None)
        assert s.llm_model_context_limits == {"qwen3:32b": 131072}

    # ---- embedding_api_key fallback ----

    def test_embedding_api_key_falls_back_to_llm_api_key(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.setenv("LLM_API_KEY", "PLACEHOLDER_LLM_KEY")
        monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
        s = AgoraSettings(_env_file=None)
        assert s.embedding_api_key is not None
        assert s.embedding_api_key.get_secret_value() == "PLACEHOLDER_LLM_KEY"

    def test_embedding_api_key_explicit_overrides_llm_key(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.setenv("LLM_API_KEY", "PLACEHOLDER_LLM_KEY")
        monkeypatch.setenv("EMBEDDING_API_KEY", "PLACEHOLDER_EMBED_KEY")
        s = AgoraSettings(_env_file=None)
        assert s.embedding_api_key.get_secret_value() == "PLACEHOLDER_EMBED_KEY"

    # ---- vector_dim mismatch ----

    def test_vector_dim_mismatch_raises(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.setenv("LLM_API_KEY", "dummy")
        monkeypatch.setenv("EMBEDDING_MODEL", "nomic-embed-text")
        monkeypatch.setenv("VECTOR_DIM", "1024")  # nomic expects 768
        with pytest.raises(ValidationError, match="VECTOR_DIM mismatch"):
            AgoraSettings(_env_file=None)

    def test_vector_dim_correct_for_model_passes(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.setenv("LLM_API_KEY", "dummy")
        monkeypatch.setenv("EMBEDDING_MODEL", "nomic-embed-text")
        monkeypatch.setenv("VECTOR_DIM", "768")
        s = AgoraSettings(_env_file=None)
        assert s.vector_dim == 768

    def test_vector_dim_unknown_model_no_check(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.setenv("LLM_API_KEY", "dummy")
        monkeypatch.setenv("EMBEDDING_MODEL", "custom-unknown-model")
        monkeypatch.setenv("VECTOR_DIM", "512")
        # Should not raise — unknown model means no constraint
        s = AgoraSettings(_env_file=None)
        assert s.vector_dim == 512

    # ---- secret_key prod validation ----

    def test_empty_secret_key_in_prod_raises(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "false")
        monkeypatch.setenv("LLM_API_KEY", "dummy")
        monkeypatch.setenv("SECRET_KEY", "")
        monkeypatch.setenv("NEO4J_PASSWORD", "PLACEHOLDER_NOT_A_REAL_PW_xxxx")
        monkeypatch.setenv("AGORA_AUTH_TOKEN", "PLACEHOLDER_NOT_A_REAL_TOKEN_xx")
        with pytest.raises(ValidationError, match="SECRET_KEY not configured"):
            AgoraSettings(_env_file=None)

    def test_placeholder_secret_key_in_prod_raises(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "false")
        monkeypatch.setenv("LLM_API_KEY", "dummy")
        monkeypatch.setenv("SECRET_KEY", "change-me")
        monkeypatch.setenv("NEO4J_PASSWORD", "PLACEHOLDER_NOT_A_REAL_PW_xxxx")
        monkeypatch.setenv("AGORA_AUTH_TOKEN", "PLACEHOLDER_NOT_A_REAL_TOKEN_xx")
        with pytest.raises(ValidationError, match="placeholder"):
            AgoraSettings(_env_file=None)

    def test_real_secret_key_in_prod_passes(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "false")
        monkeypatch.setenv("LLM_API_KEY", "dummy")
        monkeypatch.setenv("SECRET_KEY", "PLACEHOLDER_NOT_A_REAL_SECRET_xxxx")  # noqa: S105 — pytest test fixture, ggignore
        monkeypatch.setenv("NEO4J_PASSWORD", "PLACEHOLDER_NOT_A_REAL_PW_xxxx")  # noqa: S105 — pytest test fixture, ggignore
        monkeypatch.setenv("AGORA_AUTH_TOKEN", "PLACEHOLDER_NOT_A_REAL_TOKEN_xx")  # noqa: S105 — pytest test fixture, ggignore
        s = AgoraSettings(_env_file=None)
        assert s.secret_key.get_secret_value() == "PLACEHOLDER_NOT_A_REAL_SECRET_xxxx"

    # ---- neo4j_password prod validation ----

    def test_placeholder_neo4j_password_in_prod_raises(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "false")
        monkeypatch.setenv("LLM_API_KEY", "dummy")
        monkeypatch.setenv("SECRET_KEY", "PLACEHOLDER_NOT_A_REAL_SECRET_xxxx")
        monkeypatch.setenv("NEO4J_PASSWORD", "change-me")
        monkeypatch.setenv("AGORA_AUTH_TOKEN", "PLACEHOLDER_NOT_A_REAL_TOKEN_xx")
        with pytest.raises(ValidationError, match="placeholder"):
            AgoraSettings(_env_file=None)

    # ---- agora_auth_token prod validation ----

    def test_missing_auth_token_no_anon_in_prod_raises(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "false")
        monkeypatch.setenv("LLM_API_KEY", "dummy")
        monkeypatch.setenv("SECRET_KEY", "PLACEHOLDER_NOT_A_REAL_SECRET_xxxx")
        monkeypatch.setenv("NEO4J_PASSWORD", "PLACEHOLDER_NOT_A_REAL_PW_xxxx")
        monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
        monkeypatch.setenv("AGORA_ALLOW_ANONYMOUS", "false")
        with pytest.raises(ValidationError, match="AGORA_AUTH_TOKEN missing"):
            AgoraSettings(_env_file=None)

    def test_allow_anonymous_in_prod_passes(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "false")
        monkeypatch.setenv("LLM_API_KEY", "dummy")
        monkeypatch.setenv("SECRET_KEY", "PLACEHOLDER_NOT_A_REAL_SECRET_xxxx")
        monkeypatch.setenv("NEO4J_PASSWORD", "PLACEHOLDER_NOT_A_REAL_PW_xxxx")
        monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
        monkeypatch.setenv("AGORA_ALLOW_ANONYMOUS", "true")
        s = AgoraSettings(_env_file=None)
        assert s.agora_allow_anonymous is True

    # ---- llm_api_key present ----

    def test_missing_llm_api_key_raises(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        with pytest.raises(ValidationError, match="LLM_API_KEY not configured"):
            AgoraSettings(_env_file=None)

    def test_empty_llm_api_key_raises(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.setenv("LLM_API_KEY", "")
        with pytest.raises(ValidationError, match="LLM_API_KEY not configured"):
            AgoraSettings(_env_file=None)

    # ---- ontology_mutation_mode ----

    def test_ontology_mutation_mode_invalid_raises(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.setenv("LLM_API_KEY", "dummy")
        monkeypatch.setenv("ONTOLOGY_MUTATION_MODE", "invalid_value")
        with pytest.raises(ValidationError, match="ONTOLOGY_MUTATION_MODE"):
            AgoraSettings(_env_file=None)

    def test_ontology_mutation_mode_review_only_normalised(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.setenv("LLM_API_KEY", "dummy")
        monkeypatch.setenv("ONTOLOGY_MUTATION_MODE", "  REVIEW_ONLY  ")
        s = AgoraSettings(_env_file=None)
        assert s.ontology_mutation_mode == "review_only"

    # ---- event_bus_backend ----

    def test_event_bus_backend_invalid_raises(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.setenv("LLM_API_KEY", "dummy")
        monkeypatch.setenv("EVENT_BUS_BACKEND", "kafka")
        with pytest.raises(ValidationError, match="EVENT_BUS_BACKEND"):
            AgoraSettings(_env_file=None)

    def test_event_bus_backend_redis_valid(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.setenv("LLM_API_KEY", "dummy")
        monkeypatch.setenv("EVENT_BUS_BACKEND", "REDIS")
        s = AgoraSettings(_env_file=None)
        assert s.event_bus_backend == "redis"

    # ---- agora_log_format ----

    def test_agora_log_format_invalid_raises(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.setenv("LLM_API_KEY", "dummy")
        monkeypatch.setenv("AGORA_LOG_FORMAT", "yaml")
        with pytest.raises(ValidationError, match="AGORA_LOG_FORMAT"):
            AgoraSettings(_env_file=None)

    def test_agora_log_format_json_valid(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.setenv("LLM_API_KEY", "dummy")
        monkeypatch.setenv("AGORA_LOG_FORMAT", "JSON")
        s = AgoraSettings(_env_file=None)
        assert s.agora_log_format == "json"


# ---------------------------------------------------------------------------
# 4. Cache
# ---------------------------------------------------------------------------

class TestCache:
    """get_settings() returns a cached singleton; cache_clear resets it."""

    @pytest.fixture(autouse=True)
    def _isolate_cache(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.setenv("LLM_API_KEY", "dummy")
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    def test_get_settings_returns_same_instance(self):
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_cache_clear_returns_new_instance(self):
        s1 = get_settings()
        get_settings.cache_clear()
        s2 = get_settings()
        assert s1 is not s2

    def test_reload_settings_returns_new_instance(self):
        s1 = get_settings()
        s2 = reload_settings()
        assert s1 is not s2

    def test_reload_settings_subsequent_call_same_instance(self):
        reload_settings()
        s2 = get_settings()
        s3 = get_settings()
        assert s2 is s3


# ---------------------------------------------------------------------------
# 5. SecretStr opacity
# ---------------------------------------------------------------------------

class TestSecretStr:
    """repr and str of AgoraSettings must not contain plaintext secret values."""

    @pytest.fixture(autouse=True)
    def _env(self, monkeypatch):
        monkeypatch.setenv("FLASK_DEBUG", "true")
        monkeypatch.setenv("LLM_API_KEY", "super-secret-llm-key")
        monkeypatch.setenv("SECRET_KEY", "super-secret-flask-key")
        monkeypatch.setenv("NEO4J_PASSWORD", "super-secret-neo4j-pw")

    def test_repr_hides_secret_key(self):
        s = AgoraSettings(_env_file=None)
        assert "super-secret-flask-key" not in repr(s)

    def test_repr_hides_neo4j_password(self):
        s = AgoraSettings(_env_file=None)
        assert "super-secret-neo4j-pw" not in repr(s)

    def test_repr_hides_llm_api_key(self):
        s = AgoraSettings(_env_file=None)
        assert "super-secret-llm-key" not in repr(s)

    def test_get_secret_value_still_accessible(self):
        s = AgoraSettings(_env_file=None)
        assert s.secret_key.get_secret_value() == "super-secret-flask-key"
        assert s.neo4j_password.get_secret_value() == "super-secret-neo4j-pw"
        assert s.llm_api_key.get_secret_value() == "super-secret-llm-key"
