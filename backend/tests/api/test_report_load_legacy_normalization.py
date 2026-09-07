"""Review B7 (2026-09-08) — Lese-Pfad degradiert Rollenfamilien-Altbestand.

`EvidenceMapModel.validate_evidence_cross_references` zaehlte bislang den
rohen ``persona_stakeholder_group``-Wert statt der normalisierten
Rollenfamilie (siehe ``_role_family_key``). Ein Altartefakt mit zwei
Schreibweisen derselben Rollenfamilie ("Buerger"/"buerger ") validierte vor
der Verschaerfung noch als zwei Gruppen, obwohl es dieselbe Rolle ist. Nach
der Verschaerfung scheitert dieselbe Map zurecht am Anker — kein
Migrationsschritt kann den Rohtext nachtraeglich vereinheitlichen.

Dieser Test stellt sicher, dass der Lese-Pfad (``GET
/api/report/<id>/evidence``) ein solches Altartefakt degradiert (200 mit
``evidence_omitted``) statt es mit 422 abzuweisen — Parität zum JSON-Export,
der dasselbe Verhalten bereits seit Issue #987 zeigt.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from flask import Flask

from app.api import report_bp

REPORT_ID = "report_b7legacy0001"


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(report_bp, url_prefix="/api/report")
    return app.test_client()


def _agent_quote(group: str, role_family: str) -> dict:
    return {
        "type": "agent_interview",
        "source": "agent-log",
        "snippet": f"Aussage aus {group}.",
        "quote": f"Original-Zitat aus {group}.",
        "producer_key": f"agent-log#{group}",
        "match_score": 0.9,
        "supports_claim": True,
        "source_kind": "agent_quote",
        "persona_stakeholder_group": group,
        "persona_role_family": role_family,
    }


def _legacy_map_with_double_spelling() -> dict:
    """Schema-v2-Altartefakt: high-Claim, zwei Schreibweisen derselben Rolle.

    "Bürger" und "bürger " (mit Leerzeichen) sind derselbe Berufstitel in
    zwei Schreibweisen UND dieselbe ``persona_role_family``. Vor der
    Rollenfamilien-Verschaerfung zaehlte das als zwei Stakeholder-Gruppen.
    """
    return {
        "schema_version": 2,
        "report_id": REPORT_ID,
        "simulation_id": "sim_b7legacy0001",
        "global_evidence": [],
        "sections": [
            {
                "section_index": 1,
                "section_title": "Intro",
                "section_summary": "Initial framing",
                "claims": [
                    {
                        "claim_id": "claim_01",
                        "claim_text": "Die Buergerschaft erwartet Verzoegerungen im Q3.",
                        "confidence_score": 0.88,
                        "confidence_label": "high",
                        "evidence": [
                            _agent_quote("Bürger", "buergerschaft"),
                            _agent_quote("bürger ", "buergerschaft"),
                        ],
                        "audit_trail": [],
                    }
                ],
            }
        ],
    }


class TestLegacyRoleFamilyArtifactDegradesOnLoad:
    def test_double_spelling_legacy_artifact_is_degraded_not_rejected(self, client) -> None:
        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch(
                "app.api.report.ReportManager.get_evidence_map",
                return_value=_legacy_map_with_double_spelling(),
            ),
        ):
            response = client.get(f"/api/report/{REPORT_ID}/evidence")

        assert response.status_code == 200, response.get_data()
        payload = response.get_json()
        assert payload["evidence_omitted"]["reason"] == "contract_violation"
        assert "data" not in payload, (
            "eine degradierte Antwort darf keine ungeprüfte Evidence-Map als "
            "'data' mitschicken"
        )
