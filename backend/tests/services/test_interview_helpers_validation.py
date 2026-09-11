"""Regression: der Interviewpfad haelt kaputte Eingaben am Rand auf.

Vor dem Fix reichte ``load_agent_profiles`` den rohen ``json.load``-Rueckgabewert
durch und ``select_agents_for_interview``/``generate_interview_questions``
uebernahmen die LLM-Antwort ungeprueft. Die Fehler fielen erst viel spaeter an,
ohne Bezug zur Ursache.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import pytest

from app.services.graph import interview_helpers as mod


def _service_dir(tmp_path, simulation_id: str):
    """Baut den Pfad, den ``load_agent_profiles`` aus ``service_dir`` ableitet."""
    sim_dir = tmp_path / "uploads" / "simulations" / simulation_id
    sim_dir.mkdir(parents=True)
    service_dir = tmp_path / "app" / "services"
    service_dir.mkdir(parents=True)
    return str(service_dir), sim_dir


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"profiles": []}, id="wrapped-object"),
        pytest.param([None], id="null-element"),
        pytest.param(["invalid"], id="string-element"),
        pytest.param([123], id="int-element"),
    ],
)
def test_structurally_invalid_profile_file_yields_no_profiles(tmp_path, payload) -> None:
    service_dir, sim_dir = _service_dir(tmp_path, "sim_0123456789ab")
    (sim_dir / "reddit_profiles.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    profiles = mod.load_agent_profiles("sim_0123456789ab", service_dir=service_dir)

    # Kontrolliert leer statt "Liste von irgendwas": der Aufrufer meldet
    # "No Agent profile files found for interview" und erfindet nichts.
    assert profiles == []


def test_valid_profile_file_is_returned_unchanged(tmp_path) -> None:
    service_dir, sim_dir = _service_dir(tmp_path, "sim_0123456789ab")
    payload: List[Dict[str, Any]] = [
        {"username": "maria", "name": "Maria Koch", "bio": "Elternvertreterin"}
    ]
    (sim_dir / "reddit_profiles.json").write_text(json.dumps(payload), encoding="utf-8")

    profiles = mod.load_agent_profiles("sim_0123456789ab", service_dir=service_dir)

    # Keine Normalisierung: nicht gesetzte Felder duerfen NICHT als None
    # materialisiert werden, sonst bricht die realname->username-Fallbackkette.
    assert profiles == payload
    assert "realname" not in profiles[0]


def test_invalid_profile_file_falls_back_to_twitter_csv(tmp_path) -> None:
    service_dir, sim_dir = _service_dir(tmp_path, "sim_0123456789ab")
    (sim_dir / "reddit_profiles.json").write_text('{"profiles": []}', encoding="utf-8")
    (sim_dir / "twitter_profiles.csv").write_text(
        "name,username,description,user_char\nMaria,maria,Bio,Persona\n",
        encoding="utf-8",
    )

    profiles = mod.load_agent_profiles("sim_0123456789ab", service_dir=service_dir)

    assert [p["username"] for p in profiles] == ["maria"]
    assert os.path.exists(os.path.join(str(sim_dir), "twitter_profiles.csv"))


class _Llm:
    def __init__(self, response: Any) -> None:
        self._response = response
        self.schemas: List[Any] = []

    def chat_json(self, **kwargs: Any) -> Any:
        self.schemas.append(kwargs.get("schema"))
        return self._response


_PROFILES = [
    {"username": f"agent_{i}", "profession": "Lehrkraft", "bio": "Bio"} for i in range(5)
]


@pytest.mark.parametrize(
    "response",
    [
        pytest.param({"selected_indices": [True]}, id="bool-index"),
        pytest.param({"selected_indices": [1, 1]}, id="duplicate-index"),
        pytest.param({"selected_indices": ["1"]}, id="string-index"),
        pytest.param({"selected_indices": [99]}, id="out-of-range"),
    ],
)
def test_invalid_selection_response_falls_back_to_default_panel(response) -> None:
    selected, indices, reasoning = mod.select_agents_for_interview(
        profiles=_PROFILES,
        interview_requirement="Wie wirkt die Massnahme?",
        simulation_requirement="",
        max_agents=3,
        llm=_Llm(response),
    )

    assert indices == [0, 1, 2]
    assert selected == _PROFILES[:3]
    assert reasoning == "Using default selection strategy"


def test_valid_selection_response_is_honoured_and_schema_is_passed() -> None:
    from app.contracts.interview_contract import InterviewAgentSelection

    llm = _Llm({"selected_indices": [0, 2, 4], "reasoning": "Breite Sicht."})

    selected, indices, reasoning = mod.select_agents_for_interview(
        profiles=_PROFILES,
        interview_requirement="Wie wirkt die Massnahme?",
        simulation_requirement="",
        max_agents=5,
        llm=llm,
    )

    assert indices == [0, 2, 4]
    assert selected == [_PROFILES[0], _PROFILES[2], _PROFILES[4]]
    assert reasoning == "Breite Sicht."
    assert llm.schemas == [InterviewAgentSelection]


@pytest.mark.parametrize(
    "response",
    [
        pytest.param({"questions": None}, id="null"),
        pytest.param({"questions": "Warum?"}, id="bare-string"),
        pytest.param({"questions": [None]}, id="null-element"),
        pytest.param({"questions": []}, id="empty"),
    ],
)
def test_invalid_question_response_falls_back_to_default_questions(response) -> None:
    questions = mod.generate_interview_questions(
        interview_requirement="Wie wirkt die Massnahme?",
        simulation_requirement="",
        selected_agents=_PROFILES[:2],
        llm=_Llm(response),
    )

    assert isinstance(questions, list)
    assert len(questions) == 3
    assert all(isinstance(q, str) and q.strip() for q in questions)


def test_valid_question_response_is_returned() -> None:
    from app.contracts.interview_contract import InterviewQuestions

    llm = _Llm({"questions": ["Frage A?", "Frage B?", "Frage C?", "Frage D?"]})

    questions = mod.generate_interview_questions(
        interview_requirement="Wie wirkt die Massnahme?",
        simulation_requirement="",
        selected_agents=_PROFILES[:2],
        llm=llm,
    )

    assert questions == ["Frage A?", "Frage B?", "Frage C?", "Frage D?"]
    assert llm.schemas == [InterviewQuestions]
