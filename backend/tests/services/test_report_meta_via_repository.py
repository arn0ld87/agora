"""Regressionstests fuer Issue #1588.

``branching_service.create_branch`` und
``simulation_history._get_report_id_for_simulation`` lasen bisher
Report-Metadaten per ``os.listdir`` + ``open(meta.json)``/``json.load``
direkt von der Platte. Im kuenftigen Postgres-Adapter (#1588) gibt es diese
Datei nicht mehr — beide Stellen muessen ueber den ``ReportRepository``-Port
(``app/repositories/report_repository.py``) laufen.

Beide Tests schleusen ein Fake-Repository ein, das Reports liefert, OHNE dass
irgendeine ``meta.json`` auf Platte existiert — das ist der eigentliche
Beweis, dass der Port und nicht die Datei befragt wird.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

import pytest

from app.api import simulation_history
from app.config import Config
from app.contracts.report_record_contract import ReportRecord
from app.services import branching_service
from app.services.artifact_store import InMemoryArtifactStore
from app.services.run_registry import RunRegistry
from app.services.simulation_manager import SimulationManager, SimulationStatus


class _FakeReportRepository:
    """In-Memory-Stub des ``ReportRepository``-Ports, keyed nach Ablageschluessel.

    Absichtlich ohne jede Datei-I/O: ``get``/``list``/``list_ids`` bedienen
    sich ausschliesslich aus dem im Test befuellten Dict.
    """

    def __init__(self, records_by_key: Dict[str, ReportRecord]) -> None:
        self._records_by_key = dict(records_by_key)

    def get(self, report_id: str) -> Optional[ReportRecord]:
        return self._records_by_key.get(report_id)

    def save(self, record: ReportRecord) -> ReportRecord:  # pragma: no cover - unbenutzt hier
        self._records_by_key[record.report_id] = record
        return record

    def list_ids(self) -> List[str]:
        return list(self._records_by_key)

    def list(self, simulation_id: Optional[str] = None) -> List[ReportRecord]:
        records = list(self._records_by_key.values())
        if simulation_id is not None:
            records = [r for r in records if r.simulation_id == simulation_id]
        return records


def _make_record(**overrides: object) -> ReportRecord:
    base: Dict[str, object] = dict(
        report_id="report-id",
        simulation_id="sim-1",
        graph_id="graph-1",
        simulation_requirement="req",
        status="completed",
        created_at="2026-01-01T00:00:00",
    )
    base.update(overrides)
    return ReportRecord(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# (a) branching_service.create_branch kopiert ueber den Ablageschluessel
# ---------------------------------------------------------------------------


@pytest.fixture
def manager(tmp_path, monkeypatch) -> SimulationManager:
    """Manager mit isoliertem Datenverzeichnis, In-Memory-Store und tmp-RunRegistry.

    Analog ``tests/contracts/test_branch_override_contract.py::manager``.
    """
    monkeypatch.setattr(
        SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path / "simulations")
    )
    registry_dir = str(tmp_path / "run_registry")
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", registry_dir)
    RunRegistry._instance = None
    os.makedirs(registry_dir, exist_ok=True)
    yield SimulationManager(store=InMemoryArtifactStore())
    RunRegistry._instance = None


@pytest.fixture
def source_id(manager: SimulationManager) -> str:
    state = manager.create_simulation(project_id="proj-1588", graph_id="graph-1588")
    manager._set_status(state, SimulationStatus.PREPARING)
    manager._set_status(state, SimulationStatus.READY)
    manager._store.write_json(
        state.simulation_id,
        "simulation_config",
        {"llm_model": "m", "language": "de", "max_agents": 5},
    )
    return state.simulation_id


def test_create_branch_copies_report_folder_via_repository_key(
    manager: SimulationManager, source_id: str, tmp_path, monkeypatch
) -> None:
    """Kopiert wird der Ordner unter dem Ablageschluessel, nicht ``record.report_id``.

    Deckt den Fall ab, dass Ablageschluessel und ``report_id`` im Manifest
    abweichen (Altbestand, Codex-Review auf #1601), und dass eine fremde
    Simulation uebersprungen wird. Keine ``meta.json`` liegt auf Platte —
    ausschliesslich das gefakte Repository liefert die Metadaten.
    """
    uploads_dir = tmp_path / "uploads"
    reports_dir = uploads_dir / "reports"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(uploads_dir))

    matching_key = "report_deepseek_abc123"
    foreign_key = "report_foreign_999"
    os.makedirs(reports_dir / matching_key)
    (reports_dir / matching_key / "report-v3.json").write_text("{}", encoding="utf-8")
    os.makedirs(reports_dir / foreign_key)
    (reports_dir / foreign_key / "report-v3.json").write_text("{}", encoding="utf-8")
    assert not (reports_dir / matching_key / "meta.json").exists()
    assert not (reports_dir / foreign_key / "meta.json").exists()

    fake_repo = _FakeReportRepository({
        # Ablageschluessel != record.report_id, wie bei einem Altbestand.
        matching_key: _make_record(report_id="report_abc123", simulation_id=source_id),
        foreign_key: _make_record(report_id="report_999", simulation_id="other-sim"),
    })
    monkeypatch.setattr(
        branching_service,
        "get_report_repository",
        lambda reports_dir=None: fake_repo,
    )

    branch = branching_service.create_branch(
        manager, source_id, "branch-1588", copy_report_artifacts=True
    )

    branch_dir = manager._get_simulation_dir(branch.simulation_id)
    copied = os.path.join(branch_dir, "reports", matching_key)
    skipped = os.path.join(branch_dir, "reports", foreign_key)
    wrong_key = os.path.join(branch_dir, "reports", "report_abc123")

    assert os.path.isfile(os.path.join(copied, "report-v3.json"))
    assert not os.path.exists(skipped)
    assert not os.path.exists(wrong_key)


def test_create_branch_skips_missing_report_record(
    manager: SimulationManager, source_id: str, tmp_path, monkeypatch
) -> None:
    """``record is None`` (kaputtes/fehlendes Manifest) wird uebersprungen, nicht geworfen."""
    uploads_dir = tmp_path / "uploads"
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(uploads_dir))

    fake_repo = _FakeReportRepository({})
    monkeypatch.setattr(
        branching_service,
        "get_report_repository",
        lambda reports_dir=None: fake_repo,
    )
    # list_ids() liefert einen Schluessel, fuer den get() None zurueckgibt.
    fake_repo.list_ids = lambda: ["orphaned-key"]  # type: ignore[method-assign]

    branch = branching_service.create_branch(
        manager, source_id, "branch-1588-orphan", copy_report_artifacts=True
    )

    branch_dir = manager._get_simulation_dir(branch.simulation_id)
    assert not os.path.exists(os.path.join(branch_dir, "reports", "orphaned-key"))


# ---------------------------------------------------------------------------
# (b) simulation_history._get_report_id_for_simulation liefert die neueste report_id
# ---------------------------------------------------------------------------


def test_get_report_id_for_simulation_returns_newest_via_repository(monkeypatch) -> None:
    """Die zurueckgegebene ``report_id`` gehoert zum juengsten ``created_at``.

    Kein ``meta.json`` existiert — die Daten kommen ausschliesslich aus dem
    gefakten Repository.
    """
    fake_repo = _FakeReportRepository({
        "key-old": _make_record(
            report_id="report-old", simulation_id="sim-42", created_at="2026-01-01T00:00:00"
        ),
        "key-new": _make_record(
            report_id="report-new", simulation_id="sim-42", created_at="2026-02-01T00:00:00"
        ),
        "key-other-sim": _make_record(
            report_id="report-other", simulation_id="sim-999", created_at="2026-03-01T00:00:00"
        ),
    })
    monkeypatch.setattr(simulation_history, "get_report_repository", lambda: fake_repo)

    result = simulation_history._get_report_id_for_simulation("sim-42")

    assert result == "report-new"


def test_get_report_id_for_simulation_returns_none_without_match(monkeypatch) -> None:
    fake_repo = _FakeReportRepository({})
    monkeypatch.setattr(simulation_history, "get_report_repository", lambda: fake_repo)

    assert simulation_history._get_report_id_for_simulation("sim-none") is None
