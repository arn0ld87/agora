"""Haltung je Beitrag und Positionierungsquote (Issue #1778, Schritt 1.8).

Vor dem Schreiben der Abschnitte wird jeder Simulationsbeitrag einmal nach
seiner Haltung zur Streitfrage klassifiziert. Daraus entstehen
Positionierungsquote und Lagerverteilung.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List

import pytest

from app.contracts.stance_analysis_contract import StanceAnalysis
from app.services.report_agent.stance_analysis import (
    build_stance_analysis,
    classify_contributions,
    save_stance_analysis,
)
from app.services.run_budget import BudgetExceededError

STATEMENT = "Die Geburtshilfe in Brenkhausen wird zum 30. Juni 2027 geschlossen."

_POST_LINE_RE = re.compile(r"^(\d+)\. (.*)$", re.MULTILINE)


def _action(agent_id: int, agent_name: str, round_num: int, content: str | None, **extra: Any) -> Dict[str, Any]:
    action: Dict[str, Any] = {
        "round_num": round_num,
        "timestamp": f"2026-01-01T{round_num:02d}:00:00",
        "platform": "reddit",
        "agent_id": agent_id,
        "agent_name": agent_name,
        "action_type": "CREATE_POST",
        "action_args": {"content": content} if content is not None else {},
        "result": None,
        "success": True,
    }
    action.update(extra)
    return action


def _config(*stances: str, statement: str | None = STATEMENT) -> Dict[str, Any]:
    return {
        "contested_question": (
            {"statement": statement, "origin": "assistant", "absence_reason": None}
            if statement
            else {"statement": None, "origin": "none", "absence_reason": "Offene Frage."}
        ),
        "agent_configs": [
            {"agent_id": index, "entity_name": f"Agent {index}", "stance": stance}
            for index, stance in enumerate(stances)
        ],
    }


class _StubLLM:
    """Antwortet je Beitrag mit der Haltung, die ``decide`` für dessen Text liefert.

    ``decide`` gibt ``None`` zurück, wenn der Beitrag in der Antwort fehlen soll.
    """

    def __init__(self, decide: Callable[[str], str | None]) -> None:
        self._decide = decide
        self.calls: List[Dict[str, Any]] = []

    def chat_json(self, messages: List[Dict[str, str]], **kwargs: Any) -> Dict[str, Any]:
        self.calls.append({"messages": messages, **kwargs})
        posts = messages[-1]["content"].split("Posts:\n", 1)[1]
        items = []
        for index, text in _POST_LINE_RE.findall(posts):
            stance = self._decide(text)
            if stance is not None:
                items.append({"index": int(index), "stance": stance})
        return {"items": items}


def _by_keyword(text: str) -> str | None:
    if "verhindern" in text:
        return "opposed"
    if "richtig" in text:
        return "in_favour"
    return "undecided"


def test_ohne_streitfrage_ist_die_analyse_nicht_anwendbar_und_ruft_kein_llm():
    llm = _StubLLM(_by_keyword)

    analysis = build_stance_analysis(
        "sim-1",
        _config("supportive", "opposing", statement=None),
        [_action(0, "Agent 0", 1, "Wir müssen die Schließung verhindern.")],
        None,
        llm,
    )

    assert analysis.applicable is False
    assert analysis.contested_statement is None
    assert analysis.voices == []
    assert analysis.contributions == []
    assert analysis.positioning_ratio is None
    assert llm.calls == []


def test_zwei_von_vier_stimmen_beziehen_stellung():
    llm = _StubLLM(_by_keyword)
    actions = [
        _action(0, "Agent 0", 1, "Wir müssen die Schließung verhindern."),
        _action(1, "Agent 1", 2, "Diese Schließung werden wir verhindern."),
        _action(2, "Agent 2", 2, "Welche Zahlen liegen dem Kreistag vor?"),
    ]

    analysis = build_stance_analysis(
        "sim-1", _config("opposing", "supportive", "neutral", "observer"), actions, None, llm
    )

    assert analysis.applicable is True
    assert analysis.contested_statement == STATEMENT
    assert analysis.voices_total == 4
    assert analysis.voices_positioned == 2
    assert analysis.positioning_ratio == 0.5
    assert analysis.camp_distribution == {"in_favour": 0, "opposed": 2, "undecided": 2}
    assert analysis.classified_total == 3
    assert analysis.classification_failed == 0
    assert [voice.voice_key for voice in analysis.voices] == [
        "agent:0",
        "agent:1",
        "agent:2",
        "agent:3",
    ]
    assert [voice.start_class for voice in analysis.voices] == [
        "opposed",
        "in_favour",
        "undecided",
        "undecided",
    ]
    assert [voice.contribution_classes for voice in analysis.voices] == [
        ["opposed"],
        ["opposed"],
        ["undecided"],
        [],
    ]
    assert all(voice.interview_class is None for voice in analysis.voices)
    assert analysis.contributions[0].producer_key == (
        "simulation-action:reddit:1:0:CREATE_POST:2026-01-01T01:00:00"
    )


def test_gleichstand_einer_stimme_zaehlt_im_lager_als_unentschieden():
    llm = _StubLLM(_by_keyword)
    actions = [
        _action(0, "Agent 0", 1, "Wir müssen die Schließung verhindern."),
        _action(0, "Agent 0", 2, "Die Schließung ist richtig."),
    ]

    analysis = build_stance_analysis("sim-1", _config("neutral"), actions, None, llm)

    assert analysis.voices_positioned == 1
    assert analysis.camp_distribution == {"in_favour": 0, "opposed": 0, "undecided": 1}


def test_rollenkonflikte_und_aktionen_ohne_text_sind_keine_beitraege():
    llm = _StubLLM(_by_keyword)
    actions = [
        _action(0, "Agent 0", 1, "Wir müssen die Schließung verhindern.", role_conflict="foreign_role"),
        _action(1, "Agent 1", 1, None, action_type="LIKE_POST"),
    ]

    analysis = build_stance_analysis("sim-1", _config("opposing", "neutral"), actions, None, llm)

    assert analysis.contributions == []
    assert analysis.voices_positioned == 0
    assert analysis.positioning_ratio == 0.0
    assert llm.calls == []


def test_ausgelassener_index_zaehlt_nicht_als_positioniert():
    llm = _StubLLM(lambda text: None if "verhindern" in text else "undecided")
    actions = [
        _action(0, "Agent 0", 1, "Wir müssen die Schließung verhindern."),
        _action(1, "Agent 1", 2, "Welche Zahlen liegen dem Kreistag vor?"),
    ]

    analysis = build_stance_analysis("sim-1", _config("opposing", "neutral"), actions, None, llm)

    assert analysis.classification_failed == 1
    assert analysis.classified_total == 1
    assert analysis.voices_positioned == 0
    assert analysis.voices[0].contribution_classes == []


def test_budgetabbruch_kommt_beim_aufrufer_an():
    class _BudgetLLM:
        def chat_json(self, messages: List[Dict[str, str]], **kwargs: Any) -> Dict[str, Any]:
            raise BudgetExceededError("tokens", 10, 10)

    with pytest.raises(BudgetExceededError):
        build_stance_analysis(
            "sim-1",
            _config("opposing"),
            [_action(0, "Agent 0", 1, "Wir müssen die Schließung verhindern.")],
            None,
            _BudgetLLM(),
        )


def test_fehlgeschlagener_batch_liefert_none_fuer_seine_beitraege():
    class _BrokenLLM:
        def chat_json(self, messages: List[Dict[str, str]], **kwargs: Any) -> Dict[str, Any]:
            raise RuntimeError("provider down")

    contributions = [_action(0, "Agent 0", 1, "Erster Beitrag."), _action(1, "Agent 1", 1, "Zweiter Beitrag.")]

    assert classify_contributions(_BrokenLLM(), STATEMENT, contributions) == [None, None]


def test_beitraege_werden_in_batches_klassifiziert_und_gekuerzt():
    llm = _StubLLM(_by_keyword)
    contributions = [_action(i, f"Agent {i}", 1, f"Beitrag {i} " + "x" * 600) for i in range(30)]

    classes = classify_contributions(llm, STATEMENT, contributions, batch_size=25)

    assert classes == ["undecided"] * 30
    assert len(llm.calls) == 2
    user_prompt = llm.calls[0]["messages"][-1]["content"]
    assert f'Statement: "{STATEMENT}"' in user_prompt
    first_post = _POST_LINE_RE.findall(user_prompt.split("Posts:\n", 1)[1])[0][1]
    assert len(first_post) <= 500
    assert llm.calls[0]["messages"][0]["content"] == (
        "You classify short social media posts. Answer only with the requested JSON."
    )


class _Stored:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self._payload = payload

    def to_dict(self) -> Dict[str, Any]:
        return self._payload


class _Store:
    def __init__(self, config: Any) -> None:
        self._config = config

    def read_json(self, simulation_id: str, name: str, default: Any = None) -> Any:
        assert name == "simulation_config"
        return self._config if self._config is not None else default


class _Agent:
    def __init__(self, llm: Any) -> None:
        self.simulation_id = "sim-1"
        self.llm = llm


def test_workflow_berechnet_die_analyse_mit_dem_llm_client_des_agenten(monkeypatch, tmp_path):
    from app.services.report_agent import workflow
    from app.services.report_agent.manager import ReportManager
    from app.services.simulation_runner import SimulationRunner

    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path))
    monkeypatch.setattr(workflow, "resolve_default_store", lambda: _Store(_config("opposing", "neutral")))
    monkeypatch.setattr(
        SimulationRunner,
        "get_all_actions",
        staticmethod(
            lambda *_a, **_k: [_Stored(_action(0, "Agent 0", 1, "Wir müssen die Schließung verhindern."))]
        ),
    )
    monkeypatch.setattr(workflow, "action_log_health", lambda *_a, **_k: (1, 0))
    llm = _StubLLM(_by_keyword)

    result = workflow._compute_stance_analysis(_Agent(llm), "report-1")

    assert len(llm.calls) == 1
    assert result is not None
    assert result["voices_positioned"] == 1
    assert result["positioning_ratio"] == 0.5
    stored = json.loads(
        (tmp_path / "report-1" / "stance_analysis.json").read_text(encoding="utf-8")
    )
    assert stored == result


def test_workflow_behauptet_nichts_ohne_lesbare_simulationskonfiguration(monkeypatch, tmp_path):
    from app.services.report_agent import workflow
    from app.services.report_agent.manager import ReportManager

    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path))
    monkeypatch.setattr(workflow, "resolve_default_store", lambda: _Store(None))
    llm = _StubLLM(_by_keyword)

    assert workflow._compute_stance_analysis(_Agent(llm), "report-1") is None
    assert llm.calls == []
    assert not (tmp_path / "report-1" / "stance_analysis.json").exists()


def test_analyse_wird_als_stance_analysis_json_gespeichert(tmp_path):
    analysis = build_stance_analysis(
        "sim-1",
        _config("opposing"),
        [_action(0, "Agent 0", 1, "Wir müssen die Schließung verhindern.")],
        None,
        _StubLLM(_by_keyword),
    )

    path = save_stance_analysis(str(tmp_path), analysis)

    assert path == str(tmp_path / "stance_analysis.json")
    stored = json.loads((tmp_path / "stance_analysis.json").read_text(encoding="utf-8"))
    assert StanceAnalysis.model_validate(stored) == analysis


class _FailingStore:
    def read_json(self, simulation_id: str, name: str, default: Any = None) -> Any:
        raise PermissionError("simulation_config.json")


def _workflow_with(monkeypatch, tmp_path, *, store: Any, actions: List[Dict[str, Any]], health):
    from app.services.report_agent import workflow
    from app.services.report_agent.manager import ReportManager
    from app.services.simulation_runner import SimulationRunner

    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path))
    monkeypatch.setattr(workflow, "resolve_default_store", lambda: store)
    monkeypatch.setattr(
        SimulationRunner,
        "get_all_actions",
        staticmethod(lambda *_a, **_k: [_Stored(action) for action in actions]),
    )
    monkeypatch.setattr(workflow, "action_log_health", lambda *_a, **_k: health)
    return workflow


def test_workflow_meldet_einen_lesefehler_statt_zu_schweigen(monkeypatch, tmp_path):
    """Review PR #1780 (P0): ein Lese- oder Rechtefehler bleibt sichtbar."""
    workflow = _workflow_with(monkeypatch, tmp_path, store=_FailingStore(), actions=[], health=(1, 0))
    llm = _StubLLM(_by_keyword)

    result = workflow._compute_stance_analysis(_Agent(llm), "report-1")

    assert result == {"unavailable_reason": "read_failed"}
    assert llm.calls == []
    assert not (tmp_path / "report-1" / "stance_analysis.json").exists()


def test_workflow_misst_keine_quote_ohne_aktionsprotokoll(monkeypatch, tmp_path):
    """Review PR #1780: ein fehlendes Protokoll ist keine Quote von null."""
    workflow = _workflow_with(
        monkeypatch, tmp_path, store=_Store(_config("opposing", "neutral")), actions=[], health=(0, 0)
    )
    llm = _StubLLM(_by_keyword)

    assert workflow._compute_stance_analysis(_Agent(llm), "report-1") == {
        "unavailable_reason": "action_log_missing"
    }
    assert llm.calls == []


def test_workflow_misst_keine_quote_bei_beschaedigten_protokollzeilen(monkeypatch, tmp_path):
    workflow = _workflow_with(
        monkeypatch,
        tmp_path,
        store=_Store(_config("opposing", "neutral")),
        actions=[_action(0, "Agent 0", 1, "Wir müssen die Schließung verhindern.")],
        health=(1, 3),
    )
    llm = _StubLLM(_by_keyword)

    assert workflow._compute_stance_analysis(_Agent(llm), "report-1") == {
        "unavailable_reason": "action_log_unreadable"
    }
    assert llm.calls == []


def test_workflow_ohne_streitfrage_prueft_das_protokoll_nicht(monkeypatch, tmp_path):
    workflow = _workflow_with(
        monkeypatch,
        tmp_path,
        store=_Store(_config("opposing", statement=None)),
        actions=[],
        health=(0, 0),
    )

    result = workflow._compute_stance_analysis(_Agent(_StubLLM(_by_keyword)), "report-1")

    assert result is not None
    assert result["applicable"] is False


def test_action_log_health_zaehlt_dateien_und_unlesbare_zeilen(tmp_path):
    from app.services.sim.action_log_reader import action_log_health

    sim_dir = tmp_path / "sim-1"
    (sim_dir / "twitter").mkdir(parents=True)
    (sim_dir / "twitter" / "actions.jsonl").write_text(
        '{"agent_id": 0, "round": 1}\n\n{"agent_id": 1, "rou\nnicht json\n', encoding="utf-8"
    )

    assert action_log_health("sim-1", tmp_path) == (1, 2)
    (tmp_path / "sim-2").mkdir()
    assert action_log_health("sim-2", tmp_path) == (0, 0)


def test_widerspruechliche_doppelte_indizes_gelten_als_nicht_klassifiziert():
    """CLI-Review PR #1780: die zweite Nennung überschrieb still die erste."""

    class _LLM:
        def chat_json(self, **_kwargs: Any) -> Dict[str, Any]:
            return {
                "items": [
                    {"index": 1, "stance": "in_favour"},
                    {"index": 1, "stance": "opposed"},
                    {"index": 2, "stance": "opposed"},
                    {"index": 2, "stance": "opposed"},
                ]
            }

    classes = classify_contributions(
        _LLM(),
        STATEMENT,
        [_action(0, "A", 1, "Erster Beitrag."), _action(1, "B", 1, "Zweiter Beitrag.")],
    )

    assert classes == [None, "opposed"]


def test_workflow_uebernimmt_beim_resume_die_gespeicherte_analyse(monkeypatch, tmp_path):
    """CLI-Review PR #1780: ein Resume klassifiziert nicht erneut."""
    workflow = _workflow_with(
        monkeypatch,
        tmp_path,
        store=_Store(_config("opposing", "neutral")),
        actions=[_action(0, "Agent 0", 1, "Wir müssen die Schließung verhindern.")],
        health=(1, 0),
    )
    first_llm = _StubLLM(_by_keyword)
    first = workflow._compute_stance_analysis(_Agent(first_llm), "report-1")
    assert len(first_llm.calls) == 1

    second_llm = _StubLLM(_by_keyword)
    second = workflow._compute_stance_analysis(_Agent(second_llm), "report-1")

    assert second == first
    assert second_llm.calls == []


def test_workflow_ohne_streitfrage_liest_das_protokoll_nicht(monkeypatch, tmp_path):
    """CLI-Review PR #1780: ein Lesefehler dort wäre eine Warnung ohne Anlass."""
    from app.services.simulation_runner import SimulationRunner

    workflow = _workflow_with(
        monkeypatch,
        tmp_path,
        store=_Store(_config("opposing", statement=None)),
        actions=[],
        health=(0, 0),
    )

    def _boom(*_a: Any, **_k: Any) -> Any:
        raise PermissionError("actions.jsonl")

    monkeypatch.setattr(SimulationRunner, "get_all_actions", staticmethod(_boom))

    result = workflow._compute_stance_analysis(_Agent(_StubLLM(_by_keyword)), "report-1")

    assert result is not None and result["applicable"] is False


def test_workflow_rechnet_neu_wenn_sich_die_streitfrage_geaendert_hat(monkeypatch, tmp_path):
    """Review PR #1780: eine gespeicherte Analyse gilt nur für ihre Streitfrage."""
    actions = [_action(0, "Agent 0", 1, "Wir müssen die Schließung verhindern.")]
    workflow = _workflow_with(
        monkeypatch, tmp_path, store=_Store(_config("opposing", "neutral")), actions=actions, health=(1, 0)
    )
    first = workflow._compute_stance_analysis(_Agent(_StubLLM(_by_keyword)), "report-1")
    assert first["contested_statement"] == STATEMENT

    new_statement = "Die Kinderklinik in Brenkhausen wird zum 30. Juni 2027 geschlossen."
    workflow = _workflow_with(
        monkeypatch,
        tmp_path,
        store=_Store(_config("opposing", "neutral", statement=new_statement)),
        actions=actions,
        health=(1, 0),
    )
    llm = _StubLLM(_by_keyword)
    second = workflow._compute_stance_analysis(_Agent(llm), "report-1")

    assert len(llm.calls) == 1
    assert second["contested_statement"] == new_statement


def test_action_log_health_ignoriert_das_alte_protokoll_neben_plattformprotokollen(tmp_path):
    """Review PR #1780: ``get_all_actions`` liest es dann auch nicht."""
    from app.services.sim.action_log_reader import action_log_health

    sim_dir = tmp_path / "sim-1"
    (sim_dir / "reddit").mkdir(parents=True)
    (sim_dir / "reddit" / "actions.jsonl").write_text('{"agent_id": 0, "round": 1}\n', encoding="utf-8")
    (sim_dir / "actions.jsonl").write_text("kaputt\n", encoding="utf-8")

    assert action_log_health("sim-1", tmp_path) == (1, 0)

    legacy = tmp_path / "sim-2"
    legacy.mkdir()
    (legacy / "actions.jsonl").write_text("kaputt\n", encoding="utf-8")
    assert action_log_health("sim-2", tmp_path) == (1, 1)


def test_action_log_health_prueft_das_protokoll_aus_dem_die_aktionen_stammen(tmp_path):
    """Review PR #1780: liefern die Plattformprotokolle nichts, zählt das alte."""
    from app.services.sim.action_log_reader import action_log_health

    sim_dir = tmp_path / "sim-1"
    (sim_dir / "twitter").mkdir(parents=True)
    (sim_dir / "twitter" / "actions.jsonl").write_text("kaputt\n", encoding="utf-8")
    (sim_dir / "actions.jsonl").write_text('{"agent_id": 0, "round": 1}\n', encoding="utf-8")

    assert action_log_health("sim-1", tmp_path) == (1, 0)

    # Ohne verwertbares altes Protokoll bleibt der Schaden sichtbar.
    broken = tmp_path / "sim-2"
    (broken / "twitter").mkdir(parents=True)
    (broken / "twitter" / "actions.jsonl").write_text("kaputt\n", encoding="utf-8")
    assert action_log_health("sim-2", tmp_path) == (1, 1)

