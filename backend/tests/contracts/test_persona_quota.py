"""Contract-Tests für persona_contract.py — Quoten-Vertrag."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.persona_contract import (
    PersonaModel,
    PersonaQuotaActual,
    PersonaQuotaPlan,
)


# ---- PersonaQuotaPlan ----

def test_plan_total_must_match_sum():
    with pytest.raises(ValidationError, match="inkonsistent"):
        PersonaQuotaPlan(targets={"a": 2, "b": 3}, total=10)


def test_plan_consistent_passes():
    plan = PersonaQuotaPlan(
        targets={
            "kmu_ceo": 8,
            "it_admin": 6,
            "msp_decider": 5,
            "recruiter": 5,
            "educator": 5,
            "devops_peer": 5,
            "security_sensitive": 4,
            "school_related": 4,
            "solo_agency": 4,
            "non_target": 4,
            "multiplier_ihk": 1,
            "multiplier_hwk": 1,
            "multiplier_training": 1,
            "multiplier_community": 1,
        },
        total=54,
    )
    assert plan.total == 54


# ---- PersonaQuotaActual ----

def test_actual_within_zero_tolerance():
    plan = PersonaQuotaPlan(targets={"kmu": 8, "admin": 6}, total=14)
    PersonaQuotaActual(
        plan=plan,
        actual_counts={"kmu": 8, "admin": 6},
        tolerance=0,
    )


def test_actual_outside_tolerance_rejected():
    plan = PersonaQuotaPlan(targets={"kmu": 8, "admin": 6}, total=14)
    with pytest.raises(ValidationError, match="Toleranz"):
        PersonaQuotaActual(
            plan=plan,
            actual_counts={"kmu": 5, "admin": 6},
            tolerance=0,
        )


def test_unknown_segment_rejected():
    plan = PersonaQuotaPlan(targets={"kmu": 8}, total=8)
    with pytest.raises(ValidationError, match="Unbekannte Segmente"):
        PersonaQuotaActual(
            plan=plan,
            actual_counts={"kmu": 8, "ghost_segment": 3},
            tolerance=0,
        )


def test_tolerance_allows_drift():
    plan = PersonaQuotaPlan(targets={"kmu": 8, "admin": 6}, total=14)
    PersonaQuotaActual(
        plan=plan,
        actual_counts={"kmu": 7, "admin": 7},
        tolerance=1,
    )


# ---- PersonaModel ----

def test_persona_minimum_fields():
    p = PersonaModel(
        user_id=1,
        user_name="alice_dev",
        name="Alice Beispiel",
        bio="Erfahrene Entwicklerin aus Berlin.",
        persona="x" * 300,
    )
    assert p.user_id == 1


def test_persona_username_pattern():
    with pytest.raises(ValidationError):
        PersonaModel(
            user_id=1,
            user_name="Alice Dev",  # Leerzeichen verboten
            name="Alice",
            bio="Bio Bio Bio",
            persona="x" * 300,
        )


def test_persona_persona_min_length():
    with pytest.raises(ValidationError):
        PersonaModel(
            user_id=1,
            user_name="alice",
            name="Alice Test",
            bio="Bio Bio Bio",
            persona="zu kurz",  # < 300
        )
