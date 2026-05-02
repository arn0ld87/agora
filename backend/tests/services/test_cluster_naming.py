"""Tests fuer deterministisches Cluster-Naming (Sub-Slice 14)."""
from __future__ import annotations

from app.services.network_analytics import (
    _CLUSTER_LABEL_STOPWORDS,
    _derive_cluster_label,
)


def _post(agent_id: int, text: str):
    return {"agent_id": agent_id, "post_content": text}


def test_empty_members_returns_cluster_id_fallback():
    assert _derive_cluster_label([], [], cluster_id=7) == "cluster-7"


def test_no_actions_for_members_returns_cluster_id_fallback():
    actions = [_post(99, "etwas anderes")]
    assert _derive_cluster_label([1, 2], actions, cluster_id=3) == "cluster-3"


def test_top_three_tokens_by_frequency():
    actions = [
        _post(1, "alpha alpha alpha"),
        _post(1, "beta beta"),
        _post(2, "gamma"),
        _post(2, "delta delta delta delta"),
    ]
    label = _derive_cluster_label([1, 2], actions)
    # Counts: delta=4, alpha=3, beta=2, gamma=1 → Top-3 = delta, alpha, beta
    assert label == "delta, alpha, beta"


def test_alphabetic_tiebreak():
    actions = [
        _post(1, "zebra zebra apple apple banana banana"),
    ]
    label = _derive_cluster_label([1], actions)
    # Alle 3 mit count=2 → alphabetisch: apple, banana, zebra
    assert label == "apple, banana, zebra"


def test_stopwords_filtered():
    actions = [
        _post(1, "der die das und ist mit thema thema"),
    ]
    label = _derive_cluster_label([1], actions)
    # Nur "thema" ueberlebt
    assert label == "thema"
    for sw in ("der", "die", "und", "ist"):
        assert sw not in label


def test_deterministic():
    actions = [
        _post(1, "alpha beta gamma"),
        _post(2, "alpha beta"),
        _post(3, "alpha"),
    ]
    label1 = _derive_cluster_label([1, 2, 3], actions)
    label2 = _derive_cluster_label([1, 2, 3], actions)
    assert label1 == label2


def test_min_token_length_three():
    actions = [_post(1, "ab cd efg hij")]
    label = _derive_cluster_label([1], actions)
    # "ab"/"cd" sind <3 Zeichen → werden ignoriert; efg+hij gewinnen
    assert "ab" not in label
    assert "efg" in label or "hij" in label


def test_text_fields_all_inspected():
    actions = [
        {"agent_id": 1, "comment_content": "kommentartext kommentartext"},
        {"agent_id": 1, "content": "contenttext"},
    ]
    label = _derive_cluster_label([1], actions)
    assert "kommentartext" in label
    assert "contenttext" in label


def test_stopwords_set_contains_required_words():
    for word in ("der", "die", "und", "ist", "nicht", "mit", "auf", "the", "and", "for", "with", "that"):
        assert word in _CLUSTER_LABEL_STOPWORDS
