"""
M11.7d — Snapshot-Eval-Suite für ADR-0002 Evidence-Gating.

Testet die vier Provenance-Stufen (seed_only, agent_grounded, cross_stakeholder,
verified) gegen fixierte Bad-/Good-Case-Fixtures. Schützt die fünf Hartanker
aus ADR-0002 vor stillem Regression.

Refs: docs/decisions/0002-evidence-gating.md
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts.report_contract import (
    ConfidenceLabel,
    EvidenceSourceKind,
    ReportClaimModel,
)
from app.services.report_agent.evidence import auto_downgrade_unsupported_high_claims

# ---------------------------------------------------------------------------
# Pfade
# ---------------------------------------------------------------------------

_FIXTURES = Path(__file__).parent / "fixtures"
_BAD = _FIXTURES / "bad"
_GOOD = _FIXTURES / "good"
_SNAPSHOTS = Path(__file__).parent / "snapshots"


# ---------------------------------------------------------------------------
# Hilfsfunktionen + Fixtures
# ---------------------------------------------------------------------------

_HEDGE_SNAPSHOT = _SNAPSHOTS / "evidence-gating-hedge-words.txt"


def _load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    # _comment-Felder entfernen — ReportClaimModel hat extra="forbid"
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _read_hedge_words() -> list[str]:
    """Liest die Hedge-Wörter direkt aus dem ADR-0002-Anker-2-Snapshot."""
    return [
        w.strip()
        for w in _HEDGE_SNAPSHOT.read_text(encoding="utf-8").splitlines()
        if w.strip()
    ]


def _matched_hedge_words(text: str, hedge_words: list[str]) -> list[str]:
    """Gibt alle Hedge-Wörter zurück, die case-insensitive im Text vorkommen."""
    text_lower = text.lower()
    return [hw for hw in hedge_words if hw.lower() in text_lower]


@pytest.fixture(scope="module")
def hedge_words() -> list[str]:
    """Pytest-Fixture für die geladenen Hedge-Wörter (modul-weit gecached)."""
    return _read_hedge_words()


# ---------------------------------------------------------------------------
# Snapshot-Drift-Guard: Anker 2 (Hedge-Wörter) + Anker 3 (Enum-Werte)
# ---------------------------------------------------------------------------


def test_hedge_snapshot_anchor_vollstaendig():
    """Anker 2: Hedge-Snapshot enthält genau die vier ADR-0002-Pflicht-Wörter.

    Dieser Test liest die Datei direkt (nicht via Fixture), weil er gerade
    die Snapshot-Datei selbst gegen Drift absichert.
    """
    words = _read_hedge_words()
    expected = {
        "vermutlich",
        "deutet auf",
        "die Quellenlage spricht für",
        "Indizien legen nahe",
    }
    assert set(words) == expected, (
        f"Hedge-Snapshot hat sich verändert — ADR-0002 Anker 2 verletzt. "
        f"Erwartet: {sorted(expected)}, Gefunden: {sorted(words)}"
    )


def test_evidence_source_kind_enum_werte():
    """Anker 3: EvidenceSourceKind enthält genau die vier ADR-0002-Provenance-Stufen."""
    werte = {e.value for e in EvidenceSourceKind}
    erwartet = {"seed_corpus", "agent_quote", "graph_relation", "inferred"}
    assert werte == erwartet, (
        f"EvidenceSourceKind-Enum hat sich verändert — ADR-0002 Anker 3 verletzt. "
        f"Erwartet: {sorted(erwartet)}, Gefunden: {sorted(werte)}"
    )


def test_confidence_label_enum_stufen():
    """Drift-Guard: ConfidenceLabel enthält die vier erwarteten Stufen."""
    stufen = {e.value for e in ConfidenceLabel}
    assert stufen == {"low", "medium", "high", "verified"}


# ---------------------------------------------------------------------------
# BAD Cases — ValidationError erwartet
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture_name,match_fragment", [
    (
        "evidence_gating_single_stakeholder_high.json",
        "mindestens 2",
    ),
    (
        "evidence_gating_inferred_in_high.json",
        "inferred",
    ),
    (
        "evidence_gating_verified_low_match_score.json",
        "0.85",
    ),
])
def test_bad_fixture_wirft_validation_error(fixture_name: str, match_fragment: str):
    """ReportClaimModel muss für jeden Bad-Case einen ValidationError werfen.

    Prüft: Anker 4 (cross_stakeholder_for_high), Anker 5
    (reject_inferred_in_high_confidence), verified_needs_strong_match.
    """
    data = _load(_BAD / fixture_name)
    with pytest.raises(ValidationError, match=match_fragment):
        ReportClaimModel.model_validate(data)


def test_bad_seed_only_missing_hedge_kein_validator_aber_kein_hedge(
    hedge_words: list[str],
):
    """seed_only-Claim ohne Hedge-Wort: ReportClaimModel akzeptiert es (kein
    Text-Validator im Pydantic-Contract — Hedge-Pflicht ist LLM-Prompt-seitig
    via Anker 1 gesichert). Test verifiziert, dass kein silenter Hedge-Check
    entfernt wurde UND dass der Claim-Text tatsächlich kein Hedge-Wort hat.

    Ist das Ergebnis eines zukünftigen Validator-Upgrades ein ValidationError,
    muss dieser Test auf die parametrisierten bad-Cases oben migriert werden.
    """
    data = _load(_BAD / "evidence_gating_seed_only_missing_hedge.json")

    # Instanziierung muss aktuell durchlaufen (kein Pydantic-Validator für Text-Hedge)
    claim = ReportClaimModel.model_validate(data)

    # Snapshot-Assertion: kein Hedge-Wort im Claim-Text — das ist die Regression,
    # die wir einfrieren
    matched = _matched_hedge_words(claim.claim_text, hedge_words)
    assert matched == [], (
        f"Fixture 'seed_only_missing_hedge' enthält jetzt ein Hedge-Wort ({matched}). "
        "Das Fixture muss aktualisiert werden, damit der Bad-Case korrekt bleibt."
    )

    # Zusatz: confidence=low ist die einzig legale Stufe für seed_only
    assert claim.confidence_label == ConfidenceLabel.low


# ---------------------------------------------------------------------------
# Auto-Downgrade-Pfad: single_stakeholder_high → medium
# ---------------------------------------------------------------------------


def test_auto_downgrade_single_stakeholder_high_zu_medium():
    """auto_downgrade_unsupported_high_claims senkt confidence=high auf medium,
    wenn cross_stakeholder-Anforderung nicht erfüllt ist (1 Gruppe statt ≥2).

    Verifiziert den Präventiv-Pfad aus evidence.py, der den Report-Save vor
    hartem ValidationError schützt.
    """
    data = _load(_BAD / "evidence_gating_single_stakeholder_high.json")
    downgraded = auto_downgrade_unsupported_high_claims([data])
    assert len(downgraded) == 1
    assert downgraded[0]["confidence_label"] == "medium", (
        "auto_downgrade hat high nicht auf medium gesenkt, obwohl nur 1 "
        "Stakeholder-Gruppe vorhanden ist."
    )


def test_auto_downgrade_cross_stakeholder_bleibt_high():
    """auto_downgrade darf high NICHT senken, wenn ≥2 Gruppen vorhanden sind."""
    data = _load(_GOOD / "evidence_gating_cross_stakeholder_high.json")
    downgraded = auto_downgrade_unsupported_high_claims([data])
    assert downgraded[0]["confidence_label"] == "high"


# ---------------------------------------------------------------------------
# GOOD Cases — Instanziierung muss durchlaufen, Label bleibt erhalten
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture_name,expected_label", [
    ("evidence_gating_cross_stakeholder_high.json", ConfidenceLabel.high),
    ("evidence_gating_agent_grounded_medium.json", ConfidenceLabel.medium),
    ("evidence_gating_seed_only_with_hedge.json", ConfidenceLabel.low),
])
def test_good_fixture_instanziierung_erfolgreich(
    fixture_name: str, expected_label: ConfidenceLabel
):
    """ReportClaimModel muss für jeden Good-Case valide instanziiert werden,
    und confidence_label muss unverändert bleiben.
    """
    data = _load(_GOOD / fixture_name)
    claim = ReportClaimModel.model_validate(data)
    assert claim.confidence_label == expected_label, (
        f"confidence_label wurde verändert: erwartet={expected_label.value}, "
        f"erhalten={claim.confidence_label.value}"
    )


def test_good_seed_only_with_hedge_enthaelt_hedge_wort(hedge_words: list[str]):
    """seed_only-Fixture mit Hedge muss tatsächlich ein Hedge-Wort tragen.

    Sichert ab, dass das Fixture nicht ohne Hedge editiert wurde.
    """
    data = _load(_GOOD / "evidence_gating_seed_only_with_hedge.json")
    matched = _matched_hedge_words(data["claim_text"], hedge_words)
    assert matched, (
        f"Good-Fixture 'seed_only_with_hedge' enthält kein Hedge-Wort mehr. "
        f"Claim-Text: '{data['claim_text']}'. Hedge-Wörter: {hedge_words}"
    )


def test_good_cross_stakeholder_hat_zwei_verschiedene_gruppen():
    """Direkte Invariante: cross_stakeholder-Fixture trägt ≥2 verschiedene
    persona_stakeholder_group-Werte in agent_quote-Evidence.
    """
    data = _load(_GOOD / "evidence_gating_cross_stakeholder_high.json")
    gruppen = {
        e["persona_stakeholder_group"]
        for e in data["evidence"]
        if e.get("source_kind") == "agent_quote" and e.get("supports_claim")
    }
    assert len(gruppen) >= 2, (
        f"cross_stakeholder-Fixture hat weniger als 2 Stakeholder-Gruppen: {gruppen}"
    )


def test_good_agent_grounded_hat_quote_und_seed():
    """agent_grounded-Fixture muss mind. 1 agent_quote + 1 seed_corpus enthalten."""
    data = _load(_GOOD / "evidence_gating_agent_grounded_medium.json")
    kinds = {e["source_kind"] for e in data["evidence"]}
    assert "agent_quote" in kinds, "agent_grounded-Fixture fehlt agent_quote-Evidence."
    assert "seed_corpus" in kinds, "agent_grounded-Fixture fehlt seed_corpus-Evidence."
