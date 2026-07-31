"""
LLM Routing Contracts (Pydantic v2).
"""

from __future__ import annotations

from typing import Dict, Literal, Optional, Any, List
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .provider_types import AiModelRefSource, ProviderType

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

    # Issue #901: Herkunft der Routing-Entscheidung. Vorher ging sie beim
    # Seeden verloren und ai_route_from_stage_route schrieb hart
    # source="legacy" — jede explizite UI-Modellwahl war im Snapshot und im
    # AiRouteAudit von einem Legacy-Fallback ununterscheidbar.
    #
    # Bewusst das AiModelRef-Vokabular und nicht RouteSource: hier steht, was
    # das UI ausgewaehlt hat. Die Abbildung auf RouteSource passiert erst bei
    # der Projektion nach AiRoute. Umgekehrt waere sie verlustbehaftet —
    # "explicit" und "project-default" haben dort kein exaktes Pendant.
    #
    # None = Bestandsroute ohne das Feld; projiziert weiterhin auf "legacy".
    ai_model_ref_source: Optional[AiModelRefSource] = None
    fallback_reason: Optional[str] = None

    @model_validator(mode="after")
    def require_fallback_reason(self) -> "StageLLMRoute":
        """``fallback`` bildet auf ``RouteSource="provider_fallback"`` ab, und
        dessen Validator verlangt einen nicht-leeren ``fallback_reason``.

        Die Pruefung steht hier statt in ``ai_route_from_stage_route``, damit
        der Fehler dort auftritt, wo die Route gebaut wird — sonst braeche ein
        Run erst spaeter beim Projizieren, an einer Stelle ohne Bezug zur
        Ursache.
        """
        if self.ai_model_ref_source == "fallback" and not (
            self.fallback_reason and self.fallback_reason.strip()
        ):
            raise ValueError(
                "ai_model_ref_source='fallback' erfordert einen nicht-leeren "
                "fallback_reason"
            )
        return self

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


class ModelEntry(BaseModel):
    """Metadata about a single model (public, normalized)."""

    model_config = _STRICT

    id: str
    name: str
    provider_id: str
    source: Literal["live", "cached", "fallback", "custom"]
    refreshed_at: float
    supports_tools: bool = False
    supports_json_mode: bool = False
    context_window: Optional[int] = None


class ProviderDescriptor(BaseModel):
    """Metadata about an LLM provider (public, no secrets)."""

    model_config = _STRICT

    id: str
    label: str
    type: ProviderType
    base_url: Optional[str] = None
    api_key_ref: Optional[str] = None
    supports_models_endpoint: bool = False
    supports_tools: bool = False
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
