"""Issue #1160 A/B/C — Confidence-Semantik sichtbar und belastbar machen.

Drei Befunde aus dem Evidence-Chain-Audit (`docs/paper/agora-evidence-chain-audit.md`,
AS_OF 2026-08-09), Sign-off des Nutzers vom selben Tag:

* **A** — ``confidence_scope`` wird verbindlich mitgerendert. Ein Claim, den
  ausschliesslich simulierte Stakeholder stuetzen, erreicht dasselbe Label wie
  ein quellengebundener; die Skala allein unterscheidet das nicht. Additiv,
  kein ADR-0002-Eingriff.
* **B** — ``verified`` haengt bisher allein an ``match_score >= 0.85``, also an
  Retrieval-Aehnlichkeit. Die Schwelle bleibt notwendige, wird aber keine
  hinreichende Bedingung mehr: es braucht zusaetzlich ein Entailment-Urteil
  ``SUPPORTED``. Bestand ohne ``entailment`` wird auf ``high`` abgestuft statt
  abgelehnt.
* **C** — ``persona_stakeholder_group`` ist eine freie Zeichenkette. Ohne
  Normalisierung liefern zwei Schreibweisen derselben Gruppe die zwei
  "unterschiedlichen" Gruppen, die ADR-0002 Anker 4 verlangt.

B und C sind Verschaerfungen von ADR-0002 Anker 4 — zulaessig laut
Sicherheitsgrenze des Issues, die ausschliesslich Schwaechungen ausschliesst.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.report_contract import (
    ConfidenceLabel,
    EntailmentVerdict,
    EvidenceSourceKind,
    EvidenceType,
    ReportClaimModel,
)
from app.contracts.report_v3 import Claim as ReportV3Claim
from app.services.report_agent.manager import _derive_confidence_scope
from app.services.report_agent.markdown_renderer import render_claim_table


def _agent_quote(
    group: str,
    *,
    match_score: float = 0.9,
    entailment: EntailmentVerdict | None = EntailmentVerdict.SUPPORTED,
) -> dict:
    """Ein stuetzendes agent_quote-Item — der Bauteil, den Anker 4 zaehlt."""
    return {
        "type": EvidenceType.agent_interview.value,
        "source": f"agent-log:{group}",
        "snippet": f"Aussage aus der Gruppe {group}.",
        "quote": f"Originalzitat aus {group}.",
        "match_score": match_score,
        "supports_claim": True,
        "source_kind": EvidenceSourceKind.agent_quote.value,
        "persona_stakeholder_group": group,
        **({"entailment": entailment.value} if entailment is not None else {}),
    }


def _claim(label: ConfidenceLabel, evidence: list[dict]) -> ReportClaimModel:
    return ReportClaimModel(
        claim_id="claim_01",
        claim_text="Die Zielgruppe reagiert zurueckhaltend auf den Preis.",
        confidence_label=label,
        confidence_score=0.9,
        evidence=evidence,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# C — Stakeholder-Gruppen normalisiert vergleichen
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("first", "second", "warum"),
    [
        ("Buerger", "buerger", "nur Gross-/Kleinschreibung"),
        ("Buerger", "  Buerger  ", "nur fuehrender/abschliessender Whitespace"),
        ("Junge Familien", "junge   familien", "beides zugleich"),
    ],
)
def test_high_faellt_bei_derselben_gruppe_in_zwei_schreibweisen(
    first: str, second: str, warum: str
) -> None:
    """Zwei Schreibweisen einer Gruppe sind eine Gruppe, keine zwei.

    Vor der Normalisierung war genau das der Weg, ``high`` aus einer einzigen
    Stakeholder-Gruppe zu erzeugen — ohne dass ein Validator anschlug.
    """
    with pytest.raises(ValidationError, match="unterschiedlichen Stakeholder-Gruppen"):
        _claim(ConfidenceLabel.high, [_agent_quote(first), _agent_quote(second)])


def test_high_bleibt_bei_zwei_echt_verschiedenen_gruppen_gueltig() -> None:
    """Gegenprobe: die Normalisierung darf nicht ueber ihr Ziel hinausschiessen."""
    claim = _claim(
        ConfidenceLabel.high,
        [_agent_quote("Buerger"), _agent_quote("Verwaltung")],
    )
    assert claim.confidence_label == ConfidenceLabel.high


def test_fehlermeldung_zeigt_den_originalwortlaut() -> None:
    """Die Meldung nennt die Schreibweisen der Quelle, nicht die Vergleichsform.

    Sonst liest sich der Fehler wie ein Widerspruch: normalisierte Werte sehen
    identisch aus, waehrend die Meldung "mindestens 2 unterschiedliche" fordert.
    """
    with pytest.raises(ValidationError) as exc:
        _claim(ConfidenceLabel.high, [_agent_quote("Buerger"), _agent_quote("buerger")])
    text = str(exc.value)
    assert "'Buerger'" in text and "'buerger'" in text
    assert "ohne Gross-/Kleinschreibung" in text


# ---------------------------------------------------------------------------
# B — verified verlangt ein Entailment-Urteil, nicht nur Retrieval-Naehe
# ---------------------------------------------------------------------------


def test_verified_bleibt_mit_supported_entailment_ueber_der_schwelle() -> None:
    claim = _claim(
        ConfidenceLabel.verified,
        [_agent_quote("Buerger"), _agent_quote("Verwaltung")],
    )
    assert claim.confidence_label == ConfidenceLabel.verified


def test_verified_faellt_wenn_das_entailment_die_aussage_nicht_traegt() -> None:
    """``RELATED_ONLY`` heisst "gleiches Thema", nicht "belegt"."""
    with pytest.raises(ValidationError, match="entailment=SUPPORTED"):
        _claim(
            ConfidenceLabel.verified,
            [
                _agent_quote("Buerger", entailment=EntailmentVerdict.RELATED_ONLY),
                _agent_quote("Verwaltung", entailment=EntailmentVerdict.RELATED_ONLY),
            ],
        )


def test_verified_verlangt_schwelle_und_urteil_am_selben_item() -> None:
    """Getrennte Items duerfen die Bedingung nicht zusammenstueckeln.

    Sonst liefert ein thematisch passendes ``RELATED_ONLY``-Item die 0.85 und
    ein schwach gerantes zweites Item das Urteil — genau die Vermischung von
    Retrieval-Wert und Beleggrad, die der Befund adressiert.
    """
    with pytest.raises(ValidationError, match="entailment=SUPPORTED"):
        _claim(
            ConfidenceLabel.verified,
            [
                _agent_quote(
                    "Buerger", match_score=0.95, entailment=EntailmentVerdict.RELATED_ONLY
                ),
                _agent_quote(
                    "Verwaltung", match_score=0.40, entailment=EntailmentVerdict.SUPPORTED
                ),
            ],
        )


def test_bestand_ohne_entailment_wird_auf_high_abgestuft_statt_abgelehnt() -> None:
    """Artefakte aus der Zeit vor der zweiten Binding-Stufe bleiben lesbar.

    Sign-off 2026-08-09: "Bestand wird ehrlicher, nicht kaputt."
    """
    claim = _claim(
        ConfidenceLabel.verified,
        [_agent_quote("Buerger", entailment=None), _agent_quote("Verwaltung", entailment=None)],
    )
    assert claim.confidence_label == ConfidenceLabel.high
    downgrades = [e for e in claim.audit_trail if e.get("event") == "confidence_downgraded"]
    assert len(downgrades) == 1
    assert downgrades[0]["reason"] == "no_entailment_recorded"


def test_das_downgrade_ist_idempotent() -> None:
    """Erneutes Laden darf weder erneut abstufen noch den Trail aufblaehen."""
    first = _claim(
        ConfidenceLabel.verified,
        [_agent_quote("Buerger", entailment=None), _agent_quote("Verwaltung", entailment=None)],
    )
    second = ReportClaimModel.model_validate(first.model_dump())
    assert second.confidence_label == ConfidenceLabel.high
    assert len(
        [e for e in second.audit_trail if e.get("event") == "confidence_downgraded"]
    ) == 1


def test_die_match_score_schwelle_gilt_weiterhin() -> None:
    """Die alte Bedingung bleibt notwendig — sie ist nur nicht mehr hinreichend."""
    with pytest.raises(ValidationError, match="match_score >= 0.85"):
        _claim(
            ConfidenceLabel.verified,
            [
                _agent_quote("Buerger", match_score=0.5),
                _agent_quote("Verwaltung", match_score=0.5),
            ],
        )


# ---------------------------------------------------------------------------
# A — Geltungsbereich ableiten und rendern
# ---------------------------------------------------------------------------


def test_nur_agent_quotes_ergeben_simulationskonsens() -> None:
    scope = _derive_confidence_scope([_agent_quote("Buerger"), _agent_quote("Verwaltung")])
    assert scope == "simulation_consensus"


@pytest.mark.parametrize(
    "source_kind",
    ["seed_corpus", "graph_relation", "web_source"],
)
def test_eine_quellengebundene_evidence_ergibt_evidence(source_kind: str) -> None:
    evidence = [
        _agent_quote("Buerger"),
        {"source_kind": source_kind, "supports_claim": True},
    ]
    assert _derive_confidence_scope(evidence) == "evidence"


def test_nicht_stuetzende_quellenevidenz_begruendet_keine_quellenbindung() -> None:
    """``supports_claim`` ist dieselbe Bedingung, aus der ``evidence_refs`` entsteht.

    Ein widersprechendes oder nur verwandtes Dokument darf den Claim nicht als
    quellengebunden ausweisen.
    """
    evidence = [
        _agent_quote("Buerger"),
        {"source_kind": "seed_corpus", "supports_claim": False},
    ]
    assert _derive_confidence_scope(evidence) == "simulation_consensus"


@pytest.mark.parametrize("kaputt", [None, "kein-array", [], [42, "text"]])
def test_ableitung_faellt_bei_unbrauchbarer_evidence_auf_simulationskonsens(
    kaputt: object,
) -> None:
    """Im Zweifel die schwaechere Aussage — nie ungeprueft Quellenbindung behaupten."""
    assert _derive_confidence_scope(kaputt) == "simulation_consensus"


def _v3_claim(scope: str | None) -> ReportV3Claim:
    return ReportV3Claim(
        id="claim_01",
        statement="Die Zielgruppe reagiert zurueckhaltend auf den Preis.",
        evidence_refs=["ev_00000000000000000000000000000000"],
        confidence="high",
        aggregation_basis="persona",
        confidence_scope=scope,  # type: ignore[arg-type]
    )


def test_die_claim_tabelle_zeigt_den_geltungsbereich_im_klartext() -> None:
    """"high" allein verraet nicht, ob Quellen oder Agenten dahinterstehen."""
    table = render_claim_table([_v3_claim("simulation_consensus")])
    assert "Geltungsbereich" in table
    assert "Simulationskonsens" in table

    assert "Quellenbindung" in render_claim_table([_v3_claim("evidence")])


def test_bestandsartefakte_ohne_das_feld_behaupten_keinen_geltungsbereich() -> None:
    """Nicht erfasst ist nicht dasselbe wie Simulationskonsens."""
    table = render_claim_table([_v3_claim(None)])
    assert "Simulationskonsens" not in table
    assert "Quellenbindung" not in table
