"""LLM-Call-Event Contract (Pydantic v2).

Codex-Review (PR #1742): ``llm_call_events.jsonl`` (``instance/runs/<run_id>/``)
ist ein exportierbares Run-Artefakt — jeder LLM-/Decision-Provider-Aufruf
landet hier als eine Zeile, über ``LlmInvocationLogger.log_event`` geschrieben
und von ``run_usage_ledger.py`` zu ``UsageMetrics`` aggregiert. Bisher war das
ein handgeschriebenes Dict ohne Vertrag; `reported_cost_micros` (f001, Slice
`jev-budget`) wurde direkt ins Dict ergänzt und über ``event.get(...)``
konsumiert, ganz ohne Validierung oder versionierte Grenze (AGENTS.md,
Contracts-first).

Scope-Entscheidung: Dieser Vertrag validiert die **Schreibseite**
(``LlmInvocationLogger.log_event``), nicht die Leseseite. ``run_usage_ledger
.py::load_call_events`` liest laut eigenem Docstring bewusst "tolerant"
(überspringt korrupte Zeilen) und ``_Bucket.add`` wertet Felder bewusst über
``.get(...)`` mit Fallbacks aus, weil ältere Run-Verzeichnisse Events aus
Zeit vor diesem Vertrag (oder vor einzelnen Feldern wie
``reported_cost_micros``) enthalten können, die nicht rückwirkend ungültig
werden sollen. Ein ``extra="forbid"``-Vertrag auf der Leseseite würde genau
diese Abwärtskompatibilität brechen. Jeder NEU geschriebene Event geht ab
jetzt trotzdem durch dieses Modell — das schließt die Lücke, über die ein
zukünftiges Feld ungeprüft hinzugefügt werden könnte, ohne die bewusst
tolerante Leseseite anzutasten.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid")


class LlmCallEvent(BaseModel):
    """Eine Zeile aus ``llm_call_events.jsonl`` — ein einzelner Provider-Attempt.

    ``success=False`` zählt laut ``run_usage_ledger.py::_Bucket.add``
    ausdrücklich mit gegen ``llm_calls`` (Issue #764): auch fehlgeschlagene
    Requests, Retries und Fallbacks sind echte Providerattempts. Kosten-/
    Token-Felder bleiben in diesem Fall ehrlich ``None`` statt ``0`` — ein
    Provider, der scheitert, liefert i. d. R. keine Usage-Angabe.
    """

    model_config = _STRICT

    run_id: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    base_url_sanitized: Optional[str] = None
    routing_version: int = Field(ge=0)
    timestamp: float
    latency_ms: float = Field(ge=0.0)
    success: bool
    error_type: Optional[str] = None
    http_status: Optional[int] = None
    remote_request_id: Optional[str] = None
    prompt_tokens: Optional[int] = Field(default=None, ge=0)
    completion_tokens: Optional[int] = Field(default=None, ge=0)
    #: Issue #1772: gecachte Eingabe-Tokens (``usage.prompt_tokens_details
    #: .cached_tokens``), Teilmenge von ``prompt_tokens``. ``None`` (Default) =
    #: der Provider hat keine Angabe geliefert; alte Events ohne das Feld
    #: bleiben lesbar (die Leseseite wertet ueber ``.get(...)`` aus).
    cached_input_tokens: Optional[int] = Field(default=None, ge=0)
    #: f001 (Slice `jev-budget`): für Aufrufer, die ihre Kosten bereits selbst
    #: über dieselbe ``PricingRegistry`` beziffert haben, aber auf dieser
    #: Schicht keine Rohtoken mehr kennen (z. B. ``DecisionResult.cost_micros``
    #: eines Jev-Calls). ``None`` (Default) ändert nichts am bisherigen
    #: token-basierten Aggregationspfad in ``run_usage_ledger.py``.
    reported_cost_micros: Optional[int] = Field(default=None, ge=0)


__all__ = ["LlmCallEvent"]
