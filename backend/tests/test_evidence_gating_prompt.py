"""
Test für Evidence-Gating-Prompt-Block (Sub-Slice M11.7a).

Verifiziert:
1. Der Evidence-Gating-Block ist im Section-Generation-Prompt enthalten.
2. Alle 4 Hedge-Wörter sind aufgelistet.
3. Alle 4 Provenance-Level sind benannt.
4. Wording-Glossar ist sauber (keine Forecast/Prediction/Rehearsal-Vokabel).
"""

import re

from app.services.report_prompts import SECTION_SYSTEM_PROMPT_TEMPLATE


def test_evidence_gating_block_present():
    """Evidence-Gating-Block ist im Section-System-Prompt enthalten."""
    assert "<evidence_gating" in SECTION_SYSTEM_PROMPT_TEMPLATE, (
        "Evidence-gating block not found in SECTION_SYSTEM_PROMPT_TEMPLATE"
    )
    assert "</evidence_gating>" in SECTION_SYSTEM_PROMPT_TEMPLATE, (
        "Evidence-gating closing tag not found"
    )


def test_provenance_levels_present():
    """Alle 4 Provenance-Level sind benannt."""
    required_levels = ["hypothesis", "seed_only", "agent_grounded", "cross_stakeholder"]
    for level in required_levels:
        assert f'name="{level}"' in SECTION_SYSTEM_PROMPT_TEMPLATE, (
            f"Provenance level '{level}' not found in prompt"
        )


def test_hedge_words_present():
    """Alle 4 Hedge-Wörter aus der Liste sind im Prompt."""
    hedge_words = [
        "vermutlich",
        "deutet auf",
        "die Quellenlage spricht für",
        "Indizien legen nahe"
    ]
    for hedge in hedge_words:
        assert hedge in SECTION_SYSTEM_PROMPT_TEMPLATE, (
            f"Hedge word '{hedge}' not found in prompt"
        )


def test_wording_glossar_no_violations():
    """Wording-Glossar v1 ist eingehalten (keine verbotenen Vokabeln in evidence_gating)."""
    # Extrahiere nur den evidence_gating-Block für präzise Prüfung
    match = re.search(
        r"<evidence_gating.*?</evidence_gating>",
        SECTION_SYSTEM_PROMPT_TEMPLATE,
        re.DOTALL
    )
    if not match:
        # Falls Block nicht gefunden, skip (wird von test_evidence_gating_block_present geprüft)
        return

    evidence_block = match.group(0)

    # Verbotene Wörter (case-insensitive)
    forbidden_patterns = [
        r"\bprediction\b",
        r"\brehearse\b",
        r"\brehearsal\b",
        r"god.{0,2}s eye view",
        r"high.?fidelity digital world",
        r"public opinion",
        r"\bforecast\b",
        r"\brevolutionary\b",
        r"\bseamless\b",
    ]

    for pattern in forbidden_patterns:
        matches = re.findall(pattern, evidence_block, re.IGNORECASE)
        assert not matches, (
            f"Wording-Glossar violation found: '{pattern}' in evidence_gating block. "
            f"Matches: {matches}"
        )


def test_negative_examples_contain_wrong_label():
    """Negative-Examples enthalten explizite WRONG-Markierungen (Qualitätssicherung)."""
    assert "WRONG:" in SECTION_SYSTEM_PROMPT_TEMPLATE, (
        "Negative examples section not found or missing WRONG: label"
    )
    assert "FIX:" in SECTION_SYSTEM_PROMPT_TEMPLATE, (
        "Negative examples section not found or missing FIX: label"
    )


def test_source_kind_field_naming():
    """
    Source-Kind-Feld ist mit korrekten Enum-Werten referenziert.
    (Zukunfts-Sicherung für Slice B: forward-compatible naming)
    """
    required_source_kinds = [
        "seed_corpus",
        "agent_quote",
        "graph_relation",
        "inferred"
    ]
    prompt_lower = SECTION_SYSTEM_PROMPT_TEMPLATE.lower()
    for source_kind in required_source_kinds:
        # Prüfe, dass mindestens zwei dieser Werte erwähnt sind
        # (Slice B wird alle vier einführen, aber dieser Slice muss
        # mindestens die ersten zwei korrekt referenzieren)
        pass

    # Aktuelle Assertion: mindestens "seed_corpus" und "agent_quote" sind genannt
    assert "seed_corpus" in SECTION_SYSTEM_PROMPT_TEMPLATE
    assert "agent_quote" in SECTION_SYSTEM_PROMPT_TEMPLATE
