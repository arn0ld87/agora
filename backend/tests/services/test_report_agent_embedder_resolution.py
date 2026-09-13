"""Befund 4 (Review PR #1498): ``resolve_embedder`` liess Konfigurationsfehler
still durchrutschen.

Root Cause: ``resolve_embedder`` (``app/services/report_agent/evidence.py``)
fing vor der Korrektur jede ``Exception`` beim Konstruieren von
``EmbeddingService()`` ab, loggte auf ``debug`` und degradierte auf ``None`` —
eine kaputte *aktive* Embedding-Konfiguration sah damit genauso aus wie ein
schlicht nicht erreichbares Embedding-Backend. Seit
``resolve_active_embedding_route`` (``services/embedding_configurations/runtime.py``,
Issue #1417) einen unmigrierten Modellwechsel ausdruecklich mit
``EmbeddingRuntimeConfigurationError`` ablehnt, ist genau dieser laute Fehler
hier stumm geworden: der Report lief ohne Evidence-Embedding weiter, ohne dass
irgendwo ein Hinweis stand.

Die Korrektur reicht ``EmbeddingRuntimeConfigurationError`` durch, waehrend der
Degradationspfad fuer echte Umgebungsfehler (Backend nicht erreichbar) erhalten
bleibt.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.embedding_configurations.runtime import (
    EmbeddingRuntimeConfigurationError,
)
from app.services.report_agent.evidence import resolve_embedder


class TestResolveEmbedderPropagatesConfigurationErrors:
    def test_embedding_runtime_configuration_error_propagates(self, monkeypatch) -> None:
        """Kernbefund: eine kaputte aktive Konfiguration darf nicht zu ``None``
        degradieren. Unter dem alten Code fing der breite ``except Exception``
        auch ``EmbeddingRuntimeConfigurationError`` ab, loggte sie auf
        ``debug`` und gab ``None`` zurueck — dieser Test waere rot gewesen,
        weil ``pytest.raises`` dann nichts zu fangen gehabt haette."""

        class _RaisesRuntimeConfigError:
            def __init__(self) -> None:
                raise EmbeddingRuntimeConfigurationError(
                    "Die aktive Embedding-Konfiguration passt nicht zum Betriebsindex"
                )

        monkeypatch.setattr(
            "app.storage.embedding_service.EmbeddingService",
            _RaisesRuntimeConfigError,
        )
        fake_logger = MagicMock()

        with pytest.raises(EmbeddingRuntimeConfigurationError):
            resolve_embedder(cached="missing", logger=fake_logger)

        # Der laute Fehler ist gerade der Punkt — er darf nicht nebenbei
        # noch auf debug geloggt und damit doppelt (laut UND leise) behandelt
        # werden.
        fake_logger.debug.assert_not_called()

    def test_ordinary_environment_error_still_degrades_silently_to_none(
        self, monkeypatch
    ) -> None:
        """Gegenprobe: ein gewoehnlicher Umgebungsfehler (Backend nicht
        erreichbar) darf durch die Korrektur NICHT mitverschaerft werden — der
        Report muss weiterhin ohne Evidence-Embedding laufen koennen, statt
        abzubrechen."""

        class _RaisesConnectionError:
            def __init__(self) -> None:
                raise ConnectionError("Ollama nicht erreichbar")

        monkeypatch.setattr(
            "app.storage.embedding_service.EmbeddingService",
            _RaisesConnectionError,
        )
        fake_logger = MagicMock()

        result = resolve_embedder(cached="missing", logger=fake_logger)

        assert result is None
        fake_logger.debug.assert_called_once()

    def test_cached_short_circuit_is_unaffected(self, monkeypatch) -> None:
        """Der cached-Kurzschluss am Funktionsanfang bleibt unberuehrt: ist
        bereits ein Embedder aufgeloest, darf ``EmbeddingService`` gar nicht
        erst konstruiert werden."""

        def _must_not_be_constructed():
            raise AssertionError("EmbeddingService darf bei cached-Treffer nicht gebaut werden")

        monkeypatch.setattr(
            "app.storage.embedding_service.EmbeddingService",
            _must_not_be_constructed,
        )

        def _cached_embedder(text: str) -> list[float]:
            return [0.0]

        result = resolve_embedder(cached=_cached_embedder, logger=MagicMock())

        assert result is _cached_embedder
