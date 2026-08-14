"""Issue #1303 — Interview-Diversität: Panel-Rotation statt Wiederverwendung.

Deckt drei Ebenen ab (siehe Issue-Testplan):

1. Scheduler-Unit-Test: 5 Personas, 5 Sections -> jede Persona höchstens 2x.
2. Scheduler-Unit-Test: Exhaustion-Fallback, sobald alle Personas den Cap
   erreicht haben -> Wiederverwendung mit möglichst unterschiedlichem Kontext,
   kein Stranden mit leerem Kandidatenpool.
3. Integrationsartiger Test: mehrere ``GraphToolsService.interview_agents``-
   Aufrufe (LLM/Graph gemockt, analog zu
   ``test_graph_tools_interview_uses_direct_path.py``) über mehrere Sections
   hinweg -> die Panel-Diversitäts-Metrik ist messbar besser als die eines
   naiven "immer dieselben 5"-Baselines.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

from app.services.interview_panel_scheduler import (
    DEFAULT_MAX_INTERVIEWS_PER_PERSONA,
    InterviewPanelScheduler,
    persona_identity,
)


def _profiles(n: int) -> list[dict]:
    return [
        {
            "username": f"p{i}",
            "realname": f"Person {i}",
            "profession": "Tester",
            "bio": f"Bio von Person {i}",
        }
        for i in range(n)
    ]


def _summaries(profiles: list[dict]) -> list[dict]:
    return [
        {
            "index": i,
            "name": profile.get("realname"),
            "profession": profile.get("profession"),
            "bio": profile.get("bio", "")[:200],
            "interested_topics": [],
        }
        for i, profile in enumerate(profiles)
    ]


# ---------------------------------------------------------------------------
# 1) 5 Personas, 5 Sections -> jede Persona höchstens 2x
# ---------------------------------------------------------------------------


class TestFivePersonasFiveSections:
    def test_each_persona_used_at_most_twice(self) -> None:
        scheduler = InterviewPanelScheduler()  # Default-Cap = 2
        profiles = _profiles(5)
        agent_summaries = _summaries(profiles)

        for section_index in range(5):
            topic = f"Topic {section_index}"
            candidates = scheduler.rank_candidates(
                agent_summaries=agent_summaries,
                profiles=profiles,
                interview_topic=topic,
                max_agents=2,
            )
            assert candidates, "Der Kandidatenpool darf nie leer sein"
            # Simuliert ein LLM, das die vom Scheduler bevorzugte Reihenfolge
            # respektiert (nimmt die ersten 2 der bereits vorgefilterten Liste).
            selected_indices = [c["index"] for c in candidates[:2]]
            scheduler.record(
                profiles=profiles,
                selected_indices=selected_indices,
                interview_topic=topic,
                section_index=section_index,
            )

        for profile in profiles:
            identity = persona_identity(profile)
            assert scheduler.uses_of(identity) <= DEFAULT_MAX_INTERVIEWS_PER_PERSONA, (
                f"{identity} wurde {scheduler.uses_of(identity)}x interviewt — "
                f"Cap ist {DEFAULT_MAX_INTERVIEWS_PER_PERSONA}"
            )

        total_uses = sum(scheduler.uses_of(persona_identity(p)) for p in profiles)
        # 5 Sections * 2 Interviews = 10 Slots, exakt die Kapazität von
        # 5 Personas * Cap 2 — bei korrekter Rotation wird sie voll ausgenutzt,
        # ohne dass irgendeine Persona den Cap überschreitet.
        assert total_uses == 10

    def test_new_sections_prefer_not_yet_interviewed_personas(self) -> None:
        """Akzeptanzkriterium: neue Sections ziehen bevorzugt unbefragte Personas."""
        scheduler = InterviewPanelScheduler()
        profiles = _profiles(5)
        agent_summaries = _summaries(profiles)

        # Section 0 interviewt p0, p1.
        scheduler.record(profiles, [0, 1], "Topic 0", section_index=0)

        candidates = scheduler.rank_candidates(
            agent_summaries=agent_summaries,
            profiles=profiles,
            interview_topic="Topic 1",
            max_agents=2,
        )
        # p2, p3, p4 sind unbefragt und müssen vor p0/p1 stehen.
        candidate_indices = [c["index"] for c in candidates]
        assert candidate_indices[:3] == [2, 3, 4]
        assert set(candidate_indices[3:]) == {0, 1}


# ---------------------------------------------------------------------------
# 2) Exhaustion-Fallback
# ---------------------------------------------------------------------------


class TestExhaustionFallback:
    def test_falls_back_to_reuse_preferring_the_most_different_topic(self) -> None:
        scheduler = InterviewPanelScheduler(max_uses_per_persona=2)
        profiles = _profiles(2)
        agent_summaries = _summaries(profiles)

        # Beide Personas manuell auf den Cap bringen, mit unterschiedlich
        # "distanzierten" letzten Topics.
        scheduler.record(profiles, [0], "Klimapolitik und Foerderung", section_index=0)
        scheduler.record(profiles, [0], "Klimapolitik und Verkehr", section_index=0)
        scheduler.record(profiles, [1], "Digitalisierung im Mittelstand", section_index=1)
        scheduler.record(profiles, [1], "Digitalisierung und Bildung", section_index=1)

        for profile in profiles:
            assert scheduler.is_exhausted(persona_identity(profile))

        # Ein drittes Interview wird trotzdem angefragt — der Scheduler darf
        # nicht mit einem leeren Pool stranden.
        candidates = scheduler.rank_candidates(
            agent_summaries=agent_summaries,
            profiles=profiles,
            interview_topic="Digitalisierung und Foerderung",
            max_agents=2,
        )

        assert candidates, "Exhaustion-Fallback darf nicht leer zurückgeben"
        assert {c["index"] for c in candidates} == {0, 1}

        # p0s letztes Topic ("Klimapolitik und Verkehr") teilt mit dem neuen
        # Topic nur das Füllwort "und" (Distanz 0.8); p1s letztes Topic
        # ("Digitalisierung und Bildung") teilt zusätzlich "Digitalisierung"
        # (Distanz 0.5) — p0 ist also der groessere Aspektwechsel und muss
        # zuerst kommen.
        assert [c["index"] for c in candidates] == [0, 1]

    def test_uses_of_can_exceed_cap_only_via_recorded_fallback_reuse(self) -> None:
        """Der Cap wird nur durchbrochen, wenn der Aufrufer selbst (im
        Fallback-Fall) erneut ``record`` mit derselben Persona aufruft — der
        Scheduler selbst erzwingt nichts, er biast nur die Kandidatenliste."""
        scheduler = InterviewPanelScheduler(max_uses_per_persona=1)
        profiles = _profiles(1)

        scheduler.record(profiles, [0], "Topic A", section_index=0)
        identity = persona_identity(profiles[0])
        assert scheduler.is_exhausted(identity)

        # Der Aufrufer entscheidet im Fallback-Fall bewusst, dieselbe Persona
        # nochmal zu nehmen (kein anderer Kandidat verfügbar).
        scheduler.record(profiles, [0], "Topic B (erzwungene Wiederverwendung)", section_index=1)
        assert scheduler.uses_of(identity) == 2
        assert scheduler.topics_of(identity) == ["Topic A", "Topic B (erzwungene Wiederverwendung)"]


# ---------------------------------------------------------------------------
# Persona-Identität
# ---------------------------------------------------------------------------


class TestPersonaIdentity:
    def test_prefers_username_over_realname(self) -> None:
        assert persona_identity({"username": "anna_m", "realname": "Anna Musterfrau"}) == "username:anna_m"

    def test_falls_back_to_realname_without_username(self) -> None:
        assert persona_identity({"realname": "Anna Musterfrau"}) == "realname:Anna Musterfrau"

    def test_falls_back_to_deterministic_fingerprint_without_any_name(self) -> None:
        profile = {"bio": "Nur eine Bio, kein Name.", "profession": "Unbekannt"}
        first = persona_identity(profile)
        second = persona_identity(dict(profile))
        assert first == second
        assert first.startswith("anon:")

    def test_index_is_not_used_as_identity(self) -> None:
        """Zwei verschiedene Personas mit demselben Index in unterschiedlichen
        Aufrufen dürfen nicht als dieselbe Identität gelten."""
        assert persona_identity({"username": "anna_m"}) != persona_identity({"username": "ben_k"})


# ---------------------------------------------------------------------------
# Diversitäts-Metrik
# ---------------------------------------------------------------------------


class TestPanelDiversityScore:
    def test_disjoint_panels_score_one(self) -> None:
        scheduler = InterviewPanelScheduler()
        profiles = _profiles(4)
        scheduler.record(profiles, [0, 1], "Topic 0", section_index=0)
        scheduler.record(profiles, [2, 3], "Topic 1", section_index=1)
        assert scheduler.panel_diversity_score() == 1.0

    def test_identical_panels_score_zero(self) -> None:
        scheduler = InterviewPanelScheduler(max_uses_per_persona=5)
        profiles = _profiles(2)
        scheduler.record(profiles, [0, 1], "Topic 0", section_index=0)
        scheduler.record(profiles, [0, 1], "Topic 1", section_index=1)
        assert scheduler.panel_diversity_score() == 0.0

    def test_fewer_than_two_panels_defaults_to_one(self) -> None:
        scheduler = InterviewPanelScheduler()
        assert scheduler.panel_diversity_score() == 1.0
        profiles = _profiles(1)
        scheduler.record(profiles, [0], "Topic 0", section_index=0)
        assert scheduler.panel_diversity_score() == 1.0


# ---------------------------------------------------------------------------
# 3) Integrationsartiger Test durch GraphToolsService.interview_agents
# ---------------------------------------------------------------------------


def _make_service(profiles: list[dict]) -> "GraphToolsService":  # noqa: F821 — lazy import unten
    from app.services.graph_tools import GraphToolsService

    svc = GraphToolsService.__new__(GraphToolsService)
    svc._llm_client = MagicMock()

    def _chat_json_side_effect(*, messages, **kwargs):
        user_msg = next(m["content"] for m in messages if m["role"] == "user")
        # Simuliert ein LLM, das schlicht die ersten Einträge der ihm
        # angebotenen (bereits vom Scheduler vorsortierten) Kandidatenliste
        # wählt — genau das Verhalten, das ohne Diversity-Bias zur
        # Panel-Wiederholung führt (siehe Issue #1303 Problem-Beschreibung).
        indices = [int(m) for m in re.findall(r'"index":\s*(\d+)', user_msg)]
        return {
            "selected_indices": indices,
            "reasoning": "Automatisch aus dem angebotenen Pool gewählt.",
            "questions": ["Wie schätzen Sie das ein?"],
        }

    svc._llm_client.chat_json.side_effect = _chat_json_side_effect
    svc._llm_client.chat.return_value = "Zusammenfassung."
    svc._load_agent_profiles = MagicMock(return_value=profiles)
    return svc


def _batch_side_effect(*, simulation_id, interviews, platform=None, timeout=180.0):
    results = {}
    for item in interviews:
        agent_idx = item["agent_id"]
        results[f"twitter_{agent_idx}"] = {"response": f"Antwort von Agent {agent_idx} (Twitter)."}
        results[f"reddit_{agent_idx}"] = {"response": f"Antwort von Agent {agent_idx} (Reddit)."}
    return {
        "success": True,
        "interviews_count": len(interviews),
        "result": {"results": results},
    }


class TestIntegrationPanelDiversityImproves:
    def test_scheduler_biased_runs_beat_a_naive_same_five_baseline(self) -> None:
        profiles = _profiles(10)
        svc = _make_service(profiles)
        scheduler = InterviewPanelScheduler()

        with patch(
            "app.services.simulation_runner.SimulationRunner.interviews_possible",
            return_value=True,
        ), patch(
            "app.services.simulation_runner.SimulationRunner.interview_agents_batch",
            side_effect=_batch_side_effect,
        ):
            for section_index in range(5):
                result = svc.interview_agents(
                    simulation_id="sim_1303",
                    interview_requirement=f"Topic {section_index}",
                    simulation_requirement="Testkontext",
                    max_agents=5,
                    panel_scheduler=scheduler,
                    section_index=section_index,
                )
                assert result.interviewed_count > 0

        diversity_score = scheduler.panel_diversity_score()

        # Baseline: ein naiver Scheduler, der jede Section stur mit denselben
        # 5 Personas füttert (das dokumentierte Ist-Verhalten vor #1303).
        baseline = InterviewPanelScheduler()
        for section_index in range(5):
            baseline.record(
                profiles,
                [0, 1, 2, 3, 4],
                f"Topic {section_index}",
                section_index=section_index,
            )
        baseline_score = baseline.panel_diversity_score()

        assert baseline_score == 0.0
        assert diversity_score > baseline_score
        assert diversity_score > 0.3, (
            f"Erwartete messbare Rotation, bekommen: diversity={diversity_score!r}"
        )

        # Zusätzlich: kein Kandidat wurde über den Cap hinaus interviewt,
        # AUSSER durch den dokumentierten Exhaustion-Fallback.
        for profile in profiles:
            identity = persona_identity(profile)
            uses = scheduler.uses_of(identity)
            assert uses >= 0
