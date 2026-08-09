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
    def test_legacy_medium_seed_only_map_returns_unresolved_hypothesis(self, client):
        """Unverifizierbare Legacy-Seed-Evidence wird nicht zum Claim erhoben."""
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
        section = body["data"]["sections"][0]
        assert section["claims"] == []
        assert "legacy_unresolved" in section["hypotheses"][0]["rationale"]

    def test_agent_grounded_medium_claim_stays_medium(self, client):
        evidence_map = _legacy_medium_seed_only_map()
        seed_item = evidence_map["sections"][0]["claims"][0]["evidence"][0]
        seed_item["producer_key"] = "fixture-seed:doc_1"
        # Issue #1154: seed_corpus zählt nur mit verifiziertem Dokumentanker.
        # Ohne ihn verliert das Item beim Laden seinen Seed-Status und der
        # Claim fällt auf low — das prüft
        # ``test_medium_claim_with_unanchored_seed_falls_to_low``.
        seed_item["source_id_anchor"] = "seed_doc:doc_1#chunk:0"
        evidence_map["sections"][0]["claims"][0]["evidence"].append(
            {
                "producer_key": "agent:persona_1:quote:1",
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

    def test_medium_claim_with_unanchored_seed_falls_to_low(self, client):
        """ADR-0013 / Issue #1154: Seed-Status braucht einen auflösbaren Anker.

        Vor #1154 war ``seed_corpus`` der Default für alles aus dem Graphen.
        Solche Items behaupten einen Dokumentbeleg, den niemand nachschlagen
        kann — der Claim verliert deshalb beim Laden sein ``medium``. Die
        Antwort bleibt HTTP 200: abgestuft, nicht abgewiesen.
        """
        evidence_map = _legacy_medium_seed_only_map()
        seed_item = evidence_map["sections"][0]["claims"][0]["evidence"][0]
        seed_item["producer_key"] = "fixture-seed:doc_1"
        # Bewusst kein source_id_anchor.
        evidence_map["sections"][0]["claims"][0]["evidence"].append(
            {
                "producer_key": "agent:persona_1:quote:1",
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
        assert claim["confidence_label"] == "low"


def _orphan_claim_map(confidence_label: str = "medium"):
    """Schema-v2-Map mit einem Claim ganz OHNE Evidence (Issue #968).

    Solche Bestandsdaten scheitern an ``ReportClaimModel``s Validator
    ``non_low_claims_need_evidence``, sobald das Label nicht ``low`` ist.
    ``migrate_legacy_claims_to_anchored`` fängt sie ohne Datenverlust ab,
    indem es sie nach ``data_gaps`` umhängt.
    """
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
                        "claim_id": "claim_90",
                        "claim_text": "Behauptung ganz ohne Beleg.",
                        "confidence_label": confidence_label,
                        "confidence_score": 0.6,
                        "evidence": [],
                        "audit_trail": [],
                        "notes": None,
                    }
                ],
                "hypotheses": [],
                "data_gaps": [],
            }
        ],
    }


class TestReportEvidenceRouteOrphanClaims:
    """Issue #968 — ``migrate_legacy_claims_to_anchored`` im Live-Lese-Pfad.

    Die Migration lief bisher nur in Evaluationstests und im Bulk-Skript,
    nicht in ``GET /<report_id>/evidence``.
    """

    def test_orphan_medium_claim_becomes_data_gap(self, client):
        """RED ohne den Fix: der Claim ohne Evidence lässt
        ``non_low_claims_need_evidence`` scheitern, statt als ``data_gaps``-
        Eintrag mit ``gap_reason="no_evidence_bound"`` zurückzukommen."""
        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch(
                "app.api.report.ReportManager.get_evidence_map",
                return_value=_orphan_claim_map("medium"),
            ),
        ):
            resp = client.get(f"/api/report/{VALID_REPORT_ID}/evidence")

        assert resp.status_code == 200, resp.get_data(as_text=True)
        section = resp.get_json()["data"]["sections"][0]

        assert section["claims"] == [], (
            "Der orphan Claim muss aus claims[] entfernt sein, "
            f"vorgefunden: {section['claims']}"
        )
        assert len(section["data_gaps"]) == 1
        gap = section["data_gaps"][0]
        assert gap["gap_reason"] == "no_evidence_bound"
        assert gap["claim_text"] == "Behauptung ganz ohne Beleg."

    @pytest.mark.parametrize("label", ["high", "verified"])
    def test_orphan_high_and_verified_claims_become_data_gaps(self, client, label):
        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch(
                "app.api.report.ReportManager.get_evidence_map",
                return_value=_orphan_claim_map(label),
            ),
        ):
            resp = client.get(f"/api/report/{VALID_REPORT_ID}/evidence")

        assert resp.status_code == 200, resp.get_data(as_text=True)
        section = resp.get_json()["data"]["sections"][0]
        assert section["claims"] == []
        assert section["data_gaps"][0]["gap_reason"] == "no_evidence_bound"

    def test_orphan_low_claim_stays_a_claim(self, client):
        """Gegenprobe: ``low`` ohne Evidence ist zulässig und darf NICHT
        umgehängt werden — sonst verlöre der Report gültige Aussagen."""
        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch(
                "app.api.report.ReportManager.get_evidence_map",
                return_value=_orphan_claim_map("low"),
            ),
        ):
            resp = client.get(f"/api/report/{VALID_REPORT_ID}/evidence")

        assert resp.status_code == 200, resp.get_data(as_text=True)
        section = resp.get_json()["data"]["sections"][0]
        assert len(section["claims"]) == 1
        assert section["claims"][0]["claim_id"] == "claim_90"
        assert section["data_gaps"] == []

    def test_pipeline_is_idempotent(self, client):
        """Zweimal dieselbe Map durch die Route liefert dasselbe Ergebnis.

        Deckt alle drei Migrationen gemeinsam ab (AK: Idempotenz bleibt für
        die ganze Pipeline erhalten), nicht nur die neu eingehängte.
        """
        evidence_map = _orphan_claim_map("medium")
        # Zusätzlich ein medium-seed-only-Claim, damit die #963-Migration in
        # derselben Pipeline mitläuft und die Reihenfolge wirklich geprüft ist.
        evidence_map["sections"][0]["claims"].append(
            {
                "claim_id": "claim_91",
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
        )

        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch(
                "app.api.report.ReportManager.get_evidence_map",
                return_value=evidence_map,
            ),
        ):
            first = client.get(f"/api/report/{VALID_REPORT_ID}/evidence").get_json()
            second = client.get(f"/api/report/{VALID_REPORT_ID}/evidence").get_json()

        assert first == second, "Pipeline ist nicht idempotent"

        section = first["data"]["sections"][0]
        # orphan -> data_gaps, unverifizierbare Seed-Evidence -> Hypothese
        assert len(section["data_gaps"]) == 1
        assert section["data_gaps"][0]["gap_reason"] == "no_evidence_bound"
        assert section["claims"] == []
        assert any(
            "legacy_unresolved" in item["rationale"]
            for item in section["hypotheses"]
        )


class TestReportEvidenceRouteV1Migration:
    """Issue #1037 — echte v1-Maps müssen den Lese-Pfad überleben.

    Die alte ``migrate_v1_to_v2`` schrieb ``section["schema_version"]`` in
    jede Section; ``ReportSectionModel`` (``extra="forbid"``) lehnte das
    Ergebnis ab — HTTP 400 statt gerettetem Report.
    """

    @staticmethod
    def _v1_map():
        """Echte v1-Map: kein Top-Level-``schema_version``, eine Section."""
        return {
            "report_id": VALID_REPORT_ID,
            "simulation_id": "sim_0123456789ab",
            "global_evidence": [],
            "sections": [
                {
                    "section_index": 1,
                    "section_title": "Kontext",
                    "section_summary": "Zusammenfassung",
                    "claims": [],
                    "data_gaps": [],
                }
            ],
        }

    def test_v1_map_with_section_passes_endpoint(self, client):
        """RED ohne den Fix: sections.0.schema_version → Extra inputs are not
        permitted → HTTP 400."""
        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch(
                "app.api.report.ReportManager.get_evidence_map",
                return_value=self._v1_map(),
            ),
        ):
            resp = client.get(f"/api/report/{VALID_REPORT_ID}/evidence")

        assert resp.status_code == 200, resp.get_data(as_text=True)
        data = resp.get_json()["data"]
        assert data["schema_version"] == 3
        assert "schema_version" not in data["sections"][0]

    def test_poisoned_v2_map_is_healed(self, client):
        """Bestände, die die alte Migration bereits vergiftet hat (Top-Level
        v2 plus Section-Feld), werden beim Lesen geheilt."""
        poisoned = self._v1_map()
        poisoned["schema_version"] = 2
        poisoned["sections"][0]["schema_version"] = 2
        with (
            patch("app.api.report.validate_report_id", return_value=True),
            patch(
                "app.api.report.ReportManager.get_evidence_map",
                return_value=poisoned,
            ),
        ):
            resp = client.get(f"/api/report/{VALID_REPORT_ID}/evidence")

        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert "schema_version" not in resp.get_json()["data"]["sections"][0]
