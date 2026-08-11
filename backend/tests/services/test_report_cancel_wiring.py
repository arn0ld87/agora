"""Issue #1243 — ``cancel_run_id`` muss den Produktivpfad erreichen.

``generate_report`` prüft das Cancel-Flag an zwei Stage-Grenzen korrekt, aber
der Parameter ist keyword-only mit Default ``None`` und ``_is_cancel_requested``
steigt bei ``None`` sofort aus. Vor diesem Slice übergab **kein**
Produktivaufrufer den Parameter: ``POST /api/runs/<id>/cancel`` quittierte 202,
der Report lief unbeirrt weiter und war nur per ``docker restart`` zu beenden.

Der bestehende Test ``test_partial_report.py`` prüft, dass die Workflow-Funktion
das Flag **honoriert, wenn es übergeben wird** — genau die Frage, die nicht das
Problem war. Dieser Test prüft stattdessen den **Aufrufpfad**: er fährt den
produktiven Einstiegspunkt ``ReportGenerationService.start_generation`` und
assertiert, dass die ``run_id`` als Abbruchkennung beim Agent ankommt und der
Run nach einem Abbruch in seinem Abbruch-Endzustand landet.

Aufbau analog ``test_report_budget_abort_run_status.py`` (#978): ``TaskManager``
und ``RunRegistry`` bleiben echt, weil ihr Zusammenspiel den Endzustand
bestimmt.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.report import Report, ReportStatus
from app.services import report_generation as rg
from app.services.llm_runtime import RuntimeLlmConfig
from app.services.run_registry import RunRegistry
from app.services.sim.cancel_flag import clear_cancel, request_cancel


def _ensure_dir(path):
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture()
def cancel_env(tmp_path, monkeypatch):
    """Isolierte Registry + gestubbte Report-Umgebung.

    Der Agent ist ein Doppelgänger, der die erhaltenen Keyword-Argumente
    mitschneidet und — sobald das Cancel-Flag für seine ``cancel_run_id``
    gesetzt ist — einen Teilreport zurückgibt, wie es
    ``_build_partial_report`` produktiv tut (``status=COMPLETED``).
    """
    registry_dir = tmp_path / "run_registry"
    registry_dir.mkdir()
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(registry_dir))
    RunRegistry._instance = None
    registry = RunRegistry()
    monkeypatch.setattr(rg, "run_registry", registry)

    created: dict[str, str] = {}
    _real_create_run = registry.create_run

    def _capture_create_run(*args, **kwargs):
        record = _real_create_run(*args, **kwargs)
        created["run_id"] = record["run_id"]
        return record

    monkeypatch.setattr(registry, "create_run", _capture_create_run)

    run_root = tmp_path / "runs"
    run_root.mkdir()
    monkeypatch.setattr(
        "app.utils.artifact_locator.ArtifactLocator.run_dir",
        classmethod(lambda cls, run_id: str(_ensure_dir(run_root / run_id))),
    )

    state = SimpleNamespace(
        project_id="proj-1",
        graph_id="graph-1",
        source_simulation_id=None,
        root_simulation_id=None,
        branch_name=None,
        branch_depth=0,
    )
    sim_mgr = MagicMock()
    sim_mgr.get_simulation.return_value = state
    monkeypatch.setattr(rg, "SimulationManager", lambda: sim_mgr)

    project = SimpleNamespace(
        graph_id="graph-1", simulation_requirement="Requirement X", llm_profile_id=None
    )
    monkeypatch.setattr(rg.ProjectManager, "get_project", staticmethod(lambda pid: project))
    monkeypatch.setattr(rg, "seed_run_stage_routing", lambda *a, **k: None)

    resolved_route = SimpleNamespace(
        provider_id="ollama",
        model="qwen2.5:32b",
        base_url_sanitized="http://localhost:11434/v1",
    )
    router = MagicMock()
    router.resolve.return_value = resolved_route
    monkeypatch.setattr(rg, "StageModelRouter", lambda run_id: router)
    monkeypatch.setattr(rg, "resolve_route_api_key", lambda *a, **k: None)
    monkeypatch.setattr(rg, "SecretResolver", MagicMock())
    monkeypatch.setattr(rg.LLMClient, "from_route", staticmethod(lambda *a, **k: MagicMock()))
    monkeypatch.setattr(rg, "GraphToolsService", lambda **kwargs: MagicMock())
    monkeypatch.setattr(rg, "current_app", MagicMock())

    seen: dict[str, object] = {}

    class _RecordingAgent:
        def __init__(self, **kwargs):
            pass

        def generate_report(self, **kwargs):
            seen.update(kwargs)
            return Report(
                report_id=kwargs.get("report_id") or "report_test",
                simulation_id="sim_abc",
                graph_id="graph-1",
                simulation_requirement="Requirement X",
                status=ReportStatus.COMPLETED,
                markdown_content="# Teilreport",
            )

    monkeypatch.setattr(rg, "ReportAgent", _RecordingAgent)
    monkeypatch.setattr(rg.ReportManager, "save_report", staticmethod(lambda *a, **k: None))

    jobs: list[object] = []
    monkeypatch.setattr("app.jobs.enqueue", lambda name, fn: jobs.append(fn) or "job-test")

    yield SimpleNamespace(jobs=jobs, created=created, seen=seen)

    run_id = created.get("run_id")
    if run_id:
        clear_cancel(run_id)
    RunRegistry._instance = None


def _start(env, *, cancel_before_run: bool = False) -> str:
    """Fährt ``start_generation`` und führt den eingereihten Job aus.

    Mit ``cancel_before_run`` wird das Cancel-Flag gesetzt, sobald die
    ``run_id`` existiert — also genau in dem Zeitfenster, in dem der Nutzer
    ``POST /api/runs/<id>/cancel`` auslöst.
    """
    result = rg.ReportGenerationService.start_generation(
        simulation_id="sim_abc",
        report_mode="balanced",
        force_regenerate=True,
        llm_model_override=None,
        llm_runtime=RuntimeLlmConfig(),
    )
    assert result["status"] == "generating"
    assert len(env.jobs) == 1, "Report-Job wurde nicht eingereiht"

    run_id = env.created.get("run_id")
    assert run_id, "create_run wurde nicht aufgerufen"

    if cancel_before_run:
        request_cancel(run_id)

    env.jobs[0]()
    return run_id


def test_report_generation_reicht_cancel_run_id_durch(cancel_env):
    """RED ohne den Fix: ``start_generation`` übergibt den Parameter nicht."""
    run_id = _start(cancel_env)

    assert "cancel_run_id" in cancel_env.seen, (
        "ReportGenerationService ruft generate_report ohne cancel_run_id — "
        "das Cancel-Flag wird produktiv nie gelesen"
    )
    assert cancel_env.seen["cancel_run_id"] == run_id


def test_abgebrochener_report_endet_stopped_mit_termination_reason(cancel_env):
    """Ein abgebrochener Run darf nicht als regulär ``completed`` erscheinen."""
    run_id = _start(cancel_env, cancel_before_run=True)
    run = RunRegistry().get_run(run_id)

    assert run is not None
    assert run["status"] == "stopped", (
        "Nach einem Nutzerabbruch muss der Run stopped sein, nicht completed. "
        f"message={run.get('message')!r}"
    )
    assert run["termination_reason"] == "user_cancel"


def test_regulaerer_lauf_bleibt_completed(cancel_env):
    """Gegenprobe: ohne Cancel-Flag bleibt der Erfolgspfad unverändert."""
    run_id = _start(cancel_env)
    run = RunRegistry().get_run(run_id)

    assert run is not None
    assert run["status"] == "completed"
    assert run.get("termination_reason") is None


def test_runs_api_reicht_cancel_run_id_durch():
    """Der Resume-Pfad in ``api/runs.py`` darf den Parameter nicht verlieren.

    Statisch geprüft: der Aufruf im Resume-Handler steht in einem
    Worker-Thread hinter Neo4j-, Projekt- und LLM-Auflösung — ihn zu fahren
    kostet mehr Fixture, als der eine Aufrufparameter wert ist. Ein
    Signaturvergleich fängt genau die Regression, um die es geht: dass der
    Parameter beim Kopieren des Blocks wieder wegfällt.
    """
    import inspect

    from app.api import runs as runs_api

    source = inspect.getsource(runs_api._resume_report_generate)
    assert "cancel_run_id=" in source, (
        "api/runs.py ruft generate_report ohne cancel_run_id — der Resume-Pfad "
        "ist damit weiterhin nicht abbrechbar"
    )


def test_report_agent_fassade_reicht_cancel_run_id_weiter():
    """``ReportAgent.generate_report`` darf den Parameter nicht schlucken."""
    import inspect

    from app.services.report_agent.agent import ReportAgent

    params = inspect.signature(ReportAgent.generate_report).parameters
    assert "cancel_run_id" in params, (
        "Die Agent-Fassade kennt cancel_run_id nicht — der Parameter endet dort"
    )
    assert params["cancel_run_id"].kind is inspect.Parameter.KEYWORD_ONLY


def test_resume_loescht_die_abbruchbegruendung():
    """CodeRabbit PR #1251: `termination_reason` überlebte den Resume.

    `update_run` lässt das Feld stehen, solange es nicht ausdrücklich
    überschrieben wird. Ein abgebrochener, dann fortgesetzter und erfolgreich
    beendeter Run stünde als `completed` da und wäre im Monitor trotzdem als
    nutzerabgebrochen geführt.
    """
    import inspect

    from app.api import runs as runs_api

    source = inspect.getsource(runs_api._resume_report_generate)
    assert "termination_reason=None" in source, (
        "Der Resume-Erfolgspfad löscht die Abbruchbegründung nicht"
    )


def test_registry_kann_die_abbruchbegruendung_ueberhaupt_loeschen(tmp_path, monkeypatch):
    """Ohne diese Zusicherung wäre der Fix oben wirkungslos."""
    registry_dir = tmp_path / "reg"
    registry_dir.mkdir()
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(registry_dir))
    RunRegistry._instance = None
    registry = RunRegistry()

    record = registry.create_run("report_generate", "report_x")
    registry.update_run(record["run_id"], status="stopped", termination_reason="user_cancel")
    assert registry.get_run(record["run_id"])["termination_reason"] == "user_cancel"

    registry.update_run(record["run_id"], status="completed", termination_reason=None)
    assert registry.get_run(record["run_id"])["termination_reason"] is None

    RunRegistry._instance = None
