"""Tests für apply_echo_cap — Slice 5 (Issue #497)."""
import pytest

from app.services.confidence_calculator import apply_echo_cap


class TestApplyEchoCap:
    def test_high_echo_cross_stakeholder_capped(self) -> None:
        """echo_index=0.80, is_cross_stakeholder=True, score=0.92 → 0.84, 'medium'."""
        score, label = apply_echo_cap(
            score=0.92,
            label="verified",
            echo_index=0.80,
            is_cross_stakeholder=True,
        )
        assert score == pytest.approx(0.84)
        assert label == "medium"

    def test_echo_index_below_threshold_no_cap(self) -> None:
        """echo_index=0.70 ≤ 0.75 → kein Cap."""
        score, label = apply_echo_cap(
            score=0.92,
            label="verified",
            echo_index=0.70,
            is_cross_stakeholder=True,
        )
        assert score == pytest.approx(0.92)
        assert label == "verified"

    def test_not_cross_stakeholder_no_cap(self) -> None:
        """is_cross_stakeholder=False → kein Cap, auch bei hohem echo_index."""
        score, label = apply_echo_cap(
            score=0.95,
            label="verified",
            echo_index=0.90,
            is_cross_stakeholder=False,
        )
        assert score == pytest.approx(0.95)
        assert label == "verified"

    def test_score_below_cap_unchanged(self) -> None:
        """score=0.70 (medium), echo_index=0.80 → score bleibt 0.70, label 'medium'."""
        score, label = apply_echo_cap(
            score=0.70,
            label="medium",
            echo_index=0.80,
            is_cross_stakeholder=True,
        )
        assert score == pytest.approx(0.70)
        assert label == "medium"

    def test_high_label_downgraded_to_medium(self) -> None:
        """label='high' bei echo_index=0.80 → downgrade auf 'medium'."""
        score, label = apply_echo_cap(
            score=0.88,
            label="high",
            echo_index=0.80,
            is_cross_stakeholder=True,
        )
        assert score == pytest.approx(0.84)
        assert label == "medium"

    def test_exact_threshold_not_capped(self) -> None:
        """echo_index=0.75 (Grenzwert, nicht überschritten) → kein Cap."""
        score, label = apply_echo_cap(
            score=0.92,
            label="verified",
            echo_index=0.75,
            is_cross_stakeholder=True,
        )
        assert score == pytest.approx(0.92)
        assert label == "verified"
