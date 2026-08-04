"""Slice 3 (Issue #495): Hypothesen-Cap + Dedup.

Cases:
1. 8 Hypothesen, 2 textuell sehr ähnlich (> 0.88 Token-Set-Ratio) → nach Dedup 7,
   dann split: 5 visible + 2 appendix.
2. 3 Hypothesen → 3 visible, 0 appendix.
3. 12 Hypothesen, alle disjunkt → 5 visible + 7 appendix.
4. Confidence-Sort: absteigende Reihenfolge verifizieren.
5. Re-ID nach Dedup eindeutig + deterministisch.
6. Issue #1073: >50 disjunkte Hypothesen im Appendix → hart auf 50 gekappt,
   verbleibende Einträge sind die mit der höchsten Confidence.
"""
from __future__ import annotations

from typing import Any

import pytest


def _make_hyp(
    idx: int,
    text: str,
    confidence: float = 0.5,
    suggested_evidence: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "hypothesis_id": f"hypothesis_{idx:02d}",
        "hypothesis_text": text,
        "rationale": f"Rationale {idx}",
        "suggested_evidence": suggested_evidence or [],
        "confidence_score": confidence,
    }


# ---------------------------------------------------------------------------
# Case 1: 8 Hypothesen, 2 sehr ähnlich → Dedup → 7 → 5 visible + 2 appendix
# ---------------------------------------------------------------------------

def test_case1_dedup_reduces_then_split() -> None:
    from app.services.report_agent.hypothesis_cap import dedup_and_cap_hypotheses

    hyps = [
        _make_hyp(1, "Die Zielgruppe reagiert skeptisch auf den neuen Marktauftritt der Marke.", 0.7),
        _make_hyp(2, "Jüngere Nutzer bevorzugen mobile Zugangswege für die App.", 0.65),
        _make_hyp(3, "Preissensitivität ist ein zentraler Faktor bei der Kaufentscheidung.", 0.6),
        _make_hyp(4, "Vertrauen in die Marke korreliert mit Weiterempfehlungsrate.", 0.55),
        _make_hyp(5, "Nachhaltigkeitsaspekte sind für die Kernzielgruppe wichtig.", 0.5),
        _make_hyp(6, "Datenschutzbedenken beeinflussen die Akzeptanz.", 0.45),
        _make_hyp(7, "Regionale Unterschiede im DACH-Raum sind signifikant.", 0.4),
        # Sehr ähnlich zu hyp 1: token_set_ratio ≈ 95 (über Threshold 88)
        _make_hyp(8, "Die Zielgruppe reagiert skeptisch auf den neuen Marktauftritt der Firma.", 0.35),
    ]

    visible, appendix = dedup_and_cap_hypotheses(hyps)

    # Nach Dedup: 8 - 1 Duplikat = 7
    total = len(visible) + len(appendix)
    assert total == 7, f"Erwartet 7 nach Dedup, bekommen {total}"

    # Split: max 5 visible
    assert len(visible) == 5, f"Erwartet 5 visible, bekommen {len(visible)}"
    assert len(appendix) == 2, f"Erwartet 2 appendix, bekommen {len(appendix)}"


# ---------------------------------------------------------------------------
# Case 2: 3 Hypothesen → 3 visible, 0 appendix
# ---------------------------------------------------------------------------

def test_case2_few_hypotheses_no_appendix() -> None:
    from app.services.report_agent.hypothesis_cap import dedup_and_cap_hypotheses

    hyps = [
        _make_hyp(1, "Erste disjunkte Hypothese über Markttrends.", 0.8),
        _make_hyp(2, "Zweite Hypothese zu Nutzerpräferenzen im B2B-Bereich.", 0.6),
        _make_hyp(3, "Dritte Hypothese zu regionalen Unterschieden.", 0.4),
    ]

    visible, appendix = dedup_and_cap_hypotheses(hyps)

    assert len(visible) == 3
    assert len(appendix) == 0


# ---------------------------------------------------------------------------
# Case 3: 12 disjunkte Hypothesen → 5 visible + 7 appendix
# ---------------------------------------------------------------------------

_DISJOINT_TEXTS = [
    "Preissensitivität ist entscheidend für die Kaufbereitschaft der Kernzielgruppe.",
    "Datenschutzbedenken hemmen die Nutzung digitaler Gesundheitsangebote erheblich.",
    "Markenvertrauen korreliert stark mit der Zahlungsbereitschaft im Premium-Segment.",
    "Nachhaltigkeitszertifizierungen erhöhen die Akzeptanz bei Millennials signifikant.",
    "Regionale Unterschiede zwischen Nord- und Süddeutschland prägen den Absatz.",
    "Mobile-First-Nutzer konvertieren schlechter auf Desktop-optimierten Landingpages.",
    "Kundendienst-Reaktionszeit beeinflusst die Kundenbindungsrate maßgeblich.",
    "B2B-Entscheider benötigen technische Spezifikationen vor einer Kaufentscheidung.",
    "Influencer-Marketing verliert bei der Zielgruppe 50+ an Wirkung.",
    "Abonnement-Modelle stoßen im ländlichen Raum auf strukturellen Widerstand.",
    "Cross-Selling-Potenzial wird durch mangelnde Onboarding-Qualität blockiert.",
    "Wettbewerber-Positionierung im Premiumsegment schränkt eigene Preiserhöhungen ein.",
]


def test_case3_twelve_disjoint_split() -> None:
    from app.services.report_agent.hypothesis_cap import dedup_and_cap_hypotheses

    hyps = [
        _make_hyp(i + 1, text, 0.5)
        for i, text in enumerate(_DISJOINT_TEXTS)
    ]

    visible, appendix = dedup_and_cap_hypotheses(hyps)

    assert len(visible) == 5
    assert len(appendix) == 7


# ---------------------------------------------------------------------------
# Case 4: Confidence-Sort — absteigende Reihenfolge
# ---------------------------------------------------------------------------

def test_case4_sort_by_confidence_descending() -> None:
    from app.services.report_agent.hypothesis_cap import dedup_and_cap_hypotheses

    hyps = [
        _make_hyp(1, "Niedrige Konfidenz-Hypothese über einfaches Thema.", 0.2),
        _make_hyp(2, "Hohe Konfidenz-Hypothese über wichtiges Thema.", 0.9),
        _make_hyp(3, "Mittlere Konfidenz-Hypothese über mittleres Thema.", 0.5),
        _make_hyp(4, "Zweithöchste Konfidenz-Hypothese über Marktlage.", 0.8),
        _make_hyp(5, "Dritthöchste Konfidenz-Hypothese über Trends.", 0.7),
        _make_hyp(6, "Sechste Hypothese mit sehr niedriger Konfidenz.", 0.1),
    ]

    visible, appendix = dedup_and_cap_hypotheses(hyps)

    # visible hat max 5, also hyps 2,4,5,3,1 (sorted desc by score)
    assert len(visible) == 5
    assert len(appendix) == 1

    scores = [h.get("confidence_score", 0.0) for h in visible]
    assert scores == sorted(scores, reverse=True), (
        f"visible nicht absteigend sortiert: {scores}"
    )

    # Appendix enthält die niedrigste Konfidenz
    assert appendix[0].get("confidence_score") == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# Case 5: Re-ID nach Dedup eindeutig + deterministisch
# ---------------------------------------------------------------------------

def test_case5_reid_unique_and_deterministic() -> None:
    from app.models.report import Report, ReportStatus
    from app.services.report_agent.manager import ReportManager

    # Zwei Sections: section 1 hat 6 disjunkte Hypothesen,
    # section 2 hat 4 Hypothesen mit 1 Paar sehr ähnlicher Texte.
    evidence_map = {
        "sections": [
            {
                "section_index": 1,
                "section_title": "Abschnitt Eins",
                "section_summary": "Zusammenfassung eins",
                "claims": [],
                "data_gaps": [],
                "hypotheses": [
                    {
                        "hypothesis_id": "hypothesis_01",
                        "hypothesis_text": f"Hypothese eins {i}: eigenständiges Thema.",
                        "rationale": "Rationale",
                        "suggested_evidence": [],
                        "confidence_score": 0.5,
                    }
                    for i in range(1, 6)
                ],
                "hypotheses_appendix": [
                    {
                        "hypothesis_id": "hypothesis_06",
                        "hypothesis_text": "Sechste Hypothese im Appendix-Slot.",
                        "rationale": "Rationale",
                        "suggested_evidence": [],
                        "confidence_score": 0.3,
                    }
                ],
            },
            {
                "section_index": 2,
                "section_title": "Abschnitt Zwei",
                "section_summary": "Zusammenfassung zwei",
                "claims": [],
                "data_gaps": [],
                "hypotheses": [
                    {
                        "hypothesis_id": "hypothesis_01",
                        "hypothesis_text": "Alpha-Hypothese über Zielgruppen.",
                        "rationale": "Rationale",
                        "suggested_evidence": [],
                        "confidence_score": 0.6,
                    },
                    {
                        "hypothesis_id": "hypothesis_02",
                        "hypothesis_text": "Beta-Hypothese über Marktanteile.",
                        "rationale": "Rationale",
                        "suggested_evidence": [],
                        "confidence_score": 0.4,
                    },
                ],
                "hypotheses_appendix": [],
            },
        ]
    }

    report = Report(
        report_id="r_reid_test",
        simulation_id="s1",
        graph_id="g1",
        simulation_requirement="Re-ID Test",
        status=ReportStatus.COMPLETED,
    )

    v3 = ReportManager.build_report_v3(report, evidence_map, report_mode="balanced")

    ids = [h.id for h in v3.hypotheses]

    # IDs sind eindeutig
    assert len(ids) == len(set(ids)), f"Doppelte IDs: {ids}"

    # IDs sind deterministisch: visible aus section 1 → H1_01..H1_05
    # appendix aus section 1 → HA1_01
    # visible aus section 2 → H2_01, H2_02
    expected_ids = ["H1_01", "H1_02", "H1_03", "H1_04", "H1_05", "HA1_01", "H2_01", "H2_02"]
    assert ids == expected_ids, f"IDs nicht deterministisch. Erwartet {expected_ids}, bekommen {ids}"


# ---------------------------------------------------------------------------
# Case 6 (Issue #1073): 56 disjunkte Hypothesen → Appendix hart auf 50 gekappt
# ---------------------------------------------------------------------------

def test_case6_appendix_hard_capped_at_fifty() -> None:
    """ReportSectionModel.hypotheses_appendix erlaubt max_length=50
    (report_contract.py:412). dedup_and_cap_hypotheses muss den Appendix
    entsprechend kappen, sonst schlägt die EvidenceMapModel-Validierung fehl.
    """
    import hashlib

    from app.services.report_agent.hypothesis_cap import dedup_and_cap_hypotheses

    total = 56
    hyps = [
        _make_hyp(
            i,
            hashlib.sha256(f"disjoint-topic-{i}".encode()).hexdigest(),
            confidence=1.0 - (i * 0.01),
        )
        for i in range(total)
    ]

    visible, appendix = dedup_and_cap_hypotheses(hyps)

    assert len(visible) == 5
    assert len(appendix) == 50, (
        f"Appendix muss auf 50 (Contract-Limit) gekappt sein, bekommen {len(appendix)}"
    )

    # Appendix enthält exakt die 50 nach visible nächsthöchsten Confidence-Werte,
    # nicht die schwächsten (Sortierung ist absteigend, Cap verwirft am Ende).
    expected_appendix_scores = sorted(
        (h["confidence_score"] for h in hyps), reverse=True
    )[5:55]
    appendix_scores = [h["confidence_score"] for h in appendix]
    assert appendix_scores == pytest.approx(expected_appendix_scores)


def test_case7_production_shaped_hypotheses_pass_contract_after_cap() -> None:
    """Der produktionsnahe Fall: Hypothesen OHNE ``confidence_score``.

    Die drei produktiven Erzeuger (``agent.py`` zweimal,
    ``text_verification.py::as_hypothesis``) setzen das Feld nicht — es ist im
    strict-Contract ``ReportSectionHypothesisModel`` gar nicht vorgesehen.
    ``test_case6`` liefert es und prueft damit eine Rangfolge, die es in der
    Produktion so nicht gibt (Codex-Review zu PR #1078).

    Dieser Test deckt deshalb das ab, was der Fix tatsaechlich garantieren
    muss: der Appendix haelt das Contract-Limit ein, und das Ergebnis laeuft
    durch ``EvidenceMapModel`` — genau die Validierung, an der die
    Reportgenerierung nach 35 Minuten abbrach.

    Welche 50 der 56 ueberleben, ist hier bewusst NICHT festgeschrieben: ohne
    Ranking-Signal ist die Auswahl nicht sinnvoll pruefbar. Das ist der
    Gegenstand von Issue #1083, nicht dieses Fixes.
    """
    import hashlib

    from app.contracts.report_contract import EvidenceMapModel
    from app.services.report_agent.hypothesis_cap import dedup_and_cap_hypotheses

    total = 56
    hyps = [
        {
            "hypothesis_id": f"hypothesis_{i:02d}",
            "hypothesis_text": hashlib.sha256(
                f"produktionsnahe-hypothese-{i}".encode()
            ).hexdigest(),
            "rationale": f"Ohne stuetzende Quelle uebernommen ({i}).",
            "suggested_evidence": [],
        }
        for i in range(total)
    ]

    visible, appendix = dedup_and_cap_hypotheses(hyps)

    assert len(visible) == 5
    assert len(appendix) == 50
    assert not any("confidence_score" in h for h in visible + appendix), (
        "Der Cap darf kein Feld ergaenzen, das der strict-Contract verbietet"
    )

    # Der eigentliche Regressionsnachweis: genau diese Validierung brach vorher.
    EvidenceMapModel.model_validate({
        "report_id": "report_0000000000ab",
        "simulation_id": "sim_0000000000ab",
        "sections": [{
            "section_index": 1,
            "section_title": "Produktionsnaher Abschnitt",
            "section_summary": "Hypothesen ohne Evidence.",
            "claims": [],
            "hypotheses": visible,
            "hypotheses_appendix": appendix,
        }],
    })
