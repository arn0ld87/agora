"""Tests für _run_red_team_review — Slice 5 (Issue #497).

LLM-Calls werden vollständig gemockt — kein echter Ollama-Aufruf.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock


from app.contracts.report_v3 import (
    ModelAttribution,
    ReportV3,
)
from app.services.report_agent.workflow import _run_red_team_review


def _make_minimal_report_v3(
    claims: list | None = None,
    model_attribution: list | None = None,
) -> ReportV3:
    return ReportV3(
        report_id="test-report-001",
        generated_at=datetime.now(timezone.utc),
        claims=claims or [],
        model_attribution=model_attribution or [],
    )


def _make_mock_agent(llm_findings: list[str] | None = None) -> MagicMock:
    agent = MagicMock()
    agent.simulation_id = "sim-001"
    agent.llm.provider = "ollama"
    agent.llm.model = "qwen2.5:32b"
    # chat_json gibt immer {"findings": llm_findings} zurück
    agent.llm.chat_json.return_value = {"findings": llm_findings or []}
    return agent


class TestRunRedTeamReview:
    def test_findings_not_empty_when_high_echo_index(self) -> None:
        """red_team_findings ist nicht leer wenn echo_chamber_index > 0.6."""
        findings_payload = [
            "Widerspruch: Claim A behauptet hohe Akzeptanz, Claim B widerspricht.",
            "Verfrühter Konsens: Segment 'Skeptiker' fehlt in Cross-Segment-Analyse.",
        ]
        agent = _make_mock_agent(llm_findings=findings_payload)
        report = _make_minimal_report_v3()

        result = _run_red_team_review(agent, report, echo_index=0.80)

        assert len(result.red_team_findings) == 2
        assert result.red_team_findings[0] == findings_payload[0]

    def test_findings_max_10(self) -> None:
        """red_team_findings darf maximal 10 Einträge haben."""
        # LLM gibt 15 zurück — Funktion kürzt auf 10
        many_findings = [f"Befund {i}" for i in range(15)]
        agent = _make_mock_agent(llm_findings=many_findings)
        report = _make_minimal_report_v3()

        result = _run_red_team_review(agent, report, echo_index=0.80)

        assert len(result.red_team_findings) <= 10

    def test_model_attribution_has_red_team_entry(self) -> None:
        """model_attribution enthält genau einen 'red_team'-Eintrag nach dem Run."""
        agent = _make_mock_agent(llm_findings=["Befund 1"])
        report = _make_minimal_report_v3()

        result = _run_red_team_review(agent, report, echo_index=0.80)

        red_team_attrs = [a for a in result.model_attribution if a.stage == "red_team"]
        assert len(red_team_attrs) == 1
        attr = red_team_attrs[0]
        assert attr.provider == "ollama"
        assert attr.model_id == "qwen2.5:32b"

    def test_balanced_personas_empty_findings(self) -> None:
        """Bei echo_index < 0.3 darf red_team_findings leer sein (kein LLM-Call)."""
        agent = _make_mock_agent(llm_findings=["Sollte nicht aufgerufen werden"])
        report = _make_minimal_report_v3()

        result = _run_red_team_review(agent, report, echo_index=0.25)

        # Bei echo_index <= 0.6 wird kein LLM-Call gemacht
        assert result.red_team_findings == []
        agent.llm.chat_json.assert_not_called()

    def test_exactly_at_echo_threshold_no_call(self) -> None:
        """echo_index=0.6 (Grenzwert) → kein LLM-Call."""
        agent = _make_mock_agent()
        report = _make_minimal_report_v3()

        result = _run_red_team_review(agent, report, echo_index=0.6)

        assert result.red_team_findings == []
        agent.llm.chat_json.assert_not_called()

    def test_llm_failure_returns_empty_findings(self) -> None:
        """Bei LLM-Fehler: findings bleibt leer, kein Exception-Propagation."""
        agent = MagicMock()
        agent.simulation_id = "sim-001"
        agent.llm.provider = "ollama"
        agent.llm.model = "qwen2.5:32b"
        agent.llm.chat_json.side_effect = RuntimeError("Timeout")
        report = _make_minimal_report_v3()

        result = _run_red_team_review(agent, report, echo_index=0.80)

        assert result.red_team_findings == []
        # AttributionEntry trotzdem vorhanden (latency_ms unkritisch)
        assert any(a.stage == "red_team" for a in result.model_attribution)

    def test_existing_attribution_preserved(self) -> None:
        """Bestehende model_attribution-Einträge bleiben erhalten."""
        existing_attr = ModelAttribution(
            stage="report_synthesis",
            provider="ollama",
            model_id="llama3:70b",
        )
        agent = _make_mock_agent(llm_findings=["Befund"])
        report = _make_minimal_report_v3(model_attribution=[existing_attr])

        result = _run_red_team_review(agent, report, echo_index=0.80)

        stages = [a.stage for a in result.model_attribution]
        assert "report_synthesis" in stages
        assert "red_team" in stages
        assert len(result.model_attribution) == 2
