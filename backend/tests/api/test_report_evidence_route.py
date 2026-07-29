"""Tests für GET /api/report/<report_id>/evidence (Issue #963).

Der Lese-Pfad ruft ``migrate_v1_to_v2`` und validiert danach gegen
``EvidenceMapModel``. Persistierte Maps mit medium-Claims, die nur auf
``seed_corpus``/``graph_relation``-Evidence ruhen (vor PR #961 erzeugt),
müssen vor der Validation per ``migrate_medium_seed_only_claims_to_low``
auf ``low`` heruntergestuft werden — sonst HTTP 422.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from flask import Flask

from app.api import report_bp


VALID_REPORT_ID = "report_abcdef123456"


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(report_bp, url_prefix="/api/report")
    return app.test_client()


def _legacy_medium_seed_only_map():
    """Schema-v2-Map wie sie VOR PR #961 persistiert wurde: medium-Claim,
    der sich nur auf seed_corpus-Evidence stützt (heute ungültig)."""
    return {
        "schema_version": 2,
        "report_id": VALID_REPORT_ID,
        "simulation_id": "sim_0123456789ab",
        "global_evidence": [],
        "sections": [
            {
                "section_index": 1,
                "section_title": "Kontext",
                "section_summary": "Zusammenfassung",
                "claims": [
                    {
                        "claim_id": "claim_01",
                        "claim_text": "Nutzer bevorzugen Variante A.",
                        "confidence_label": "medium",
                        "confidence_score": 0.6,
                        "evidence": [
                            {
                                "type": "entity_summary",
                                "source_kind": "seed_corpus",
                                "source": "seed:doc_1",
                                "snippet": "Beleg aus dem Korpus.",
                            }
                        ],
                        "audit_trail": [],
                        "notes": None,
                    }
                ],
                "hypotheses": [],
                "data_gaps": [],
            }
        ],
    }


class TestReportEvidenceRoute:
    def test_legacy_medium_seed_only_map_returns_200_and_low_label(self, client):
        """Persistierte medium-seed-only-Map bricht nicht mit 422 — die
        Migration stuft den Claim vor dem Validator auf ``low``."""
        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch(
                "app.api.report.ReportManager.get_evidence_map",
                return_value=_legacy_medium_seed_only_map(),
            ),
        ):
            resp = client.get(f"/api/report/{VALID_REPORT_ID}/evidence")

        assert resp.status_code == 200
        body = resp.get_json()
        claim = body["data"]["sections"][0]["claims"][0]
        assert claim["confidence_label"] == "low"

    def test_agent_grounded_medium_claim_stays_medium(self, client):
        evidence_map = _legacy_medium_seed_only_map()
        evidence_map["sections"][0]["claims"][0]["evidence"].append(
            {
                "type": "agent_interview",
                "source_kind": "agent_quote",
                "source": "agent:persona_1",
                "snippet": "Wörtliches Zitat.",
                "quote": "Wörtliches Zitat.",
                "persona_stakeholder_group": "kunden",
            }
        )
        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch(
                "app.api.report.ReportManager.get_evidence_map",
                return_value=evidence_map,
            ),
        ):
            resp = client.get(f"/api/report/{VALID_REPORT_ID}/evidence")

        assert resp.status_code == 200
        body = resp.get_json()
        claim = body["data"]["sections"][0]["claims"][0]
        assert claim["confidence_label"] == "medium"
