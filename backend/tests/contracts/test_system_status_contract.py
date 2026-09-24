"""Contract-Tests fuer den Neo4j-/Disk-Teilbaum von ``/api/status`` (Issue #1466).

Vorher waren ``_get_neo4j_status``/``_get_disk_status`` handgeschriebene
Dicts ohne Gegenstueck in ``schemas/`` und ohne Zod-Drift-Check — nur der
Ollama-Teilbaum (#955/#1458) war bereits vertraglich abgedeckt. Diese Tests
bewachen ``SystemStatusNeo4j``/``SystemStatusDisk``: strikte Validierung und
das ``exclude_unset``-Serialisierungsverhalten, das das bisherige,
zweigabhaengige Wire-Format exakt nachbildet.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.system_status_contract import (
    StatusCheckError,
    StatusErrorCode,
    SystemStatusDisk,
    SystemStatusDiskUploads,
    SystemStatusNeo4j,
)


class TestSystemStatusNeo4j:
    def test_no_storage_branch_omits_is_connected_and_last_success_ts(self):
        """``storage is None`` — bisheriges Dict liess beide Felder ganz aus."""
        status = SystemStatusNeo4j(
            reachable=False,
            error=StatusCheckError(code=StatusErrorCode.UNREACHABLE),
            uri="bolt://localhost:7687",
        )
        dumped = status.model_dump(mode="json", exclude_unset=True)
        assert dumped == {
            "reachable": False,
            "error": {"code": "unreachable"},
            "uri": "bolt://localhost:7687",
        }
        assert "is_connected" not in dumped
        assert "last_success_ts" not in dumped

    def test_reachable_branch_includes_all_fields_even_null_timestamp(self):
        """Erfolgreiche Probe ohne je erfolgreichen Sync — ``last_success_ts``
        bleibt als explizites ``null``-Feld erhalten, nicht ausgelassen."""
        status = SystemStatusNeo4j(
            reachable=True,
            error=None,
            uri="bolt://localhost:7687",
            is_connected=True,
            last_success_ts=None,
        )
        dumped = status.model_dump(mode="json", exclude_unset=True)
        assert dumped == {
            "reachable": True,
            "error": None,
            "uri": "bolt://localhost:7687",
            "is_connected": True,
            "last_success_ts": None,
        }

    def test_unreachable_branch_carries_structured_error(self):
        status = SystemStatusNeo4j(
            reachable=False,
            error=StatusCheckError(code=StatusErrorCode.TIMEOUT),
            uri="bolt://localhost:7687",
            is_connected=False,
            last_success_ts="2026-09-20T10:00:00+00:00",
        )
        dumped = status.model_dump(mode="json", exclude_unset=True)
        assert dumped["error"] == {"code": "timeout"}
        assert dumped["is_connected"] is False
        assert dumped["last_success_ts"] == "2026-09-20T10:00:00+00:00"

    def test_unknown_field_is_rejected(self):
        with pytest.raises(ValidationError):
            SystemStatusNeo4j(reachable=True, unexpected_field=True)  # type: ignore[call-arg]


class TestSystemStatusDisk:
    def test_success_branch_omits_error_field(self):
        status = SystemStatusDisk(
            uploads=SystemStatusDiskUploads(
                path="/srv/agora/uploads",
                total_bytes=1000,
                free_bytes=500,
                used_pct=50.0,
            )
        )
        dumped = status.model_dump(mode="json", exclude_unset=True)
        assert dumped == {
            "uploads": {
                "path": "/srv/agora/uploads",
                "total_bytes": 1000,
                "free_bytes": 500,
                "used_pct": 50.0,
            }
        }
        assert "error" not in dumped["uploads"]

    def test_failure_branch_includes_null_metrics_and_structured_error(self):
        status = SystemStatusDisk(
            uploads=SystemStatusDiskUploads(
                path="/srv/agora/uploads",
                total_bytes=None,
                free_bytes=None,
                used_pct=None,
                error=StatusCheckError(code=StatusErrorCode.AUTH),
            )
        )
        dumped = status.model_dump(mode="json", exclude_unset=True)
        assert dumped == {
            "uploads": {
                "path": "/srv/agora/uploads",
                "total_bytes": None,
                "free_bytes": None,
                "used_pct": None,
                "error": {"code": "auth"},
            }
        }

    def test_unknown_field_on_uploads_is_rejected(self):
        with pytest.raises(ValidationError):
            SystemStatusDiskUploads(path="/x", unexpected_field=True)  # type: ignore[call-arg]
