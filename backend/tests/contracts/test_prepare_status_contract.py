"""Contract-Tests fuer PrepareStatusResponse (Issue #1174, Codex-Finding 1).

Vorher lieferten die Kurzschluss-Antworten von
``POST /api/simulation/prepare`` und ``POST /api/simulation/prepare/status``
handgeschriebene Dicts an der API-Grenze aus. Diese Tests bewachen den
Vertrag: strikte Validierung, das ``message_key``-Feld aus #1458/#1174 und
das erhaltene Bestandsverhalten (unbesetzte optionale Felder erscheinen
nicht als ``null`` im JSON).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.persona_target_contract import PersonaTargetContract
from app.contracts.prepare_status_contract import PrepareStatusResponse


def test_prepared_shortcut_payload_round_trips():
    payload = PrepareStatusResponse(
        simulation_id="sim_0123456789ab",
        status="ready",
        message="Preparation already completed, no need to regenerate",
        message_key="prepare.already_completed",
        already_prepared=True,
        prepare_info={"status": "ready"},
    )
    dumped = payload.model_dump(mode="json", exclude_none=True)
    assert dumped == {
        "simulation_id": "sim_0123456789ab",
        "status": "ready",
        "message": "Preparation already completed, no need to regenerate",
        "message_key": "prepare.already_completed",
        "already_prepared": True,
        "prepare_info": {"status": "ready"},
    }


def test_task_started_payload_nests_persona_target_contract():
    target = PersonaTargetContract(
        entity_count=7, persona_target_count=50, floor_applied=True, floor=50
    )
    payload = PrepareStatusResponse(
        simulation_id="sim_0123456789ab",
        task_id="task-1",
        run_id="run-1",
        status="preparing",
        message="Preparation task started; query progress via /api/simulation/prepare/status",
        message_key="prepare.task_started",
        already_prepared=False,
        expected_entities_count=7,
        entity_types=["Person"],
        persona_target=target,
    )
    dumped = payload.model_dump(mode="json", exclude_none=True)
    assert dumped["persona_target"] == {
        "entity_count": 7,
        "persona_target_count": 50,
        "floor_applied": True,
        "floor": 50,
    }


def test_unset_optional_fields_are_excluded_from_serialization():
    """Bewacht das Bestandsverhalten: `_already_prepared_response` liefert kein
    `task_id`/`progress`/`persona_target` — diese Felder duerfen im JSON nicht
    als `null` auftauchen (sonst wich die neue Vertrags-Serialisierung von den
    alten handgeschriebenen Dicts ab)."""
    payload = PrepareStatusResponse(
        simulation_id="sim_0123456789ab",
        status="ready",
        message="Preparation already completed, no need to regenerate",
        message_key="prepare.already_completed",
        already_prepared=True,
        prepare_info={},
    )
    dumped = payload.model_dump(mode="json", exclude_none=True)
    for absent_field in ("task_id", "run_id", "progress", "expected_entities_count", "entity_types", "persona_target"):
        assert absent_field not in dumped


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        PrepareStatusResponse(
            simulation_id="sim_0123456789ab",
            status="ready",
            message="x",
            message_key="prepare.already_completed",
            already_prepared=True,
            unexpected_field=True,
        )


def test_unknown_status_value_rejected():
    """Der Live-Task-Zweig (Task.to_dict()) liefert z.B. "processing" — dieser
    Contract deckt nur die drei literalen Kurzschluss-Zustaende ab."""
    with pytest.raises(ValidationError):
        PrepareStatusResponse(
            simulation_id="sim_0123456789ab",
            status="processing",
            message="x",
            message_key="prepare.already_completed",
            already_prepared=False,
        )


def test_unknown_message_key_rejected():
    with pytest.raises(ValidationError):
        PrepareStatusResponse(
            simulation_id="sim_0123456789ab",
            status="ready",
            message="x",
            message_key="prepare.unbekannt",
            already_prepared=True,
        )
