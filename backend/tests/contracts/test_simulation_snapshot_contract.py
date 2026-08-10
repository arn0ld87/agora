"""Der Report weist aus, auf welchem Simulationsstand er beruht (Issue #1192).

Eine Reportgenerierung darf starten, während die zugrunde liegende Simulation
noch läuft — das bleibt erlaubt. Fachlich fragwürdig war die Stille darüber:
der Report analysierte dann einen Zwischenstand, dessen Rundenzahl im Ergebnis
nirgends stand. Einem fertigen Bericht war nicht anzusehen, ob er auf zehn
abgeschlossenen Runden beruht oder auf vieren.

Die Rückwärtskompatibilität ist Abnahmekriterium: Reports, die vor dieser
Änderung geschrieben wurden, kennen das Feld nicht und müssen unverändert
laden, validieren und exportieren.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contracts.report_contract import ReportModel, SimulationSnapshotModel
from app.contracts.report_v3 import ReportV3
from app.models.report import Report, ReportStatus
from app.services.report_agent.markdown_renderer import render_simulation_snapshot
from app.services.report_agent.simulation_snapshot import capture_simulation_snapshot


def _report_payload(**overrides) -> dict:
    payload = {
        "report_id": "report_test",
        "simulation_id": "sim_test",
        "graph_id": "graph_test",
        "simulation_requirement": "Akzeptanzanalyse",
        "status": "completed",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# 1. Der Vertrag traegt den Stand
# ---------------------------------------------------------------------------


def test_report_traegt_den_simulationsstand():
    model = ReportModel.model_validate(
        _report_payload(
            simulation_snapshot={
                "rounds_completed": 4,
                "total_rounds": 10,
                "simulation_running": True,
                "captured_at": "2026-08-10T20:20:00",
            }
        )
    )

    assert model.simulation_snapshot is not None
    assert model.simulation_snapshot.rounds_completed == 4
    assert model.simulation_snapshot.total_rounds == 10
    assert model.simulation_snapshot.simulation_running is True


def test_negative_rundenzahl_wird_abgelehnt():
    with pytest.raises(ValidationError):
        SimulationSnapshotModel.model_validate({"rounds_completed": -1})


# ---------------------------------------------------------------------------
# 2. Rueckwaertskompatibilitaet — Abnahmekriterium
# ---------------------------------------------------------------------------


def test_bestandsreport_ohne_snapshot_laedt_unveraendert():
    """Ein vor der Änderung geschriebener Report kennt das Feld nicht."""
    model = ReportModel.model_validate(_report_payload())

    assert model.simulation_snapshot is None
    # Der Report bleibt vollstaendig exportierbar.
    assert model.model_dump(mode="json")["simulation_snapshot"] is None


def test_report_v3_ohne_snapshot_laedt_unveraendert():
    report = ReportV3(report_id="report_test", generated_at=datetime.now(timezone.utc))

    assert report.simulation_snapshot is None


# ---------------------------------------------------------------------------
# 3. Der Stand steht im Report — nicht nur in den Metadaten
# ---------------------------------------------------------------------------


def test_zwischenstand_wird_als_solcher_ausgewiesen():
    report = ReportV3(
        report_id="report_test",
        generated_at=datetime.now(timezone.utc),
        simulation_snapshot=SimulationSnapshotModel(
            rounds_completed=4, total_rounds=10, simulation_running=True
        ),
    )

    gerendert = render_simulation_snapshot(report)

    assert "Zwischenstand" in gerendert
    assert "4" in gerendert and "10" in gerendert
    assert "noch weiter" in gerendert


def test_abgeschlossene_simulation_wird_nicht_als_zwischenstand_ausgewiesen():
    report = ReportV3(
        report_id="report_test",
        generated_at=datetime.now(timezone.utc),
        simulation_snapshot=SimulationSnapshotModel(
            rounds_completed=10, total_rounds=10, simulation_running=False
        ),
    )

    gerendert = render_simulation_snapshot(report)

    assert "Zwischenstand" not in gerendert
    assert "10" in gerendert


def test_fehlender_stand_wird_als_unbekannt_ausgewiesen():
    """Erfinden ist keine Option — 'unbekannt' ist die ehrliche Aussage."""
    report = ReportV3(report_id="report_test", generated_at=datetime.now(timezone.utc))

    assert "unbekannt" in render_simulation_snapshot(report)


# ---------------------------------------------------------------------------
# 4. Erfassung
# ---------------------------------------------------------------------------


class _FakeRunnerStatus:
    def __init__(self, value: str) -> None:
        self.value = value


class _FakeRunState:
    def __init__(self, *, current_round: int, total_rounds: int, status: str) -> None:
        self.current_round = current_round
        self.total_rounds = total_rounds
        self.runner_status = _FakeRunnerStatus(status)


def test_erfassung_liest_laufenden_zwischenstand(monkeypatch):
    from app.services import simulation_runner as runner_module

    monkeypatch.setattr(
        runner_module.SimulationRunner,
        "get_run_state",
        classmethod(
            lambda cls, sid: _FakeRunState(
                current_round=4, total_rounds=10, status="running"
            )
        ),
    )

    snapshot = capture_simulation_snapshot("sim_test")

    assert snapshot is not None
    assert snapshot["rounds_completed"] == 4
    assert snapshot["total_rounds"] == 10
    assert snapshot["simulation_running"] is True
    # Muss gegen den Vertrag validieren.
    SimulationSnapshotModel.model_validate(snapshot)


def test_erfassung_ohne_laufzustand_liefert_none(monkeypatch):
    from app.services import simulation_runner as runner_module

    monkeypatch.setattr(
        runner_module.SimulationRunner,
        "get_run_state",
        classmethod(lambda cls, sid: None),
    )

    assert capture_simulation_snapshot("sim_test") is None


def test_erfassungsfehler_kostet_keinen_report(monkeypatch):
    """Ein unbekannter Stand darf die Reportgenerierung nicht stoppen."""
    from app.services import simulation_runner as runner_module

    def _explode(cls, sid):
        raise RuntimeError("Run-State-Store nicht erreichbar")

    monkeypatch.setattr(
        runner_module.SimulationRunner, "get_run_state", classmethod(_explode)
    )

    assert capture_simulation_snapshot("sim_test") is None


def test_dataclass_reicht_den_stand_durch():
    report = Report(
        report_id="report_test",
        simulation_id="sim_test",
        graph_id="graph_test",
        simulation_requirement="Akzeptanzanalyse",
        status=ReportStatus.COMPLETED,
        simulation_snapshot={
            "rounds_completed": 4,
            "total_rounds": 10,
            "simulation_running": True,
            "captured_at": "2026-08-10T20:20:00",
        },
    )

    assert report.to_dict()["simulation_snapshot"]["rounds_completed"] == 4
