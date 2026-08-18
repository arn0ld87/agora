"""Das Red Team bewertet den Bericht, nicht die ersten 4000 Zeichen (#1359 B).

Vorher sah der Reviewer ``claims[:20]``, ``hypotheses[:10]`` und davon die
ersten 4000 Zeichen — gemessen an acht Artefakten griff die Zeichengrenze in
fuenf Faellen, mitten im Satz. Im Referenzlauf erzeugte er daraus einen Befund,
der Bericht breche ab. Das war der Schnitt des Excerpts.

Die Schwellen fehlten vollstaendig. Genau dort lag der Widerspruch, den zu
finden die Aufgabe der Stage ist.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from app.contracts.report_v3 import Claim, Hypothesis, ReportV3, Threshold
from app.services.report_agent.workflow import (
    _RED_TEAM_EXCERPT_BUDGET,
    _RED_TEAM_USER_TEMPLATE,
    _build_red_team_excerpt,
)

#: Die Evidence-ID folgt dem Vertragsmuster ``^ev_[0-9a-f]{32}$``.
EVIDENCE_ID = "ev_" + "a1" * 16


def _claim(section: int, slot: int, statement: str, confidence: str = "medium") -> Claim:
    return Claim(
        id=f"C{section}_{slot:02d}",
        statement=statement,
        evidence_refs=[EVIDENCE_ID],
        confidence=confidence,  # type: ignore[arg-type]
        aggregation_basis="persona",
        confidence_scope="simulation_consensus",
    )


def _threshold(threshold_id: str, value: float, label: str = "Pilotdauer") -> Threshold:
    return Threshold(
        id=threshold_id,
        label=label,
        value=value,
        unit="weeks",
        purpose="target",
        origin="model_proposal",
        evidence_status="heuristic",
    )


def _report(
    claims: List[Claim] | None = None,
    thresholds: List[Threshold] | None = None,
    hypotheses: List[Hypothesis] | None = None,
) -> ReportV3:
    return ReportV3(
        report_id="report_test",
        generated_at=datetime(2026, 8, 18, tzinfo=timezone.utc),
        # ReportV3 prueft, dass jede evidence_ref im Index steht — der Entwurf
        # fuer das Red Team entsteht aus einem validierten Artefakt.
        evidence_index={
            EVIDENCE_ID: {
                "evidence_id": EVIDENCE_ID,
                "producer_key": "red-team-excerpt-fixture",
                "type": "seed_document",
                "source": "fixture",
                "snippet": "Belegtext.",
                "source_kind": "seed_corpus",
            }
        },
        claims=claims or [],
        thresholds=thresholds or [],
        hypotheses=hypotheses or [],
    )


# --- Was der Reviewer jetzt sieht ------------------------------------------

def test_a_report_beyond_the_old_limit_arrives_whole():
    """Der alte Schnitt lag bei 4000 Zeichen und traf fuenf von acht Artefakten."""
    claims = [
        _claim(1, i, f"Befund Nummer {i} mit einer Aussage von brauchbarer Laenge. " * 3)
        for i in range(1, 41)
    ]
    excerpt = _build_red_team_excerpt(_report(claims=claims))

    assert len(excerpt) > 4000
    assert "gekürzt" not in excerpt
    # Auch der einundzwanzigste Claim ist da — die alte Kappung lag bei 20.
    assert "[C1_21]" in excerpt
    assert "[C1_40]" in excerpt


def test_the_thresholds_are_in_the_draft_at_all():
    """Ohne sie kann der Reviewer den 4-gegen-8-Wochen-Widerspruch nicht sehen."""
    excerpt = _build_red_team_excerpt(
        _report(thresholds=[_threshold("pilot_dauer_mitte", 4.0)])
    )
    assert "pilot_dauer_mitte" in excerpt
    assert "4 weeks" in excerpt
    assert "model_proposal" in excerpt


def test_two_thresholds_for_the_same_quantity_stand_side_by_side():
    """Der Referenzfall: Abschnitt 1 fordert vier Wochen, Abschnitt 7 acht."""
    excerpt = _build_red_team_excerpt(
        _report(thresholds=[
            _threshold("pilot_dauer_mitte", 4.0),
            _threshold("th_pilot_duration_mitte", 8.0),
        ])
    )
    assert "4 weeks" in excerpt
    assert "8 weeks" in excerpt


def test_the_id_carries_the_section_so_distant_contradictions_are_attributable():
    excerpt = _build_red_team_excerpt(
        _report(claims=[
            _claim(1, 1, "Ein vierwoechiger Pilotbetrieb genuegt."),
            _claim(7, 3, "Der Pilotbetrieb muss mindestens acht Wochen dauern."),
        ])
    )
    assert "[C1_01]" in excerpt
    assert "[C7_03]" in excerpt


def test_the_prompt_asks_for_contradictory_numbers_and_explains_the_ids():
    """Die Zahlen im Entwurf nuetzen nichts, wenn niemand nach ihnen fragt."""
    assert "operative Zahlen" in _RED_TEAM_USER_TEMPLATE
    assert "C3_02" in _RED_TEAM_USER_TEMPLATE
    assert "gekürzt" not in _RED_TEAM_USER_TEMPLATE.split("{report_excerpt}")[0]


def test_hypotheses_stay_in_the_draft():
    excerpt = _build_red_team_excerpt(
        _report(hypotheses=[
            Hypothesis(id="H1_01", hypothesis_text="Die Schulungsquote bleibt unter 80 Prozent."),
        ])
    )
    assert "[H1_01] [hypothese] Die Schulungsquote" in excerpt


# --- Wenn doch gekuerzt wird -----------------------------------------------

def test_truncation_cuts_at_a_line_boundary_and_says_so():
    """Ein Reviewer, der eine Kuerzung fuer einen Abbruch haelt, meldet Unsinn."""
    long_statement = "Ein sehr ausfuehrlich formulierter Befund. " * 40
    claims = [_claim(1, i, long_statement) for i in range(1, 60)]
    excerpt = _build_red_team_excerpt(_report(claims=claims))

    lines = excerpt.splitlines()
    assert len(excerpt) > _RED_TEAM_EXCERPT_BUDGET * 0.5
    assert lines[-1].startswith("[gekürzt:")
    assert "der Bericht ist vollständig" in lines[-1]
    # Kein halber Satz: jede Inhaltszeile endet so, wie sie gebaut wurde.
    for line in lines[:-1]:
        assert line.rstrip().endswith(long_statement.rstrip())


def test_the_marker_names_how_many_entries_are_missing():
    long_statement = "Ein sehr ausfuehrlich formulierter Befund. " * 40
    claims = [_claim(1, i, long_statement) for i in range(1, 60)]
    excerpt = _build_red_team_excerpt(_report(claims=claims))

    lines = excerpt.splitlines()
    kept = len(lines) - 1
    assert f"{len(claims) - kept} weitere Einträge" in lines[-1]


def test_a_single_oversized_entry_is_never_dropped_silently():
    """Der erste Eintrag bleibt, auch wenn er allein das Budget sprengt.

    Sonst entstuende ein Entwurf, der nur aus der Kuerzungsmarke besteht.
    """
    huge = "x" * (_RED_TEAM_EXCERPT_BUDGET + 1000)
    excerpt = _build_red_team_excerpt(_report(claims=[_claim(1, 1, huge)]))
    assert huge in excerpt
    assert "gekürzt" not in excerpt


def test_an_empty_report_stays_recognisable_as_empty():
    assert _build_red_team_excerpt(_report()) == "(kein Inhalt)"
