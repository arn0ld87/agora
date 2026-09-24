"""Prepare-Status — Contract fuer die literalen Statusantworten von
``POST /api/simulation/prepare`` und ``POST /api/simulation/prepare/status``
(Issue #1174, Muster aus #1458).

Deckt die Kurzschluss-Antworten dieser beiden Endpunkte ab: Prepared-Shortcut
(``_already_prepared_response``), Task-gestartet-Antwort
(``_build_prepare_response``) und die drei Kurzschluesse in
``get_prepare_status`` (already_completed via ``simulation_id``, not_started,
Task-nicht-gefunden-aber-fertig). Der Live-Task-Zweig — ``Task.to_dict()``,
sobald ein laufender Task existiert — bleibt bewusst aussen vor: ``Task``
(``app/models/task.py``) ist eine ueber viele Services geteilte, gesperrte
Dataclass; ihre Umstellung auf einen Pydantic-Contract waere ein eigener,
groesserer Schnitt und nicht Gegenstand dieses Fixes.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.persona_target_contract import PersonaTargetContract

_STRICT = ConfigDict(extra="forbid")

# Die drei Kurzschluss-Zustaende dieser beiden Endpunkte — kein "processing"
# o.ae.: das liefert ausschliesslich der Live-Task-Zweig (Task.to_dict()).
PrepareStatusValue = Literal["ready", "preparing", "not_started"]

# Stabile i18n-Schluessel (Frontend: `i18n/statusMessage.ts`, Kataloge unter
# `prepare.*` in `locales/{de,en}.json`).
PrepareMessageKey = Literal[
    "prepare.already_completed",
    "prepare.task_started",
    "prepare.not_started",
]


class PrepareStatusResponse(BaseModel):
    """Statusantwort der literalen Prepare-Kurzschluesse.

    ``message`` bleibt neben ``message_key`` als Klartext-Fallback fuer
    Consumer, die den Schluessel noch nicht kennen (Rueckwaertskompat.).
    """

    model_config = _STRICT

    simulation_id: str
    status: PrepareStatusValue
    message: str
    message_key: PrepareMessageKey
    already_prepared: bool

    # Nur in der Task-gestartet-Antwort (`_build_prepare_response`).
    task_id: Optional[str] = None
    run_id: Optional[str] = None
    expected_entities_count: Optional[int] = None
    entity_types: Optional[list[str]] = None
    persona_target: Optional[PersonaTargetContract] = None

    # Nur in `get_prepare_status` (Live-Poll traegt zusaetzlich `progress`).
    progress: Optional[int] = Field(default=None, ge=0, le=100)
    # `_check_simulation_prepared()`-Diagnose; Form je Aufrufer verschieden,
    # deshalb bewusst ungetypt statt eines eigenen Contracts.
    prepare_info: Optional[dict[str, Any]] = None


__all__ = ["PrepareStatusResponse", "PrepareStatusValue", "PrepareMessageKey"]
