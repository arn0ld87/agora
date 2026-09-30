"""Contract-Tests fuer SimActionRecord/SimActionPage/RoundSummary (#1713 UI-2a).

Layer 0 — extra="forbid", Enum-Werte hart, Pflichtfelder hart.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts.sim_action_contract import (
    RoundSummary,
    SimActionPage,
    SimActionRecord,
    SimActionType,
)


def _valid_record_payload(**overrides) -> dict:
    payload = {
        "round_num": 1,
        "sim_time": None,
        "timestamp": datetime.now(timezone.utc),
        "platform": "twitter",
        "agent_id": "agent-1",
        "agent_name": "Mara Lindner",
        "action_type": "CREATE_POST",
        "target_post_id": None,
        "target_comment_id": None,
        "target_agent_id": None,
        "target_agent_name": None,
        "content": "Hallo Welt",
        "success": True,
        "role_conflict": None,
    }
    payload.update(overrides)
    return payload


class TestSimActionRecord:
    def test_accepts_valid_payload(self) -> None:
        rec = SimActionRecord.model_validate(_valid_record_payload())
        assert rec.action_type is SimActionType.CREATE_POST
        assert rec.success is True

    def test_rejects_unknown_field(self) -> None:
        payload = _valid_record_payload()
        payload["extra"] = "x"
        with pytest.raises(ValidationError):
            SimActionRecord.model_validate(payload)

    def test_rejects_unknown_action_type(self) -> None:
        payload = _valid_record_payload(action_type="RETWEET")
        with pytest.raises(ValidationError):
            SimActionRecord.model_validate(payload)

    def test_other_action_type_accepted(self) -> None:
        rec = SimActionRecord.model_validate(_valid_record_payload(action_type="OTHER"))
        assert rec.action_type is SimActionType.OTHER

    def test_success_defaults_true(self) -> None:
        payload = _valid_record_payload()
        del payload["success"]
        rec = SimActionRecord.model_validate(payload)
        assert rec.success is True

    def test_role_conflict_accepts_known_reason(self) -> None:
        rec = SimActionRecord.model_validate(
            _valid_record_payload(role_conflict="foreign_role")
        )
        assert rec.role_conflict == "foreign_role"

    def test_role_conflict_rejects_unknown_reason(self) -> None:
        with pytest.raises(ValidationError):
            SimActionRecord.model_validate(
                _valid_record_payload(role_conflict="not-a-real-reason")
            )

    def test_target_fields_optional(self) -> None:
        rec = SimActionRecord.model_validate(
            _valid_record_payload(
                action_type="REPOST",
                target_post_id="twitter:p-1",
            )
        )
        assert rec.target_post_id == "twitter:p-1"

    def test_agent_id_required_non_empty(self) -> None:
        payload = _valid_record_payload(agent_id="")
        with pytest.raises(ValidationError):
            SimActionRecord.model_validate(payload)

    def test_round_num_rejects_negative(self) -> None:
        with pytest.raises(ValidationError):
            SimActionRecord.model_validate(_valid_record_payload(round_num=-1))


class TestSimActionPage:
    def test_accepts_empty_page(self) -> None:
        page = SimActionPage.model_validate({"items": [], "next_cursor": None})
        assert page.items == []
        assert page.next_cursor is None

    def test_accepts_items_with_cursor(self) -> None:
        page = SimActionPage.model_validate(
            {"items": [_valid_record_payload()], "next_cursor": "42"}
        )
        assert len(page.items) == 1
        assert page.next_cursor == "42"

    def test_rejects_unknown_field(self) -> None:
        with pytest.raises(ValidationError):
            SimActionPage.model_validate({"items": [], "next_cursor": None, "total": 1})


class TestRoundSummary:
    def test_accepts_valid_payload(self) -> None:
        summary = RoundSummary.model_validate(
            {
                "round_num": 2,
                "platform": "reddit",
                "action_counts": {"CREATE_POST": 3, "CREATE_COMMENT": 5},
            }
        )
        assert summary.action_counts[SimActionType.CREATE_POST] == 3

    def test_action_counts_defaults_empty(self) -> None:
        summary = RoundSummary.model_validate({"round_num": 0, "platform": "twitter"})
        assert summary.action_counts == {}

    def test_rejects_unknown_action_type_key(self) -> None:
        with pytest.raises(ValidationError):
            RoundSummary.model_validate(
                {
                    "round_num": 0,
                    "platform": "twitter",
                    "action_counts": {"RETWEET": 1},
                }
            )

    def test_rejects_unknown_field(self) -> None:
        with pytest.raises(ValidationError):
            RoundSummary.model_validate(
                {"round_num": 0, "platform": "twitter", "extra": "x"}
            )


class TestSchemaDump:
    @pytest.mark.parametrize(
        "filename",
        [
            "sim-action-record.schema.json",
            "sim-action-page.schema.json",
            "round-summary.schema.json",
        ],
    )
    def test_schema_dump_exists(self, filename: str) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        schema_path = repo_root / "schemas" / filename
        assert schema_path.exists(), f"Schema-Dump fehlt: {schema_path}"
        json.loads(schema_path.read_text(encoding="utf-8"))
