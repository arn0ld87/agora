"""Issue #1012 — ein abgestufter Claim weist seinen Wortlaut aus.

Wird ein Claim nachträglich auf `low` abgestuft, ändert sich nur das Label.
Der `claim_text` und der bereits gerenderte Abschnittstext behalten ihre
Formulierung — oft eine deklarative ohne Hedge, weil das Modell sie unter
`high` geschrieben hat. Der Report besteht die Validierung, transportiert im
Fließtext aber weiter eine Behauptung in einer Sicherheit, die das Label nicht
mehr deckt.

**Der gewählte Weg** (Entscheidung am Issue dokumentiert): die Abstufung
ausweisen, statt generierten Text zu bearbeiten. Dieselbe Linie wie #1160 A
(`confidence_scope`), B (`audit_trail`-Eintrag) und E (`origin`): Agora ändert
nicht, was das Modell geschrieben hat, sondern sagt dem Leser, was er vor sich
hat.

**Was das ausdrücklich nicht leistet:** Der bereits gerenderte Abschnittstext
wird nicht nachgezogen. Eine deklarativ formulierte Passage bleibt deklarativ
formuliert. Sie steht dann aber nicht mehr unkommentiert da — Claim-Tabelle
und Evidenzstatus weisen sie aus, und der Evidenzstatus steht vor dem
narrativen Text.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.contracts.report_contract import EvidenceRecordModel
from app.contracts.report_v3 import Claim, ReportV3
from app.services.report_agent.evidence import (
    TEXT_CONFIDENCE_DOWNGRADE_EVENT,
    auto_downgrade_unsupported_high_claims,
    text_confidence_label_of,
)
from app.services.report_agent.markdown_renderer import (
    render_claim_table,
    render_evidence_status,
)

EVIDENCE_ID = "ev_00000000000000000000000000000001"


def _agent_quote(group: str) -> dict:
    return {
        "type": "agent_interview",
        "source": "agent-log",
        "snippet": f"Aussage aus {group}.",
        "quote": f"Original-Zitat aus {group}.",
        "match_score": 0.9,
        "supports_claim": True,
        "source_kind": "agent_quote",
        "persona_stakeholder_group": group,
    }


def _high_claim_with_one_group() -> dict:
    """Ein ``high``-Claim, dem die zweite Stakeholder-Gruppe fehlt.

    Genau die Konstellation, die ``auto_downgrade_unsupported_high_claims``
    abstuft — und in der der Wortlaut unter ``high`` entstanden ist.
    """
    return {
        "claim_id": "claim_01",
        "claim_text": "Die Zielgruppe lehnt den Preis ab.",
        "confidence_label": "high",
        "confidence_score": 0.88,
        "evidence": [_agent_quote("Belegschaft")],
        "audit_trail": [],
    }


class TestDowngradeIsRecorded:
    def test_die_ausgangsstufe_wird_festgehalten(self) -> None:
        [claim] = auto_downgrade_unsupported_high_claims([_high_claim_with_one_group()])

        assert claim["confidence_label"] != "high", "Vorbedingung: es wurde abgestuft"
        assert text_confidence_label_of(claim) == "high"

    def test_der_wortlaut_bleibt_unveraendert(self) -> None:
        """Der Kern der Entscheidung: kein Eingriff in generierten Text."""
        original = _high_claim_with_one_group()
        [claim] = auto_downgrade_unsupported_high_claims([dict(original)])

        assert claim["claim_text"] == original["claim_text"]

    def test_ein_zweiter_downgrade_ueberschreibt_die_ausgangsstufe_nicht(self) -> None:
        """Bei mehrfacher Abstufung bleibt die *ursprüngliche* Stufe stehen.

        Unter ihr ist der Wortlaut entstanden. Ein zwischenzeitliches
        ``medium`` wäre selbst schon abgestuft und damit die falsche Referenz —
        genau das Idempotenzproblem, an dem der Weg über ein Hedge-Präfix
        (Option 3 im Issue) gescheitert wäre.
        """
        [once] = auto_downgrade_unsupported_high_claims([_high_claim_with_one_group()])
        once["confidence_label"] = "high"  # erneut angehoben, erneut abgestuft
        [twice] = auto_downgrade_unsupported_high_claims([once])

        entries = [
            entry
            for entry in twice["audit_trail"]
            if entry.get("event") == TEXT_CONFIDENCE_DOWNGRADE_EVENT
        ]
        assert len(entries) == 1
        assert entries[0]["text_confidence_label"] == "high"

    def test_ein_nicht_abgestufter_claim_bekommt_keinen_eintrag(self) -> None:
        """Gegenprobe — sonst trüge jeder Claim eine Abstufung, die keine ist."""
        claim = {
            "claim_id": "claim_02",
            "claim_text": "Zwei Gruppen stuetzen diese Aussage.",
            "confidence_label": "high",
            "confidence_score": 0.88,
            "evidence": [_agent_quote("Belegschaft"), _agent_quote("Leitung")],
            "audit_trail": [],
        }

        [result] = auto_downgrade_unsupported_high_claims([claim])

        assert result["confidence_label"] == "high"
        assert text_confidence_label_of(result) is None

    def test_ein_claim_ohne_audit_trail_stuerzt_nicht_ab(self) -> None:
        claim = _high_claim_with_one_group()
        del claim["audit_trail"]

        [result] = auto_downgrade_unsupported_high_claims([claim])

        assert text_confidence_label_of(result) == "high"


def _evidence_index() -> dict:
    """Der ReportV3-Validator verlangt, dass jede evidence_ref aufloesbar ist."""
    return {
        EVIDENCE_ID: EvidenceRecordModel(
            evidence_id=EVIDENCE_ID,
            producer_key="briefing.md#absatz-1",
            type="graph_fact",  # type: ignore[arg-type]
            source="briefing.md",
            snippet="Beleg aus dem Seed-Dokument.",
        )
    }


def _claim(
    confidence: str, text_confidence: str | None, claim_id: str = "C1_01"
) -> Claim:
    # Issue #1341: ReportV3 lehnt kollidierende Claim-IDs ab. Wo ein Test
    # mehrere Claims in denselben Report legt, muss er sie unterscheiden —
    # vorher trugen sie unbemerkt alle dieselbe ID.
    return Claim(
        id=claim_id,
        statement="Die Zielgruppe lehnt den Preis ab.",
        evidence_refs=[EVIDENCE_ID],
        confidence=confidence,  # type: ignore[arg-type]
        aggregation_basis="persona",
        text_confidence=text_confidence,  # type: ignore[arg-type]
    )


class TestRendering:
    def test_die_tabelle_weist_den_wortlaut_aus(self) -> None:
        table = render_claim_table([_claim("low", "high")])

        assert "low (Wortlaut: high)" in table

    def test_ein_nicht_abgestufter_claim_bleibt_schlicht(self) -> None:
        table = render_claim_table([_claim("high", None)])

        assert "Wortlaut" not in table

    def test_gleiche_stufe_wird_nicht_als_abstufung_gezeigt(self) -> None:
        """Defensiv: stimmen beide Werte überein, ist nichts abgestuft."""
        table = render_claim_table([_claim("high", "high")])

        assert "Wortlaut" not in table

    def test_der_evidenzstatus_nennt_die_zahl_vor_dem_fliesstext(self) -> None:
        """Der Block steht vor dem narrativen Text — genau dort gehört der
        Hinweis hin, weil der Fließtext selbst nicht nachgezogen wird."""
        report = ReportV3(
            schema_version=4,
            report_id="rep-1012",
            generated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
            evidence_index=_evidence_index(),
            claims=[
                _claim("low", "high", claim_id="C1_01"),
                _claim("high", None, claim_id="C1_02"),
            ],
        )

        status = render_evidence_status(report)

        assert "Nachtraeglich abgestuft" in status
        assert "| Nachtraeglich abgestuft | 1 |" in status

    def test_ohne_abgestufte_claims_steht_dort_null(self) -> None:
        report = ReportV3(
            schema_version=4,
            report_id="rep-1012",
            generated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
            evidence_index=_evidence_index(),
            claims=[_claim("high", None)],
        )

        assert "| Nachtraeglich abgestuft | 0 |" in render_evidence_status(report)


def test_bestandsartefakte_ohne_das_feld_laden_unveraendert() -> None:
    """Additiv — kein Bestandsreport wird ungültig."""
    claim = Claim(
        id="claim_01",
        statement="Bestandsclaim ohne das neue Feld.",
        evidence_refs=[EVIDENCE_ID],
        confidence="medium",
        aggregation_basis="persona",
    )
    assert claim.text_confidence is None
