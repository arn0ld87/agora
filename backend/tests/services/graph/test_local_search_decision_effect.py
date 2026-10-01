"""Regressionstest für die Wirkung des Decision-Layer-Verdikts auf
``local_search`` im Modus ``authoritative`` (f001, Slice `search-effect`).

Abgrenzung zu den Nachbartests:
- ``test_local_search_decision_shadow.py`` deckt ``disabled``/``shadow`` ab
  (Ergebnis bleibt dort unverändert) sowie die Fehlertoleranz und die
  run_id-Weiterleitung.
- ``tests/services/decisions/test_local_search_relevance.py`` deckt
  ``resolve_relevance`` selbst ab (Jev/Rule-Rückfall, Budget, Logging).

Dieser Test injiziert ``resolve_relevance`` direkt (wie der Shadow-Test) und
prüft nur, was ``local_search`` mit dem zurückgegebenen ``DecisionResult``
tut.
"""

from __future__ import annotations

from typing import Optional
from unittest.mock import MagicMock

import pytest

from app.config import Config
from app.contracts.decision_contract import DecisionResult
from app.services.graph.graph_reader import local_search
from app.storage.graph_storage import GraphStorage


def _decision_result(
    *,
    provider: str = "jev",
    probability_yes: Optional[float] = 1.0,
    shadow: bool = False,
    fallback_chain: Optional[list[str]] = None,
) -> DecisionResult:
    return DecisionResult(
        use_case_id="local-search-relevance",
        provider=provider,  # type: ignore[arg-type]
        answer=None,
        probability_yes=probability_yes,
        confidence=1.0,
        cost_micros=0,
        latency_ms=0,
        shadow=shadow,
        fallback_chain=fallback_chain or [provider],
    )


def _make_storage_with_two_matching_edges() -> MagicMock:
    """Zwei Kanten, die beide über die Query matchen — die zweite bleibt in
    jedem Szenario unangetastet, damit Filterung nicht versehentlich alles
    trifft."""
    storage = MagicMock(spec=GraphStorage)
    storage.get_all_edges.return_value = [
        {
            "uuid": "top-edge",
            "name": "Bundeskanzleramt",
            "fact": "Das Bundeskanzleramt koordiniert die Ressorts.",
            "source_node_uuid": "n1",
            "target_node_uuid": "n2",
            "episode_ids": [],
        },
        {
            "uuid": "second-edge",
            "name": "x",
            "fact": "Bundeskanzleramt taucht hier auch auf.",
            "source_node_uuid": "n3",
            "target_node_uuid": "n4",
            "episode_ids": [],
        },
    ]
    storage.get_all_nodes.return_value = []
    return storage


@pytest.fixture
def authoritative_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "authoritative")


def _patch_resolve_relevance(monkeypatch: pytest.MonkeyPatch, decision: Optional[DecisionResult]) -> None:
    monkeypatch.setattr(
        "app.services.graph.graph_reader.resolve_relevance",
        lambda *args, **kwargs: decision,
    )


class TestAuthoritativeIrrelevant:
    def test_top_fact_removed_from_facts_and_edges(
        self, authoritative_mode: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_resolve_relevance(
            monkeypatch, _decision_result(provider="jev", probability_yes=0.2)
        )
        storage = _make_storage_with_two_matching_edges()

        result = local_search("g1", "Bundeskanzleramt", storage=storage)

        assert result.facts == ["Bundeskanzleramt taucht hier auch auf."]
        assert [edge["uuid"] for edge in result.edges] == ["second-edge"]
        assert result.total_count == 1

    def test_relevance_field_reflects_the_verdict(
        self, authoritative_mode: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_resolve_relevance(
            monkeypatch, _decision_result(provider="jev", probability_yes=0.2)
        )
        storage = _make_storage_with_two_matching_edges()

        result = local_search("g1", "Bundeskanzleramt", storage=storage)

        assert result.relevance == {
            "top_fact_relevant": False,
            "provider": "jev",
            "probability_yes": 0.2,
            "fallback": False,
        }

    def test_exactly_the_scored_top_edge_is_removed_not_a_text_duplicate(
        self, authoritative_mode: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Zwei Kanten mit identischem Fakt-Text, aber unterschiedlichem
        Score (über ``name``): entfernt werden darf nur die tatsächlich
        bewertete Top-Kante (Identität über ``uuid``), nicht die andere mit
        demselben Fakt-Text.

        Query hat zwei Keywords, damit die Scores sich unterscheiden
        (``match_score`` ist bei einem einzelnen Keyword sonst binär 0/100,
        siehe ``graph_reader.py::match_score``): Die exakte Phrase
        "bundeskanzleramt koordination" im Namen von ``top-edge`` trifft den
        100er-Volltreffer, "bundeskanzleramt" allein im Namen von
        ``duplicate-text-edge`` nur den 10er-Keyword-Treffer.
        """
        _patch_resolve_relevance(
            monkeypatch, _decision_result(provider="jev", probability_yes=0.1)
        )
        storage = MagicMock(spec=GraphStorage)
        storage.get_all_edges.return_value = [
            {
                "uuid": "top-edge",
                "name": "Bundeskanzleramt Koordination",
                "fact": "Derselbe Text.",
                "source_node_uuid": "n1",
                "target_node_uuid": "n2",
                "episode_ids": [],
            },
            {
                "uuid": "duplicate-text-edge",
                "name": "Bundeskanzleramt only",
                "fact": "Derselbe Text.",
                "source_node_uuid": "n3",
                "target_node_uuid": "n4",
                "episode_ids": [],
            },
        ]
        storage.get_all_nodes.return_value = []

        result = local_search("g1", "Bundeskanzleramt Koordination", storage=storage)

        assert [edge["uuid"] for edge in result.edges] == ["duplicate-text-edge"]
        assert result.facts == ["Derselbe Text."]

    def test_result_can_become_empty(
        self, authoritative_mode: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_resolve_relevance(
            monkeypatch, _decision_result(provider="jev", probability_yes=0.0)
        )
        storage = MagicMock(spec=GraphStorage)
        storage.get_all_edges.return_value = [
            {
                "uuid": "only-edge",
                "name": "Bundeskanzleramt",
                "fact": "Das Bundeskanzleramt koordiniert die Ressorts.",
                "source_node_uuid": "n1",
                "target_node_uuid": "n2",
                "episode_ids": [],
            }
        ]
        storage.get_all_nodes.return_value = []

        result = local_search("g1", "Bundeskanzleramt", storage=storage)

        assert result.facts == []
        assert result.edges == []
        assert result.total_count == 0
        assert result.relevance == {
            "top_fact_relevant": False,
            "provider": "jev",
            "probability_yes": 0.0,
            "fallback": False,
        }

    def test_fact_of_another_edge_is_never_removed_when_top_edge_has_no_fact(
        self, authoritative_mode: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Top-Kante matcht nur über ``name`` und hat keinen Fakt —
        ``facts[0]`` gehört dann zur zweiten Kante. Selbst wenn (entgegen dem
        heutigen ``resolve_relevance``) ein Irrelevanz-Verdikt käme, darf
        dieser fremde Fakt nicht verschwinden."""
        _patch_resolve_relevance(
            monkeypatch, _decision_result(provider="jev", probability_yes=0.0)
        )
        storage = MagicMock(spec=GraphStorage)
        storage.get_all_edges.return_value = [
            {
                "uuid": "top-edge",
                "name": "Bundeskanzleramt Koordination",
                "fact": "",
                "source_node_uuid": "n1",
                "target_node_uuid": "n2",
                "episode_ids": [],
            },
            {
                "uuid": "fact-edge",
                "name": "x",
                "fact": "Bundeskanzleramt taucht hier auf.",
                "source_node_uuid": "n3",
                "target_node_uuid": "n4",
                "episode_ids": [],
            },
        ]
        storage.get_all_nodes.return_value = []

        result = local_search("g1", "Bundeskanzleramt Koordination", storage=storage)

        assert result.facts == ["Bundeskanzleramt taucht hier auf."]
        assert result.total_count == 1

    def test_no_decision_when_limit_excludes_every_edge(
        self, authoritative_mode: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``limit=0``: die Top-Kante steht nicht im Ergebnis — kein
        Decision-Aufruf (kein Jev-Call) und kein ``relevance``-Verdikt über
        einen Treffer, den der Aufrufer nie sieht."""
        calls: list[tuple] = []

        def _recording(*args: object, **kwargs: object) -> DecisionResult:
            calls.append(args)
            return _decision_result(provider="jev", probability_yes=0.0)

        monkeypatch.setattr("app.services.graph.graph_reader.resolve_relevance", _recording)
        storage = _make_storage_with_two_matching_edges()

        result = local_search("g1", "Bundeskanzleramt", storage=storage, limit=0)

        assert calls == []
        assert result.relevance is None
        assert result.facts == []
        assert "relevance" not in result.to_dict()


class TestAuthoritativeRelevant:
    def test_nothing_is_removed_and_relevance_marks_it_relevant(
        self, authoritative_mode: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_resolve_relevance(
            monkeypatch, _decision_result(provider="jev", probability_yes=0.9)
        )
        storage = _make_storage_with_two_matching_edges()

        result = local_search("g1", "Bundeskanzleramt", storage=storage)

        assert result.facts == [
            "Das Bundeskanzleramt koordiniert die Ressorts.",
            "Bundeskanzleramt taucht hier auch auf.",
        ]
        assert [edge["uuid"] for edge in result.edges] == ["top-edge", "second-edge"]
        assert result.total_count == 2
        assert result.relevance == {
            "top_fact_relevant": True,
            "provider": "jev",
            "probability_yes": 0.9,
            "fallback": False,
        }

    def test_probability_exactly_at_threshold_counts_as_relevant(
        self, authoritative_mode: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_resolve_relevance(
            monkeypatch, _decision_result(provider="jev", probability_yes=0.5)
        )
        storage = _make_storage_with_two_matching_edges()

        result = local_search("g1", "Bundeskanzleramt", storage=storage)

        assert result.total_count == 2
        assert result.relevance["top_fact_relevant"] is True


class TestAuthoritativeRuleFallback:
    def test_relevance_reports_rule_provider_and_fallback_true(
        self, authoritative_mode: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_resolve_relevance(
            monkeypatch,
            _decision_result(
                provider="rule",
                probability_yes=0.1,
                fallback_chain=["jev", "rule"],
            ),
        )
        storage = _make_storage_with_two_matching_edges()

        result = local_search("g1", "Bundeskanzleramt", storage=storage)

        assert result.relevance == {
            "top_fact_relevant": False,
            "provider": "rule",
            "probability_yes": 0.1,
            "fallback": True,
        }
        assert [edge["uuid"] for edge in result.edges] == ["second-edge"]


class TestAuthoritativeNoVerdict:
    def test_none_leaves_the_result_unchanged(
        self, authoritative_mode: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Erschöpfte Fallback-Kette (Jev UND Rule scheitern) -> ``None``.
        Byte-gleich zu einem Lauf ganz ohne Decision Layer."""
        _patch_resolve_relevance(monkeypatch, None)
        storage_authoritative = _make_storage_with_two_matching_edges()
        storage_reference = _make_storage_with_two_matching_edges()
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "disabled")
        reference = local_search("g1", "Bundeskanzleramt", storage=storage_reference)
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "authoritative")

        result = local_search("g1", "Bundeskanzleramt", storage=storage_authoritative)

        assert result.facts == reference.facts
        assert result.edges == reference.edges
        assert result.total_count == reference.total_count
        assert result.relevance is None
        assert result.to_dict() == reference.to_dict()
        assert result.to_text() == reference.to_text()


class TestShadowAndDisabledByteIdenticalSerialization:
    """shadow/disabled: Ergebnis UND Serialisierung (to_dict/to_text) exakt
    gleich wie ganz ohne Decision Layer — verglichen gegen eine
    Referenzausgabe, nicht nur gegen sich selbst."""

    def test_disabled_matches_reference_without_decision_layer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "disabled")
        storage = _make_storage_with_two_matching_edges()
        reference_storage = _make_storage_with_two_matching_edges()

        result = local_search("g1", "Bundeskanzleramt", storage=storage)
        reference = local_search("g1", "Bundeskanzleramt", storage=reference_storage)

        assert result.to_dict() == reference.to_dict()
        assert result.to_text() == reference.to_text()
        assert "relevance" not in result.to_dict()
        assert result.relevance is None

    def test_shadow_matches_reference_without_decision_layer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")
        storage = _make_storage_with_two_matching_edges()
        reference_storage = _make_storage_with_two_matching_edges()

        result = local_search("g1", "Bundeskanzleramt", storage=storage)
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "disabled")
        reference = local_search("g1", "Bundeskanzleramt", storage=reference_storage)

        assert result.to_dict() == reference.to_dict()
        assert result.to_text() == reference.to_text()
        assert "relevance" not in result.to_dict()
        assert result.relevance is None

    def test_shadow_with_a_real_authoritative_like_verdict_still_stays_untouched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Selbst wenn (hypothetisch) ein ``shadow=True``-Ergebnis mit
        niedriger ``probability_yes`` zurückkäme, darf das im shadow-Modus
        nichts entfernen — ``_apply_relevance_verdict`` wirkt nur bei
        ``shadow is False``."""
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "shadow")
        _patch_resolve_relevance(
            monkeypatch,
            _decision_result(provider="rule", probability_yes=0.0, shadow=True),
        )
        storage = _make_storage_with_two_matching_edges()
        reference_storage = _make_storage_with_two_matching_edges()

        result = local_search("g1", "Bundeskanzleramt", storage=storage)
        monkeypatch.setattr(Config, "DECISION_LAYER_MODE", "disabled")
        reference = local_search("g1", "Bundeskanzleramt", storage=reference_storage)

        assert result.to_dict() == reference.to_dict()
        assert result.relevance is None
