"""InterviewBudgetExceededResponse — Vertrag für den 409-Body der Interview-Endpunkte.

Issue #1805 (Review-Finding F6): ``_budget_exceeded_response`` in
``app/api/simulation_interviews.py`` baute den Body als handgeschriebenes
``extra``-Dict. Ein erreichtes hartes Run-Budget ist hier das Ende der
Interviews dieser Simulation, nie eine Erfolgsantwort (``success`` ist immer
``false``) und nie ein Fallback-Text.

Die Form ist flach und entspricht dem Standard-Fehler-Envelope
(``json_error``: ``success``/``error``/``code``) plus den Feldern von
``BudgetExceededError``. Anders als der Legacy-Envelope der Interview-Endpunkte
(``InterviewEnvelope``, HTTP 200) kommt dieser Body mit HTTP 409.

``persisted_count`` zaehlt die Antworten dieses Aufrufs, die vor dem Abbruch
bereits gespeichert (und damit verbucht) wurden. Die Antwort selbst enthaelt
keine Teilantworten; gespeicherte Antworten bleiben im Interview-Verlauf. Der
IPC-Pfad kennt die Zahl nicht und meldet ``0``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.run_budget_contract import BudgetDimension, TerminationReason


class InterviewBudgetExceededResponse(BaseModel):
    """409-Body ``budget_exceeded`` der Interview-Endpunkte."""

    model_config = ConfigDict(extra="forbid")

    success: Literal[False] = False
    error: str = Field(min_length=1)
    code: Literal["budget_exceeded"] = "budget_exceeded"
    termination_reason: TerminationReason
    dimension: BudgetDimension
    observed: int
    threshold: int
    persisted_count: int = Field(0, ge=0)


__all__ = ["InterviewBudgetExceededResponse"]
