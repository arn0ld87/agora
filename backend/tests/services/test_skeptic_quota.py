"""Tests für _ensure_skeptic_quota — Slice 5 (Issue #497)."""


from app.services.simulation_config_generator import (
    AgentActivityConfig,
    SimulationConfigGenerator,
)


def _make_agent(agent_id: int, stance: str = "neutral") -> AgentActivityConfig:
    return AgentActivityConfig(
        agent_id=agent_id,
        entity_uuid=f"uuid-{agent_id}",
        entity_name=f"Agent {agent_id}",
        entity_type="Person",
        stance=stance,
    )


class TestEnsureSkepticQuota:
    def test_no_skeptics_adds_required(self) -> None:
        """10 Personas ohne Skeptiker → nach _ensure_skeptic_quota ≥ 2 skeptisch."""
        personas = [_make_agent(i, "neutral") for i in range(10)]
        result = SimulationConfigGenerator._ensure_skeptic_quota(personas, min_ratio=0.20)
        skeptic_count = sum(1 for p in result if p.stance == "opposing")
        assert skeptic_count >= 2

    def test_sufficient_skeptics_unchanged(self) -> None:
        """10 Personas mit 5 Skeptikern → Liste bleibt gleich (Quote schon ok)."""
        personas = [_make_agent(i, "opposing" if i < 5 else "neutral") for i in range(10)]
        result = SimulationConfigGenerator._ensure_skeptic_quota(personas, min_ratio=0.20)
        # Original 5 Skeptiker + keine neuen → exakt 5
        skeptic_count = sum(1 for p in result if p.stance == "opposing")
        assert skeptic_count == 5
        assert len(result) == len(personas)

    def test_synthetic_skeptics_are_valid(self) -> None:
        """Generierte Skeptiker erfüllen Pflichtfelder von AgentActivityConfig."""
        personas = [_make_agent(i) for i in range(10)]
        result = SimulationConfigGenerator._ensure_skeptic_quota(personas, min_ratio=0.20)
        synthetics = result[10:]  # nur die neuen
        assert synthetics, "Es müssen synthetische Skeptiker generiert worden sein"
        for s in synthetics:
            assert s.stance == "opposing"
            assert s.agent_id >= 10
            assert s.entity_uuid.startswith("synthetic-skeptic-")
            assert isinstance(s.activity_level, float)
            assert 0.0 <= s.activity_level <= 1.0
            assert s.sentiment_bias < 0  # Skeptiker haben negativen Bias

    def test_empty_list_returns_empty(self) -> None:
        """Leere Liste bleibt leer."""
        result = SimulationConfigGenerator._ensure_skeptic_quota([], min_ratio=0.20)
        assert result == []

    def test_exactly_one_needed(self) -> None:
        """5 Personas, 0 Skeptiker, min_ratio=0.20 → math.ceil(1.0)=1 Skeptiker."""
        personas = [_make_agent(i) for i in range(5)]
        result = SimulationConfigGenerator._ensure_skeptic_quota(personas, min_ratio=0.20)
        skeptic_count = sum(1 for p in result if p.stance == "opposing")
        assert skeptic_count >= 1
