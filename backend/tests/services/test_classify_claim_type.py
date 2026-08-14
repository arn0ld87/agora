"""Issue #1301 — Heuristische Claim-Typ-Klassifikation.

``classify_claim_type`` ordnet einen Claim-Chunk vor der
Evidence-Bindung einer :class:`app.contracts.report_contract.ClaimType`-
Kategorie zu (als ``str``, s. Moduldoc in ``report_agent/sections.py`` fuer
die Begruendung, warum kein Enum-Import). ``empirical`` bleibt der Default —
nur explizite Cues stufen auf die anderen drei Typen um.
"""
from __future__ import annotations

import pytest

from app.services.report_agent.sections import classify_claim_type


@pytest.mark.parametrize(
    "text",
    [
        "Das Angebot ueberzeugt 68 Prozent der befragten Personen.",
        "Der Betriebsrat kritisiert die kurze Ankuendigungsfrist.",
        "",
        "   ",
    ],
)
def test_defaults_to_empirical(text: str) -> None:
    assert classify_claim_type(text) == "empirical"


@pytest.mark.parametrize(
    "text",
    [
        "## Zusammenfassung der Ergebnisse",
        "### Reibungspunkte",
        "**Wichtiger Hinweis**",
    ],
)
def test_headings_and_standalone_bold_are_structural(text: str) -> None:
    assert classify_claim_type(text) == "structural"


@pytest.mark.parametrize(
    "text",
    [
        "Wir empfehlen einen stufenweisen Rollout ab Q3.",
        "Der Betriebsrat sollte fruehzeitig eingebunden werden.",
        "Es ist ratsam, zunaechst ein Pilotprojekt zu starten.",
    ],
)
def test_recommendation_cues(text: str) -> None:
    assert classify_claim_type(text) == "recommendation"


@pytest.mark.parametrize(
    "text",
    [
        "Zusammenfassend laesst sich sagen, dass die Reaktionen gemischt ausfallen.",
        "Dies deutet darauf hin, dass die Skepsis primaer bei der IT-Leitung liegt.",
        "Im Gesamtbild zeigt sich eine klare Polarisierung zwischen den Gruppen.",
    ],
)
def test_analytical_cues(text: str) -> None:
    assert classify_claim_type(text) == "analytical"


def test_structural_check_runs_before_cue_checks() -> None:
    """Eine Ueberschrift, die zufaellig auch ein Empfehlungswort enthaelt,
    bleibt structural — die Formprüfung (Heading/Bold) geht cue-basierten
    Textprüfungen vor."""
    assert classify_claim_type("## Empfehlung") == "structural"
