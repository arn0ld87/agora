"""API-Tests für Run-Budgets (Issue #764).

Abgedeckt:
  1  POST /api/simulation/preflight-estimate → 200 mit Schätzbereichen
  2  preflight-estimate ohne Parameter → 400 (strukturierter Fehler)
  3  preflight-estimate mit ungültigem ai_model_ref → 400
  4  preflight-estimate via simulation_id + lokalem Modell → cost_status free
  5  GET /api/runs/<id> → budget/usage angereichert
  6  GET /api/runs/<id>/usage → Verbrauchsaufstellung
  7  Legacy-Manifest ohne neue Felder bleibt lesbar (kein budget/usage-Key)
  8  Secret-Hygiene: serialize_for_manifest + usage.json ohne Key-Material
"""
from __future__ import annotations

import json
import zipfile
from io import BytesIO

import pytest
from flask import Flask

from app.api import runs_bp, simulation_bp
from app.services.artifact_store import InMemoryArtifactStore
from app.services.run_registry import RunRegistry
from app.services.run_usage_ledger import reset_usage_cache


@pytest.fixture()
def env(tmp_path, monkeypatch):
    registry_dir = tmp_path / "run_registry"
    registry_dir.mkdir()
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(registry_dir))
    RunRegistry._instance = None
    run_dirs = tmp_path / "runs"
    run_dirs.mkdir()
    monkeypatch.setattr(
        "app.services.run_usage_ledger.ArtifactLocator.run_dir",
        staticmethod(lambda run_id: str(run_dirs / run_id)),
    )
    monkeypatch.setattr(
        "app.services.run_budget.ArtifactLocator.run_dir",
        staticmethod(lambda run_id: str(run_dirs / run_id)),
    )
    reset_usage_cache()

    artifact_store = InMemoryArtifactStore()
    app = Flask(__name__)
    app.extensions = {"artifact_store": artifact_store}
    app.register_blueprint(runs_bp, url_prefix="/api/runs")
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")

    yield {
        "client": app.test_client(),
        "registry": RunRegistry(),
        "artifact_store": artifact_store,
        "run_dirs": run_dirs,
    }

    RunRegistry._instance = None
    reset_usage_cache()


def _write_events(run_dirs, run_id: str, events: list[dict]) -> None:
    run_dir = run_dirs / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "llm_call_events.jsonl", "w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event) + "\n")
    reset_usage_cache()


def _event(**overrides) -> dict:
    base = {
        "stage": "simulation_rounds",
        "provider_id": "openai",
        "model": "gpt-4o-mini",
        "base_url_sanitized": "https://api.openai.com",
        "timestamp": 1_700_000_000.0,
        "latency_ms": 100.0,
        "success": True,
        "prompt_tokens": 1000,
        "completion_tokens": 500,
    }
    base.update(overrides)
    return base


class TestPreflightEstimate:
    def test_estimate_with_explicit_params(self, env):
        resp = env["client"].post(
            "/api/simulation/preflight-estimate",
            json={"num_agents": 5, "max_rounds": 10},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        data = body["data"]
        assert data["is_estimate"] is True
        assert data["estimated_tokens_low"] is not None
        assert data["estimated_tokens_high"] >= data["estimated_tokens_low"]
        assert data["pricing_version"]
        # Ohne Modellangabe sind Kosten ehrlich unbekannt, nicht 0
        assert data["cost_status"] in ("unknown", "estimated", "free")

    def test_estimate_missing_params_returns_400(self, env):
        resp = env["client"].post("/api/simulation/preflight-estimate", json={})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["success"] is False

    def test_estimate_invalid_model_ref_returns_400(self, env):
        resp = env["client"].post(
            "/api/simulation/preflight-estimate",
            json={
                "num_agents": 5,
                "max_rounds": 10,
                "ai_model_ref": {"provider_connection_id": 123},
            },
        )
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_estimate_from_simulation_config_local_model_free(self, env):
        env["artifact_store"].write_json(
            "sim_abcdef012345",
            "simulation_config",
            {
                "agent_configs": [{"name": "a"}, {"name": "b"}, {"name": "c"}],
                "time_config": {"total_simulation_hours": 2, "minutes_per_round": 30},
                "llm_model": "llama3.1",
                "llm_base_url": "http://localhost:11434/v1",
            },
        )
        resp = env["client"].post(
            "/api/simulation/preflight-estimate",
            json={"simulation_id": "sim_abcdef012345"},
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["models"], "Modell aus simulation_config erwartet"
        model = data["models"][0]
        assert model["model_id"] == "llama3.1"
        # Lokale Modelle sind ehrlich als kostenfrei markiert
        assert model["cost_status"] == "free"
        assert data["cost_status"] == "free"
        assert data["estimated_cost_micros_low"] == 0

    def test_estimate_invalid_simulation_id_returns_400(self, env):
        resp = env["client"].post(
            "/api/simulation/preflight-estimate",
            json={"simulation_id": "../etc/passwd"},
        )
        assert resp.status_code == 400


class TestRunDetailEnrichment:
    def test_detail_contains_budget_and_usage(self, env):
        manifest = env["registry"].create_run(
            "simulation_run",
            "sim_1",
            metadata={"budget": {"max_tokens": 5000, "enforcement": "soft"}},
        )
        run_id = manifest["run_id"]
        _write_events(env["run_dirs"], run_id, [_event(), _event(prompt_tokens=2000)])

        resp = env["client"].get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["budget"]["config"]["max_tokens"] == 5000
        assert data["budget"]["status"] in ("ok", "warning", "exceeded")
        assert data["usage"]["totals"]["total_tokens"] == 4000
        assert data["usage"]["totals"]["llm_calls"] == 2
        assert "simulation_rounds" in data["usage"]["by_stage"]
        assert "openai" in data["usage"]["by_provider"]
        assert "gpt-4o-mini" in data["usage"]["by_model"]

    def test_legacy_run_without_budget_stays_readable(self, env):
        manifest = env["registry"].create_run("simulation_run", "sim_legacy")
        run_id = manifest["run_id"]

        resp = env["client"].get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        # Legacy-Runs: keine erfundenen Budgetdaten
        assert data.get("budget") is None
        assert data.get("termination_reason") is None

    def test_usage_endpoint(self, env):
        manifest = env["registry"].create_run("simulation_run", "sim_2")
        run_id = manifest["run_id"]
        _write_events(env["run_dirs"], run_id, [_event()])

        resp = env["client"].get(f"/api/runs/{run_id}/usage")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["schema_version"] == 1
        assert data["totals"]["input_tokens"] == 1000
        assert data["totals"]["output_tokens"] == 500
        assert data["measurement_status"] in ("complete", "partial", "unknown")

    def test_usage_endpoint_404_for_unknown_run(self, env):
        resp = env["client"].get("/api/runs/run_000000000000/usage")
        assert resp.status_code == 404


class TestSecretHygiene:
    def test_serialize_for_manifest_rejects_key_material(self):
        from app.services.run_budget import serialize_for_manifest

        with pytest.raises(ValueError, match="api_key"):
            serialize_for_manifest({"config": {"api_key": "sk-secret"}})
        with pytest.raises(ValueError, match="Bearer "):
            serialize_for_manifest({"note": "Bearer abc123"})
        # Saubere Payloads passieren unverändert
        clean = {"config": {"max_tokens": 100, "currency": "USD"}}
        assert serialize_for_manifest(clean) == clean

    def test_usage_json_contains_no_secrets(self, env):
        manifest = env["registry"].create_run(
            "simulation_run",
            "sim_secret",
            metadata={"budget": {"max_tokens": 1000}},
        )
        run_id = manifest["run_id"]
        _write_events(env["run_dirs"], run_id, [_event()])

        from app.services.run_usage_ledger import persist_usage_summary

        persist_usage_summary(run_id)
        usage_path = env["run_dirs"] / run_id / "usage_summary.json"
        assert usage_path.exists()
        raw = usage_path.read_text(encoding="utf-8")
        for forbidden in ("api_key", "apiKey", "secret", "Bearer "):
            assert forbidden not in raw


class TestReportGenerateBudget:
    """POST /api/report/generate akzeptiert/validiert budget (Issue #764)."""

    @pytest.fixture()
    def report_client(self, env):
        from app.api import report_bp

        app = Flask(__name__)
        app.config["AGORA_REPORT_RATE_LIMIT_MAX"] = 100
        app.config["AGORA_REPORT_RATE_LIMIT_WINDOW_SECONDS"] = 60
        app.extensions = {"artifact_store": env["artifact_store"]}
        app.register_blueprint(report_bp, url_prefix="/api/report")
        return app.test_client()

    def test_invalid_budget_returns_400(self, report_client):
        resp = report_client.post(
            "/api/report/generate",
            json={
                "simulation_id": "sim_abcdef012345",
                "budget": {"max_tokens": -5},
            },
        )
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_valid_budget_passes_validation(self, report_client):
        # Gültiges Budget darf nicht an der Validierung scheitern — der Run
        # selbst schlägt fehl, weil die Simulation nicht existiert (404/500),
        # aber NICHT mit einem Budget-Validierungsfehler.
        resp = report_client.post(
            "/api/report/generate",
            json={
                "simulation_id": "sim_abcdef012345",
                "budget": {"max_llm_calls": 2, "enforcement": "hard"},
            },
        )
        assert resp.status_code != 400 or "budget" not in (
            resp.get_json().get("message") or ""
        )


class TestWorkflowBudgetPassthrough:
    """BudgetExceededError darf nicht in Fallback-/Fehlerpfaden versanden."""

    def test_section_fallback_reraises_budget_error(self):
        from app.services.report_agent import workflow
        from app.services.run_budget import BudgetExceededError

        def _raise_budget(*args, **kwargs):
            raise BudgetExceededError("calls", 3, 2)

        original = workflow.generate_section_react
        workflow.generate_section_react = _raise_budget
        try:
            with pytest.raises(BudgetExceededError):
                workflow._safe_generate_section_react(
                    object(),
                    section=object(),
                    outline="",
                    previous_sections=[],
                    progress_callback=None,
                    section_index=1,
                    report_id="report_x",
                )
        finally:
            workflow.generate_section_react = original


class TestApplyBudgetToSimulation:
    """Unit-Tests für die Start-Hilfsfunktion (CRG-Test-Gap, Issue #764)."""

    def test_writes_config_and_clears_stale_abort(self, tmp_path, monkeypatch):
        from app.api.simulation_run import _apply_budget_to_simulation
        from app.contracts.run_budget_contract import RunBudgetConfig

        sim_dir = tmp_path / "sim"
        sim_dir.mkdir()
        (sim_dir / "budget_abort.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(
            "app.api.simulation_run._simulation_dir", lambda _sid: str(sim_dir)
        )
        captured: list[tuple[str, object]] = []

        _apply_budget_to_simulation(
            "sim_abc",
            "run_abc",
            RunBudgetConfig(max_tokens=100, enforcement="hard"),
            lambda run_id, cfg: captured.append((run_id, cfg)),
        )

        assert captured and captured[0][0] == "run_abc"
        config = json.loads((sim_dir / "budget_config.json").read_text())
        assert config["max_tokens"] == 100
        assert config["enforcement"] == "hard"
        assert not (sim_dir / "budget_abort.json").exists()

    def test_without_budget_removes_stale_artifacts(self, tmp_path, monkeypatch):
        from app.api.simulation_run import _apply_budget_to_simulation

        sim_dir = tmp_path / "sim"
        sim_dir.mkdir()
        (sim_dir / "budget_config.json").write_text("{}", encoding="utf-8")
        (sim_dir / "budget_abort.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(
            "app.api.simulation_run._simulation_dir", lambda _sid: str(sim_dir)
        )

        called: list[object] = []
        _apply_budget_to_simulation(
            "sim_abc", "run_abc", None, lambda *args: called.append(args)
        )

        assert not called, "ohne Budget darf keine Config gesetzt werden"
        assert not (sim_dir / "budget_config.json").exists()
        assert not (sim_dir / "budget_abort.json").exists()


class TestExportBundle:
    def test_zip_bundle_contains_usage_and_budget(self, env, monkeypatch):
        """_add_budget_usage_to_zip legt usage.json/budget.json ins ZIP."""
        from app.contracts.run_budget_contract import RunBudgetConfig
        from app.services.report_export import ReportExportService

        manifest = env["registry"].create_run("report_generate", "rep_1")
        run_id = manifest["run_id"]
        # Manifest so verlinken, dass find_by_linked_id("report_id", ...) greift
        raw = env["registry"].get_run(run_id)
        raw.setdefault("linked_ids", {})["report_id"] = "rep_1"
        env["registry"]._write_run(raw)

        from app.services.run_budget import set_run_budget_config
        from app.services.run_usage_ledger import persist_usage_summary

        set_run_budget_config(
            run_id, RunBudgetConfig(max_tokens=1000, enforcement="hard")
        )
        _write_events(env["run_dirs"], run_id, [_event()])
        persist_usage_summary(run_id)

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            ReportExportService._add_budget_usage_to_zip(zf, "prefix", "rep_1")
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            assert "prefix/usage.json" in names
            assert "prefix/budget.json" in names
            usage = json.loads(zf.read("prefix/usage.json"))
            assert usage["totals"]["total_tokens"] == 1500
