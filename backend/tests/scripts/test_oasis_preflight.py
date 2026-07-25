"""Tests für ``preflight_model_probe``: ein einzelner Chat-Completion-Probe
vor dem OASIS-Agenten-Fan-out.

Verifiziert die beiden Akzeptanzkriterien aus dem OASIS-404-Fix:
- permanenter Provider-Fehler (404) wird mit ``ValueError`` abgelehnt, statt
  den Fan-out mit N identischen Fehlern laufen zu lassen;
- der Probe ruft ``model.run`` genau einmal (kein eigener Fan-out, kein
  Mehrfach-Call bei dauerhaftem Fehler).

Zusätzlich (Issue #871): der Probe ist per ``AGORA_SKIP_PREFLIGHT=1`` per Opt-out
deaktivierbar, damit die Simulation ohne erreichbares Ollama starten kann.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import openai
import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import _sim_common  # noqa: E402
from _sim_common import preflight_model_probe  # noqa: E402


def _make_openai_error(status_code: int, message: str = "boom") -> openai.APIStatusError:
    """Baut eine ``openai.APIStatusError`` mit gesetztem ``status_code``.

    Der reale Konstruktor verlangt ein Response-Objekt; für den Probe reicht
    ein Mock, der ``status_code`` und eine Message exponiert, wie es
    ``preflight_model_probe`` über ``getattr(exc, "status_code", None)`` liest.
    """
    response = MagicMock()
    response.status_code = status_code
    exc = openai.APIStatusError.__new__(openai.APIStatusError)
    exc.status_code = status_code  # type: ignore[attr-defined]
    exc.message = message  # type: ignore[attr-defined]
    exc.response = response  # type: ignore[attr-defined]
    exc.body = None  # type: ignore[attr-defined]
    exc.request = None  # type: ignore[attr-defined]
    return exc


class TestPreflightPermanentErrors:
    def test_permanent_404_raises_value_error_before_fanout(self) -> None:
        """Ein permanenter 404 (``model MiniMax-M3 not found``) muss den Probe
        mit einer klaren Root-Cause-``ValueError`` abbrechen — kein Retry,
        kein Fan-out."""
        model = MagicMock()
        model.run.side_effect = _make_openai_error(404, "model MiniMax-M3 not found")

        with pytest.raises(ValueError, match="404"):
            preflight_model_probe(model, max_retries=3)

        assert model.run.call_count == 1, (
            "Permanenter 404 darf nicht retried werden — genau ein Probe-Call."
        )

    def test_permanent_401_raises_value_error(self) -> None:
        model = MagicMock()
        model.run.side_effect = _make_openai_error(401, "invalid api key")

        with pytest.raises(ValueError, match="401"):
            preflight_model_probe(model, max_retries=3)

        assert model.run.call_count == 1

    def test_permanent_403_raises_value_error(self) -> None:
        model = MagicMock()
        model.run.side_effect = _make_openai_error(403, "forbidden")

        with pytest.raises(ValueError, match="403"):
            preflight_model_probe(model, max_retries=3)

        assert model.run.call_count == 1


class TestPreflightRunsOnce:
    def test_successful_probe_calls_run_exactly_once(self) -> None:
        """Ein erfolgreicher Probe ruft ``model.run`` genau einmal auf und
        kehrt ohne Exception zurück — kein Mehrfach-Probe, kein Fan-out."""
        model = MagicMock()
        model.run.return_value = MagicMock(name="ChatMessage")

        preflight_model_probe(model, max_retries=3)

        assert model.run.call_count == 1
        # Probe-Nachricht ist ein einzelner User-"ping".
        sent = model.run.call_args.args[0]
        assert isinstance(sent, list) and len(sent) == 1
        assert sent[0]["role"] == "user"

    def test_transient_429_retries_then_succeeds_within_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Transiente Fehler (429) werden mit Backoff retried; nach endlich
        vielen Versuchen läuft der Probe erfolgreich — und insgesamt öfter
        als einmal, aber nur weil der Retry-Policy es so vorsieht."""
        monkeypatch.setattr("_sim_common.time.sleep", lambda _s: None)
        model = MagicMock()
        model.run.side_effect = [
            _make_openai_error(429, "rate limit"),
            MagicMock(name="ok"),
        ]

        preflight_model_probe(model, max_retries=3, backoff_base=0.0)

        assert model.run.call_count == 2

    def test_transient_500_exhausts_retries_then_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Bleibt der transiente Fehler dauerhaft, erschöpft der Probe die
        Retries und schlägt mit ``ValueError`` fehl — kein endloser Fan-out."""
        monkeypatch.setattr("_sim_common.time.sleep", lambda _s: None)
        model = MagicMock()
        model.run.side_effect = _make_openai_error(500, "server error")

        with pytest.raises(ValueError):
            preflight_model_probe(model, max_retries=2, backoff_base=0.0)

        assert model.run.call_count == 3  # 1 initial + 2 retries


class TestPreflightSkipSwitch:
    """Issue #871: ``AGORA_SKIP_PREFLIGHT=1`` entkoppelt den Sim-Start von der
    Ollama-/Provider-Verfügbarkeit (Opt-out, Default off → Probe läuft)."""

    def test_default_probes_model_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default (ENV nicht gesetzt) → Probe wird ausgeführt, ``model.run`` genau einmal."""
        monkeypatch.delenv("AGORA_SKIP_PREFLIGHT", raising=False)
        model = MagicMock()
        model.run.return_value = MagicMock(name="ok")

        preflight_model_probe(model, max_retries=3)

        assert model.run.call_count == 1, (
            "Ohne AGORA_SKIP_PREFLIGHT muss der Probe ausgeführt werden."
        )

    def test_skip_env_skips_probe_and_warns(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """``AGORA_SKIP_PREFLIGHT=1`` → Probe wird übersprungen, ``model.run``
        nie aufgerufen, Warnung geloggt."""
        monkeypatch.setenv("AGORA_SKIP_PREFLIGHT", "1")
        model = MagicMock()

        with caplog.at_level("WARNING", logger="agora._sim_common"):
            preflight_model_probe(model, max_retries=3)

        assert model.run.call_count == 0, (
            "Bei gesetztem AGORA_SKIP_PREFLIGHT darf model.run nicht aufgerufen werden."
        )
        assert any(
            "preflight probe skipped via AGORA_SKIP_PREFLIGHT" in r.getMessage()
            and r.levelname == "WARNING"
            for r in caplog.records
        ), "Skip muss eine WARNUNG mit dem dokumentierten Wortlaut loggen."

    def test_skip_helper_reads_env_lazily(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``_should_skip_preflight`` liest ENV live — Änderung zur Laufzeit
        wird respektiert (kein Modul-Level-Cache des Werts)."""
        monkeypatch.delenv("AGORA_SKIP_PREFLIGHT", raising=False)
        assert _sim_common._should_skip_preflight() is False
        monkeypatch.setenv("AGORA_SKIP_PREFLIGHT", "1")
        assert _sim_common._should_skip_preflight() is True
        monkeypatch.setenv("AGORA_SKIP_PREFLIGHT", "0")
        assert _sim_common._should_skip_preflight() is False
