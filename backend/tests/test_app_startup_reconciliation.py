"""``create_app`` — Startup-Reconciliation-Einhängepunkt (Tech-Review
2026-09-07, Slice B1).

Prüft nur den Einhängepunkt selbst (wird ``reconcile_stale_runs`` genau
einmal aufgerufen, überlebt der App-Start eine Exception darin) — die
eigentliche Reconciliation-Logik ist in
``tests/services/sim/test_reconciliation.py`` abgedeckt.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

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
        """App-Start darf nie an der Reconciliation scheitern — best effort, geloggt."""
        _prepare_startup_env(monkeypatch)
        _reset_run_registry(tmp_path, monkeypatch)

        def boom(*args, **kwargs):
            raise RuntimeError("run registry corrupted")

        monkeypatch.setattr(reconciliation_module, "reconcile_stale_runs", boom)

        error_spy = MagicMock()
        monkeypatch.setattr(logging.getLogger("agora"), "error", error_spy)

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
