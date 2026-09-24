"""Contract fuer ``GET /api/graph/task/<task_id>`` und ``GET /api/graph/tasks``
(Issue #1466).

Bislang serialisierten beide Endpunkte ``Task.to_dict()``
(``app/models/task.py``) handgeschrieben, ohne Gegenstueck in ``schemas/``
und ohne Zod-Drift-Check. Dieses Modul deckt die Item-Form ab, die beide
Endpunkte teilen: ``get_task`` liefert genau ein Item, ``list_tasks`` eine
Liste desselben Shapes.

``message_key`` ist additiv seit #1458: aeltere Consumer, die das Feld
nicht kennen, lesen weiterhin ``message`` als menschenlesbaren Fallback.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TaskStatusValue(str, Enum):
    """Spiegel von ``app.models.task.TaskStatus``.

    Bewusst dupliziert statt importiert: Contracts in diesem Paket haengen
    nicht von ``app.models`` ab (siehe z. B. ``ProjectStatus`` in
    ``project_contract.py``, ``ReportStatus`` in ``report_contract.py``) —
    das haelt die Vertragsebene unabhaengig von der internen
    Modell-Implementierung.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatusResponse(BaseModel):
    """Wire-Form von ``Task.to_dict()``.

    Item-Form fuer ``GET /api/graph/task/<task_id>`` (ein Item) und
    ``GET /api/graph/tasks`` (Liste desselben Shapes je Element).
    ``Task.to_dict()`` setzt alle Felder immer explizit (keine bedingte
    Auslassung), daher genuegt ``model_dump(mode="json")`` ohne
    ``exclude_unset``/``exclude_none`` fuer eine byte-genaue Wire-Format-
    Erhaltung.
    """

    model_config = ConfigDict(extra="forbid")

    task_id: str
    task_type: str
    status: TaskStatusValue
    created_at: str
    updated_at: str
    progress: int
    message: str
    message_key: str | None = None
    progress_detail: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
