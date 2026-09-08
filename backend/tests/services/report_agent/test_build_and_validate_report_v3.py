"""Direkttests für ``workflow._build_and_validate_report_v3``.

Der Vorab-Build von ReportV3 (Issue #1299) lag bis zu diesem Slice inline in
``generate_report`` und war nur über einen vollständigen Report-Lauf mit rund
einem Dutzend Mocks erreichbar. Als eigene Funktion lässt sich sein Vertrag
direkt prüfen: er mutiert ``report`` in place und stuft den Status ab, statt
einen fehlgeschlagenen Build still auf ``COMPLETED`` stehen zu lassen.

``ReportManager`` wird bewusst über den Modul-Namensraum aufgelöst — dieselben
``patch("...workflow.ReportManager")``-Ziele wie im übrigen Testbestand.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import BaseModel, ValidationError

from app.models.report import ReportStatus
from app.services.report_agent import workflow as wf


class _Probe(BaseModel):
    title: str


def _validation_error() -> ValidationError:
    try:
        _Probe.model_validate({})
    except ValidationError as exc:
        return exc
    raise AssertionError("erwarteter ValidationError blieb aus")


def _report(status: ReportStatus = ReportStatus.COMPLETED, error: str | None = None):
    return SimpleNamespace(status=status, error=error, run_degradations=[])


_UNSET = object()


def _agent(evidence_map: object = _UNSET):
    """Ohne Argument eine gefuellte Evidence-Map; ``None`` bleibt ``None``.

    Ein Default, der ``None`` still durch ein truthy dict ersetzt, wuerde den
    Falsy-Zweig der Funktion unpruefbar machen.
    """
    return SimpleNamespace(
        evidence_map={"sections": []} if evidence_map is _UNSET else evidence_map
    )


def test_erfolgreicher_build_laesst_report_unveraendert():
    report = _report()
    agent = _agent()

    with patch.object(wf, "ReportManager") as manager:
        wf._build_and_validate_report_v3(
            report, agent, report_mode="balanced", report_id="report_x"
        )

    assert manager.build_report_v3.called
    assert report.status == ReportStatus.COMPLETED
    assert report.error is None
    assert report.run_degradations == []


@pytest.mark.parametrize(
    "status,evidence_map",
    [
        (ReportStatus.INCOMPLETE, {"sections": []}),
        (ReportStatus.FAILED, {"sections": []}),
        (ReportStatus.COMPLETED, {}),
        (ReportStatus.COMPLETED, None),
    ],
)
def test_kein_build_ohne_completed_und_evidence_map(status, evidence_map):
    """Der Vorab-Build greift nur bei COMPLETED MIT Evidence-Map.

    Beide Bedingungen zusammen sind der Vertrag: save_report() baut das
    Artefakt ebenfalls nur unter COMPLETED, ohne Evidence-Map gibt es nichts
    zu bauen.
    """
    report = _report(status=status)
    agent = _agent(evidence_map)

    with patch.object(wf, "ReportManager") as manager:
        wf._build_and_validate_report_v3(
            report, agent, report_mode=None, report_id="report_x"
        )

    assert not manager.build_report_v3.called
    assert report.status == status


def test_validation_error_stuft_status_ab_und_setzt_fehlertext():
    report = _report()
    agent = _agent()
    exc = _validation_error()

    with patch.object(wf, "ReportManager") as manager:
        manager.build_report_v3.side_effect = exc
        wf._build_and_validate_report_v3(
            report, agent, report_mode=None, report_id="report_x"
        )

    assert report.status != ReportStatus.COMPLETED
    assert report.error is not None
    assert "unvollständige Section" in report.error


def test_bestehender_fehlertext_wird_nicht_ueberschrieben():
    """Der erste Fehler ist der aussagekräftigere — er bleibt stehen."""
    report = _report(error="Ursprünglicher Fehler aus einem früheren Schritt.")
    agent = _agent()

    with patch.object(wf, "ReportManager") as manager:
        manager.build_report_v3.side_effect = _validation_error()
        wf._build_and_validate_report_v3(
            report, agent, report_mode=None, report_id="report_x"
        )

    assert report.error == "Ursprünglicher Fehler aus einem früheren Schritt."


def test_run_degradations_werden_ergaenzt_nicht_ersetzt():
    """Die Bilanz wurde vom Aufrufer bereits gezogen; der Nachtrag kommt dazu.

    Ohne das bliebe run_degradations leer und die API meldete einen
    unvollständigen Contract-Export ohne einen einzigen Grund.
    """
    report = _report()
    report.run_degradations = [{"kind": "vorher_bestehend"}]
    agent = _agent()

    with patch.object(wf, "ReportManager") as manager:
        manager.build_report_v3.side_effect = _validation_error()
        wf._build_and_validate_report_v3(
            report, agent, report_mode=None, report_id="report_x"
        )

    assert report.run_degradations[0] == {"kind": "vorher_bestehend"}
    assert len(report.run_degradations) > 1


def test_nur_validation_error_wird_gefangen():
    """Andere Exceptions gehören dem äußeren Handler in generate_report."""
    report = _report()
    agent = _agent()

    with patch.object(wf, "ReportManager") as manager:
        manager.build_report_v3.side_effect = RuntimeError("etwas anderes")
        with pytest.raises(RuntimeError):
            wf._build_and_validate_report_v3(
                report, agent, report_mode=None, report_id="report_x"
            )
