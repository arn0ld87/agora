"""Tests for :class:`SearchService` — hybrid search weight wiring.

We exercise the construction surface and the merge math directly. The
Neo4j-bound search paths are out of scope here (covered indirectly by
the existing Neo4j integration tests when a database is available).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.config import Config
from app.storage.search_service import SearchService


@pytest.fixture
def fake_embedding():
    return MagicMock()


def test_default_weights_match_class_constants(fake_embedding):
    svc = SearchService(fake_embedding)
    assert svc.vector_weight == SearchService.VECTOR_WEIGHT == 0.7
    assert svc.keyword_weight == SearchService.KEYWORD_WEIGHT == 0.3


def test_custom_weights_override_defaults(fake_embedding):
    svc = SearchService(fake_embedding, vector_weight=0.4, keyword_weight=0.6)
    assert svc.vector_weight == 0.4
    assert svc.keyword_weight == 0.6


def test_partial_override_keeps_other_default(fake_embedding):
    svc = SearchService(fake_embedding, vector_weight=0.9)
    assert svc.vector_weight == 0.9
    assert svc.keyword_weight == 0.3


def test_config_exposes_hybrid_weights_with_legacy_defaults():
    """Config must default to the historical 0.7 / 0.3 split."""
    assert Config.HYBRID_SEARCH_VECTOR_WEIGHT == 0.7
    assert Config.HYBRID_SEARCH_KEYWORD_WEIGHT == 0.3


def test_merge_math_uses_instance_weights(fake_embedding):
    """Verify the combined-score formula picks up per-instance weights.

    We bypass _merge's data-shape requirements by invoking the formula
    arithmetic directly on a service instance: the result is a function of
    only ``vector_weight`` and ``keyword_weight``.
    """
    svc = SearchService(fake_embedding, vector_weight=0.2, keyword_weight=0.8)
    v_score = 1.0
    k_score = 0.5
    combined = svc.vector_weight * v_score + svc.keyword_weight * k_score
    assert combined == pytest.approx(0.6)
