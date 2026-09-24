"""Issue #1359 — eine gewollte Abweichung verweist auf den anderen Wert.

Zwei Werte für dieselbe Größe sind ein Widerspruch, solange nichts sie
verbindet. ``deviates_from`` stellt die Verbindung her, ``deviation_rationale``
begründet sie. Beides ist additiv: Bestandsartefakte ohne die Felder laden
unverändert.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contracts.report_v3 import ReportV3, Threshold


def _threshold(**overrides) -> Threshold:
    payload = {
        "id": "T1_01",
        "label": "Pilotdauer",
        "value": 4.0,
        "unit": "weeks",
        "purpose": "target",
        "origin": "model_proposal",
    }
    payload.update(overrides)
    return Threshold(**payload)  # type: ignore[arg-type]


def _report(*thresholds: Threshold) -> ReportV3:
    return ReportV3(
        report_id="report_1359",
        generated_at=datetime(2026, 9, 24, tzinfo=timezone.utc),
        thresholds=list(thresholds),
    )


def test_bestandsartefakte_ohne_verweis_laden_unveraendert() -> None:
    threshold = _threshold()

    assert threshold.deviates_from is None
    assert threshold.deviation_rationale is None


def test_ein_verweis_ohne_begruendung_ist_kein_verweis() -> None:
    with pytest.raises(ValidationError, match="deviation_rationale"):
        _threshold(id="T7_01", value=8.0, deviates_from="T1_01")
    with pytest.raises(ValidationError, match="deviation_rationale"):
        _threshold(
            id="T7_01", value=8.0, deviates_from="T1_01", deviation_rationale="  "
        )


def test_ein_wert_weicht_nicht_von_sich_selbst_ab() -> None:
    with pytest.raises(ValidationError, match="selbst"):
        _threshold(deviates_from="T1_01", deviation_rationale="Begründung.")


def test_ein_leerer_verweis_ist_ungueltig() -> None:
    with pytest.raises(ValidationError, match="leer"):
        _threshold(deviates_from=" ", deviation_rationale="Begründung.")


def test_der_bericht_akzeptiert_einen_begruendeten_verweis() -> None:
    report = _report(
        _threshold(),
        _threshold(
            id="T7_01",
            value=8.0,
            purpose="target",
            deviates_from="T1_01",
            deviation_rationale="Nach dem Ausfall im Testbetrieb verlängert.",
        ),
    )

    assert report.thresholds[1].deviates_from == "T1_01"


def test_ein_verweis_ins_leere_sprengt_den_bericht() -> None:
    with pytest.raises(ValidationError, match="unbekannte Schwellenwerte"):
        _report(
            _threshold(
                id="T7_01",
                value=8.0,
                deviates_from="T1_99",
                deviation_rationale="Begründung.",
            )
        )


def test_das_schema_beschreibt_beide_felder_fuer_das_modell() -> None:
    """Die Beschreibungen erreichen das Modell über ``model_json_schema()``."""
    properties = Threshold.model_json_schema()["properties"]

    assert "Kennung" in properties["deviates_from"]["description"]
    assert "Pflicht" in properties["deviation_rationale"]["description"]
