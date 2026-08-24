"""Issue #1160 E — operative Zahlen tragen ihre Herkunft mit.

Zahlen wie „>90 % Traffic-Baseline“ oder „14-Tage-Rankinggrenze“ sahen im
Fließtext alle gleich aus, egal ob sie aus dem Auftragsdokument stammten, aus
gemessenen Daten, aus einer Norm, aus einer Betreiberentscheidung oder daraus,
dass ein Sprachmodell sie plausibel fand. Der Leser konnte sie nicht
unterscheiden und behandelte im Zweifel alle gleich verbindlich.

`origin` ist bewusst eine **eigene Dimension neben** `EvidenceSourceKind` und
wird nicht mit ihr vermischt: die Quellengattung beschreibt, woher ein *Beleg*
kommt, `origin`, wie eine *Zahl* zustande kam. Eine Vermischung würde ADR-0002
Anker 3 verwässern — deshalb prüft ein Test das ausdrücklich.

Additiv: `ReportV3` ohne `thresholds` lädt unverändert, ADR-0002 bleibt
unberührt, und der Prompt-Block in `report_prompts/sections.py` (Anker 1) wird
nicht angefasst — die Feldbeschreibungen erreichen das Modell über
`model_json_schema()`.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contracts.report_contract import EvidenceSourceKind
from app.contracts.report_v3 import ReportV3, Threshold
from app.services.report_agent.markdown_renderer import (
    render_report_v3,
    render_threshold_table,
)
from app.services.report_agent.metadata_merge import (
    STRUCTURED_SLOTS,
    merge_section_metadata,
)
from app.services.report_agent.schemas import SectionMetadata

EVIDENCE_ID = "ev_00000000000000000000000000000001"


def _threshold(**overrides) -> Threshold:
    payload = {
        "id": "thr_01",
        "label": "Traffic-Baseline",
        "value": 90.0,
        "unit": "percent",
        "purpose": "baseline",
        "origin": "document_requirement",
    }
    payload.update(overrides)
    return Threshold(**payload)  # type: ignore[arg-type]


class TestOriginIsItsOwnDimension:
    def test_origin_und_quellengattung_teilen_keine_werte(self) -> None:
        """Der Kern der Modellierungsentscheidung, als Drift-Guard.

        Würde jemand später `origin` und `EvidenceSourceKind` zusammenlegen,
        verlöre ADR-0002 Anker 3 seine Trennschärfe: die Gattung eines Belegs
        und die Entstehung einer Zahl sind verschiedene Fragen.
        """
        origins = set(Threshold.model_fields["origin"].annotation.__args__)  # type: ignore[union-attr]
        source_kinds = {kind.value for kind in EvidenceSourceKind}

        assert not origins & source_kinds, (
            f"origin und EvidenceSourceKind teilen Werte: {origins & source_kinds}. "
            "Die beiden Dimensionen duerfen nicht verschmelzen."
        )

    @pytest.mark.parametrize(
        "origin",
        [
            "document_requirement",
            "empirical_data",
            "external_standard",
            "operator_policy",
            "model_proposal",
            "simulation_proposal",
        ],
    )
    def test_alle_sechs_herkunftsarten_sind_gueltig(self, origin: str) -> None:
        assert _threshold(origin=origin).origin == origin

    def test_eine_erfundene_herkunft_wird_abgelehnt(self) -> None:
        with pytest.raises(ValidationError):
            _threshold(origin="bauchgefuehl")


class TestVerifiedNeedsAnAnchor:
    def test_belegt_ohne_beleg_ist_ungueltig(self) -> None:
        """Eine Zahl als belegt auszuweisen, ohne einen Beleg zu nennen, wäre
        schlimmer als sie ehrlich als unbelegt zu führen — der Leser verlässt
        sich dann auf etwas, das es nicht gibt."""
        with pytest.raises(ValidationError, match="verlangt mindestens eine evidence_ref"):
            _threshold(evidence_status="verified")

    def test_belegt_mit_beleg_ist_gueltig(self) -> None:
        threshold = _threshold(evidence_status="verified", evidence_refs=[EVIDENCE_ID])
        assert threshold.evidence_status == "verified"

    @pytest.mark.parametrize("status", ["derived", "heuristic"])
    def test_die_schwaecheren_stufen_brauchen_keinen_beleg(self, status: str) -> None:
        assert _threshold(evidence_status=status).evidence_refs == []

    def test_der_default_ist_die_schwaechste_aussage(self) -> None:
        """Im Zweifel unbelegt — nicht belegt."""
        assert _threshold().evidence_status == "heuristic"


class TestExtractionPath:
    def test_das_section_dto_kennt_den_slot(self) -> None:
        """Ohne das Feld im DTO liefert das Modell nie Schwellenwerte —
        die Extraktion läuft über ``chat_json(schema=SectionMetadata)``."""
        assert "thresholds" in SectionMetadata.model_fields

    def test_die_feldbeschreibungen_erreichen_das_modell(self) -> None:
        """Der Prompt-Block in ``sections.py`` (ADR-0002 Anker 1) bleibt
        unberührt: die Anweisung steckt im JSON-Schema, das
        ``generate_section_metadata`` mitschickt."""
        schema = SectionMetadata.model_json_schema()
        rendered = str(schema)

        assert "model_proposal" in rendered
        assert "keine" in rendered.lower() and "erfinden" in rendered.lower(), (
            "Die Anweisung, keine Zahlen zu erfinden, fehlt im Schema-Text"
        )

    def test_der_merge_kennt_den_slot(self) -> None:
        assert STRUCTURED_SLOTS["thresholds"] is Threshold

    def test_thresholds_aus_mehreren_abschnitten_landen_im_report(self) -> None:
        sections = [
            {
                "structured_metadata": {
                    "thresholds": [
                        _threshold(id="thr_01").model_dump(mode="json"),
                    ]
                }
            },
            {
                "structured_metadata": {
                    "thresholds": [
                        _threshold(id="thr_02", origin="model_proposal").model_dump(
                            mode="json"
                        ),
                        # Dieselbe ID noch einmal — der Merge dedupliziert.
                        _threshold(id="thr_01").model_dump(mode="json"),
                    ]
                }
            },
        ]

        merged = merge_section_metadata(sections)

        assert [t.id for t in merged.thresholds] == ["thr_01", "thr_02"]
        assert "thresholds" in merged.as_report_v3_kwargs()

    def test_ein_halluzinierter_eintrag_sprengt_den_report_nicht(self) -> None:
        """Ein unbrauchbarer Eintrag wird verworfen und protokolliert, statt
        einen sonst gültigen Report zu verhindern."""
        sections = [
            {
                "structured_metadata": {
                    "thresholds": [
                        {"id": "thr_kaputt", "label": "ohne Wert"},
                        _threshold(id="thr_01").model_dump(mode="json"),
                    ]
                }
            }
        ]

        merged = merge_section_metadata(sections)

        assert [t.id for t in merged.thresholds] == ["thr_01"]
        assert merged.rejected


class TestRendering:
    def test_die_herkunft_steht_im_klartext(self) -> None:
        """Als Enum-Wert leistet das Feld nicht, wozu es da ist."""
        table = render_threshold_table([_threshold(origin="model_proposal")])

        assert "Modellvorschlag" in table
        assert "model_proposal" not in table

    def test_der_wert_wird_ohne_ueberfluessige_nachkommastelle_gezeigt(self) -> None:
        assert "90 percent" in render_threshold_table([_threshold()])
        assert "90.0" not in render_threshold_table([_threshold()])
        assert "12.5 percent" in render_threshold_table([_threshold(value=12.5)])

    def test_ein_report_ohne_zahlen_sagt_das_ausdruecklich(self) -> None:
        assert "Keine operativen Zahlen" in render_threshold_table([])

    def test_der_gesamtreport_enthaelt_den_abschnitt(self) -> None:
        report = ReportV3(
            schema_version=4,
            report_id="rep-1160e",
            generated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
            thresholds=[_threshold()],
        )
        markdown = render_report_v3(report)

        assert "## Operative Zahlen" in markdown
        assert "Vorgabe aus Dokument" in markdown


def test_bestandsreports_ohne_den_slot_laden_unveraendert() -> None:
    """Additiv — kein Bestandsartefakt wird ungültig."""
    report = ReportV3(
        schema_version=4,
        report_id="rep-bestand",
        generated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
    )
    assert report.thresholds == []
