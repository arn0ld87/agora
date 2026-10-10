"""Abnahmemaße der Haltungsanalyse (#1779, Entscheidung vom 10.10.2026).

Die Positionierungsquote ist gesättigt (eine Position je Stimme genügt). Die Maße in
``scripts/stance_acceptance.py`` ergänzen sie um Verfall, Treue zur Startklasse und den
Anteil positionierter Stimmen unter den unentschiedenen. Reine Funktionen über einer
synthetischen ``StanceAnalysis``, kein Modell, kein Lauf.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from app.contracts.stance_analysis_contract import (
    ClassifiedContribution,
    StanceAnalysis,
    StanceClass,
    VoiceStance,
)

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

stance_acceptance = importlib.import_module("stance_acceptance")

_Spec = Tuple[int, StanceClass, List[Tuple[int, StanceClass]]]

#: (agent_id, Startklasse, [(Runde, Klasse), ...])
_VOICES: List[_Spec] = [
    (0, "opposed", [(0, "opposed"), (7, "opposed"), (8, "opposed"), (9, "undecided"),
                    (12, "undecided"), (13, "undecided"), (20, "opposed")]),
    (1, "opposed", [(7, "in_favour"), (11, "undecided"), (15, "undecided")]),
    (2, "in_favour", [(7, "in_favour"), (10, "undecided"), (12, "in_favour"), (24, "undecided")]),
    (3, "undecided", [(8, "opposed"), (12, "undecided")]),
    (4, "undecided", [(9, "undecided")]),
    (5, "undecided", []),
]


def _analysis(extra_unmatched: bool = True) -> StanceAnalysis:
    contributions: List[ClassifiedContribution] = []
    voices: List[VoiceStance] = []
    for agent_id, start, items in _VOICES:
        for round_num, stance in items:
            contributions.append(_contribution(agent_id, round_num, stance))
        voices.append(
            VoiceStance(
                voice_key=f"agent:{agent_id}",
                agent_name=f"Agent {agent_id}",
                start_class=start,
                contribution_classes=[stance for _r, stance in items],
            )
        )
    if extra_unmatched:
        contributions.append(_contribution(99, 8, "opposed"))
    positioned = sum(any(c != "undecided" for c in v.contribution_classes) for v in voices)
    return StanceAnalysis(
        contested_statement="Der Kreistag schließt den Kreißsaal.",
        applicable=True,
        voices_total=len(voices),
        voices_positioned=positioned,
        positioning_ratio=positioned / len(voices),
        voices=voices,
        contributions=contributions,
        classified_total=len(contributions),
        classification_failed=2,
    )


def _contribution(agent_id: int, round_num: int, stance: StanceClass) -> ClassifiedContribution:
    return ClassifiedContribution(
        agent_id=agent_id,
        agent_name=f"Agent {agent_id}",
        platform="reddit",
        round_num=round_num,
        action_type="CREATE_COMMENT",
        producer_key=f"simulation-action:reddit:{round_num}:{agent_id}:CREATE_COMMENT:t",
        stance_class=stance,
    )


def test_positioning_ratio_is_reported_with_the_strict_threshold() -> None:
    metrics = stance_acceptance.compute_acceptance_metrics(_analysis())

    assert metrics["applicable"] is True
    assert metrics["positioning_ratio"] == pytest.approx(4 / 6)
    assert metrics["positioning_ratio_above_half"] is True
    assert metrics["voices_total"] == 6 and metrics["voices_positioned"] == 4
    assert metrics["classification_failed"] == 2
    assert metrics["unmatched_contributions"] == 1


def test_a_ratio_of_exactly_one_half_is_not_above_half() -> None:
    analysis = _analysis().model_copy(update={"positioning_ratio": 0.5})
    assert stance_acceptance.compute_acceptance_metrics(analysis)["positioning_ratio_above_half"] is False


def test_positioned_share_per_round_counts_only_configured_sided_voices() -> None:
    by_round = stance_acceptance.compute_acceptance_metrics(_analysis())["positioned_contribution_share_by_round"]

    # Agent 3 (undecided) und der Beitrag ohne Stimme (Agent 99) zählen hier nicht.
    assert by_round[7] == {"contributions": 3, "positioned": 3, "share": 1.0}
    assert by_round[8] == {"contributions": 1, "positioned": 1, "share": 1.0}
    assert by_round[12] == {"contributions": 2, "positioned": 1, "share": 0.5}
    assert by_round[0] == {"contributions": 1, "positioned": 1, "share": 1.0}
    assert list(by_round) == sorted(by_round)
    assert by_round[24] == {"contributions": 1, "positioned": 0, "share": 0.0}


def test_decay_compares_early_and_late_windows_for_sided_voices() -> None:
    decay = stance_acceptance.compute_acceptance_metrics(_analysis())["decay"]

    assert decay["early_rounds"] == [7, 11] and decay["late_rounds"] == [12, 24]
    assert decay["early"] == {"contributions": 7, "positioned": 4, "share": pytest.approx(4 / 7)}
    assert decay["late"] == {"contributions": 6, "positioned": 2, "share": pytest.approx(2 / 6)}
    assert decay["delta"] == pytest.approx(2 / 6 - 4 / 7)
    opposed, in_favour = decay["by_start_class"]["opposed"], decay["by_start_class"]["in_favour"]
    assert opposed["early"]["contributions"] == 5 and opposed["early"]["positioned"] == 3
    assert opposed["late"]["contributions"] == 4 and opposed["late"]["positioned"] == 1
    assert in_favour["early"]["share"] == pytest.approx(0.5) and in_favour["late"]["share"] == pytest.approx(0.5)
    assert in_favour["delta"] == pytest.approx(0.0)


def test_decay_windows_are_configurable() -> None:
    decay = stance_acceptance.compute_acceptance_metrics(
        _analysis(), early_rounds=(0, 7), late_rounds=(8, 11)
    )["decay"]
    assert decay["early_rounds"] == [0, 7] and decay["late_rounds"] == [8, 11]
    # Runde 0 (Agent 0) und Runde 7 (Agenten 0, 1, 2): alle vier Beiträge positioniert.
    assert decay["early"] == {"contributions": 4, "positioned": 4, "share": 1.0}
    # Runden 8-11: Agent 0 (Runden 8, 9), Agent 1 (11), Agent 2 (10); nur Runde 8 positioniert.
    assert decay["late"] == {"contributions": 4, "positioned": 1, "share": pytest.approx(0.25)}


def test_start_class_fidelity_compares_contribution_class_with_configured_side() -> None:
    fidelity = stance_acceptance.compute_acceptance_metrics(_analysis())["start_class_fidelity"]

    assert fidelity["opposed"] == {"contributions": 10, "matching": 4, "share": pytest.approx(0.4)}
    assert fidelity["in_favour"] == {"contributions": 4, "matching": 2, "share": pytest.approx(0.5)}
    assert fidelity["all"] == {"contributions": 14, "matching": 6, "share": pytest.approx(6 / 14)}


def test_undecided_voices_positioned_share() -> None:
    undecided = stance_acceptance.compute_acceptance_metrics(_analysis())["undecided_voices"]
    assert undecided == {"total": 3, "positioned": 1, "share": pytest.approx(1 / 3)}


def test_empty_groups_have_no_share_instead_of_dividing_by_zero() -> None:
    analysis = StanceAnalysis(
        contested_statement="X",
        applicable=True,
        voices_total=1,
        voices_positioned=0,
        positioning_ratio=0.0,
        voices=[VoiceStance(voice_key="agent:0", agent_name="A", start_class="opposed")],
    )
    metrics = stance_acceptance.compute_acceptance_metrics(analysis)

    assert metrics["decay"]["early"]["share"] is None and metrics["decay"]["delta"] is None
    assert metrics["start_class_fidelity"]["all"]["share"] is None
    assert metrics["undecided_voices"] == {"total": 0, "positioned": 0, "share": None}
    assert metrics["positioned_contribution_share_by_round"] == {}


def test_analysis_without_contested_question_reports_not_applicable() -> None:
    metrics = stance_acceptance.compute_acceptance_metrics(StanceAnalysis(applicable=False))
    assert metrics == {"applicable": False}


# --- CLI ----------------------------------------------------------------------------------------


def _write(tmp_path: Path) -> Path:
    path = tmp_path / "stance_analysis.json"
    path.write_text(_analysis().model_dump_json(), encoding="utf-8")
    return path


def test_cli_prints_json_for_a_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert stance_acceptance.main([str(_write(tmp_path))]) == 0

    metrics: Dict[str, Any] = json.loads(capsys.readouterr().out)
    assert metrics["positioning_ratio"] == pytest.approx(4 / 6)
    assert metrics["decay"]["late_rounds"] == [12, 24]


def test_cli_accepts_a_report_directory_and_window_options(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path)
    assert stance_acceptance.main([str(tmp_path), "--early", "7-9", "--late", "10-24"]) == 0

    metrics = json.loads(capsys.readouterr().out)
    assert metrics["decay"]["early_rounds"] == [7, 9] and metrics["decay"]["late_rounds"] == [10, 24]


def test_cli_fails_for_missing_or_invalid_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert stance_acceptance.main([str(tmp_path / "gibt-es-nicht.json")]) == 2
    broken = tmp_path / "stance_analysis.json"
    broken.write_text("{\"nicht\": \"der Vertrag\"}", encoding="utf-8")
    assert stance_acceptance.main([str(broken)]) == 2
    assert capsys.readouterr().out == ""


def test_cli_rejects_malformed_windows(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        stance_acceptance.main([str(_write(tmp_path)), "--early", "elf"])
    with pytest.raises(SystemExit):
        stance_acceptance.main([str(_write(tmp_path)), "--late", "24-12"])
