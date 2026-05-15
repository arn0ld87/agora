"""Workspace-weite LLM-Routing-Defaults (Pydantic v2).

Diese Defaults werden global pro Workspace persistiert (eine JSON-Datei).
Beim Run-Start mergt ``llm_routing_seed.seed_run_stage_routing`` den
Workspace-Default mit ggf. per Request übergebenen Overrides in die
runspezifische ``RuntimeLlmRouting``.

Strikt getrennt von ``RuntimeLlmRouting`` (per-Run, lebt im Run-Verzeichnis):
hier sprechen wir über den Wunsch-Default des Workspaces, der bei jedem
neuen Run wirksam wird, solange ein Stage noch nicht versiegelt ist.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from .llm_routing_contract import StageId, StageLLMRoute

_STRICT = ConfigDict(extra="forbid")


class WorkspaceLlmRoutingDefaults(BaseModel):
    """Workspace-weit gültiger LLM-Default plus optionale Stage-Overrides."""

    model_config = _STRICT

    global_default: StageLLMRoute = Field(default_factory=StageLLMRoute)
    stage_overrides: Dict[StageId, StageLLMRoute] = Field(default_factory=dict)
    updated_at: Optional[datetime] = None
    version: int = 1
