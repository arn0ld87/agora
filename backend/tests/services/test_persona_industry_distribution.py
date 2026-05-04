"""Tests für Destatis-WZ-2008-Default-Branchenverteilung.

Sub-Slice 215 (Issue #215) — Persona-IT-Bias-Fix.

Verifiziert:
- IT-Anteil ≤ 12 % bei 100 Personas (und pools >= 10)
- Mindestens 7 Branchen im Default-Plan
- Summe der targets == total_personas
- Keine Branche > 25 %
- Clamp-Logik bei sehr kleinen Pools (< 7 Personas)
- Prompt-Block enthält WZ-Hinweis
- PersonaQuotaPlan ist valide (Pydantic-Validator)
"""
from __future__ import annotations

import pytest

from app.contracts import PersonaQuotaPlan
from app.services.persona_quota_defaults import (
    _DACH_INDUSTRY_DISTRIBUTION,
    build_industry_quota_prompt_block,
    build_industry_quota_prompt_block_en,
    default_dach_industry_quota,
)


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

IT_LABEL = "Information und Kommunikation (J)"
IT_CAP_PCT = 0.12   # 12 %
MIN_BRANCHES = 7
MAX_SINGLE_BRANCH_PCT = 0.25


# ---------------------------------------------------------------------------
# Hilfsfunktion
# ---------------------------------------------------------------------------

def _it_share(plan: PersonaQuotaPlan) -> float:
    """IT-Anteil als Dezimalzahl (0–1)."""
    it_count = plan.targets.get(IT_LABEL, 0)
    return it_count / plan.total


# ---------------------------------------------------------------------------
# Haupt-Assertions für 100 Personas (die kanonische Spec-Größe)
# ---------------------------------------------------------------------------

class TestDefaultDachIndustryQuota100:
    """Kanonischer Smoke-Test mit total=100."""

    def setup_method(self) -> None:
        self.plan = default_dach_industry_quota(100)

    def test_pydantic_valid(self) -> None:
        """PersonaQuotaPlan muss valide sein (inkl. total==sum(targets))."""
        assert self.plan.total == 100
        assert sum(self.plan.targets.values()) == 100

    def test_it_share_at_most_12_percent(self) -> None:
        """IT-Anteil darf 12 % nicht überschreiten."""
        share = _it_share(self.plan)
        assert share <= IT_CAP_PCT, (
            f"IT-Anteil {share:.1%} überschreitet den Hard-Cap von {IT_CAP_PCT:.0%}. "
            f"Targets: {self.plan.targets}"
        )

    def test_at_least_7_branches(self) -> None:
        """Mindestens 7 verschiedene Branchen im Default-Plan."""
        n = len(self.plan.targets)
        assert n >= MIN_BRANCHES, (
            f"Nur {n} Branchen im Plan — Mindest-Anforderung ist {MIN_BRANCHES}. "
            f"Targets: {self.plan.targets}"
        )

    def test_no_single_branch_above_25_percent(self) -> None:
        """Keine Einzelbranche darf mehr als 25 % der Personas halten."""
        for label, count in self.plan.targets.items():
            share = count / self.plan.total
            assert share <= MAX_SINGLE_BRANCH_PCT, (
                f"Branche '{label}' hat {share:.1%} — überschreitet {MAX_SINGLE_BRANCH_PCT:.0%}. "
                f"Targets: {self.plan.targets}"
            )

    def test_sum_equals_total(self) -> None:
        """Summe der targets muss exakt total ergeben."""
        assert sum(self.plan.targets.values()) == self.plan.total


# ---------------------------------------------------------------------------
# Verschiedene Pool-Größen
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("total", [1, 4, 7, 10, 20, 50, 100, 200, 500])
def test_sum_always_equals_total(total: int) -> None:
    """Für alle gültigen Poolgrößen muss sum(targets) == total gelten."""
    plan = default_dach_industry_quota(total)
    assert sum(plan.targets.values()) == total, (
        f"total={total}: Summe {sum(plan.targets.values())} != {total}. "
        f"Targets: {plan.targets}"
    )


@pytest.mark.parametrize("total", [10, 20, 50, 100, 200, 500])
def test_it_cap_never_exceeded(total: int) -> None:
    """IT-Cap darf für Pools >= 10 Personas nicht überschritten werden.

    Bei total < 10 ist der Cap mathematisch nicht erzwingbar, da schon die
    Largest-Remainder-Methode IT auf 1/total hebt (z. B. 1/4 = 25 %).
    Die Spec gilt für realistische Simulations-Pools (>= 10 Personas).
    """
    plan = default_dach_industry_quota(total)
    share = _it_share(plan)
    assert share <= IT_CAP_PCT + 1e-9, (
        f"total={total}: IT-Anteil {share:.1%} > {IT_CAP_PCT:.0%}. "
        f"Targets: {plan.targets}"
    )


def test_small_pool_clamp_covers_main_branches() -> None:
    """Bei total=4 müssen alle Einträge im Plan mindestens 1 Persona haben."""
    plan = default_dach_industry_quota(4)
    assert sum(plan.targets.values()) == 4
    assert len(plan.targets) >= 1
    for label, count in plan.targets.items():
        assert count >= 1, f"Branche '{label}' hat 0 Personas trotz Clamp."


def test_invalid_total_raises() -> None:
    """total_personas < 1 muss einen ValueError werfen."""
    with pytest.raises(ValueError, match="total_personas"):
        default_dach_industry_quota(0)


def test_total_1_is_valid() -> None:
    """total=1 ist Grenzfall — ein Eintrag mit count=1 muss existieren."""
    plan = default_dach_industry_quota(1)
    assert plan.total == 1
    assert sum(plan.targets.values()) == 1
    assert len(plan.targets) >= 1


# ---------------------------------------------------------------------------
# Prompt-Block-Tests
# ---------------------------------------------------------------------------

def test_prompt_block_contains_wz_reference() -> None:
    """Prompt-Block muss WZ-2008-Referenz enthalten."""
    plan = default_dach_industry_quota(100)
    block = build_industry_quota_prompt_block(plan)
    assert "WZ 2008" in block or "Destatis" in block, (
        "Prompt-Block enthält keine Destatis/WZ-2008-Referenz."
    )


def test_prompt_block_mentions_it_cap() -> None:
    """Prompt-Block muss explizit auf den IT-12%-Cap hinweisen."""
    plan = default_dach_industry_quota(100)
    block = build_industry_quota_prompt_block(plan)
    assert "12" in block, "Prompt-Block erwähnt IT-12%-Cap nicht."
    assert "Information" in block or "IT" in block, (
        "Prompt-Block enthält keinen Hinweis auf IT/Information."
    )


def test_prompt_block_en_contains_wz_reference() -> None:
    """English prompt block must reference WZ 2008."""
    plan = default_dach_industry_quota(100)
    block = build_industry_quota_prompt_block_en(plan)
    assert "WZ 2008" in block or "Destatis" in block


def test_prompt_block_is_string() -> None:
    """Prompt-Block muss ein nicht-leerer String sein."""
    plan = default_dach_industry_quota(50)
    block = build_industry_quota_prompt_block(plan)
    assert isinstance(block, str)
    assert len(block) > 50


# ---------------------------------------------------------------------------
# Verteilungs-Plausibilität
# ---------------------------------------------------------------------------

def test_distribution_entries_count() -> None:
    """_DACH_INDUSTRY_DISTRIBUTION muss mind. 7 Branchen definieren."""
    assert len(_DACH_INDUSTRY_DISTRIBUTION) >= MIN_BRANCHES


def test_distribution_shares_sum_to_one() -> None:
    """Anteile müssen (bis auf Rundungsfehler) auf 1.0 summieren."""
    total_share = sum(share for _, share in _DACH_INDUSTRY_DISTRIBUTION)
    assert abs(total_share - 1.0) < 0.01, (
        f"Summe der Branchenanteile: {total_share:.4f} — sollte 1.0 sein."
    )


def test_it_share_in_distribution_at_most_12_pct() -> None:
    """Der IT-Anteil in _DACH_INDUSTRY_DISTRIBUTION darf ≤ 12 % sein."""
    it_share_raw = next(
        (share for label, share in _DACH_INDUSTRY_DISTRIBUTION if "Information" in label),
        0.0,
    )
    assert it_share_raw <= IT_CAP_PCT, (
        f"IT-Rohanteil {it_share_raw:.1%} überschreitet Hard-Cap {IT_CAP_PCT:.0%}."
    )


def test_pydantic_plan_validates_correctly() -> None:
    """PersonaQuotaPlan-Validator muss für den Default-Plan ohne Exception durchlaufen."""
    plan = default_dach_industry_quota(100)
    revalidated = PersonaQuotaPlan.model_validate(plan.model_dump())
    assert revalidated.total == plan.total
    assert revalidated.targets == plan.targets
