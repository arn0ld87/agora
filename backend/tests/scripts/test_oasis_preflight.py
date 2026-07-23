"""Tests für ``preflight_model_probe``: ein einzelner Chat-Completion-Probe
vor dem OASIS-Agenten-Fan-out.

Verifiziert die beiden Akzeptanzkriterien aus dem OASIS-404-Fix:
- permanenter Provider-Fehler (404) wird mit ``ValueError`` abgelehnt, statt
  den Fan-out mit N identischen Fehlern laufen zu lassen;
- der Probe ruft ``model.run`` genau einmal (kein eigener Fan-out, kein
  Mehrfach-Call bei dauerhaftem Fehler).
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