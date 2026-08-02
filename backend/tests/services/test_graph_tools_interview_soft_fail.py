"""Sub-Slice 05.6 / Issue #999 — Interview-Tool gibt terminal-Hint bei toter Sim.

Ursprünglich (05.6): `result.summary` endete mit "Please ensure the OASIS
environment is running" — verleitete den ReACT-Loop, interview_agents immer
wieder zu rufen, bis die max-iteration-Grenze erreicht war und Force-Generate
griff. Fix: Early-Check vor LLM-Calls + klarer Terminal-Hint, der das Modell
auf insight_forge / panorama_search / quick_search umleitet.

Issue #999: der Early-Check prüfte bis dahin ausschließlich die IPC-Liveness
(`check_env_alive`), die für jede abgeschlossene Simulation `False` ist — der
Normalzustand eines Report-Laufs. Der Soft-Fail griff dadurch bei praktisch
jedem Interview, obwohl der Direktpfad (persistierte Personas) in aller Regel
funktioniert. Der Gate-Check fragt jetzt `interviews_possible` (IPC ODER
Direktpfad) ab; ein Soft-Fail ist nur noch terminal, wenn BEIDE Pfade fehlen.
Die Fehlermeldung nennt jetzt die konkrete Ursache statt des pauschalen
"TERMINALLY UNAVAILABLE"-Markers.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.graph.graph_dtos import InterviewResult


class TestInterviewEarlyCheck:
    """Ein Interview wird vor jedem teuren LLM-Call auf Beantwortbarkeit geprüft."""

    def _make_service(self):
        from app.services.graph_tools import GraphToolsService
        svc = GraphToolsService.__new__(GraphToolsService)
        # Produktivcode liest self._llm_client (via die self.llm-Property) —
        # nicht ein Attribut namens "llm_client". Ein Mock unter dem falschen
        # Namen wuerde die Kostenschutz-Invariante ungetestet lassen (#999).
        svc._llm_client = MagicMock()
        return svc

    def test_sim_dead_returns_terminal_soft_fail_before_llm_call(self):
        """Bei IPC tot UND Direktpfad nicht verfügbar: keine LLM-Calls, sofort Soft-Fail."""
        svc = self._make_service()

        with patch(
            "app.services.sim.interview_client.check_env_alive",
            return_value=False,
        ), patch(
            "app.services.sim.interview_client.direct_interviews_available",
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
        assert (
            "neither a running simulation worker nor persisted agent personas"
            in result.summary
        ), f"Summary muss die konkrete Ursache nennen, bekommen: {result.summary!r}"
        assert "Do NOT call interview_agents again" in result.summary, (
            "LLM braucht eine klare Anweisung, das Tool nicht erneut zu rufen"
        )
        assert "insight_forge" in result.summary, "Alternativen-Hint fehlt"

        # _select_agents_for_interview macht LLM-Calls — darf NICHT angesprungen
        # worden sein, sonst hat der Slice nichts gebracht.
        svc._llm_client.chat.assert_not_called()
        svc._llm_client.chat_json.assert_not_called()

    def test_sim_alive_proceeds_to_profile_load(self):
        """Bei beantwortbarem Interview: Pfad geht durch zu _load_agent_profiles (nicht
        von diesem Test getrieben — wir checken nur, dass NICHT der Early-Exit-Branch zieht).
        """
        svc = self._make_service()
        svc._load_agent_profiles = MagicMock(return_value=[])  # leer → other branch

        with patch(
            "app.services.simulation_runner.SimulationRunner.interviews_possible",
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
        # Summary darf NICHT den Early-Exit-Hinweis tragen
        assert "neither a running simulation worker" not in result.summary


class TestInterviewSoftFailMessages:
    """Die drei Soft-Fail-Pfade nutzen alle den Terminal-Hint statt
    'please ensure ... running' (was zu Retry-Loops führte).
    """

    def test_early_exit_message_format(self):
        """Early-Exit-Message nennt die konkrete Ursache + alle drei Alternativen."""
        svc = TestInterviewEarlyCheck._make_service(TestInterviewEarlyCheck())

        with patch(
            "app.services.sim.interview_client.check_env_alive",
            return_value=False,
        ), patch(
            "app.services.sim.interview_client.direct_interviews_available",
            return_value=False,
        ):
            result = svc.interview_agents(
                simulation_id="sim_x",
                interview_requirement="t",
                simulation_requirement="ctx",
            )

        msg = result.summary
        assert "neither a running simulation worker nor persisted agent personas" in msg
        assert "Do NOT call interview_agents again" in msg
        for alternative in ("insight_forge", "panorama_search", "quick_search"):
            assert alternative in msg, f"Alternative {alternative} fehlt im Hint"

    def test_no_retry_hint_in_summary(self):
        """Wichtigste Anti-Regression: kein 'please ensure ... running'-String."""
        svc = TestInterviewEarlyCheck._make_service(TestInterviewEarlyCheck())

        with patch(
            "app.services.sim.interview_client.check_env_alive",
            return_value=False,
        ), patch(
            "app.services.sim.interview_client.direct_interviews_available",
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
