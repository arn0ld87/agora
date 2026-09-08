"""Startup-Reconciliation-Einhängepunkte (Tech-Review 2026-09-07, Slice B1;
Codex-Review Finding A, 2026-09-08, PR #1476).

Prüft nur die Einhängepunkte selbst (wird ``reconcile_stale_runs`` genau
einmal aufgerufen, überlebt der App-/Worker-Start eine Exception darin) —
die eigentliche Reconciliation-Logik ist in
``tests/services/sim/test_reconciliation.py`` abgedeckt.

Zwei Einhängepunkte seit Finding A:
- ``app/__init__.py::create_app`` — einziger Trigger in Entwicklungs-/
  Testbetrieb ohne gunicorn (``TestStartupReconciliationHook``).
- ``gunicorn.conf.py::post_fork`` — kanonischer Trigger in Produktion, läuft
  bei jedem Worker-Start, auch nach Replacement des einzigen Workers
  (``TestPostForkReconciliationHook``).
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

from app.services.run_registry import RunRegistry
from app.services.sim import reconciliation as reconciliation_module


def _prepare_startup_env(monkeypatch):
    """Bringt ``create_app()`` bis zum Ende durch, ohne echte Infrastruktur.

    Analog zu ``tests/test_embedding_service.py::_prepare_startup_env`` —
    ``Config.validate()`` verlangt mit ``DEBUG=False`` einen nicht-leeren
    ``SECRET_KEY``/``NEO4J_PASSWORD``/``AGORA_AUTH_TOKEN``-Ersatz
    (``AGORA_ALLOW_ANONYMOUS``); ohne diese Werte scheitert ``create_app()``
    schon vor dem Reconciliation-Hook.
    """
    monkeypatch.setenv("FLASK_DEBUG", "false")
    monkeypatch.setenv("AGORA_ALLOW_ANONYMOUS", "true")
    monkeypatch.delenv("AGORA_CORS_ALLOW_ALL", raising=False)

    from app.config import Config as _Config

    monkeypatch.setattr(_Config, "DEBUG", False)
    monkeypatch.setattr(_Config, "SECRET_KEY", "test-secret-key-not-a-placeholder")
    monkeypatch.setattr(_Config, "NEO4J_PASSWORD", "test-neo4j-password")

    # Kein echtes Embedding-Backend in der Test-Umgebung nötig — deterministisch
    # als "valide, 768 Dimensionen" beantworten, statt einen Netzwerk-Call zu riskieren.
    monkeypatch.setattr(
        "app.storage.embedding_service.validate_embedding_configuration",
        lambda skip_probe=False: 768,
    )


def _reset_run_registry(tmp_path, monkeypatch):
    """RunRegistry-Singleton auf ein tmp-Verzeichnis umbiegen (wie test_run_registry.py)."""
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(tmp_path / "run_registry"))
    RunRegistry._instance = None


class TestStartupReconciliationHook:
    def test_reconcile_stale_runs_is_called_exactly_once(self, tmp_path, monkeypatch):
        _prepare_startup_env(monkeypatch)
        _reset_run_registry(tmp_path, monkeypatch)

        call_count = {"n": 0}

        def fake_reconcile(*args, **kwargs):
            call_count["n"] += 1
            return reconciliation_module.ReconciliationResult()

        monkeypatch.setattr(reconciliation_module, "reconcile_stale_runs", fake_reconcile)

        from app import create_app

        app = create_app()

        assert app is not None
        assert call_count["n"] == 1

    def test_reconciliation_exception_does_not_abort_startup(self, tmp_path, monkeypatch):
        """App-Start darf nie an der Reconciliation scheitern — best effort, geloggt.

        Der Fehler wird seit Finding A in ``run_startup_reconciliation``
        (Modul ``app.services.sim.reconciliation``) geloggt, nicht mehr
        direkt in ``create_app`` — daher wird der "agora.sim.reconciliation"-
        Logger gespyt, nicht mehr der Root-"agora"-Logger.
        """
        _prepare_startup_env(monkeypatch)
        _reset_run_registry(tmp_path, monkeypatch)

        def boom(*args, **kwargs):
            raise RuntimeError("run registry corrupted")

        monkeypatch.setattr(reconciliation_module, "reconcile_stale_runs", boom)

        error_spy = MagicMock()
        monkeypatch.setattr(logging.getLogger("agora.sim.reconciliation"), "error", error_spy)

        from app import create_app

        app = create_app()  # darf nicht raisen

        assert app is not None
        assert any(
            "Reconciliation" in str(call.args[0])
            for call in error_spy.call_args_list
            if call.args
        )

    def test_disabled_flag_skips_reconciliation_entirely(self, tmp_path, monkeypatch):
        _prepare_startup_env(monkeypatch)
        _reset_run_registry(tmp_path, monkeypatch)
        monkeypatch.setenv("AGORA_STARTUP_RECONCILIATION", "false")

        from app.config import Config as _Config

        monkeypatch.setattr(_Config, "AGORA_STARTUP_RECONCILIATION", False)

        call_count = {"n": 0}

        def fake_reconcile(*args, **kwargs):
            call_count["n"] += 1
            return reconciliation_module.ReconciliationResult()

        monkeypatch.setattr(reconciliation_module, "reconcile_stale_runs", fake_reconcile)

        from app import create_app

        app = create_app()

        assert app is not None
        assert call_count["n"] == 0


def _load_gunicorn_conf():
    """``gunicorn.conf.py`` per ``spec_from_file_location`` laden — dasselbe
    Muster wie ``tests/test_fork_safety.py::test_gunicorn_post_fork_hook_*``,
    weil die Datei kein regulär importierbares Package-Modul ist."""
    import importlib.util
    from pathlib import Path

    conf_path = Path(__file__).resolve().parents[1] / "gunicorn.conf.py"
    spec = importlib.util.spec_from_file_location(
        "agora_gunicorn_conf_reconciliation", conf_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestPostForkReconciliationHook:
    """``gunicorn.conf.py::post_fork`` — Finding A (Codex-Review 2026-09-08,
    PR #1476): mit ``preload_app=True`` + ``workers=1`` läuft ``create_app``
    genau einmal im Master vor dem ersten Fork. Ersetzt gunicorn den
    einzigen Worker später (Timeout, Crash, manueller Restart), ohne den
    Master neu zu starten, läuft ``create_app`` nie wieder — nur
    ``post_fork`` feuert für jeden Worker-Start, auch für diesen Ersatz.
    Reconciliation muss deshalb hier laufen, um die Lücke tatsächlich zu
    schließen. Config-Flag-Verhalten und Fehlerbehandlung selbst sind über
    ``run_startup_reconciliation`` bereits in
    ``TestStartupReconciliationHook`` abgedeckt — hier wird nur geprüft,
    dass der Hook sie tatsächlich aufruft und ein Fehler darin den
    Worker-Start nicht abbricht.
    """

    def test_post_fork_triggers_startup_reconciliation(self):
        module = _load_gunicorn_conf()

        with (
            patch("app.extensions.reset_pools_after_fork"),
            patch(
                "app.services.sim.reconciliation.run_startup_reconciliation"
            ) as mock_reconcile,
        ):
            module.post_fork(MagicMock(), MagicMock(pid=4242))

        mock_reconcile.assert_called_once()

    def test_post_fork_respects_disabled_flag(self):
        module = _load_gunicorn_conf()

        from app.config import Config

        with (
            patch("app.extensions.reset_pools_after_fork"),
            patch.object(Config, "AGORA_STARTUP_RECONCILIATION", False),
            patch(
                "app.services.sim.reconciliation.run_startup_reconciliation"
            ) as mock_reconcile,
        ):
            module.post_fork(MagicMock(), MagicMock(pid=99))

        mock_reconcile.assert_called_once_with(enabled=False)

    def test_post_fork_reconciliation_error_does_not_crash_worker(self):
        """Ein Fehler in der Reconciliation darf den Worker-Start genauso
        wenig abbrechen wie bisher den App-Start (Finding A, Briefing)."""
        module = _load_gunicorn_conf()

        with (
            patch("app.extensions.reset_pools_after_fork"),
            patch(
                "app.services.sim.reconciliation.run_startup_reconciliation",
                side_effect=RuntimeError("boom"),
            ),
        ):
            module.post_fork(MagicMock(), MagicMock(pid=99))  # darf nicht raisen
