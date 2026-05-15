"""Tests für Slice 3b: init_logging-Verdrahtung in App-Factory und Runner.

Smoke-Spec:
  - create_app() ruft init_logging auf (nach init_tracing, vor init_metrics).
  - init_runner_logging delegiert an init_logging und schlägt lautlos fehl
    wenn OTEL-Deps fehlen (ImportError-Pfad).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch



# ---------------------------------------------------------------------------
# Case 1: App-Factory verdrahtet init_logging
# ---------------------------------------------------------------------------


def test_create_app_imports_and_calls_init_logging():
    """app.__init__ importiert init_logging aus app.observability.

    Prüft statisch, dass:
    1. init_logging im app-Modul-Namespace vorhanden und aufrufbar ist.
    2. create_app() init_logging in korrekter Reihenfolge aufruft —
       geprüft via Quelltext-Positionsanalyse (init_logging zwischen
       init_tracing und init_metrics).

    Keine echte create_app()-Ausführung (Blueprint-Reregistrierungs-Problem
    bei Gesamtsuite). Stattdessen Quelltext-basierte Reihenfolgenprüfung.
    """
    import inspect
    import app as app_module

    # init_logging muss im Modul-Namespace sichtbar sein
    assert hasattr(app_module, "init_logging"), (
        "init_logging fehlt im app-Modul-Namespace — Import vergessen?"
    )
    assert callable(app_module.init_logging)

    # Quelltext von create_app lesen und Aufruf-Reihenfolge prüfen
    source = inspect.getsource(app_module.create_app)
    tracing_pos = source.find("init_tracing(")
    logging_pos = source.find("init_logging(")
    metrics_pos = source.find("init_metrics(")

    assert logging_pos != -1, "init_logging() wird in create_app() nicht aufgerufen"
    assert tracing_pos < logging_pos, (
        "init_logging() muss nach init_tracing() aufgerufen werden"
    )
    assert logging_pos < metrics_pos, (
        "init_logging() muss vor init_metrics() aufgerufen werden"
    )


# ---------------------------------------------------------------------------
# Case 2: init_runner_logging delegiert an init_logging
# ---------------------------------------------------------------------------


def test_init_runner_logging_calls_init_logging():
    """init_runner_logging delegiert an app.observability.init_logging.

    Laufzeit-Prüfung: init_logging wird mit dem service_name aufgerufen.
    Importiert _sim_common über sys.path (scripts/-Verzeichnis), damit
    der Test unabhängig von der Paket-Installationsform funktioniert.
    """
    import sys
    import os

    scripts_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
    )
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    # Importiere direkt — scripts-Verzeichnis ist nun im sys.path
    import importlib
    sim_common = importlib.import_module("_sim_common")

    assert hasattr(sim_common, "init_runner_logging"), (
        "init_runner_logging fehlt in _sim_common"
    )

    # Laufzeit-Prüfung: init_logging wird mit service_name aufgerufen
    fake_init_logging = MagicMock()

    with patch("app.observability.init_logging", fake_init_logging):
        sim_common.init_runner_logging("agora-oasis-runner")

    fake_init_logging.assert_called_once_with("agora-oasis-runner")


# ---------------------------------------------------------------------------
# Case 3: init_runner_logging schweigt bei ImportError
# ---------------------------------------------------------------------------


def test_init_runner_logging_silent_on_import_error():
    """init_runner_logging schlägt lautlos fehl wenn OTEL-Deps fehlen.

    Statische Prüfung via Quelltext: try/except ImportError mit
    frühem Return muss vorhanden sein — kein fragiles sys.modules-Hacking.
    """
    from pathlib import Path

    source_path = (
        Path(__file__).parent.parent.parent / "scripts" / "_sim_common.py"
    )
    source = source_path.read_text(encoding="utf-8")

    func_start = source.find("def init_runner_logging(")
    assert func_start != -1, "init_runner_logging nicht in _sim_common.py gefunden"

    # Funktionskörper: bis zur nächsten Funktion auf gleichem Einrückungslevel
    func_body = source[func_start:]
    next_def = func_body.find("\ndef ", 1)
    if next_def != -1:
        func_body = func_body[:next_def]

    assert "ImportError" in func_body, (
        "init_runner_logging fehlt ImportError-Handler für fehlende OTEL-Deps"
    )
    assert "return" in func_body, "kein früher Return-Pfad bei ImportError"
