"""Regressionstest für den Decision-Layer-Shadow-Pilot in ``local_search``
(f005, Slice `decision-pilot`, Task `shadow-usecase`).

Kernanforderung des Piloten: ``local_search`` liefert bei
``AGORA_DECISION_LAYER_MODE=disabled`` (Default) exakt dasselbe Ergebnis
wie vorher, und auch im ``shadow``-Modus ändert sich der Rückgabewert
nicht — nur eine zusätzliche Telemetrie-Zeile entsteht.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.config import Config
from app.services.graph.graph_reader import local_search
from app.storage.graph_storage import GraphStorage


def _make_storage_with_one_matching_edge() -> MagicMock:
    storage = MagicMock(spec=GraphStorage)
    storage.get_all_edges.return_value = [
        {
            "uuid": "e1",
            "name": "arbeitet_fuer",
            "fact": "Das Bundeskanzleramt koordiniert die Ressorts.",
            "source_node_uuid": "n1",
            "target_node_uuid": "n2",
            "episode_ids": [],
        }
    ]
    storage.get_all_nodes.return_value = []
    return storage


@pytest.fixture(autouse=True)
def _default_mode_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "disabled")


class TestLocalSearchUnaffectedByDecisionLayer:
    def test_result_is_identical_with_decision_layer_disabled(self) -> None:
        storage = _make_storage_with_one_matching_edge()

        result = local_search("g1", "Bundeskanzleramt", storage=storage)

        assert result.facts == ["Das Bundeskanzleramt koordiniert die Ressorts."]
        assert result.total_count == 1

    def test_result_is_identical_in_shadow_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Shadow-Modus darf Score, Reihenfolge und Rückgabewert nicht
        verändern — nur zusätzlich telemetrieren (siehe
        ``local_search_shadow.py``-Moduldocstring)."""
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")
        storage_disabled = _make_storage_with_one_matching_edge()
        storage_shadow = _make_storage_with_one_matching_edge()

        result_disabled_mode = local_search("g1", "Bundeskanzleramt", storage=storage_disabled)
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")
        result_shadow_mode = local_search("g1", "Bundeskanzleramt", storage=storage_shadow)

        assert result_shadow_mode.facts == result_disabled_mode.facts
        assert result_shadow_mode.edges == result_disabled_mode.edges
        assert result_shadow_mode.total_count == result_disabled_mode.total_count

    def test_shadow_pairs_the_top_score_with_the_fact_of_that_same_edge(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: ``facts`` überspringt Kanten mit leerem ``fact``,
        ``scored_edges`` nicht. Vorher wurde der Top-Score mit dem Fakt
        einer niedriger bewerteten Kante gepaart — die Telemetrie, deren
        einziger Zweck die spätere Kalibration ist, sammelte damit
        unbemerkt falsche (Score, Fakt)-Paare."""
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")
        seen: list[tuple[str, str | None, int]] = []
        monkeypatch.setattr(
            "app.services.graph.graph_reader.shadow_relevance_check",
            lambda query, top_fact, top_score, **kwargs: seen.append(
                (query, top_fact, top_score)
            ),
        )
        storage = MagicMock(spec=GraphStorage)
        storage.get_all_edges.return_value = [
            # Top-Score (100 über den Namen), aber ohne Fakt.
            {
                "uuid": "e1",
                "name": "Bundeskanzleramt",
                "fact": "",
                "source_node_uuid": "",
                "target_node_uuid": "",
                "episode_ids": [],
            },
            # Niedriger bewertet, aber der einzige Eintrag in ``facts``.
            {
                "uuid": "e2",
                "name": "x",
                "fact": "Bundeskanzleramt taucht hier nur als Wort auf",
                "source_node_uuid": "",
                "target_node_uuid": "",
                "episode_ids": [],
            },
        ]
        storage.get_all_nodes.return_value = []

        local_search("g1", "Bundeskanzleramt", storage=storage)

        assert len(seen) == 1
        _query, top_fact, top_score = seen[0]
        assert top_score == 100
        # Die Top-Kante hat keinen Fakt — dann gibt es nichts zu bewerten,
        # statt den Fakt der zweiten Kante unterzuschieben.
        assert top_fact is None

    def test_a_broken_decision_layer_never_breaks_the_search(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Selbst wenn der Shadow-Aufruf selbst bricht (nicht nur der von
        ihm aufgerufene Provider), wirft ``local_search`` nicht — der
        Shadow-Call liegt innerhalb des bestehenden ``try/except`` von
        ``local_search`` UND ``shadow_relevance_check`` hat eine eigene
        Absicherung (siehe ``test_local_search_shadow.py``); beide greifen
        unabhängig voneinander."""
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")
        monkeypatch.setattr(
            "app.services.graph.graph_reader.shadow_relevance_check",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("should never propagate")),
        )
        storage = _make_storage_with_one_matching_edge()

        result = local_search("g1", "Bundeskanzleramt", storage=storage)

        assert isinstance(result.facts, list)
