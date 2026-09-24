"""Tests für den Job-Lease-Guard in POST /api/runs/<id>/resume.

Issue #1472, Architekturentscheidung 2026-09-24 (inkl. Korrektur): eine
gültige, unabgelaufene Lease blockiert Resume mit 409/``job_lease_active`` —
aber NUR, wenn der Run laut Registry noch nicht-terminal ist
(``pending``/``processing``). Ein Run mit terminalem Status (insbesondere
``failed``/``process_restart``, von ``reconcile_stale_jobs`` ehrlich als
verwaist markiert) darf trotz einer rechnerisch noch nicht abgelaufenen
Lease fortgesetzt werden — sonst wäre ein bereits korrekt terminalisierter
Job bis zu ``lease_ttl_s`` Sekunden lang blockiert.

Reine Dispatcher-Ebene: ``_resume_or_restart_graph_build`` wird gepatcht
(Sentinel-Stub), damit dieser Test nur prüft, OB der Guard durchlässt —
nicht, was der eigentliche Graph-Build-Resume tut (das deckt
``tests/api/test_resume_graph_build.py`` ab).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from flask import Flask

from app.api import runs_bp
from app.config import Config
from app.contracts.job_lease_contract import JobLease
from app.jobs.identity import current_worker_identity
from app.models.project import ProjectManager
from app.services.artifact_store import InMemoryArtifactStore
from app.services.run_registry import RunRegistry
from app.services.simulation_manager import SimulationManager


@pytest.fixture()
def env(tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(upload_root / "projects"))
    monkeypatch.setattr(
        SimulationManager, "SIMULATION_DATA_DIR", str(upload_root / "simulations")
    )
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(upload_root / "run_registry"))
    RunRegistry._instance = None
    os.makedirs(RunRegistry.REGISTRY_DIR, exist_ok=True)

    artifact_store = InMemoryArtifactStore()

    app = Flask(__name__)
    app.extensions = {"artifact_store": artifact_store}
    app.register_blueprint(runs_bp, url_prefix="/api/runs")

    registry = RunRegistry()

    yield {
        "app": app,
        "client": app.test_client(),
        "registry": registry,
    }

    RunRegistry._instance = None


def _create_graph_build_run(
    registry: RunRegistry,
    *,
    status: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return registry.create_run(
        run_type="graph_build",
        entity_id="proj_lease",
        status=status,
        message="ok",
        linked_ids={"project_id": "proj_lease", "graph_id": "graph-lease"},
        metadata=metadata,
    )


def _valid_lease_metadata() -> dict[str, Any]:
    return JobLease(
        owner_pid=os.getpid(),
        owner_token="a-foreign-or-own-token-doesnt-matter",
        heartbeat_at=datetime.now(UTC),
        lease_ttl_s=90,
    ).to_metadata()


def _expired_lease_metadata() -> dict[str, Any]:
    return JobLease(
        owner_pid=os.getpid(),
        owner_token="whatever",
        heartbeat_at=datetime.now(UTC) - timedelta(seconds=999),
        lease_ttl_s=90,
    ).to_metadata()


def _patched_dispatch():
    return patch(
        "app.api.runs._resume_or_restart_graph_build",
        return_value={"path": "dispatched"},
    )


# ---------------------------------------------------------------------------
# 1. Nicht-terminaler Run + gültige Lease → 409/job_lease_active
# ---------------------------------------------------------------------------


class TestLeaseBlocksResumeWhileRunIsNonTerminal:
    @pytest.mark.parametrize("status", ["pending", "processing"])
    def test_valid_lease_returns_409_with_lease_active_code(self, env, status: str) -> None:
        run = _create_graph_build_run(
            env["registry"], status=status, metadata=_valid_lease_metadata()
        )

        with _patched_dispatch() as dispatch_stub:
            resp = env["client"].post(f"/api/runs/{run['run_id']}/resume")

        assert resp.status_code == 409
        payload = resp.get_json()
        assert payload["success"] is False
        assert payload.get("code") == "job_lease_active"
        dispatch_stub.assert_not_called()


# ---------------------------------------------------------------------------
# 2. Korrektur des Maintainers: terminaler Status trotz gültiger Lease → OK
# ---------------------------------------------------------------------------


class TestTerminalStatusBypassesTheLeaseGuard:
    @pytest.mark.parametrize("status", ["failed", "stopped", "completed"])
    def test_valid_lease_does_not_block_a_terminal_run(self, env, status: str) -> None:
        """Ein ehrlich terminalisierter Run (insbesondere failed/
        process_restart nach ``reconcile_stale_jobs``) darf nicht bis zu
        ``lease_ttl_s`` Sekunden lang blockiert bleiben, nur weil die Lease
        rechnerisch noch nicht abgelaufen ist."""
        run = _create_graph_build_run(
            env["registry"], status=status, metadata=_valid_lease_metadata()
        )

        with _patched_dispatch() as dispatch_stub:
            resp = env["client"].post(f"/api/runs/{run['run_id']}/resume")

        assert resp.status_code == 200, resp.get_json()
        dispatch_stub.assert_called_once()


# ---------------------------------------------------------------------------
# 3. Abgelaufene Lease erlaubt Resume, auch bei nicht-terminalem Status
# ---------------------------------------------------------------------------


class TestExpiredLeaseAllowsResume:
    def test_expired_lease_on_a_processing_run_does_not_block_resume(self, env) -> None:
        run = _create_graph_build_run(
            env["registry"], status="processing", metadata=_expired_lease_metadata()
        )

        with _patched_dispatch() as dispatch_stub:
            resp = env["client"].post(f"/api/runs/{run['run_id']}/resume")

        assert resp.status_code == 200, resp.get_json()
        dispatch_stub.assert_called_once()


# ---------------------------------------------------------------------------
# 4. Rückwärtskompatibilität: Altbestand ohne Lease (nur PID+Token-Stempel)
# ---------------------------------------------------------------------------


class TestLegacyStampWithoutLeaseIsUnaffected:
    def test_legacy_metadata_without_heartbeat_does_not_block_resume(self, env) -> None:
        run = _create_graph_build_run(
            env["registry"], status="processing", metadata=current_worker_identity()
        )

        with _patched_dispatch() as dispatch_stub:
            resp = env["client"].post(f"/api/runs/{run['run_id']}/resume")

        assert resp.status_code == 200, resp.get_json()
        dispatch_stub.assert_called_once()

    def test_run_without_any_metadata_does_not_block_resume(self, env) -> None:
        run = _create_graph_build_run(env["registry"], status="processing", metadata={})

        with _patched_dispatch() as dispatch_stub:
            resp = env["client"].post(f"/api/runs/{run['run_id']}/resume")

        assert resp.status_code == 200, resp.get_json()
        dispatch_stub.assert_called_once()
