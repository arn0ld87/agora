"""Vier Wochen in Abschnitt 1, acht in Abschnitt 7 — und nichts dazwischen (#1359).

Im Referenzlauf nannte Abschnitt 1 vier Wochen Pilotbetrieb, Abschnitt 7
mindestens acht. Beide Werte standen unverbunden im Bericht. Drei Schäden lagen
übereinander:

- Beide Abschnitte vergaben dieselbe Modell-ID; der Merge verwarf den zweiten
  Wert still — genau den, der dem ersten widersprach.
- Die Extraktion eines Abschnitts kannte die Zahlen früherer Abschnitte nicht
  und konnte eine gewollte Abweichung gar nicht ausdrücken.
- Ob ein Widerspruch gemeldet wurde, hing am LLM-Red-Team, das nur bei
  bestimmten Report-Typen läuft und Abzählbares übersehen kann.

Der Red-Team-Test läuft deshalb über den deterministischen Pfad: der
Widerspruch ist eine Zählung, kein Urteil. Dass das LLM beide Werte samt
Verweis zu sehen bekommt, prüft ein eigener Test.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock

from app.contracts.report_v3 import ReportV3, Segment, Threshold
from app.services.report_agent.markdown_renderer import render_threshold_table
from app.services.report_agent.metadata_merge import merge_section_metadata
from app.services.report_agent.schemas import SectionMetadata
from app.services.report_agent.threshold_deviation import (
    CONFLICT_FINDINGS_LIMIT,
    drop_unresolvable_deviations,
    find_threshold_conflicts,
    threshold_conflict_findings,
)
from app.services.report_agent.threshold_provenance import dedup_thresholds
from app.services.report_agent.workflow import (
    _build_red_team_excerpt,
    _prior_thresholds_prompt,
    _run_red_team_review,
)
from app.services.report_intent import ReportIntent


def _raw(threshold_id: str, value: float, **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "id": threshold_id,
        "label": "Pilotdauer",
        "kind": "quantity",
        "value": value,
        "unit": "weeks",
        "purpose": "target",
        "origin": "model_proposal",
    }
    payload.update(extra)
    return payload


def _section(index: int, *thresholds: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "section_index": index,
        "structured_metadata": {"thresholds": list(thresholds)},
    }


def _build(sections: List[Dict[str, Any]]) -> ReportV3:
    """Derselbe Weg wie ``ReportManager.build_report_v3``: Merge, Dedup, Verweise."""
    merged = merge_section_metadata(sections)
    return ReportV3(
        report_id="report_1359",
        generated_at=datetime(2026, 9, 24, tzinfo=timezone.utc),
        thresholds=drop_unresolvable_deviations(dedup_thresholds(merged.thresholds)),
    )


#: Der Referenzfall: beide Abschnitte vergeben ``thr_01``.
CONTRADICTION = [
    _section(1, _raw("thr_01", 4.0)),
    _section(7, _raw("thr_01", 8.0)),
]


def _agent(llm_findings: List[str] | None = None) -> MagicMock:
    agent = MagicMock()
    agent.llm.provider = "ollama"
    agent.llm.model = "qwen2.5:32b"
    agent.llm.chat_json.return_value = {"findings": llm_findings or []}
    return agent


# --- Identität ---------------------------------------------------------------

def test_der_widersprechende_wert_ueberlebt_den_merge() -> None:
    report = _build(CONTRADICTION)

    assert [(t.id, t.value) for t in report.thresholds] == [
        ("T1_01", 4.0),
        ("T7_01", 8.0),
    ]


def test_ein_abschnittsinterner_verweis_wird_mit_umbenannt() -> None:
    report = _build([
        _section(
            3,
            _raw("a", 4.0),
            _raw("b", 6.0, deviates_from="a", deviation_rationale="Für Filialen."),
        )
    ])

    assert report.thresholds[1].id == "T3_02"
    assert report.thresholds[1].deviates_from == "T3_01"


def test_ein_verweis_auf_einen_frueheren_abschnitt_bleibt_stehen() -> None:
    report = _build([
        _section(1, _raw("thr_01", 4.0)),
        _section(
            7,
            _raw(
                "thr_01",
                8.0,
                deviates_from="T1_01",
                deviation_rationale="Nach dem Ausfall im Testbetrieb verlängert.",
            ),
        ),
    ])

    assert report.thresholds[1].deviates_from == "T1_01"
    assert find_threshold_conflicts(report.thresholds) == []


def test_ein_verweis_ohne_begruendung_kostet_den_wert_nicht() -> None:
    """Der Wert bleibt; ohne Verbindung meldet ihn die Erkennung."""
    report = _build([
        _section(1, _raw("thr_01", 4.0)),
        _section(7, _raw("thr_01", 8.0, deviates_from="T1_01")),
    ])

    assert [t.id for t in report.thresholds] == ["T1_01", "T7_01"]
    assert report.thresholds[1].deviates_from is None
    assert len(find_threshold_conflicts(report.thresholds)) == 1


def test_ein_verweis_ins_leere_faellt_weg_statt_den_bericht_zu_sprengen() -> None:
    report = _build([
        _section(
            7,
            _raw("thr_01", 8.0, deviates_from="T1_09", deviation_rationale="x"),
        )
    ])

    assert report.thresholds[0].deviates_from is None


def test_ein_verweis_auf_eine_verschmolzene_dublette_folgt_ihr() -> None:
    """T2_01 geht in T1_01 auf; der Verweis darauf zeigt danach auf T1_01."""
    report = _build([
        _section(1, _raw("x", 4.0)),
        _section(2, _raw("x", 4.0)),
        _section(
            7,
            _raw("x", 8.0, deviates_from="T2_01", deviation_rationale="Verlängert."),
        ),
    ])

    assert [t.id for t in report.thresholds] == ["T1_01", "T7_01"]
    assert report.thresholds[1].deviates_from == "T1_01"


def test_eine_dublette_mit_verweis_auf_den_verbleibenden_eintrag_verweist_nicht_auf_sich() -> None:
    """Review PR #1566: T2_01 geht in T1_01 auf und verwies selbst auf T1_01.

    Die Übernahme der Abweichung hätte ``T1_01 → T1_01`` erzeugt — an der
    Validierung vorbei, weil ``model_copy`` sie nicht erneut ausführt.
    """
    report = _build([
        _section(1, _raw("x", 4.0)),
        _section(
            2,
            _raw("x", 4.0, deviates_from="T1_01", deviation_rationale="Verlängert."),
        ),
    ])

    assert [t.id for t in report.thresholds] == ["T1_01"]
    assert report.thresholds[0].deviates_from is None
    assert report.thresholds[0].deviation_rationale is None


# --- Prompt -------------------------------------------------------------------

def test_die_extraktion_sieht_fruehere_zahlen_mit_der_kennung_des_merges() -> None:
    agent = MagicMock()
    agent.evidence_map = {"sections": CONTRADICTION}

    prompt = _prior_thresholds_prompt(agent, SectionMetadata, section_index=7)

    assert "[T1_01] Pilotdauer: 4.0 weeks (target)" in prompt
    # Der eigene und spätere Abschnitte gehören nicht in die Liste.
    assert "T7_01" not in prompt
    assert "deviates_from" in prompt
    # Die Kennung im Prompt ist dieselbe, die der Merge vergibt.
    assert _build(CONTRADICTION).thresholds[0].id == "T1_01"


def test_ohne_schwellenwert_slot_bleibt_der_prompt_unveraendert() -> None:
    agent = MagicMock()
    agent.evidence_map = {"sections": CONTRADICTION}

    assert _prior_thresholds_prompt(agent, Segment, section_index=7) == ""


# --- Erkennung ----------------------------------------------------------------

def _threshold(threshold_id: str, value: float, **extra: Any) -> Threshold:
    return Threshold.model_validate(_raw(threshold_id, value, **extra))


def test_alarmschwelle_und_zielwert_derselben_kennzahl_widersprechen_sich_nicht() -> None:
    thresholds = [
        _threshold("T1_01", 4.0),
        _threshold("T7_01", 8.0, purpose="alert"),
    ]

    assert find_threshold_conflicts(thresholds) == []


def test_verschiedene_einheiten_werden_nicht_verglichen() -> None:
    thresholds = [
        _threshold("T1_01", 4.0),
        _threshold("T7_01", 30.0, unit="days"),
    ]

    assert find_threshold_conflicts(thresholds) == []


def test_ein_label_ohne_stichwort_bildet_keine_gruppe() -> None:
    thresholds = [
        _threshold("T1_01", 4.0, label="KPI"),
        _threshold("T7_01", 8.0, label="KPI"),
    ]

    assert find_threshold_conflicts(thresholds) == []


def test_drei_werte_an_einem_bezugswert_sind_verbunden() -> None:
    thresholds = [
        _threshold("T1_01", 4.0),
        _threshold("T5_01", 6.0, deviates_from="T1_01", deviation_rationale="a"),
        _threshold("T7_01", 8.0, deviates_from="T1_01", deviation_rationale="b"),
    ]

    assert find_threshold_conflicts(thresholds) == []


def test_viele_widersprueche_verdraengen_die_modellbefunde_nicht() -> None:
    thresholds = [
        threshold
        for index in range(CONFLICT_FINDINGS_LIMIT + 2)
        for threshold in (
            _threshold(f"T1_{index:02d}", 4.0, label=f"Kennzahl{index}abc"),
            _threshold(f"T7_{index:02d}", 8.0, label=f"Kennzahl{index}abc"),
        )
    ]

    findings = threshold_conflict_findings(thresholds)

    assert len(findings) == CONFLICT_FINDINGS_LIMIT + 1
    assert findings[-1].startswith("2 weitere")


# --- Darstellung --------------------------------------------------------------

def test_eine_begruendete_abweichung_nennt_den_anderen_wert() -> None:
    table = render_threshold_table([
        _threshold("T1_01", 4.0),
        _threshold(
            "T7_01",
            8.0,
            deviates_from="T1_01",
            deviation_rationale="Nach dem Ausfall im Testbetrieb verlängert.",
        ),
    ])

    assert (
        "Weicht bewusst ab von 4 weeks (Pilotdauer): Nach dem Ausfall im "
        "Testbetrieb verlängert." in table
    )
    assert "Widersprüchliche Werte" not in table


def test_ein_unbegruendeter_widerspruch_steht_sichtbar_unter_der_tabelle() -> None:
    table = render_threshold_table(_build(CONTRADICTION).thresholds)

    assert "Widersprüchliche Werte ohne Begründung" in table
    assert "4 weeks [T1_01] und 8 weeks [T7_01]" in table


# --- Red Team -----------------------------------------------------------------

def test_das_red_team_meldet_den_widerspruch_zwischen_abschnitt_1_und_7() -> None:
    """Der Kern von #1359: ein echter Befund, auch wenn das Modell nichts sieht."""
    result = _run_red_team_review(
        _agent(llm_findings=[]),
        _build(CONTRADICTION),
        echo_index=0.0,
        intent=ReportIntent.FULL,
    )

    conflict = [f for f in result.red_team_findings if "Pilotdauer" in f]
    assert len(conflict) == 1
    assert "4 weeks [T1_01]" in conflict[0]
    assert "8 weeks [T7_01]" in conflict[0]


def test_der_befund_haengt_nicht_am_intent_gate() -> None:
    """Das LLM-Red-Team läuft bei Meinungsbildern nur ab der Echo-Schwelle —
    der abzählbare Widerspruch wird trotzdem gemeldet."""
    agent = _agent()

    result = _run_red_team_review(
        agent, _build(CONTRADICTION), echo_index=0.0, intent=ReportIntent.OPINION
    )

    agent.llm.chat_json.assert_not_called()
    assert any("[T7_01]" in finding for finding in result.red_team_findings)


def test_eine_begruendete_abweichung_ist_kein_befund() -> None:
    report = _build([
        _section(1, _raw("thr_01", 4.0)),
        _section(
            7,
            _raw("thr_01", 8.0, deviates_from="T1_01", deviation_rationale="Verlängert."),
        ),
    ])

    result = _run_red_team_review(
        _agent(), report, echo_index=0.0, intent=ReportIntent.FULL
    )

    assert result.red_team_findings == []


def test_das_llm_sieht_beide_werte_und_den_verweis() -> None:
    excerpt = _build_red_team_excerpt(_build([
        _section(1, _raw("thr_01", 4.0)),
        _section(
            7,
            _raw("thr_01", 8.0, deviates_from="T1_01", deviation_rationale="Verlängert."),
        ),
    ]))

    assert "[T1_01] [schwelle: target] Pilotdauer: 4 weeks" in excerpt
    assert "[T7_01] [schwelle: target] Pilotdauer: 8 weeks" in excerpt
    assert "weicht begründet ab von [T1_01]: Verlängert." in excerpt
