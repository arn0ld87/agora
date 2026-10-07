"""Tests für GET /api/report/<id>/evidence-density und /stance-analysis (Issue #1804).

Beide Endpunkte liefern die je Bericht gespeicherten Artefakte
``evidence_density.json`` (#1779) und ``stance_analysis.json`` (#1778) aus. Der
Vertrag unterscheidet drei Zustände: Datei vorhanden und gültig (Daten),
Datei fehlt (404 wie bei einer fehlenden Evidence-Map), Datei vertragswidrig
(HTTP 200 mit ``artifact_omitted`` statt stiller Leere).
"""

from __future__ import annotations

import json
import os

import pytest
from flask import Flask

from app.api import report_bp
from app.contracts.evidence_density_contract import EvidenceDensity
from app.contracts.report_artifact_contract import (
    EvidenceDensityResponseModel,
    StanceAnalysisResponseModel,
)
from app.contracts.stance_analysis_contract import (
    ClassifiedContribution,
    StanceAnalysis,
    VoiceStance,
)
from app.services.report_agent import ReportManager
from app.services.report_agent.evidence_density import EVIDENCE_DENSITY_FILENAME
from app.services.report_agent.stance_analysis import (
    STANCE_ANALYSIS_FILENAME,
    save_stance_analysis,
)

REPORT_ID = "report_abcdef123456"

ENDPOINTS = {
    "evidence-density": (EVIDENCE_DENSITY_FILENAME, "evidence_density"),
    "stance-analysis": (STANCE_ANALYSIS_FILENAME, "stance_analysis"),
}


@pytest.fixture
def reports_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def client(reports_dir):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(report_bp, url_prefix="/api/report")
    return app.test_client()


def _density() -> EvidenceDensity:
    return EvidenceDensity(
        claims_total=4,
        claims_without_support=1,
        claims_single_support=2,
        claims_multi_support=1,
        claims_multi_independent=1,
        claims_at_single_source_cap=2,
        claims_with_action_support=1,
        supporting_links_by_type={"agent_action": 1, "graph_fact": 3},
        single_support_ratio=0.5,
        action_support_ratio=0.25,
        single_source_cap_ratio=0.5,
        multi_independent_ratio=0.25,
    )


def _stance() -> StanceAnalysis:
    return StanceAnalysis(
        contested_statement="Die Maßnahme soll kommen.",
        applicable=True,
        voices_total=2,
        voices_positioned=1,
        positioning_ratio=0.5,
        camp_distribution={"in_favour": 1, "undecided": 1},
        voices=[
            VoiceStance(
                voice_key="agent:1",
                agent_name="Anna",
                start_class="in_favour",
                contribution_classes=["in_favour"],
            ),
            VoiceStance(voice_key="agent:2", agent_name="Ben", start_class="undecided"),
        ],
        contributions=[
            ClassifiedContribution(
                agent_id=1,
                agent_name="Anna",
                platform="twitter",
                round_num=1,
                action_type="CREATE_POST",
                producer_key="simulation-action:twitter:1:1:CREATE_POST:2026-08-02T15:02:16",
                stance_class="in_favour",
            )
        ],
        classified_total=1,
    )


def _write_density() -> None:
    ReportManager.save_evidence_density(REPORT_ID, _density())


def _write_stance() -> None:
    save_stance_analysis(ReportManager._ensure_report_folder(REPORT_ID), _stance())


class TestEvidenceDensityRoute:
    def test_delivers_stored_density_in_success_envelope(self, client):
        _write_density()

        resp = client.get(f"/api/report/{REPORT_ID}/evidence-density")

        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = resp.get_json()
        assert body["success"] is True
        assert "artifact_omitted" not in body
        assert body["data"] == _density().model_dump(mode="json")
        # Antwort ist vertragsgültig: dieselbe Wire-Form, die das Frontend parst.
        EvidenceDensityResponseModel.model_validate(body)

    def test_missing_file_is_404_like_a_missing_evidence_map(self, client):
        resp = client.get(f"/api/report/{REPORT_ID}/evidence-density")

        assert resp.status_code == 404
        body = resp.get_json()
        assert body["success"] is False
        assert REPORT_ID in body["error"]

    def test_contract_violating_file_is_reported_not_silently_empty(self, client, reports_dir):
        folder = ReportManager._ensure_report_folder(REPORT_ID)
        broken = _density().model_dump(mode="json")
        broken["claims_total"] = 99  # Summe der Buckets stimmt nicht mehr
        with open(os.path.join(folder, EVIDENCE_DENSITY_FILENAME), "w", encoding="utf-8") as fh:
            json.dump(broken, fh)

        resp = client.get(f"/api/report/{REPORT_ID}/evidence-density")

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert "data" not in body
        omitted = body["artifact_omitted"]
        assert omitted["artifact"] == "evidence_density"
        assert omitted["reason"] == "contract_violation"
        assert omitted["validation_errors"], "die Einstufung muss belegt sein"
        EvidenceDensityResponseModel.model_validate(body)

    def test_corrupt_json_is_reported_as_contract_violation(self, client):
        folder = ReportManager._ensure_report_folder(REPORT_ID)
        with open(os.path.join(folder, EVIDENCE_DENSITY_FILENAME), "w", encoding="utf-8") as fh:
            fh.write("{not json")

        resp = client.get(f"/api/report/{REPORT_ID}/evidence-density")

        assert resp.status_code == 200
        assert resp.get_json()["artifact_omitted"]["reason"] == "contract_violation"

    def test_invalid_report_id_is_400(self, client):
        resp = client.get("/api/report/not-a-report/evidence-density")
        assert resp.status_code == 400


class TestStanceAnalysisRoute:
    def test_delivers_stored_analysis_in_success_envelope(self, client):
        _write_stance()

        resp = client.get(f"/api/report/{REPORT_ID}/stance-analysis")

        assert resp.status_code == 200, resp.get_data(as_text=True)
        body = resp.get_json()
        assert body["success"] is True
        assert "artifact_omitted" not in body
        assert body["data"] == _stance().model_dump(mode="json")
        assert body["data"]["positioning_ratio"] == 0.5
        StanceAnalysisResponseModel.model_validate(body)

    def test_not_applicable_analysis_is_delivered_as_data(self, client):
        # ``applicable=False`` ist ein im Vertrag vorgesehener Zustand (Lauf ohne
        # Streitfrage) und kein Fehler — die Quote bleibt ``None``.
        save_stance_analysis(
            ReportManager._ensure_report_folder(REPORT_ID),
            StanceAnalysis(applicable=False),
        )

        resp = client.get(f"/api/report/{REPORT_ID}/stance-analysis")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["applicable"] is False
        assert data["positioning_ratio"] is None

    def test_missing_file_is_404(self, client):
        resp = client.get(f"/api/report/{REPORT_ID}/stance-analysis")

        assert resp.status_code == 404
        assert resp.get_json()["success"] is False

    def test_contract_violating_file_is_reported_not_silently_empty(self, client):
        folder = ReportManager._ensure_report_folder(REPORT_ID)
        broken = _stance().model_dump(mode="json")
        broken["positioning_ratio"] = 7.0  # le=1.0 verletzt
        with open(os.path.join(folder, STANCE_ANALYSIS_FILENAME), "w", encoding="utf-8") as fh:
            json.dump(broken, fh)

        resp = client.get(f"/api/report/{REPORT_ID}/stance-analysis")

        assert resp.status_code == 200
        body = resp.get_json()
        assert "data" not in body
        omitted = body["artifact_omitted"]
        assert omitted["artifact"] == "stance_analysis"
        assert any("positioning_ratio" in err for err in omitted["validation_errors"])
        StanceAnalysisResponseModel.model_validate(body)

    def test_invalid_report_id_is_400(self, client):
        resp = client.get("/api/report/not-a-report/stance-analysis")
        assert resp.status_code == 400


@pytest.mark.parametrize("endpoint", sorted(ENDPOINTS))
def test_artifact_read_does_not_mutate_the_stored_file(client, reports_dir, endpoint):
    """Rein lesender Pfad: die gespeicherte Datei bleibt byte-identisch."""
    filename, _ = ENDPOINTS[endpoint]
    _write_density() if endpoint == "evidence-density" else _write_stance()
    path = os.path.join(ReportManager._get_report_folder(REPORT_ID), filename)
    before = open(path, "rb").read()

    assert client.get(f"/api/report/{REPORT_ID}/{endpoint}").status_code == 200

    assert open(path, "rb").read() == before
