"""Branch-Override-Contract für ``POST /api/simulation/<id>/branch`` (Issue #886).

Kanonisiert die bisher ungetypte Override-Whitelist aus
``branching_service.create_branch`` (``allowed_override_keys``) als
Pydantic-Vertrag. ``ai_model_ref`` ist die kanonische (Provider-Connection,
Modell)-Referenz; ``llm_model`` bleibt als **deprecated Legacy-Key**
akzeptiert (reiner Modell-Name ohne Connection-Bindung). Beide zusammen sind
widersprüchlich — dieselbe Modell-ID kann auf mehreren Provider-Connections
liegen, ohne die Connection-ID ist die Route nicht eindeutig auflösbar
(vgl. ``app/services/llm_routing_seed.py``).

Feld-Menge und -Typen spiegeln den historischen Ist-Zustand aus
``branching_service.create_branch``, damit heute gültige Payloads gültig
bleiben. Die Whitelist selbst bleibt zusätzlich per AST-Test in
``tests/contracts/test_branch_override_contract.py`` gepinnt.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, model_validator

from .ai_provider_contract import AiModelRef

_STRICT = ConfigDict(extra="forbid")


class BranchOverrides(BaseModel):
    """Override-Parameter für einen Simulation-Branch.

    Alle Felder optional — nur gesetzte Felder überschreiben die
    Source-Simulation. Eine leere Zeichenkette gilt wie bisher als
    Nicht-Override (siehe ``branching_service.create_branch``).
    """

    model_config = _STRICT

    # Deprecated (Issue #886): reiner Modell-Name ohne Connection-Bindung.
    # Bleibt als Legacy-Kompatibilität akzeptiert; darf nicht zusammen mit
    # ai_model_ref gesetzt werden (siehe Validator unten).
    llm_model: Optional[str] = None
    language: Optional[str] = None
    max_agents: Optional[int] = None
    time_config: Optional[dict[str, Any]] = None
    enable_twitter: Optional[bool] = None
    enable_reddit: Optional[bool] = None
    persona_additions: Optional[list[dict[str, Any]]] = None
    persona_removals: Optional[list[str]] = None
    # Kanonische (Provider-Connection, Modell)-Referenz (Issue #886).
    ai_model_ref: Optional[AiModelRef] = None

    @model_validator(mode="after")
    def _reject_ai_model_ref_with_legacy_llm_model(self) -> "BranchOverrides":
        """``ai_model_ref`` + ``llm_model`` sind widersprüchlich (Issue #886).

        Ein nicht-leerer ``llm_model``-String neben einer ``ai_model_ref``
        wäre ein zweiter, unabgestimmter Modellwunsch — welcher gilt, wäre
        Rateraten. Ein leerer String bleibt erlaubt: er ist historisch ein
        Nicht-Override, kein zweiter Wunsch.
        """
        if self.ai_model_ref is not None and self.llm_model:
            raise ValueError(
                "ai_model_ref darf nicht mit llm_model kombiniert werden"
            )
        return self


__all__ = ["BranchOverrides"]
