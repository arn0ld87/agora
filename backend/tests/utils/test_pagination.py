"""Tests für den clamp_int-Helper in app.utils.pagination.

Baustein C — Hardening PR 5
"""
from __future__ import annotations


from app.utils.pagination import clamp_int, DEFAULT_LIMIT, MAX_LIMIT


class TestClampInt:
    def test_clamp_int_returns_default_when_none(self):
        result = clamp_int(None, default=100, minimum=1, maximum=500)
        assert result == 100

    def test_clamp_int_clamps_to_max(self):
        result = clamp_int(10000, default=100, minimum=1, maximum=500)
        assert result == 500

    def test_clamp_int_clamps_to_min(self):
        result = clamp_int(0, default=100, minimum=1, maximum=500)
        assert result == 1

    def test_clamp_int_clamps_negative_to_min(self):
        result = clamp_int(-5, default=100, minimum=1, maximum=500)
        assert result == 1

    def test_clamp_int_passes_through_valid_range(self):
        result = clamp_int(250, default=100, minimum=1, maximum=500)
        assert result == 250

    def test_clamp_int_passes_through_boundary_min(self):
        result = clamp_int(1, default=100, minimum=1, maximum=500)
        assert result == 1

    def test_clamp_int_passes_through_boundary_max(self):
        result = clamp_int(500, default=100, minimum=1, maximum=500)
        assert result == 500

    def test_default_limit_and_max_limit_constants(self):
        assert DEFAULT_LIMIT == 100
        assert MAX_LIMIT == 500
