"""API-Tests für GET /api/simulation/<sim_id>/compare (Sub-Slice 24, Closes #66).

Nutzt Flask-Test-Client mit app.extensions["compare_service"]-Override,
um echte Filesystem-/Neo4j-Abhängigkeiten zu vermeiden.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import simulation_bp
from app.contracts.branch_comparison import (
    BranchComparison,
    BranchMetrics,
    ComparisonDeltas,
)
from app.services.compare_service import BranchIncompleteError, BranchNotFoundError

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

VALID_SIM_ID = "sim_000000000000"
VALID_BRANCH_A = "sim_aaaaaaaaaaaa"
VALID_BRANCH_B = "sim_bbbbbbbbbbbb"


# ---------------------------------------------------------------------------
# Hilfs-Konstruktoren
# ---------------------------------------------------------------------------


def _make_branch_metrics(**overrides) -> BranchMetrics:
    defaults: dict = {
        "echo_chamber_index": 0.5,
        "cluster_count": 2,
        "dominant_clusters": [],
        "bridge_agent_ids": [],
        "total_agents": 10,
        "total_interactions": 40,
        "interaction_density": 4.0,
        "confidence_distribution": {"low": 1, "medium": 2, "high": 3, "verified": 0},
        "avg_evidence_per_claim": 2.0,
        "claims_without_evidence_ratio": 0.1,
        "contradiction_ratio": 0.05,
        "persona_reach": {},
    }
    defaults.update(overrides)
    return BranchMetrics(**defaults)


def _make_comparison() -> BranchComparison:
    now = datetime.now(timezone.utc)
    metrics_a = _make_branch_metrics(echo_chamber_index=0.4)
    metrics_b = _make_branch_metrics(echo_chamber_index=0.6)
    deltas = ComparisonDeltas(
        echo_chamber_delta=0.2,
        cluster_delta=0,
        bridge_agents_delta=0,
        confidence_distribution_delta={"low": 0, "medium": 0, "high": 0, "verified": 0},
        avg_evidence_delta=0.0,
        contradiction_ratio_delta=0.0,
        interaction_density_delta=0.0,
        clusters_only_in_a=[],
        clusters_only_in_b=[],
        clusters_changed=[],
    )
    return BranchComparison(
        simulation_id=VALID_SIM_ID,
        branch_a_id=VALID_BRANCH_A,
        branch_b_id=VALID_BRANCH_B,
        created_at=now,
        branch_a_completed_at=now,
        branch_b_completed_at=now,
        metrics_a=metrics_a,
        metrics_b=metrics_b,
        deltas=deltas,
    )


def _mock_service(comparison: BranchComparison | None = None) -> MagicMock:
    svc = MagicMock()
    svc.compare_branches.return_value = comparison or _make_comparison()
    return svc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app_factory():
    """Gibt eine Factory-Funktion zurück, die eine Flask-App mit optionalem Service-Override erzeugt."""

    def _build(*, service: MagicMock | None = None):
        flask_app = Flask(__name__)
        flask_app.extensions = {}
        if service is not None:
            flask_app.extensions["compare_service"] = service
        flask_app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
        return flask_app

    return _build


@pytest.fixture
def client(app_factory):
    svc = _mock_service()
    app = app_factory(service=svc)
    return app.test_client()


# ---------------------------------------------------------------------------
# Happy-Path
# ---------------------------------------------------------------------------


def test_get_compare_happy_path_200(app_factory):
    svc = _mock_service()
    app = app_factory(service=svc)
    c = app.test_client()

    resp = c.get(
        f"/api/simulation/{VALID_SIM_ID}/compare"
        f"?branch_a={VALID_BRANCH_A}&branch_b={VALID_BRANCH_B}"
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert "comparison" in body["data"]
    assert "timing" in body


def test_response_passes_pydantic_strict_roundtrip(app_factory):
    """Response-JSON ist per BranchComparison.model_validate parseable (strict Layer-0-Boundary)."""
    svc = _mock_service()
    app = app_factory(service=svc)
    c = app.test_client()

    resp = c.get(
        f"/api/simulation/{VALID_SIM_ID}/compare"
        f"?branch_a={VALID_BRANCH_A}&branch_b={VALID_BRANCH_B}"
    )
    body = resp.get_json()
    comparison_data = body["data"]["comparison"]
    parsed = BranchComparison.model_validate(comparison_data)
    assert parsed.simulation_id == VALID_SIM_ID
    assert parsed.branch_a_id == VALID_BRANCH_A
    assert parsed.branch_b_id == VALID_BRANCH_B


def test_window_size_rounds_passed_to_service(app_factory):
    svc = _mock_service()
    app = app_factory(service=svc)
    c = app.test_client()

    c.get(
        f"/api/simulation/{VALID_SIM_ID}/compare"
        f"?branch_a={VALID_BRANCH_A}&branch_b={VALID_BRANCH_B}&window_size_rounds=5"
    )
    svc.compare_branches.assert_called_once_with(
        simulation_id=VALID_SIM_ID,
        branch_a_id=VALID_BRANCH_A,
        branch_b_id=VALID_BRANCH_B,
        window_size_rounds=5,
    )


# ---------------------------------------------------------------------------
# 400-Fehler
# ---------------------------------------------------------------------------


def test_get_compare_missing_branch_a_400(app_factory):
    app = app_factory(service=_mock_service())
    c = app.test_client()
    resp = c.get(f"/api/simulation/{VALID_SIM_ID}/compare?branch_b={VALID_BRANCH_B}")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["success"] is False
    assert "branch_a" in body["error"].lower() or body.get("code") == "validation_failed"


def test_get_compare_missing_branch_b_400(app_factory):
    app = app_factory(service=_mock_service())
    c = app.test_client()
    resp = c.get(f"/api/simulation/{VALID_SIM_ID}/compare?branch_a={VALID_BRANCH_A}")
    assert resp.status_code == 400


def test_get_compare_identical_branches_400(app_factory):
    """Pre-Service-Guard: branch_a == branch_b → 400 ohne Service-Aufruf."""
    svc = _mock_service()
    app = app_factory(service=svc)
    c = app.test_client()
    resp = c.get(
        f"/api/simulation/{VALID_SIM_ID}/compare"
        f"?branch_a={VALID_BRANCH_A}&branch_b={VALID_BRANCH_A}"
    )
    assert resp.status_code == 400
    svc.compare_branches.assert_not_called()


def test_get_compare_invalid_sim_id_400(app_factory):
    app = app_factory(service=_mock_service())
    c = app.test_client()
    resp = c.get(
        "/api/simulation/not-a-valid-sim/compare"
        f"?branch_a={VALID_BRANCH_A}&branch_b={VALID_BRANCH_B}"
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body.get("code") == "invalid_id"


def test_get_compare_invalid_branch_id_format_400(app_factory):
    app = app_factory(service=_mock_service())
    c = app.test_client()
    resp = c.get(
        f"/api/simulation/{VALID_SIM_ID}/compare"
        "?branch_a=not-a-valid-branch&branch_b=also-invalid"
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 404 / 422-Fehler
# ---------------------------------------------------------------------------


def test_get_compare_branch_not_found_404(app_factory):
    svc = MagicMock()
    svc.compare_branches.side_effect = BranchNotFoundError(
        branch_id=VALID_BRANCH_A, simulation_id=VALID_SIM_ID
    )
    app = app_factory(service=svc)
    c = app.test_client()
    resp = c.get(
        f"/api/simulation/{VALID_SIM_ID}/compare"
        f"?branch_a={VALID_BRANCH_A}&branch_b={VALID_BRANCH_B}"
    )
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["success"] is False
    assert body.get("code") == "not_found"


def test_get_compare_branch_incomplete_422(app_factory):
    svc = MagicMock()
    svc.compare_branches.side_effect = BranchIncompleteError(
        branch_id=VALID_BRANCH_A, status="preparing"
    )
    app = app_factory(service=svc)
    c = app.test_client()
    resp = c.get(
        f"/api/simulation/{VALID_SIM_ID}/compare"
        f"?branch_a={VALID_BRANCH_A}&branch_b={VALID_BRANCH_B}"
    )
    assert resp.status_code == 422
    body = resp.get_json()
    assert body["success"] is False
    assert body.get("code") == "incomplete_state"
