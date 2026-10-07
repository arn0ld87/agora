"""Modell je Berichtsfassung in GET /api/report/<id> und /list (Issue #1804).

Die Berichts-Metadatei trägt kein Modell. Belegt ist es am Berichts-Job der
RunRegistry (``report_generate``, ``entity_id=<report_id>``). Die Lese-Endpunkte
liefern es als additive, optionale Felder ``llm_model``, ``llm_provider_id`` und
``generation_run_id``; ohne Job oder ohne Angabe bleiben sie ``None`` — nichts
wird aus Workspace-Defaults geraten.
"""

from __future__ import annotations

import uuid

import pytest
from flask import Flask

from app.api import report_bp
from app.contracts.report_contract import ReportModel
from app.models.report import Report, ReportStatus
from app.services.report_agent import ReportManager
from app.services.report_export import ReportExportService
from app.services.report_provenance import load_generation_info
from app.services.run_registry import RunRegistry


@pytest.fixture
def stores(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    runs = tmp_path / "run_registry"
    reports.mkdir()
    runs.mkdir()
    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(reports))
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(runs))
    # Der Singleton cached Manifeste je run_id; frische Ids je Test reichen,
    # der Cache wird trotzdem geleert, damit kein Eintrag aus einem früheren
    # Test mit anderem Verzeichnis überlebt.
    RunRegistry()._cache.clear()
    yield tmp_path
    RunRegistry()._cache.clear()


@pytest.fixture
def client(stores):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(report_bp, url_prefix="/api/report")
    return app.test_client()


def _new_report_id() -> str:
    return f"report_{uuid.uuid4().hex[:12]}"


def _save_report(report_id: str, *, simulation_id: str = "sim_0123456789ab") -> Report:
    report = Report(
        report_id=report_id,
        simulation_id=simulation_id,
        graph_id="graph_1",
        simulation_requirement="Anforderung",
        status=ReportStatus.COMPLETED,
        created_at="2026-09-01T10:00:00",
        completed_at="2026-09-01T10:05:00",
    )
    ReportManager.save_report(report)
    return report


def _add_run(
    report_id: str,
    *,
    model: str | None = "MiniMax-M3",
    provider_id: str | None = "minimax",
    base_url: str | None = None,
) -> str:
    metadata: dict = {"llm_model": model}
    metadata["llm_provider"] = (
        {"provider_id": provider_id, "base_url": base_url} if provider_id else None
    )
    run = RunRegistry().create_run(
        "report_generate",
        report_id,
        linked_ids={"report_id": report_id, "simulation_id": "sim_0123456789ab"},
        metadata=metadata,
        status="completed",
    )
    return run["run_id"]


class TestReportDetailCarriesGenerationProvenance:
    def test_get_report_returns_model_provider_and_run(self, client):
        report_id = _new_report_id()
        _save_report(report_id)
        run_id = _add_run(report_id, model="glm-5.2:cloud", provider_id="ollama")

        resp = client.get(f"/api/report/{report_id}")

        assert resp.status_code == 200, resp.get_data(as_text=True)
        data = resp.get_json()["data"]
        assert data["llm_model"] == "glm-5.2:cloud"
        assert data["llm_provider_id"] == "ollama"
        assert data["generation_run_id"] == run_id
        ReportModel.model_validate(data)

    def test_base_url_is_not_exposed(self, client):
        report_id = _new_report_id()
        _save_report(report_id)
        _add_run(report_id, base_url="https://api.minimax.io/v1")

        data = client.get(f"/api/report/{report_id}").get_json()["data"]

        assert "base_url" not in data
        assert "api.minimax.io" not in str(data)

    def test_report_without_job_keeps_fields_empty(self, client):
        report_id = _new_report_id()
        _save_report(report_id)

        data = client.get(f"/api/report/{report_id}").get_json()["data"]

        assert data["llm_model"] is None
        assert data["llm_provider_id"] is None
        assert data["generation_run_id"] is None

    def test_job_without_model_keeps_model_empty_but_links_the_run(self, client):
        # 8 von 53 Berichts-Jobs im Referenzbestand tragen kein Modell. Das Feld
        # bleibt leer; der Job ist trotzdem verlinkbar.
        report_id = _new_report_id()
        _save_report(report_id)
        run_id = _add_run(report_id, model=None, provider_id=None)

        data = client.get(f"/api/report/{report_id}").get_json()["data"]

        assert data["llm_model"] is None
        assert data["llm_provider_id"] is None
        assert data["generation_run_id"] == run_id

    def test_most_recent_job_wins_after_a_resume(self, client):
        report_id = _new_report_id()
        _save_report(report_id)
        _add_run(report_id, model="old-model", provider_id="openai")
        newest = _add_run(report_id, model="new-model", provider_id="google")

        data = client.get(f"/api/report/{report_id}").get_json()["data"]

        assert data["llm_model"] == "new-model"
        assert data["generation_run_id"] == newest

    def test_other_run_types_and_other_reports_are_ignored(self, client):
        report_id = _new_report_id()
        _save_report(report_id)
        RunRegistry().create_run(
            "simulation",
            report_id,
            linked_ids={"report_id": report_id},
            metadata={"llm_model": "sim-model"},
        )
        _add_run(_new_report_id(), model="foreign-model")

        data = client.get(f"/api/report/{report_id}").get_json()["data"]

        assert data["llm_model"] is None
        assert data["generation_run_id"] is None

    def test_by_simulation_route_carries_the_same_fields(self, client):
        report_id = _new_report_id()
        _save_report(report_id, simulation_id="sim_aaaaaaaaaaaa")
        _add_run(report_id, model="gpt-5.6-terra", provider_id="openai")

        resp = client.get("/api/report/by-simulation/sim_aaaaaaaaaaaa")

        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert resp.get_json()["data"]["llm_model"] == "gpt-5.6-terra"


class TestReportListCarriesGenerationProvenance:
    def test_list_returns_provenance_per_version(self, client):
        with_job = _new_report_id()
        without_job = _new_report_id()
        _save_report(with_job)
        _save_report(without_job)
        run_id = _add_run(with_job, model="MiniMax-M3", provider_id="minimax")

        resp = client.get("/api/report/list")

        assert resp.status_code == 200, resp.get_data(as_text=True)
        by_id = {item["report_id"]: item for item in resp.get_json()["data"]}
        assert by_id[with_job]["llm_model"] == "MiniMax-M3"
        assert by_id[with_job]["llm_provider_id"] == "minimax"
        assert by_id[with_job]["generation_run_id"] == run_id
        assert by_id[without_job]["llm_model"] is None
        assert by_id[without_job]["generation_run_id"] is None
        for item in by_id.values():
            ReportModel.model_validate(item)

    def test_list_scans_the_registry_once_not_per_report(self, client, monkeypatch):
        for _ in range(3):
            _save_report(_new_report_id())
        calls: list[dict] = []
        original = RunRegistry.list_runs

        def counting(self, **kwargs):
            calls.append(kwargs)
            return original(self, **kwargs)

        monkeypatch.setattr(RunRegistry, "list_runs", counting)

        assert client.get("/api/report/list").status_code == 200
        assert len(calls) == 1


class TestExportStaysUnchanged:
    def test_contract_model_without_generation_leaves_fields_empty(self):
        report = Report(
            report_id=_new_report_id(),
            simulation_id="sim_0123456789ab",
            graph_id="graph_1",
            simulation_requirement="Anforderung",
            status=ReportStatus.COMPLETED,
        )

        model = ReportExportService.build_report_contract_model(report)

        assert model.llm_model is None
        assert model.llm_provider_id is None
        assert model.generation_run_id is None


def test_load_generation_info_filters_to_the_requested_reports(stores):
    wanted = _new_report_id()
    other = _new_report_id()
    _add_run(wanted, model="a")
    _add_run(other, model="b")

    info = load_generation_info([wanted])

    assert set(info) == {wanted}
    assert info[wanted].llm_model == "a"
