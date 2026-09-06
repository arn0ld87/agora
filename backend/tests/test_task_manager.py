"""Tests for ``app.models.task`` — insbesondere den i18n-Schlüssel (#1458).

``TaskManager.complete_task``/``fail_task`` setzten bislang nur eine
hartkodiert-englische ``message`` ("Task completed"/"Task failed"), die ohne
Übersetzung in einer deutschen Oberfläche landete. Diese Tests decken den
neuen ``message_key`` ab, der dem Frontend einen i18n-Lookup erlaubt, während
``message`` unverändert als Fallback für ältere Consumer erhalten bleibt.
"""

from __future__ import annotations

from app.models.task import TaskManager, TaskStatus


def test_complete_task_sets_message_key_and_keeps_fallback_message():
    """``complete_task`` liefert Schlüssel + unveränderten Fallback-Text."""
    task_id = TaskManager().create_task("graph_build")

    TaskManager().complete_task(task_id, result={"ok": True})

    task = TaskManager().get_task(task_id)
    assert task is not None
    assert task.status == TaskStatus.COMPLETED
    # Fallback bleibt exakt der bisherige Text — kein Consumer, der nur
    # ``message`` liest, darf leer laufen oder eine andere Sprache sehen.
    assert task.message == "Task completed"
    assert task.message_key == "task.completed"

    as_dict = task.to_dict()
    assert as_dict["message"] == "Task completed"
    assert as_dict["message_key"] == "task.completed"


def test_fail_task_sets_message_key_and_keeps_fallback_message():
    """``fail_task`` liefert Schlüssel + unveränderten Fallback-Text."""
    task_id = TaskManager().create_task("graph_build")

    TaskManager().fail_task(task_id, error="boom")

    task = TaskManager().get_task(task_id)
    assert task is not None
    assert task.status == TaskStatus.FAILED
    assert task.message == "Task failed"
    assert task.message_key == "task.failed"
    assert task.error == "boom"

    as_dict = task.to_dict()
    assert as_dict["message"] == "Task failed"
    assert as_dict["message_key"] == "task.failed"


def test_new_task_has_no_message_key_by_default():
    """Ein frisch erzeugter Task ohne explizites Update hat keinen Schlüssel.

    ``message_key`` ist additiv — ältere Codepfade, die ``update_task`` ohne
    ``message_key`` aufrufen, dürfen keinen falschen Schlüssel erben.
    """
    task_id = TaskManager().create_task("graph_build")

    task = TaskManager().get_task(task_id)
    assert task is not None
    assert task.message_key is None
    assert task.to_dict()["message_key"] is None


def test_update_task_can_set_message_key_explicitly():
    """``update_task`` erlaubt beliebige Aufrufer, einen eigenen Schlüssel zu setzen."""
    task_id = TaskManager().create_task("graph_build")

    TaskManager().update_task(
        task_id,
        status=TaskStatus.PROCESSING,
        message="Chunking text...",
        message_key="task.chunking",
    )

    task = TaskManager().get_task(task_id)
    assert task is not None
    assert task.message == "Chunking text..."
    assert task.message_key == "task.chunking"
