"""Sub-Slice 05.6 — Interview-Tool gibt terminal-Hint bei toter Sim.

Vorher: `result.summary` endete mit "Please ensure the OASIS environment is
running" — verleitete den ReACT-Loop, interview_agents immer wieder zu rufen,
bis die max-iteration-Grenze erreicht war und Force-Generate griff.

Jetzt: Early-Check vor LLM-Calls + klarer Terminal-Hint, der das Modell auf
insight_forge / panorama_search / quick_search umleitet.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.graph.graph_dtos import InterviewResult


class TestInterviewEarlyCheck:
    """Sim-Status wird vor jedem teuren LLM-Call geprüft."""

    def _make_service(self):
        from app.services.graph_tools import GraphToolsService
        svc = GraphToolsService.__new__(GraphToolsService)
        svc.llm_client = MagicMock()
        return svc

    def test_sim_dead_returns_terminal_soft_fail_before_llm_call(self):
        """Bei check_env_alive == False: keine LLM-Calls, sofort Soft-Fail."""
        svc = self._make_service()

        with patch(
            "app.services.simulation_runner.SimulationRunner.check_env_alive",
            return_value=False,
        ):
            result = svc.interview_agents(
                simulation_id="sim_dead_xyz",
                interview_requirement="Wie bewerten Sie X?",
                simulation_requirement="Kontext",
                max_agents=5,
            )

        assert isinstance(result, InterviewResult)
        assert result.interviewed_count == 0
        assert "TERMINALLY UNAVAILABLE" in result.summary, (
            f"Summary muss terminal markiert sein, bekommen: {result.summary!r}"
        )
        assert "Do NOT call interview_agents again" in result.summary, (
            "LLM braucht eine klare Anweisung, das Tool nicht erneut zu rufen"
        )
        assert "insight_forge" in result.summary, "Alternativen-Hint fehlt"

        # _select_agents_for_interview macht LLM-Calls — darf NICHT angesprungen
        # worden sein, sonst hat der Slice nichts gebracht.
        svc.llm_client.chat.assert_not_called()
        svc.llm_client.chat_json.assert_not_called()

    def test_sim_alive_proceeds_to_profile_load(self):
        """Bei alive sim: Pfad geht durch zu _load_agent_profiles (nicht durch dieses Test
        getrieben — wir checken nur, dass NICHT der Early-Exit-Branch zieht).
        """
        svc = self._make_service()
        svc._load_agent_profiles = MagicMock(return_value=[])  # leer → other branch

        with patch(
            "app.services.simulation_runner.SimulationRunner.check_env_alive",
            return_value=True,
        ):
            result = svc.interview_agents(
                simulation_id="sim_alive_abc",
                interview_requirement="Topic",
                simulation_requirement="Ctx",
                max_agents=5,
            )

        assert isinstance(result, InterviewResult)
        # _load_agent_profiles MUSS angesprochen worden sein
        svc._load_agent_profiles.assert_called_once_with("sim_alive_abc")
        # Summary darf NICHT den Terminal-Marker tragen
        assert "TERMINALLY UNAVAILABLE" not in result.summary


class TestInterviewSoftFailMessages:
    """Die drei Soft-Fail-Pfade nutzen alle den Terminal-Hint statt
    'please ensure ... running' (was zu Retry-Loops führte).
    """

    def test_early_exit_message_format(self):
        """Early-Exit-Message hat Terminal-Marker + alle drei Alternativen."""
        svc = TestInterviewEarlyCheck._make_service(TestInterviewEarlyCheck())

        with patch(
            "app.services.simulation_runner.SimulationRunner.check_env_alive",
            return_value=False,
        ):
            result = svc.interview_agents(
                simulation_id="sim_x",
                interview_requirement="t",
                simulation_requirement="ctx",
            )

        msg = result.summary
        assert "TERMINALLY UNAVAILABLE" in msg
        assert "Do NOT call interview_agents again" in msg
        for alternative in ("insight_forge", "panorama_search", "quick_search"):
            assert alternative in msg, f"Alternative {alternative} fehlt im Hint"

    def test_no_retry_hint_in_summary(self):
        """Wichtigste Anti-Regression: kein 'please ensure ... running'-String."""
        svc = TestInterviewEarlyCheck._make_service(TestInterviewEarlyCheck())

        with patch(
            "app.services.simulation_runner.SimulationRunner.check_env_alive",
            return_value=False,
        ):
            result = svc.interview_agents(
                simulation_id="sim_x",
                interview_requirement="t",
                simulation_requirement="ctx",
            )

        retry_phrases = (
            "Please ensure",
            "please ensure",
            "may be closed",  # alter String — heute terminal, nicht "may"
        )
        for phrase in retry_phrases:
            assert phrase not in result.summary, (
                f"{phrase!r} darf NICHT mehr im Soft-Fail stehen — verleitet "
                f"LLM zu Retry-Loops"
            )
