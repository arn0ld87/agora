"""Der JSON-Export normalisiert Evidence wie der Lese-Pfad — Issue #987.

Zwei produktive Pfade lasen dieselbe persistierte ``evidence-map.json``, aber
nur einer hat sie vollstaendig migriert:

- ``GET /api/report/<id>/evidence`` (``api/report.py``) faehrt die bindende
  Kette ``migrate_v1_to_v2 -> migrate_legacy_claims_to_anchored ->
  migrate_medium_seed_only_claims_to_low`` und validiert danach.
- ``GET /api/report/<id>/export?format=json``
  (``services/report_export.py::build_export_envelope``) rief nur
  ``migrate_v1_to_v2`` und fing die anschliessende ``ValidationError`` mit
  einer ``logger.warning`` ab. Ergebnis: HTTP 200, ein herunterladbares
  JSON — und ``evidence: null``. Die komplette Evidence-Map fiel aus dem
  Envelope, ohne dass die Antwort das erkennen liess.

Die Tests hier fahren den echten HTTP-Endpunkt, nicht die Migrationsfunktion.
Ein Unit-Test der Migration war die ganze Zeit gruen, waehrend der Export sie
nicht aufrief — genau die Luecke, die dieser Slice schliesst.
"""

from __future__ import annotations

import json

import pytest
from flask import Flask

from app.api import report_bp
from app.services.report_agent import (
    Report,
    ReportManager,
    ReportOutline,
    ReportSection,
    ReportStatus,
)
from app.services.report_prompts import DEFAULT_REPORT_SECTIONS

REPORT_ID = "report_987abcdef012"
SIMULATION_ID = "sim_987abcdef012"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path / "reports"))
    app = Flask(__name__)
    app.register_blueprint(report_bp, url_prefix="/api/report")
    return app.test_client()


def _persist(evidence_map: dict) -> None:
    """Legt einen abgeschlossenen Report mit genau dieser Evidence-Map ab."""
    ReportManager._ensure_report_folder(REPORT_ID)
    ReportManager.save_evidence_map(REPORT_ID, evidence_map)
    ReportManager.save_report(
        Report(
            report_id=REPORT_ID,
            simulation_id=SIMULATION_ID,
            graph_id="graph_987abcdef012",
            simulation_requirement="Test requirement",
            status=ReportStatus.COMPLETED,
            outline=ReportOutline(
                title="Demo",
                summary="Summary",
                sections=[
                    ReportSection(title=title, content=description)
                    for title, description in DEFAULT_REPORT_SECTIONS
                ],
            ),
            markdown_content="# Demo\n\nBody",
            created_at="2026-08-03T10:00:00",
            completed_at="2026-08-03T10:05:00",
        )
    )


def _orphan_claim_map() -> dict:
    """Bestandsmap mit einem medium-Claim ganz ohne Evidence.

    Genau die Gestalt, die ``migrate_legacy_claims_to_anchored`` nach
    ``data_gaps`` umhaengt. Ohne diesen Schritt scheitert
    ``ReportClaimModel.non_low_claims_need_evidence`` — im Lese-Pfad sichtbar
    als Fehler, im Export-Pfad unsichtbar als ``evidence: null``.
    """
    return {
        "schema_version": 2,
        "report_id": REPORT_ID,
        "simulation_id": SIMULATION_ID,
        "global_evidence": [],
        "sections": [
            {
                "section_index": 1,
                "section_title": "Intro",
                "section_summary": "Initial framing",
                "claims": [
                    {
                        "claim_id": "claim_01",
                        "claim_text": "Belegschaft erwartet Verzoegerungen im Q3.",
                        "confidence_score": 0.6,
                        "confidence_label": "medium",
                        "evidence": [],
                        "audit_trail": [],
                    }
                ],
            }
        ],
    }


def _export_json(client) -> dict:
    response = client.get(f"/api/report/{REPORT_ID}/export?format=json")
    assert response.status_code == 200, response.data
    return json.loads(response.data)


class TestExportRunsFullMigrationPipeline:
    """Teilpunkt 1 — der Export faehrt dieselbe Migrationskette wie der Lese-Pfad."""

    def test_orphan_medium_claim_survives_export_as_data_gap(self, client):
        """Der Export verliert die Evidence-Map nicht, er migriert sie.

        Vor dem Fix: ``migrate_v1_to_v2`` allein laesst den evidenzlosen
        medium-Claim stehen, ``EvidenceMapModel.model_validate`` wirft, der
        ``except ValidationError``-Zweig setzt ``evidence=None``. Der Test
        scheiterte an ``payload["evidence"] is None``.
        """
        _persist(_orphan_claim_map())

        payload = _export_json(client)

        assert payload["evidence"] is not None, (
            "Evidence-Map ist aus dem Export-Envelope gefallen — "
            "der Export migriert nicht wie der Lese-Pfad"
        )
        section = payload["evidence"]["sections"][0]
        assert section["claims"] == [], "orphan Claim haette nach data_gaps gehoert"
        assert len(section["data_gaps"]) == 1
        gap = section["data_gaps"][0]
        assert gap["gap_reason"] == "no_evidence_bound"
        assert "Verzoegerungen" in gap["claim_text"]

    def test_medium_seed_only_claim_is_downgraded_in_export(self, client):
        """Auch der dritte Migrationsschritt (#963) wirkt im Export.

        Ein medium-Claim, der sich nur auf ``seed_corpus`` stuetzt, muss auf
        ``low`` abgestuft werden — sonst bricht
        ``ReportClaimModel.agent_grounded_for_medium``.
        """
        evidence_map = _orphan_claim_map()
        evidence_map["sections"][0]["claims"][0]["evidence"] = [
            {
                "type": "graph_fact",
                "source_kind": "seed_corpus",
                "source": "briefing.md",
                "snippet": "Das Vorhaben startet im Q3.",
                "match_score": 0.75,
                "supports_claim": True,
            }
        ]
        _persist(evidence_map)

        payload = _export_json(client)

        assert payload["evidence"] is not None
        claim = payload["evidence"]["sections"][0]["claims"][0]
        assert claim["confidence_label"] == "low", (
            "seed-only medium-Claim wurde im Export nicht abgestuft"
        )


class TestExportAndReadPathAgree:
    """Sentinel gegen den Rueckfall in zwei Migrationsreihenfolgen.

    Wird eine der beiden Stellen spaeter einseitig geaendert, geht dieser Test
    rot — unabhaengig davon, ob die Aenderung fuer sich genommen plausibel
    aussieht. Das ist der Zweck: es gibt genau eine kanonische Normalisierung.
    """

    @pytest.mark.parametrize(
        "mutate",
        [
            pytest.param(lambda m: m, id="orphan-medium-claim"),
            pytest.param(
                lambda m: _with_seed_only_evidence(m), id="seed-only-medium-claim"
            ),
        ],
    )
    def test_export_envelope_matches_read_route(self, client, mutate):
        _persist(mutate(_orphan_claim_map()))

        read_response = client.get(f"/api/report/{REPORT_ID}/evidence")
        assert read_response.status_code == 200, read_response.data
        from_read = json.loads(read_response.data)["data"]

        from_export = _export_json(client)["evidence"]

        assert from_export == from_read, (
            "Lese-Pfad und Export liefern verschiedene Evidence-Maps — "
            "die Normalisierung ist wieder doppelt implementiert"
        )


def _with_seed_only_evidence(evidence_map: dict) -> dict:
    evidence_map["sections"][0]["claims"][0]["evidence"] = [
        {
            "type": "graph_fact",
            "source_kind": "seed_corpus",
            "source": "briefing.md",
            "snippet": "Das Vorhaben startet im Q3.",
            "match_score": 0.75,
            "supports_claim": True,
        }
    ]
    return evidence_map


class TestResidualContractViolationIsVisible:
    """Teilpunkt 2 — bleibt nach allen Migrationen ein Vertragsbruch, sagt der Envelope das.

    Fault Injection: eine Map, die keine Migration reparieren kann (unbekanntes
    Feld, ``model_config = extra='forbid'``). Der Fallback — Envelope ohne
    Evidence — bleibt bestehen; er darf nur nicht laenger stumm sein.
    """

    def _unrepairable_map(self) -> dict:
        evidence_map = _orphan_claim_map()
        evidence_map["sections"][0]["claims"] = []
        evidence_map["voellig_unbekanntes_feld"] = "kein Migrationsschritt kennt das"
        return evidence_map

    def test_dropped_evidence_map_is_reported_in_envelope(self, client):
        _persist(self._unrepairable_map())

        payload = _export_json(client)

        assert payload["evidence"] is None
        omission = payload["evidence_omitted"]
        assert omission is not None, (
            "Evidence-Map still verworfen — der Export meldet Erfolg, "
            "ohne den Verlust auszuweisen"
        )
        assert omission["reason"] == "contract_violation"
        assert omission["detail"].strip()
        assert omission["validation_errors"], "Ursache ist nicht belegt"

    def test_healthy_export_carries_no_omission(self, client):
        """Der Normalfall bleibt rauschfrei — kein Hinweis ohne Anlass."""
        _persist(_orphan_claim_map())

        payload = _export_json(client)

        assert payload["evidence"] is not None
        assert payload["evidence_omitted"] is None

    def test_empty_persisted_map_is_reported_not_treated_as_missing(self, client):
        """Eine vorhandene, aber leere evidence-map.json ist kein fehlendes Artefakt.

        Mit einer Truthiness-Pruefung (``if raw_evidence_map``) war ``{}``
        von „kein Artefakt" nicht zu unterscheiden: Migration und Validierung
        wurden uebersprungen, der Envelope trug ``evidence: null`` **und**
        ``evidence_omitted: null``. Genau der stille Verlust, den dieser Slice
        behebt — eine Ebene tiefer.
        """
        _persist({})

        payload = _export_json(client)

        assert payload["evidence"] is None
        assert payload["evidence_omitted"] is not None, (
            "leere Evidence-Map wurde wie ein fehlendes Artefakt behandelt"
        )
        assert payload["evidence_omitted"]["reason"] == "contract_violation"

    def test_report_without_any_evidence_map_carries_no_omission(self, client):
        """Kein Evidence-Artefakt ist kein Verlust — nur ein Report ohne Evidence."""
        ReportManager.save_report(
            Report(
                report_id=REPORT_ID,
                simulation_id=SIMULATION_ID,
                graph_id="graph_987abcdef012",
                simulation_requirement="Test requirement",
                status=ReportStatus.COMPLETED,
                outline=ReportOutline(
                    title="Demo",
                    summary="Summary",
                    sections=[
                        ReportSection(title=title, content=description)
                        for title, description in DEFAULT_REPORT_SECTIONS
                    ],
                ),
                markdown_content="# Demo",
                created_at="2026-08-03T10:00:00",
                completed_at="2026-08-03T10:05:00",
            )
        )

        payload = _export_json(client)

        assert payload["evidence"] is None
        assert payload["evidence_omitted"] is None
