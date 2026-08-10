"""Issue #1160 G — dieselbe kaputte Evidence-Map, dasselbe Verhalten in allen Pfaden.

Der Audit-Befund lautete ursprünglich „Evidence-Map fällt stumm bei
``contract_violation``". Die Verifikation ergab etwas anderes: der stille
Verlust ist seit #987 behoben, stattdessen verhielten sich **drei Pfade bei
derselben vertragswidrigen Map unterschiedlich**:

===========================  ================================================
Pfad                         Verhalten vor diesem Slice
===========================  ================================================
JSON-Export                  fing ``ValidationError``, setzte
                             ``evidence_omitted`` — korrekt
``GET .../evidence``         ``model_validate`` ohne ``try`` — 500 statt
                             nutzbarer Antwort
ZIP und CSV                  migrierten, validierten **nie** — vertragswidrige
                             Evidenz landete ungeprüft in der Datei
===========================  ================================================

Der dritte Fall ist der gravierendste und stand so nicht im Audit: wer den
Report als ZIP oder CSV zieht, bekommt eine Datei, die aussieht wie geprüfte
Evidenz, ohne dass die Prüfung je stattgefunden hätte. Das ist kein stiller
Verlust, sondern eine stille Behauptung.

Die Tests fahren die echten HTTP-Endpunkte. Ein Unit-Test der Validierung wäre
grün gewesen, während die Export-Pfade sie gar nicht aufriefen — genau die
Lücke, um die es geht.
"""

from __future__ import annotations

import io
import json
import zipfile

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

REPORT_ID = "report_1160aabbccdd"
SIMULATION_ID = "sim_1160aabbccdd"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path / "reports"))
    app = Flask(__name__)
    app.register_blueprint(report_bp, url_prefix="/api/report")
    return app.test_client()


def _persist(evidence_map: dict) -> None:
    ReportManager._ensure_report_folder(REPORT_ID)
    ReportManager.save_evidence_map(REPORT_ID, evidence_map)
    ReportManager.save_report(
        Report(
            report_id=REPORT_ID,
            simulation_id=SIMULATION_ID,
            graph_id="graph_1160aabbccdd",
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
            created_at="2026-08-10T10:00:00",
            completed_at="2026-08-10T10:05:00",
        )
    )


def _agent_quote(group: str) -> dict:
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
    }


def _violating_map() -> dict:
    """Eine Map, die **auch nach** der Migration vertragswidrig bleibt.

    Ein ``high``-Claim mit Stimmen aus nur einer Stakeholder-Gruppe verletzt
    ADR-0002 Anker 4. Kein Migrationsschritt fängt das auf — anders als bei
    evidenzlosen oder seed-only-Claims gibt es hier nichts umzuhängen. Genau
    deshalb taugt der Fall als Prüfstein: er kommt garantiert bis zum
    Validator durch.
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
                        "claim_text": "Die Belegschaft erwartet Verzoegerungen im Q3.",
                        "confidence_score": 0.88,
                        "confidence_label": "high",
                        "evidence": [_agent_quote("Belegschaft")],
                        "audit_trail": [],
                    }
                ],
            }
        ],
    }


def _valid_map() -> dict:
    """Dieselbe Map mit einer zweiten Stakeholder-Gruppe — vertragskonform."""
    evidence_map = _violating_map()
    evidence_map["sections"][0]["claims"][0]["evidence"].append(
        _agent_quote("Geschaeftsfuehrung")
    )
    return evidence_map


def _zip_names(client, *, stream: bool) -> list[str]:
    """Dateiliste des ZIP-Bundles über den echten Endpunkt.

    Beide ZIP-Pfade schreiben dasselbe Archiv — deshalb wäre ein Test, der
    versehentlich zweimal den In-Memory-Pfad fährt, trotzdem grün und der
    Streaming-Pfad bliebe ungeprüft. Genau diese Fehlerklasse (#961/#966/#985:
    Test am falschen Codepfad) schließt der Aufruf-Zähler unten aus.
    """
    import app.api.report as report_api

    calls = {"stream": 0, "memory": 0}
    original_stream = report_api._stream_zip_bundle
    original_build = report_api._build_zip_bundle
    original_threshold = report_api._ZIP_STREAM_THRESHOLD_BYTES

    def counting_stream(*args, **kwargs):
        calls["stream"] += 1
        return original_stream(*args, **kwargs)

    def counting_build(*args, **kwargs):
        calls["memory"] += 1
        return original_build(*args, **kwargs)

    report_api._stream_zip_bundle = counting_stream
    report_api._build_zip_bundle = counting_build
    # Der Streaming-Pfad greift erst oberhalb der Größenschwelle. Sie auf 0 zu
    # ziehen ist die einzige Möglichkeit, ihn mit einer Test-Fixture zu
    # erreichen.
    if stream:
        report_api._ZIP_STREAM_THRESHOLD_BYTES = 0
    try:
        response = client.get(f"/api/report/{REPORT_ID}/export?format=zip")
        body = response.get_data()
    finally:
        report_api._stream_zip_bundle = original_stream
        report_api._build_zip_bundle = original_build
        report_api._ZIP_STREAM_THRESHOLD_BYTES = original_threshold

    expected = "stream" if stream else "memory"
    assert calls[expected] == 1, (
        f"Erwartet war der {expected}-Pfad, tatsaechlich aufgerufen: {calls}. "
        "Der Test haette den falschen Codepfad geprueft."
    )

    assert response.status_code == 200, body
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        return [name.split("/", 1)[-1] for name in zf.namelist()]


class TestZipWithholdsUnvalidatedEvidence:
    @pytest.mark.parametrize("stream", [False, True], ids=["in-memory", "streaming"])
    def test_violating_map_yields_the_omission_note_instead_of_evidence(
        self, client, stream: bool
    ) -> None:
        """Weder ``evidence-map.json`` noch ``claims.csv`` — beide stammen aus
        derselben Quelle. Eine der beiden auszuliefern würde die stille
        Behauptung erhalten, um die es hier geht."""
        _persist(_violating_map())

        names = _zip_names(client, stream=stream)

        assert "evidence-omitted.json" in names
        assert "evidence-map.json" not in names
        assert "claims.csv" not in names
        # Der Report-Rumpf bleibt vollständig — der Export ist nicht kaputt,
        # er ist ehrlich.
        assert "personas.csv" in names
        assert "segments.csv" in names

    @pytest.mark.parametrize("stream", [False, True], ids=["in-memory", "streaming"])
    def test_valid_map_is_exported_unchanged(self, client, stream: bool) -> None:
        """Gegenprobe: die Prüfung darf den Normalfall nicht beschneiden."""
        _persist(_valid_map())

        names = _zip_names(client, stream=stream)

        assert "evidence-map.json" in names
        assert "claims.csv" in names
        assert "evidence-omitted.json" not in names

    def test_the_omission_note_carries_the_validation_errors(self, client) -> None:
        """Wer das Archiv ohne Agora öffnet, soll die Begründung darin finden."""
        _persist(_violating_map())

        response = client.get(f"/api/report/{REPORT_ID}/export?format=zip")
        with zipfile.ZipFile(io.BytesIO(response.get_data())) as zf:
            entry = next(n for n in zf.namelist() if n.endswith("evidence-omitted.json"))
            note = json.loads(zf.read(entry))

        assert note["reason"] == "contract_violation"
        assert note["detail"]
        assert note["validation_errors"], "ohne Fehlerliste ist der Hinweis wertlos"


class TestCsvRefusesInsteadOfAsserting:
    def test_claims_csv_is_refused_with_the_same_reason(self, client) -> None:
        """Ein CSV kann keinen Auslassungshinweis tragen — also keine Datei."""
        _persist(_violating_map())

        response = client.get(f"/api/report/{REPORT_ID}/export?format=csv&table=claims")

        assert response.status_code == 422, response.get_data()
        payload = json.loads(response.data)
        assert payload["evidence_omitted"]["reason"] == "contract_violation"

    def test_claims_csv_still_works_for_a_valid_map(self, client) -> None:
        _persist(_valid_map())

        response = client.get(f"/api/report/{REPORT_ID}/export?format=csv&table=claims")

        assert response.status_code == 200, response.get_data()

    @pytest.mark.parametrize("table", ["personas", "segments"])
    def test_other_tables_are_unaffected(self, client, table: str) -> None:
        """Personas und Segmente stammen aus ``report-v3.json``, nicht aus der
        Evidence-Map — eine kaputte Map darf sie nicht mitreissen."""
        _persist(_violating_map())

        response = client.get(f"/api/report/{REPORT_ID}/export?format=csv&table={table}")

        assert response.status_code == 200, response.get_data()


class TestReadRouteAnswersInsteadOfCrashing:
    def test_violating_map_yields_422_not_500(self, client) -> None:
        """Vorher lief hier ``model_validate`` ohne ``try``: ein 500er, an dem
        der Aufrufer nicht erkennen konnte, ob Agora kaputt ist oder die
        Daten."""
        _persist(_violating_map())

        response = client.get(f"/api/report/{REPORT_ID}/evidence")

        assert response.status_code == 422, response.get_data()
        payload = json.loads(response.data)
        assert payload["evidence_omitted"]["reason"] == "contract_violation"


class TestAllThreePathsAgree:
    def test_same_reason_in_json_zip_csv_and_read_route(self, client) -> None:
        """Der Kern von #1160 G: ein Konsument sieht überall denselben Grund.

        Vorher hing die Antwort auf dieselbe kaputte Map davon ab, welches
        Format er zufällig gewählt hat.
        """
        _persist(_violating_map())

        json_payload = json.loads(
            client.get(f"/api/report/{REPORT_ID}/export?format=json").data
        )
        csv_payload = json.loads(
            client.get(f"/api/report/{REPORT_ID}/export?format=csv&table=claims").data
        )
        read_payload = json.loads(client.get(f"/api/report/{REPORT_ID}/evidence").data)

        with zipfile.ZipFile(
            io.BytesIO(client.get(f"/api/report/{REPORT_ID}/export?format=zip").get_data())
        ) as zf:
            entry = next(n for n in zf.namelist() if n.endswith("evidence-omitted.json"))
            zip_note = json.loads(zf.read(entry))

        reasons = {
            "json": json_payload["evidence_omitted"]["reason"],
            "zip": zip_note["reason"],
            "csv": csv_payload["evidence_omitted"]["reason"],
            "read": read_payload["evidence_omitted"]["reason"],
        }
        assert set(reasons.values()) == {"contract_violation"}, reasons

        # Und der JSON-Export liefert weiterhin keine ungeprüfte Evidenz mit.
        assert json_payload["evidence"] is None
