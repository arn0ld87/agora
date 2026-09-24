"""Contract-Tests fuer ``TaskStatusResponse`` (Issue #1466).

``GET /api/graph/task/<task_id>`` und ``GET /api/graph/tasks`` serialisierten
bislang ``Task.to_dict()`` handgeschrieben, ohne Gegenstueck in ``schemas/``
und ohne Zod-Drift-Check. Dieser Test bewacht, dass der neue Vertrag exakt
das bisherige Wire-Format von ``Task.to_dict()`` validiert und unveraendert
zurueckgibt.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from app.contracts.task_status_contract import TaskStatusResponse, TaskStatusValue
from app.models.task import Task, TaskManager, TaskStatus


def _make_task(**overrides) -> Task:
    now = datetime(2026, 9, 24, 10, 0, 0)
    defaults = dict(
        task_id="11111111-1111-4111-8111-111111111111",
        task_type="graph_build",
        status=TaskStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return Task(**defaults)


def test_task_to_dict_round_trips_through_the_contract():
    task = _make_task()
    response = TaskStatusResponse.model_validate(task.to_dict())
    assert response.model_dump(mode="json") == task.to_dict()


def test_completed_task_with_message_key_round_trips():
    task_id = TaskManager().create_task("graph_build")
    TaskManager().complete_task(task_id, result={"ok": True})
    task = TaskManager().get_task(task_id)
    assert task is not None

    response = TaskStatusResponse.model_validate(task.to_dict())

    assert response.status == TaskStatusValue.COMPLETED
    assert response.message_key == "task.completed"
    assert response.model_dump(mode="json") == task.to_dict()


def test_unknown_field_is_rejected():
    task = _make_task().to_dict()
    task["unexpected_field"] = True
    with pytest.raises(ValidationError):
        TaskStatusResponse.model_validate(task)


def test_unknown_status_value_is_rejected():
    task = _make_task().to_dict()
    task["status"] = "unknown_status"
    with pytest.raises(ValidationError):
        TaskStatusResponse.model_validate(task)
