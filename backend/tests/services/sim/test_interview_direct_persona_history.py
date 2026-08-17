"""Tests für den optionalen ``persona_history``-Block in ``build_persona_messages``.

Issue #1304 Slice 1: die Persona hat 10-20 Simulationsrunden hinter sich, davon
steht im heutigen Prompt nichts. ``build_persona_messages`` bekommt dafür einen
optionalen Keyword-Parameter fuer die eigene Aktionshistorie der Persona (Form
von ``AgentAction.to_dict()``, siehe ``action_log_reader.py``). Reine Funktion,
kein LLM-Call, kein Mock noetig.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.sim.interview_direct import build_persona_messages


PERSONA: Dict[str, Any] = {
    "user_id": 1,
    "username": "lena_k",
    "name": "Lena Krüger",
    "bio": "Product Ownerin in einem mittelständischen SaaS-Team",
    "persona": "Skeptisch gegenüber neuen Tools, achtet auf Datenschutz.",
    "age": 38,
    "country": "DE",
    "profession": "Product Ownerin",
    "interested_topics": ["SaaS", "Datenschutz"],
}

CONTEXT: Dict[str, Any] = {
    "requirement": "Wie lässt sich das Onboarding verbessern?",
    "language": "de",
}


def _action(round_num: int, content: str, action_type: str = "CREATE_POST") -> Dict[str, Any]:
    """Baue ein Aktions-Dict in der Form von ``AgentAction.to_dict()``."""
    return {
        "round_num": round_num,
        "timestamp": f"2026-08-17T10:{round_num:02d}:00",
        "platform": "reddit",
        "agent_id": 1,
        "agent_name": "Lena Krüger",
        "action_type": action_type,
        "action_args": {"content": content},
        "result": None,
        "success": True,
    }


def _system_content(messages: List[Dict[str, str]]) -> str:
    assert messages[0]["role"] == "system"
    return messages[0]["content"]


def test_persona_history_texts_landen_im_system_prompt() -> None:
    history = [
        _action(1, "Ich finde den neuen Onboarding-Flow ziemlich unuebersichtlich."),
        _action(2, "Nach dem zweiten Versuch klappt es besser.", action_type="CREATE_COMMENT"),
    ]

    messages = build_persona_messages(
        PERSONA, 1, "Wie war dein Eindruck?", context=CONTEXT, persona_history=history
    )
    system = _system_content(messages)

    assert "Ich finde den neuen Onboarding-Flow ziemlich unuebersichtlich." in system
    assert "Nach dem zweiten Versuch klappt es besser." in system
    assert "eigenen Beitraege aus dieser Simulation" in system


def test_ohne_historie_ist_prompt_byte_identisch() -> None:
    baseline = build_persona_messages(PERSONA, 1, "Wie war dein Eindruck?", context=CONTEXT)

    ohne_kwarg = build_persona_messages(
        PERSONA, 1, "Wie war dein Eindruck?", context=CONTEXT
    )
    mit_none = build_persona_messages(
        PERSONA, 1, "Wie war dein Eindruck?", context=CONTEXT, persona_history=None
    )
    mit_leerer_liste = build_persona_messages(
        PERSONA, 1, "Wie war dein Eindruck?", context=CONTEXT, persona_history=[]
    )

    assert ohne_kwarg == baseline
    assert mit_none == baseline
    assert mit_leerer_liste == baseline


def test_obergrenze_acht_eintraege_und_kuerzung_auf_240_zeichen() -> None:
    """Die letzten acht Beitraege, jeder auf 240 Zeichen gekuerzt.

    Bewusst die *letzten*: das Aktionslog ist chronologisch, und wonach im
    Interview gefragt wird, ist die aktuelle Haltung der Persona — nicht die
    aus Runde eins.
    """
    history = [_action(i, f"Beitrag Nummer {i} zum Thema Onboarding.") for i in range(20)]
    long_text = "X" * 500
    history[-1]["action_args"]["content"] = long_text

    messages = build_persona_messages(
        PERSONA, 1, "Wie war dein Eindruck?", context=CONTEXT, persona_history=history
    )
    system = _system_content(messages)

    bullet_lines = [
        line for line in system.splitlines() if line.startswith("- (CREATE_POST)")
    ]
    assert len(bullet_lines) == 8

    assert long_text not in system
    assert ("X" * 240) in system
    assert ("X" * 241) not in system

    # Der juengste Block bleibt, der aelteste faellt jenseits der Obergrenze weg.
    assert "Beitrag Nummer 12 zum Thema Onboarding." in system
    assert "Beitrag Nummer 11 zum Thema Onboarding." not in system
    assert "Beitrag Nummer 0 zum Thema Onboarding." not in system
