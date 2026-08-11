"""Task 1 — PostCreatedEvent.sim_time Contract-Tests.

Sichert ab:
- sim_time ist optional und akzeptiert None / fehlt
- tz-aware Werte werden akzeptiert (UTC, +0200)
- tz-naive Werte werden abgelehnt (Layer-0 erzwingt Offset)
- Snapshot-Drift: schemas/post-created-event.schema.json enthält das Feld
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts.post_event_contract import PostCreatedEvent


def _base_payload(**overrides):
    payload = {
        "event_type": "post_created",
        "simulation_id": "sim-1",
        "post_id": "p-1",
        "parent_post_id": None,
        "platform": "twitter",
        "persona_id": "persona-1",
        "persona_name": "Test Persona",
        "voice_register": "neutral-de",
        "is_simulated": True,
        "body": "Hello",
        "timestamp": datetime.now(timezone.utc),
    }
    payload.update(overrides)
    return payload


def test_sim_time_field_is_optional_default_none() -> None:
    event = PostCreatedEvent(**_base_payload())
    assert event.sim_time is None


def test_sim_time_accepts_tz_aware_utc() -> None:
    dt = datetime(2026, 5, 16, 10, 30, tzinfo=timezone.utc)
    event = PostCreatedEvent(**_base_payload(sim_time=dt))
    assert event.sim_time == dt


def test_sim_time_accepts_tz_aware_offset() -> None:
    tz = timezone(timedelta(hours=2))
    dt = datetime(2026, 5, 16, 12, 30, tzinfo=tz)
    event = PostCreatedEvent(**_base_payload(sim_time=dt))
    assert event.sim_time == dt


def test_sim_time_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError) as exc_info:
        PostCreatedEvent(**_base_payload(sim_time=datetime(2026, 5, 16, 10, 30)))
    msg = str(exc_info.value)
    assert "tz-aware" in msg or "tzinfo" in msg or "UTC" in msg or "Offset" in msg or "offset" in msg


def test_schema_dump_contains_sim_time_field() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "schemas" / "post-created-event.schema.json"
    assert schema_path.exists(), f"Schema-Dump fehlt: {schema_path}"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    props = schema.get("properties", {})
    assert "sim_time" in props, "sim_time muss im dumped Schema vorhanden sein"
