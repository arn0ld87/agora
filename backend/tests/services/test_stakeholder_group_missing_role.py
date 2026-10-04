"""Issue #1766: Fehlende Rollenangabe ist keine Stakeholder-Gruppe "Unknown".

Befund (Lauf ``report_a8fa9ff9fad0``): 37 von 57 Interview-Evidence-Eintraegen
trugen ``persona_stakeholder_group: "Unknown"``, verteilt auf 31 Agenten. Der
Default-String war nicht leer und blockierte den Fallback in
``ReportAgent._record_tool_evidence``.

Randbedingung ADR-0002 Anker 4: Die Korrektur darf die Zahl unterscheidbarer
Gruppen fuer ``cross_stakeholder_for_high`` nicht erhoehen.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.contracts import (
    ConfidenceLabel,
    EvidenceItemModel,
    EvidenceSourceKind,
    EvidenceType,
    ReportClaimModel,
)
from app.contracts.report_contract import EntailmentVerdict
from app.services.graph.graph_dtos import AgentInterview, InterviewResult
from app.services.graph.interview_helpers import (
    generate_interview_questions,
    generate_interview_summary,
    load_agent_profiles,
    select_agents_for_interview,
)
from app.services.persona_role import (
    NO_ROLE_LABEL,
    display_role,
    normalize_role,
    resolve_stakeholder_group,
)
from app.services.report_agent import ReportAgent
from app.services.report_agent.evidence import init_evidence_map
from app.services.sim import interview_direct


# --------------------------------------------------------------------------
# persona_role: eine Definition von "fehlend"
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [None, "", "   ", "\t\n", "Unknown", "unknown", "UNKNOWN", " Unknown ", "unbekannt", "Unbekannt"],
)
def test_missing_role_values_normalize_to_empty(value: Optional[str]) -> None:
    assert normalize_role(value) == ""
    assert display_role(value) == NO_ROLE_LABEL


def test_real_role_is_kept_and_whitespace_collapsed() -> None:
    assert normalize_role("  Festangestellte   Dozentin ") == "Festangestellte Dozentin"
    assert display_role("Pflegekraft") == "Pflegekraft"


@pytest.mark.parametrize(
    ("role", "family", "expected"),
    [
        ("Pflegekraft", "LocalGovernment", "Pflegekraft"),
        ("", "LocalGovernment", "LocalGovernment"),
        ("Unknown", "LocalGovernment", "LocalGovernment"),
        ("unbekannt", " LocalGovernment ", "LocalGovernment"),
        # Auffangtypen bezeichnen keine Rollenfamilie (report_contract).
        ("", "Organization", NO_ROLE_LABEL),
        ("Unknown", "Person", NO_ROLE_LABEL),
        ("", None, NO_ROLE_LABEL),
        ("", "Unknown", NO_ROLE_LABEL),
    ],
)
def test_resolve_stakeholder_group_chain(
    role: str, family: Optional[str], expected: str
) -> None:
    assert resolve_stakeholder_group(role, family) == expected


# --------------------------------------------------------------------------
# ReportAgent: Interview-Evidence-Item
# --------------------------------------------------------------------------


def _make_agent() -> ReportAgent:
    agent = ReportAgent.__new__(ReportAgent)
    agent.graph_id = "graph_test"
    agent.simulation_id = "sim_test"
    agent.simulation_requirement = "Test-Requirement"
    agent.llm = MagicMock()
    agent.web_tools = MagicMock()
    agent.graph_tools = MagicMock()
    agent.evidence_map = init_evidence_map(
        report_id="report_test", simulation_id="sim_test", global_evidence=[]
    )
    agent._active_section_evidence = []
    agent._active_section_unresolved_evidence = []
    return agent


def _interview_records(interviews: List[AgentInterview]) -> List[Dict[str, Any]]:
    agent = _make_agent()
    agent._record_tool_evidence(
        tool_name="conduct_agent_interview",
        parameters={},
        structured_result=InterviewResult(
            interview_topic="Thema",
            interview_questions=["Frage?"],
            interviews=interviews,
        ),
        rendered_result="",
        section_index=1,
    )
    records = list((agent.evidence_map or {})["evidence_index"].values())
    return [r for r in records if r["type"] == "agent_interview"]


def _interview(
    name: str,
    role: str,
    family: Optional[str] = None,
) -> AgentInterview:
    return AgentInterview(
        agent_name=name,
        agent_role=role,
        agent_role_family=family,
        agent_bio="Bio",
        question="Frage?",
        response=f"Antwort von {name}.",
        key_quotes=[],
    )


def test_collective_persona_without_profession_gets_role_family() -> None:
    (record,) = _interview_records(
        [_interview("Stadtverwaltung Dresden", "", "LocalGovernment")]
    )
    assert record["persona_stakeholder_group"] == "LocalGovernment"
    assert record["persona_role_family"] == "LocalGovernment"


def test_legacy_unknown_role_gets_same_result_as_empty_role() -> None:
    (record,) = _interview_records(
        [_interview("Stadtverwaltung Dresden", "Unknown", "LocalGovernment")]
    )
    assert record["persona_stakeholder_group"] == "LocalGovernment"


def test_real_profession_stays_unchanged() -> None:
    (record,) = _interview_records(
        [_interview("Anna", "Pflegekraft", "LocalGovernment")]
    )
    assert record["persona_stakeholder_group"] == "Pflegekraft"


def test_roleless_persona_without_family_does_not_become_unknown_or_name() -> None:
    records = _interview_records(
        [
            _interview("Ort A", "Unknown", None),
            _interview("Ort B", "", "Organization"),
            _interview("Ort C", "   ", "Person"),
        ]
    )
    groups = {r["persona_stakeholder_group"] for r in records}
    assert groups == {NO_ROLE_LABEL}
    assert "Unknown" not in groups


# --------------------------------------------------------------------------
# ADR-0002 Anker 4: Zahl der Gruppen steigt nicht
# --------------------------------------------------------------------------


def _quote_from_record(record: Dict[str, Any]) -> EvidenceItemModel:
    return EvidenceItemModel(
        type=EvidenceType.agent_interview,
        source="agent-log",
        snippet=record["snippet"],
        quote=record["quote"],
        match_score=0.7,
        entailment=EntailmentVerdict.SUPPORTED,
        supports_claim=True,
        source_kind=EvidenceSourceKind.agent_quote,
        persona_stakeholder_group=record["persona_stakeholder_group"],
        persona_role_family=record["persona_role_family"],
    )


def _high_claim(records: List[Dict[str, Any]]) -> ReportClaimModel:
    return ReportClaimModel(
        claim_id="claim_01",
        claim_text="High-Claim aus rollenlosen Personas.",
        confidence_label=ConfidenceLabel.high,
        confidence_score=0.78,
        evidence=[_quote_from_record(r) for r in records],
    )


@pytest.mark.parametrize(
    "families",
    [
        # Gleiche nicht-generische Familie: family:localgovernment zaehlt einmal.
        ("LocalGovernment", "LocalGovernment"),
        # Generische Familien: beide Titel sind ``ohne Rollenangabe`` -> eine Gruppe.
        ("Organization", "Organization"),
        ("Organization", "Person"),
        (None, "Organization"),
    ],
)
def test_two_roleless_personas_do_not_count_as_two_groups(
    families: tuple[Optional[str], Optional[str]],
) -> None:
    records = _interview_records(
        [
            _interview("Ort A", "", families[0]),
            _interview("Ort B", "Unknown", families[1]),
        ]
    )
    assert len(records) == 2
    with pytest.raises(ValidationError, match="2 unterschiedlichen Stakeholder-Rollenfamilien"):
        _high_claim(records)


def test_roleless_persona_with_distinct_families_still_counts_as_two() -> None:
    """Gegenprobe: kontrollierte, verschiedene Familien bleiben zwei Gruppen."""
    records = _interview_records(
        [
            _interview("Ort A", "", "LocalGovernment"),
            _interview("Firma B", "", "Company"),
        ]
    )
    assert _high_claim(records).confidence_label == ConfidenceLabel.high


# --------------------------------------------------------------------------
# Quelle: kein "Unknown" aus graph_tools / interview_helpers
# --------------------------------------------------------------------------


def test_twitter_csv_profiles_carry_no_unknown_profession(tmp_path: Path) -> None:
    sim_dir = tmp_path / "uploads" / "simulations" / "sim_csv"
    sim_dir.mkdir(parents=True)
    with open(sim_dir / "twitter_profiles.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["name", "username", "description", "user_char"])
        writer.writerow(["Stadt Dresden", "stadt_dd", "Verwaltung", "Persona"])
    service_dir = tmp_path / "app" / "services"
    service_dir.mkdir(parents=True)
    # ``load_agent_profiles`` loest ``<service_dir>/../../uploads/...`` auf.
    profiles = load_agent_profiles("sim_csv", service_dir=str(service_dir))
    assert len(profiles) == 1
    assert profiles[0]["profession"] == ""
    assert "Unknown" not in json.dumps(profiles)


def _llm_returning(payload: Dict[str, Any]) -> MagicMock:
    llm = MagicMock()
    llm.chat_json.return_value = payload
    llm.chat.return_value = "Zusammenfassung."
    return llm


def _prompt_text(call: Any) -> str:
    return "\n".join(m["content"] for m in call.kwargs["messages"])


def test_prompts_use_neutral_label_for_missing_profession() -> None:
    profiles = [{"realname": "Ort A", "username": "ort_a", "bio": "x"}]

    llm = _llm_returning({"selected_indices": [0], "reasoning": "r"})
    select_agents_for_interview(profiles, "Frage", "Kontext", 3, llm)
    selection_prompt = _prompt_text(llm.chat_json.call_args)
    assert "Unknown" not in selection_prompt
    assert NO_ROLE_LABEL in selection_prompt

    llm = _llm_returning({"questions": ["a?", "b?", "c?"]})
    generate_interview_questions("Frage", "Kontext", [{"realname": "Ort A", "profession": ""}], llm)
    question_prompt = _prompt_text(llm.chat_json.call_args)
    assert "Unknown" not in question_prompt
    assert NO_ROLE_LABEL in question_prompt


def test_summary_prompt_has_no_empty_parentheses_or_unknown() -> None:
    llm = _llm_returning({})
    generate_interview_summary([_interview("Ort A", "")], "Frage", llm)
    prompt = "\n".join(m["content"] for m in llm.chat.call_args.kwargs["messages"])
    assert "()" not in prompt
    assert "Unknown" not in prompt
    assert f"Ort A ({NO_ROLE_LABEL})" in prompt


def test_to_text_shows_neutral_label_for_missing_role() -> None:
    text = _interview("Ort A", "").to_text()
    assert f"**Ort A** ({NO_ROLE_LABEL})" in text
    assert "()" not in text
    assert "None" not in text


def test_interview_agents_leaves_missing_profession_empty() -> None:
    from app.services.graph_tools import GraphToolsService

    svc = GraphToolsService.__new__(GraphToolsService)
    svc._llm_client = MagicMock()
    svc._llm_client.chat_json.return_value = {
        "selected_indices": [0],
        "reasoning": "Testauswahl",
        "questions": ["Wie bewerten Sie das Angebot?"],
    }
    svc._llm_client.chat.return_value = "Zusammenfassung."
    svc._load_agent_profiles = MagicMock(
        return_value=[
            {
                "realname": "Stadtverwaltung Dresden",
                "username": "stadt_dd",
                "bio": "Verwaltung",
                "source_entity_type": "LocalGovernment",
            }
        ]
    )
    api_success = {
        "success": True,
        "interviews_count": 1,
        "result": {
            "results": {
                "reddit_0": {
                    "response": "Die Verwaltung sieht das Angebot grundsaetzlich positiv."
                }
            }
        },
        "timestamp": "2026-10-04T00:00:00Z",
    }
    store = MagicMock()
    store.read_json.side_effect = lambda simulation_id, name, default=None: (
        [{"user_id": 1, "username": "stadt_dd", "name": "Stadtverwaltung Dresden"}]
        if name == "reddit_profiles"
        else default
    )
    with patch(
        "app.services.simulation_runner.SimulationRunner.check_env_alive",
        return_value=False,
    ), patch(
        "app.services.sim.interview_client.check_env_alive", return_value=False
    ), patch.object(interview_direct, "_store", return_value=store), patch(
        "app.services.simulation_runner.SimulationRunner.interview_agents_batch",
        return_value=api_success,
    ):
        result = svc.interview_agents(
            simulation_id="sim_1766",
            interview_requirement="Wie bewerten Sie das Angebot?",
            simulation_requirement="Kontext",
            max_agents=1,
        )

    assert result.interviews, result
    interview = result.interviews[0]
    assert interview.agent_role == ""
    assert interview.agent_role_family == "LocalGovernment"
    assert resolve_stakeholder_group(interview.agent_role, interview.agent_role_family) == "LocalGovernment"
    assert "Unknown" not in json.dumps(interview.to_dict())
