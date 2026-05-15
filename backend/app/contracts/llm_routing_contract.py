"""
LLM Routing Contracts (Pydantic v2).
"""

from __future__ import annotations

from typing import Dict, Literal, Optional, Any, List
from pydantic import BaseModel, ConfigDict, Field, model_validator

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

    stage: Optional[StageId] = None
    provider_id: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    reasoning_effort: Optional[ReasoningEffort] = "none"
    provider_options: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def handle_legacy_and_rejections(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # reasoning_effort legacy mapping: thinking=True → "medium", False → "none"
        if "thinking" in data:
            thinking = data.pop("thinking")
            if "reasoning_effort" not in data:
                data["reasoning_effort"] = "medium" if thinking else "none"

        # num_ctx at top-level rejected
        if "num_ctx" in data:
            raise ValueError("num_ctx must be inside provider_options, not at top-level")

        return data


class RuntimeLlmRouting(BaseModel):
    """Runtime LLM routing configuration for a run."""

    model_config = _STRICT

    global_default: StageLLMRoute
    stage_overrides: Dict[StageId, StageLLMRoute] = Field(default_factory=dict)
    routing_version: int = 1


class ProviderDescriptor(BaseModel):
    """Metadata about an LLM provider (public, no secrets)."""

    model_config = _STRICT

    id: str
    label: str
    type: Literal["ollama_local", "openai", "google", "openai_compatible", "github_copilot"]
    base_url: Optional[str] = None
    api_key_ref: Optional[str] = None
    supports_models_endpoint: bool = False
    fallback_models: List[str] = Field(default_factory=list)


class ResolvedRoute(BaseModel):
    """The final resolved configuration for an LLM call inside a stage."""

    model_config = _STRICT

    stage: StageId
    provider_id: str
    model: str
    base_url_sanitized: Optional[str] = None
    reasoning_effort: ReasoningEffort = "none"
    routing_version: int
    provider_options: Dict[str, Any] = Field(default_factory=dict)
    started_at: Optional[str] = None
