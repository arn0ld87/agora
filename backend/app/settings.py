"""
Pydantic-Settings-basierte Konfiguration für Agora.

Singleton via ``get_settings()`` (``lru_cache``-geschützt). Alle 41
Laufzeit-Felder spiegeln ``app/config.py`` 1:1 — Defaults, Env-Aliases und
Validator-Logik werden hier schrittweise konsolidiert.

Referenz: ADR-0003 — docs/decisions/0003-pydantic-settings-migration.md
"""

from __future__ import annotations

import json
import logging
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .config import (
    KNOWN_EMBEDDING_DIMS,  # noqa: F401 — re-exported for convenience
    NEO4J_PASSWORD_PLACEHOLDERS,
    SECRET_KEY_PLACEHOLDERS,
    infer_vector_dim_for_model,
)

_logger = logging.getLogger(__name__)


def _project_env_path() -> Path:
    """Resolve the project-root .env path (three levels above this file)."""
    return Path(__file__).resolve().parent.parent.parent / ".env"


class AgoraSettings(BaseSettings):
    """Alle Laufzeit-Konfigurationen an einem Ort. Singleton via get_settings()."""

    model_config = SettingsConfigDict(
        env_file=_project_env_path(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------ Flask
    secret_key: SecretStr = Field(default=SecretStr(""), alias="SECRET_KEY")
    debug: bool = Field(default=False, alias="FLASK_DEBUG")

    # -------------------------------------------------------------------- LLM
    llm_api_key: SecretStr | None = Field(default=None, alias="LLM_API_KEY")
    llm_base_url: str = Field(
        default="http://localhost:11434/v1", alias="LLM_BASE_URL"
    )
    llm_model_name: str = Field(default="qwen2.5:32b", alias="LLM_MODEL_NAME")
    llm_max_output_tokens: int = Field(default=8192, alias="LLM_MAX_OUTPUT_TOKENS")
    llm_context_limit: int = Field(default=262144, alias="LLM_CONTEXT_LIMIT")
    # Parsed from LLM_MODEL_CONTEXT_LIMITS_JSON env var (JSON string → dict).
    # Declared as Any so pydantic-settings 2.x does not attempt its own
    # json.loads() before the field_validator can intercept; the validator
    # guarantees the runtime type is dict[str, int].
    llm_model_context_limits: Any = Field(
        default_factory=dict, alias="LLM_MODEL_CONTEXT_LIMITS_JSON"
    )

    # ------------------------------------------------------------------ Neo4j
    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: SecretStr = Field(default=SecretStr(""), alias="NEO4J_PASSWORD")

    # ------------------------------------------------------------- Agent-Tools
    enable_agent_tools: bool = Field(default=False, alias="ENABLE_AGENT_TOOLS")
    max_tool_calls_per_action: int = Field(
        default=2, alias="MAX_TOOL_CALLS_PER_ACTION"
    )

    # ------------------------------------------------------------ Embeddings
    embedding_model: str = Field(default="nomic-embed-text", alias="EMBEDDING_MODEL")
    embedding_base_url: str = Field(
        default="http://localhost:11434", alias="EMBEDDING_BASE_URL"
    )
    embedding_api_key: SecretStr | None = Field(
        default=None, alias="EMBEDDING_API_KEY"
    )
    vector_dim: int = Field(default=768, alias="VECTOR_DIM")

    # -------------------------------------------------------------- Chunking
    default_chunk_size: int = Field(default=1500, alias="GRAPH_CHUNK_SIZE")
    default_chunk_overlap: int = Field(default=150, alias="GRAPH_CHUNK_OVERLAP")
    graph_parallel_chunks: int = Field(default=4, alias="GRAPH_PARALLEL_CHUNKS")

    # -------------------------------------------------------------- Ontology
    ontology_min_entity_types: int = Field(
        default=8, alias="ONTOLOGY_MIN_ENTITY_TYPES"
    )
    ontology_max_entity_types: int = Field(
        default=16, alias="ONTOLOGY_MAX_ENTITY_TYPES"
    )
    ontology_max_edge_types: int = Field(default=12, alias="ONTOLOGY_MAX_EDGE_TYPES")
    # Literal enforced via validator after strip+lower normalisation.
    ontology_mutation_mode: str = Field(
        default="disabled", alias="ONTOLOGY_MUTATION_MODE"
    )
    ontology_mutation_min_confidence: float = Field(
        default=0.6, alias="ONTOLOGY_MUTATION_MIN_CONFIDENCE"
    )

    # --------------------------------------------------------------- Search
    hybrid_search_vector_weight: float = Field(
        default=0.7, alias="HYBRID_SEARCH_VECTOR_WEIGHT"
    )
    hybrid_search_keyword_weight: float = Field(
        default=0.3, alias="HYBRID_SEARCH_KEYWORD_WEIGHT"
    )

    # ---------------------------------------------------------- GraphMemory
    graph_memory_queue_max: int = Field(
        default=10000, alias="GRAPH_MEMORY_QUEUE_MAX"
    )
    graph_memory_put_timeout: float = Field(
        default=2.0, alias="GRAPH_MEMORY_PUT_TIMEOUT"
    )

    # ---------------------------------------------------------------- OASIS
    oasis_default_max_rounds: int = Field(
        default=10, alias="OASIS_DEFAULT_MAX_ROUNDS"
    )

    # ---------------------------------------------------------- Report-Agent
    # str (not Literal) because the normaliser provides fail-soft fallback to
    # "xml" for unknown values instead of raising ValidationError. The allowed
    # set is {"native", "xml"}.
    report_toolcall_mode: str = Field(
        default="native", alias="REPORT_TOOLCALL_MODE"
    )
    report_agent_max_tool_calls: int = Field(
        default=5, alias="REPORT_AGENT_MAX_TOOL_CALLS"
    )
    report_agent_max_reflection_rounds: int = Field(
        default=2, alias="REPORT_AGENT_MAX_REFLECTION_ROUNDS"
    )
    report_agent_temperature: float = Field(
        default=0.5, alias="REPORT_AGENT_TEMPERATURE"
    )

    # --------------------------------------------------------------- Sprache
    report_language: str = Field(default="German", alias="REPORT_LANGUAGE")
    agent_language: str = Field(default="de", alias="AGENT_LANGUAGE")

    # --------------------------------------------------------- Time/Persona
    time_profile: str = Field(default="dach_default", alias="TIME_PROFILE")
    persona_review_enabled: bool = Field(
        default=False, alias="PERSONA_REVIEW_ENABLED"
    )

    # --------------------------------------------------------------- Logging
    # str (not Literal) so the normaliser can strip+lower before Literal check
    # happens implicitly via the validator whitelist.
    agora_log_format: str = Field(default="text", alias="AGORA_LOG_FORMAT")

    # ----------------------------------------------------------- Event-Bus
    redis_url: str = Field(
        default="redis://redis:6379/0", alias="REDIS_URL"
    )
    # str (not Literal) — normaliser strips+lowers then whitelists.
    event_bus_backend: str = Field(default="auto", alias="EVENT_BUS_BACKEND")

    # ---------------------------------------------------------- Rate-Limit
    agora_ticket_rate_limit_max: int = Field(
        default=60, alias="AGORA_TICKET_RATE_LIMIT_MAX"
    )
    agora_ticket_rate_limit_window_seconds: int = Field(
        default=60, alias="AGORA_TICKET_RATE_LIMIT_WINDOW_SECONDS"
    )
    agora_upload_rate_limit_max: int = Field(
        default=10, alias="AGORA_UPLOAD_RATE_LIMIT_MAX"
    )
    agora_upload_rate_limit_window_seconds: int = Field(
        default=60, alias="AGORA_UPLOAD_RATE_LIMIT_WINDOW_SECONDS"
    )
    agora_llm_trigger_rate_limit_max: int = Field(
        default=20, alias="AGORA_LLM_TRIGGER_RATE_LIMIT_MAX"
    )
    agora_llm_trigger_rate_limit_window_seconds: int = Field(
        default=60, alias="AGORA_LLM_TRIGGER_RATE_LIMIT_WINDOW_SECONDS"
    )
    agora_report_rate_limit_max: int = Field(
        default=10, alias="AGORA_REPORT_RATE_LIMIT_MAX"
    )
    agora_report_rate_limit_window_seconds: int = Field(
        default=60, alias="AGORA_REPORT_RATE_LIMIT_WINDOW_SECONDS"
    )

    # ------------------------------------------------------------- ProxyFix
    agora_proxy_fix_x_for: int = Field(default=0, alias="AGORA_PROXY_FIX_X_FOR")
    agora_proxy_fix_x_proto: int = Field(default=0, alias="AGORA_PROXY_FIX_X_PROTO")
    agora_proxy_fix_x_host: int = Field(default=0, alias="AGORA_PROXY_FIX_X_HOST")
    agora_proxy_fix_x_port: int = Field(default=0, alias="AGORA_PROXY_FIX_X_PORT")
    agora_proxy_fix_x_prefix: int = Field(
        default=0, alias="AGORA_PROXY_FIX_X_PREFIX"
    )

    # ----------------------------------------------------------------- Auth
    agora_auth_token: SecretStr | None = Field(
        default=None, alias="AGORA_AUTH_TOKEN"
    )
    agora_allow_anonymous: bool = Field(
        default=False, alias="AGORA_ALLOW_ANONYMOUS"
    )

    # ================================================================ Validators

    @field_validator("report_toolcall_mode", mode="before")
    @classmethod
    def _normalize_report_toolcall_mode(cls, v: Any) -> str:
        """Strip+lower; unknown values fall back to 'xml' with a warning."""
        normalized = str(v).strip().lower()
        if normalized not in {"native", "xml"}:
            _logger.warning(
                "Invalid REPORT_TOOLCALL_MODE=%r — falling back to 'xml'",
                v,
            )
            return "xml"
        return normalized

    @field_validator("ontology_mutation_mode", mode="before")
    @classmethod
    def _normalize_ontology_mutation_mode(cls, v: Any) -> str:
        """Strip+lower; Literal enforcement via whitelist ValidationError."""
        normalized = str(v).strip().lower()
        allowed = {"disabled", "review_only", "auto"}
        if normalized not in allowed:
            raise ValueError(
                f"ONTOLOGY_MUTATION_MODE must be one of {allowed!r}, got {v!r}"
            )
        return normalized

    @field_validator("event_bus_backend", mode="before")
    @classmethod
    def _normalize_event_bus_backend(cls, v: Any) -> str:
        """Strip+lower; Literal enforcement via whitelist ValidationError."""
        normalized = str(v).strip().lower()
        allowed = {"redis", "file", "auto"}
        if normalized not in allowed:
            raise ValueError(
                f"EVENT_BUS_BACKEND must be one of {allowed!r}, got {v!r}"
            )
        return normalized

    @field_validator("agora_log_format", mode="before")
    @classmethod
    def _normalize_agora_log_format(cls, v: Any) -> str:
        """Strip+lower; Literal enforcement via whitelist ValidationError."""
        normalized = str(v).strip().lower()
        allowed = {"text", "json"}
        if normalized not in allowed:
            raise ValueError(
                f"AGORA_LOG_FORMAT must be one of {allowed!r}, got {v!r}"
            )
        return normalized

    @field_validator("agent_language", mode="before")
    @classmethod
    def _normalize_agent_language(cls, v: Any) -> str:
        """Strip+lower; non-fatal."""
        return str(v).strip().lower()

    @field_validator("llm_model_context_limits", mode="before")
    @classmethod
    def _parse_llm_model_context_limits_json(cls, v: Any) -> Any:
        """JSON-parse if string; fail-soft → {} on invalid JSON."""
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, dict):
                    return parsed
                _logger.warning(
                    "LLM_MODEL_CONTEXT_LIMITS_JSON is not a JSON object — ignoring"
                )
                return {}
            except json.JSONDecodeError:
                _logger.warning(
                    "LLM_MODEL_CONTEXT_LIMITS_JSON contains invalid JSON — ignoring"
                )
                return {}
        return v

    @model_validator(mode="after")
    def _embedding_api_key_fallback_to_llm(self) -> "AgoraSettings":
        """If embedding_api_key is None, inherit llm_api_key."""
        if self.embedding_api_key is None and self.llm_api_key is not None:
            object.__setattr__(self, "embedding_api_key", self.llm_api_key)
        return self

    @model_validator(mode="after")
    def _validate_vector_dim_matches_model(self) -> "AgoraSettings":
        """vector_dim must match the known dimension for embedding_model."""
        expected = infer_vector_dim_for_model(self.embedding_model)
        if expected is not None and self.vector_dim != expected:
            raise ValueError(
                f"VECTOR_DIM mismatch for EMBEDDING_MODEL {self.embedding_model!r}: "
                f"configured {self.vector_dim}, expected {expected}"
            )
        return self

    @model_validator(mode="after")
    def _validate_secrets_in_prod(self) -> "AgoraSettings":
        """In non-debug mode secret_key must be non-empty and not a placeholder."""
        if self.debug:
            return self
        secret_val = self.secret_key.get_secret_value().strip()
        if not secret_val:
            raise ValueError(
                "SECRET_KEY not configured (required when FLASK_DEBUG is false)"
            )
        if secret_val.lower() in SECRET_KEY_PLACEHOLDERS:
            raise ValueError(
                "SECRET_KEY uses a known placeholder value — generate a real secret"
            )
        return self

    @model_validator(mode="after")
    def _validate_neo4j_password_in_prod(self) -> "AgoraSettings":
        """In non-debug mode neo4j_password must be non-empty and not a placeholder."""
        if self.debug:
            return self
        pw_val = self.neo4j_password.get_secret_value().strip()
        if not pw_val:
            raise ValueError("NEO4J_PASSWORD not configured")
        if pw_val.lower() in NEO4J_PASSWORD_PLACEHOLDERS:
            raise ValueError(
                "NEO4J_PASSWORD uses a known placeholder value — set a real password"
            )
        return self

    @model_validator(mode="after")
    def _validate_auth_in_prod(self) -> "AgoraSettings":
        """In non-debug mode either agora_auth_token or agora_allow_anonymous must be set."""
        if self.debug:
            return self
        auth_token = (
            self.agora_auth_token.get_secret_value().strip()
            if self.agora_auth_token is not None
            else ""
        )
        if not auth_token and not self.agora_allow_anonymous:
            raise ValueError(
                "AGORA_AUTH_TOKEN missing in non-debug mode "
                "(set AGORA_ALLOW_ANONYMOUS=true to opt out explicitly)"
            )
        return self

    @model_validator(mode="after")
    def _validate_llm_api_key_present(self) -> "AgoraSettings":
        """llm_api_key must not be empty (debug allows 'dummy')."""
        if self.llm_api_key is None:
            raise ValueError(
                "LLM_API_KEY not configured "
                "(set to any non-empty value, e.g. 'ollama')"
            )
        key_val = self.llm_api_key.get_secret_value().strip()
        if not key_val:
            raise ValueError(
                "LLM_API_KEY not configured "
                "(set to any non-empty value, e.g. 'ollama')"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> AgoraSettings:
    """Return the cached AgoraSettings singleton."""
    return AgoraSettings()


def reload_settings() -> AgoraSettings:
    """Clear the settings cache and return a fresh AgoraSettings instance."""
    get_settings.cache_clear()
    return get_settings()


def bootstrap_settings_if_missing_secret_in_debug() -> None:
    """
    Pre-flight helper for app startup in debug mode.

    Sets SECRET_KEY in os.environ (via setdefault) when the variable is absent
    so that AgoraSettings() does not raise on an empty secret_key.  Must be
    called BEFORE AgoraSettings() is instantiated (i.e. before get_settings()).

    This side-effect is intentionally NOT performed inside a validator
    (settings objects are read-only after construction).  PR 2 will wire this
    into the app factory.
    """
    import os

    if os.environ.get("FLASK_DEBUG", "false").lower() == "true":
        os.environ.setdefault("SECRET_KEY", secrets.token_urlsafe(32))
