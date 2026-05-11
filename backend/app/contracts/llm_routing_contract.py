"""
LLM Routing Contracts (Pydantic v2).
"""

from __future__ import annotations

from typing import Dict, Literal, Optional, Any
from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")

StageId = Literal[
    "document_ingest",
    "ontology_generation",
    "graph_build",
    "persona_generation",
    "simulation_rounds",
    "report_generation",
    "evaluation",
]

ReasoningEffort = Literal["none", "minimal", "low", "medium", "high"]


class StageLLMRoute(BaseModel):
    """Configuration for a single stage route."""

    model_config = _STRICT

    provider_id: str
    model: str
    base_url: Optional[str] = None
    reasoning_effort: ReasoningEffort = "none"
    provider_options: Dict[str, Any] = Field(default_factory=dict)


class RuntimeLlmRouting(BaseModel):
    """Runtime LLM routing configuration for a run."""

    model_config = _STRICT

    default_route: StageLLMRoute
    stage_overrides: Dict[StageId, StageLLMRoute] = Field(default_factory=dict)
    routing_version: int = 1


class ProviderDescriptor(BaseModel):
    """Metadata about an LLM provider."""

    model_config = _STRICT

    id: str
    name: str
    type: Literal["ollama_local", "openai", "google", "openai_compatible"]
    default_base_url: Optional[str] = None
    auth_status: Literal["configured", "missing", "session_required"] = "missing"


class ResolvedRoute(BaseModel):
    """The final resolved configuration for an LLM call inside a stage.

    ``base_url`` is the runtime URL used for the actual LLM call. Callers must
    never embed secrets (userinfo, query-string keys) into provider URLs; the
    invocation logger and snapshot writer apply defensive sanitization when
    emitting URLs to logs/disk via ``SecretResolver.sanitize_url``.
    """

    model_config = _STRICT

    stage: StageId
    provider_id: str
    model: str
    base_url: Optional[str] = None
    reasoning_effort: ReasoningEffort = "none"
    routing_version: int
    provider_options: Dict[str, Any] = Field(default_factory=dict)
    started_at: Optional[str] = None
