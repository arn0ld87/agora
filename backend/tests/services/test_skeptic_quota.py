"""Tests für _ensure_skeptic_quota — Slice 5 (Issue #497)."""

import pytest


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


class TestQuotaHoldsForFinalPopulation:
    """Regression: die Quote galt gegen die *urspruengliche* Population.

    ``required = ceil(original_total * min_ratio)`` ignorierte, dass jeder
    hinzugefuegte Skeptiker die Population mitvergroessert. 10 Personas ohne
    Skeptiker bei 20 % ergaben zwei Zusaetze — 2/12 = 16,67 %, nicht 20 %.
    Die Zusage im Docstring ("Erzwingt >= min_ratio Skeptiker im Persona-Set")
    war damit fuer jedes Set verletzt, das ueberhaupt aufgefuellt werden musste.
    """

    @staticmethod
    def _ratio(result) -> float:
        return sum(1 for p in result if p.stance == "opposing") / len(result)

    def test_ten_personas_without_skeptics_reach_twenty_percent(self) -> None:
        personas = [_make_agent(i, "neutral") for i in range(10)]

        result = SimulationConfigGenerator._ensure_skeptic_quota(personas, min_ratio=0.20)

        assert self._ratio(result) >= 0.20
        # 3 Zusaetze: 3/13 = 23,1 % — 2/12 = 16,7 % waere zu wenig.
        assert len(result) == 13

    def test_added_skeptics_are_minimal(self) -> None:
        """Kein Ueberschiessen: ein Zusatz weniger unterschreitet die Quote."""
        personas = [_make_agent(i, "neutral") for i in range(10)]

        result = SimulationConfigGenerator._ensure_skeptic_quota(personas, min_ratio=0.20)

        added = len(result) - len(personas)
        assert (added - 1) / (len(personas) + added - 1) < 0.20

    def test_existing_skeptics_are_counted(self) -> None:
        personas = [_make_agent(i, "opposing" if i < 2 else "neutral") for i in range(10)]

        result = SimulationConfigGenerator._ensure_skeptic_quota(personas, min_ratio=0.40)

        assert self._ratio(result) >= 0.40

    def test_already_satisfied_quota_adds_nothing(self) -> None:
        personas = [_make_agent(i, "opposing" if i < 5 else "neutral") for i in range(10)]

        result = SimulationConfigGenerator._ensure_skeptic_quota(personas, min_ratio=0.20)

        assert result == personas

    def test_small_population(self) -> None:
        personas = [_make_agent(0, "neutral")]

        result = SimulationConfigGenerator._ensure_skeptic_quota(personas, min_ratio=0.20)

        assert self._ratio(result) >= 0.20
        assert len(result) == 2

    def test_zero_ratio_adds_nothing(self) -> None:
        personas = [_make_agent(i, "neutral") for i in range(10)]

        assert SimulationConfigGenerator._ensure_skeptic_quota(personas, min_ratio=0.0) == personas

    @pytest.mark.parametrize("min_ratio", [0.05, 0.1, 0.2, 0.25, 0.33, 0.5, 0.75, 0.9])
    @pytest.mark.parametrize("existing_skeptics", [0, 1, 3])
    def test_quota_holds_across_the_valid_range(
        self, min_ratio: float, existing_skeptics: int
    ) -> None:
        personas = [
            _make_agent(i, "opposing" if i < existing_skeptics else "neutral")
            for i in range(12)
        ]

        result = SimulationConfigGenerator._ensure_skeptic_quota(personas, min_ratio=min_ratio)

        assert self._ratio(result) >= min_ratio

    @pytest.mark.parametrize("min_ratio", [1.0, 1.5])
    def test_unreachable_ratio_terminates_without_infinite_loop(self, min_ratio: float) -> None:
        """``min_ratio >= 1`` ist durch Hinzufuegen nicht erreichbar, solange
        Nicht-Skeptiker im Set stehen. Die Funktion muss trotzdem terminieren
        und ein brauchbares Set zurueckgeben (bestehender Contract)."""
        personas = [_make_agent(i, "neutral") for i in range(10)]

        result = SimulationConfigGenerator._ensure_skeptic_quota(personas, min_ratio=min_ratio)

        assert len(result) >= len(personas)
        assert all(p.stance == "neutral" for p in result[: len(personas)])

    def test_all_opposing_satisfies_ratio_one(self) -> None:
        personas = [_make_agent(i, "opposing") for i in range(4)]

        result = SimulationConfigGenerator._ensure_skeptic_quota(personas, min_ratio=1.0)

        assert result == personas


class TestSyntheticSkepticProfiles:
    """#1779: Die Skeptiker der Quotenregel bekommen nachgelagert ein Profil.

    Die Konfiguration entsteht nach der Persona-Phase. Im Lauf
    ``sim_c8c6b30aa652`` blieben die Agenten 50 bis 53 deshalb ohne Profil,
    existierten in OASIS nicht und schrieben nie.
    """

    @staticmethod
    def _config_with_skeptics(entity_count: int = 10) -> dict:
        from dataclasses import asdict

        personas = [_make_agent(i) for i in range(entity_count)]
        agents = SimulationConfigGenerator._ensure_skeptic_quota(personas, min_ratio=0.20)
        return {
            "simulation_requirement": "Soll der Kreißsaal geschlossen werden?",
            "contested_question": {
                "statement": "Der Kreistag beschließt, den Kreißsaal zu schließen.",
                "origin": "user",
                "absence_reason": None,
            },
            "agent_configs": [asdict(a) for a in agents],
        }

    @staticmethod
    def _entity_profiles(entity_count: int = 10) -> list:
        from app.services.oasis_profile_models import OasisAgentProfile

        return [
            OasisAgentProfile(
                user_id=i, user_name=f"user_{i}", name=f"Agent {i}", bio="Bio", persona="Persona"
            )
            for i in range(entity_count)
        ]

    def test_synthetic_skeptics_get_profiles(self) -> None:
        from app.services.prepare_skeptic_profiles import build_skeptic_profiles

        config = self._config_with_skeptics()
        existing = self._entity_profiles()

        created = build_skeptic_profiles(config, existing, language="de")

        profiles = [*existing, *created]
        assert len(profiles) == len(config["agent_configs"])
        synthetic = [
            c for c in config["agent_configs"] if c["entity_uuid"].startswith("synthetic-skeptic-")
        ]
        assert synthetic, "Die Quotenregel muss Skeptiker ergänzt haben"
        by_user_id = {p.user_id: p for p in created}
        for agent_config in synthetic:
            profile = by_user_id[agent_config["agent_id"]]
            assert profile.source_entity_uuid == agent_config["entity_uuid"]
            assert profile.name == agent_config["entity_name"]
            # Haltung (ablehnend) und Streitfrage stehen im Profiltext.
            assert "ablehnend" in profile.persona
            assert "Kreißsaal" in profile.persona
            assert profile.generation_source == "rule_based"

    def test_profiles_satisfy_the_persona_contract_without_invented_demography(self) -> None:
        from app.contracts.persona_contract import PersonaModel
        from app.services.prepare_skeptic_profiles import build_skeptic_profiles

        created = build_skeptic_profiles(
            self._config_with_skeptics(), self._entity_profiles(), language="de"
        )

        assert created
        for profile in created:
            payload = {
                k: v
                for k, v in profile.to_reddit_format().items()
                if k not in ("created_at", "age", "gender", "mbti")
            }
            payload["user_name"] = payload.pop("username")
            model = PersonaModel.model_validate(payload)
            assert model.persona_kind == "collective"
            assert profile.age is None and profile.gender is None and profile.mbti is None
            assert profile.profession is None

    def test_existing_profile_is_not_duplicated(self) -> None:
        from app.services.prepare_skeptic_profiles import build_skeptic_profiles

        config = self._config_with_skeptics()
        existing = self._entity_profiles()
        first = build_skeptic_profiles(config, existing, language="de")

        assert build_skeptic_profiles(config, [*existing, *first], language="de") == []

    def test_english_language_is_respected(self) -> None:
        from app.services.prepare_skeptic_profiles import build_skeptic_profiles

        created = build_skeptic_profiles(
            self._config_with_skeptics(), self._entity_profiles(), language="en"
        )

        assert created
        assert all("oppose" in p.persona for p in created)

    def test_without_contested_question_the_simulation_requirement_is_referenced(self) -> None:
        from app.services.prepare_skeptic_profiles import build_skeptic_profiles

        config = self._config_with_skeptics()
        config["contested_question"] = {"statement": None, "origin": "none", "absence_reason": None}

        created = build_skeptic_profiles(config, self._entity_profiles(), language="de")

        assert created
        assert all("Soll der Kreißsaal geschlossen werden?" in p.persona for p in created)
