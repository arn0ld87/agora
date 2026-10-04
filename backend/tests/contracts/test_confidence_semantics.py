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

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.contracts import EvidenceMapModel
from app.contracts.report_contract import (
    ConfidenceLabel,
    EntailmentVerdict,
    EvidenceSourceKind,
    EvidenceType,
    ReportClaimModel,
)
from app.contracts.report_v3 import Claim as ReportV3Claim
from app.services.report_agent import ReportAgent
from app.services.report_agent.manager import _derive_confidence_scope
from app.services.report_agent.markdown_renderer import render_claim_table
from app.services.report_agent.schemas import SectionKeyTakeaway, SectionMetadata
from app.services.report_agent.takeaway_confidence import (
    cap_section_key_takeaways,
    cap_takeaway_confidence,
)


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
    with pytest.raises(ValidationError, match="unterschiedlichen Stakeholder-Rollenfamilien"):
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
        _agent_quote("Verwaltung"),
        {"source_kind": "seed_corpus", "supports_claim": False},
    ]
    assert _derive_confidence_scope(evidence) == "simulation_consensus"
    # #1766: mit nur einer stuetzenden Stimme bleibt es eine Einzelstimme.
    assert _derive_confidence_scope(evidence[:1] + evidence[2:]) == "simulation_single_voice"


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


def test_die_claim_tabelle_nennt_eine_einzelstimme_nicht_konsens() -> None:
    """#1766: Eine einzelne simulierte Perspektive steht nicht als Konsens da."""
    table = render_claim_table([_v3_claim("simulation_single_voice")])
    assert "Einzelstimme (Simulation)" in table
    assert "Simulationskonsens" not in table


def test_der_vertrag_nimmt_die_einzelstimme_an_und_laedt_den_altwert_weiter() -> None:
    """Neuer Wert gueltig; Berichte mit ``simulation_consensus`` bleiben lesbar."""
    for scope in ("simulation_single_voice", "simulation_consensus", "evidence"):
        claim = ReportV3Claim.model_validate(
            {
                "id": "claim_01",
                "statement": "Die Zielgruppe reagiert zurueckhaltend auf den Preis.",
                "evidence_refs": ["ev_00000000000000000000000000000000"],
                "confidence": "low",
                "aggregation_basis": "persona",
                "confidence_scope": scope,
            }
        )
        assert claim.confidence_scope == scope


def test_bestandsartefakte_ohne_das_feld_behaupten_keinen_geltungsbereich() -> None:
    """Nicht erfasst ist nicht dasselbe wie Simulationskonsens."""
    table = render_claim_table([_v3_claim(None)])
    assert "Simulationskonsens" not in table
    assert "Quellenbindung" not in table


# ---------------------------------------------------------------------------
# #1766 — Kernaussagen tragen kein eigenes Confidence-Urteil
# ---------------------------------------------------------------------------

_SEED_EVIDENCE_ID = "ev_00000000000000000000000000000001"


def _claim_dict(label: str, *, claim_id: str = "claim_01") -> dict:
    return {
        "claim_id": claim_id,
        "claim_text": "Ein ausreichend langer Claim-Text fuer den Test.",
        "confidence_label": label,
        "confidence_score": 0.5,
        "evidence": [{"evidence_id": _SEED_EVIDENCE_ID, "supports_claim": True}],
        "audit_trail": [],
    }


def _takeaway(confidence: object, *, scope: str = "simulation_consensus") -> dict:
    return {
        "statement": "Eine Kernaussage des Abschnitts.",
        "confidence": confidence,
        "confidence_scope": scope,
    }


def test_key_takeaway_confidence_never_exceeds_claim_label() -> None:
    """Kernaussage ``high`` neben nur ``low``-Claims wird ``low`` (Lauf report_a8fa9ff9fad0)."""
    low = [_claim_dict("low")]
    assert cap_takeaway_confidence([_takeaway("high")], low)[0]["confidence"] == "low"

    # Ein schwaecheres eigenes Urteil bleibt: min(), nie ein Anheben.
    medium = [_claim_dict("medium")]
    assert cap_takeaway_confidence([_takeaway("low")], medium)[0]["confidence"] == "low"
    assert cap_takeaway_confidence([_takeaway("high")], medium)[0]["confidence"] == "medium"

    # ``verified`` zaehlt als hoechste Takeaway-Stufe.
    verified = [_claim_dict("verified")]
    assert cap_takeaway_confidence([_takeaway("high")], verified)[0]["confidence"] == "high"

    # Der staerkste Claim des Abschnitts zaehlt, nicht der schwaechste.
    mixed = [_claim_dict("low"), _claim_dict("high", claim_id="claim_02")]
    assert cap_takeaway_confidence([_takeaway("high")], mixed)[0]["confidence"] == "high"


@pytest.mark.parametrize("claims", [[], [_claim_dict("speculative")]])
def test_ein_abschnitt_ohne_tragenden_claim_hat_keine_kernaussagen_confidence(
    claims: list,
) -> None:
    capped = cap_takeaway_confidence([_takeaway("high"), _takeaway("low")], claims)
    assert [t["confidence"] for t in capped] == [None, None]


def test_der_deckel_veraendert_die_eingabe_nicht_und_laesst_fremde_eintraege_durch() -> None:
    original = [_takeaway("high"), "kein-dict"]
    capped = cap_takeaway_confidence(original, [_claim_dict("low")])
    assert original[0]["confidence"] == "high"
    assert capped[0]["confidence"] == "low"
    assert capped[1] == "kein-dict"
    assert cap_takeaway_confidence(None, [_claim_dict("low")]) == []


def test_die_kernaussage_behauptet_keine_quellenbindung_ohne_gebundenen_claim() -> None:
    index = {
        _SEED_EVIDENCE_ID: {"evidence_id": _SEED_EVIDENCE_ID, "source_kind": "seed_corpus"}
    }
    bound = cap_takeaway_confidence(
        [_takeaway("low", scope="evidence"), _takeaway("low", scope="empirical")],
        [_claim_dict("low")],
        evidence_index=index,
    )
    # Gebunden: ``evidence`` bleibt, ``empirical`` wird nie bestaetigt.
    assert [t["confidence_scope"] for t in bound] == ["evidence", "evidence"]

    unbound = cap_takeaway_confidence(
        [_takeaway("low", scope="evidence"), _takeaway("low", scope="empirical")],
        [_claim_dict("low")],
        evidence_index={},
    )
    assert [t["confidence_scope"] for t in unbound] == ["simulation_consensus"] * 2


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("high", "high"),
        (" HIGH ", "high"),
        ("hoch", "high"),
        ("Mittel", "medium"),
        ("very high", None),
        ("verified", None),
        ("", None),
        (None, None),
        (3, None),
    ],
)
def test_ein_ungueltiger_llm_wert_kippt_den_abschnitt_nicht(raw: object, expected: object) -> None:
    """Das Enum im Schema, die Toleranz im Validator: kein ``ValidationError``."""
    assert SectionKeyTakeaway(statement="Aussage", confidence=raw).confidence == expected  # type: ignore[arg-type]
    metadata = SectionMetadata.model_validate(
        {"section_title": "Abschnitt", "key_takeaways": [{"statement": "A", "confidence": raw}]}
    )
    assert metadata.key_takeaways[0].confidence == expected


def test_das_llm_schema_deklariert_confidence_als_enum_mit_null() -> None:
    prop = SectionKeyTakeaway.model_json_schema()["properties"]["confidence"]
    options = prop["anyOf"]
    assert {"enum": ["low", "medium", "high"], "type": "string"} in options
    assert {"type": "null"} in options


def test_altbestand_mit_freien_confidence_strings_laedt_und_wird_idempotent_gedeckelt() -> None:
    """Persistierte ``evidence_map.json`` vor #1766: freie Strings, kein Migrationszwang."""
    payload = {
        "schema_version": 3,
        "report_id": "r-alt",
        "simulation_id": "sim-alt",
        "evidence_index": {},
        "global_evidence_refs": [],
        "degradation_log": [],
        "sections": [
            {
                "section_index": 1,
                "section_title": "Alter Abschnitt",
                "section_summary": "Zusammenfassung des alten Abschnitts.",
                "claims": [],
                "hypotheses": [],
                "hypotheses_appendix": [],
                "data_gaps": [],
                "structured_metadata": {
                    "key_takeaways": [
                        {"statement": "A", "confidence": "high"},
                        {"statement": "B", "confidence": "sehr hoch, wirklich"},
                        {"statement": "C"},
                    ]
                },
                "generation_failed": False,
            }
        ],
    }
    loaded = EvidenceMapModel.model_validate(payload).model_dump(mode="json")
    stored = loaded["sections"][0]["structured_metadata"]["key_takeaways"]
    assert [t.get("confidence") for t in stored] == ["high", "sehr hoch, wirklich", None]

    assert cap_section_key_takeaways(loaded, 1) == 2
    capped = loaded["sections"][0]["structured_metadata"]["key_takeaways"]
    assert [t["confidence"] for t in capped] == [None, None, None]
    # Zweiter Lauf aendert nichts mehr.
    assert cap_section_key_takeaways(loaded, 1) == 0
    EvidenceMapModel.model_validate(loaded)


class _FakeAgentForTakeaways:
    """Minimaler Double fuer den ungebundenen Aufruf von ``_save_evidence_section``."""

    def __init__(self, *, evidence_map: dict, claims: list, takeaways: list) -> None:
        self.evidence_map = evidence_map
        self._pending_prose_hypotheses: dict = {}
        self._pending_section_metadata: dict = {2: {"key_takeaways": takeaways}}
        self._collect_simulation_evidence_items = lambda: []
        self._build_claims_for_section = lambda content, heartbeat=None: []
        self._finalize_section_claims = lambda raw: (claims, [], [], [])
        self._truncate = lambda text, length: text[:length] if isinstance(text, str) else text
        self._section_dedup_check = lambda **kwargs: None
        self._init_evidence_map = lambda report_id: None
        self._active_section_evidence: list = []
        self._active_section_unresolved_evidence: list = []
        self._remap_active_evidence_ids = (
            lambda id_remap: ReportAgent._remap_active_evidence_ids(self, id_remap)
        )


def _persist_section_two(claims: list, takeaways: list) -> dict:
    """Laeuft durch die echte Persistenz und gibt die geschriebene Section zurueck."""
    agent = _FakeAgentForTakeaways(
        evidence_map={
            "schema_version": 3,
            "report_id": "r1",
            "simulation_id": "sim1",
            "evidence_index": {
                _SEED_EVIDENCE_ID: {
                    "evidence_id": _SEED_EVIDENCE_ID,
                    "producer_key": "seed_dokument_01#takeaway-fixture",
                    "type": "graph_fact",
                    "source": "seed_dokument_01",
                    "snippet": "Beleg-Snippet aus dem Seed-Korpus.",
                    "source_kind": "seed_corpus",
                }
            },
            "global_evidence_refs": [],
            "sections": [],
            "degradation_log": [],
        },
        claims=claims,
        takeaways=takeaways,
    )
    with patch("app.services.report_agent.ReportManager.save_evidence_map") as mock_save:
        ReportAgent._save_evidence_section(
            agent, "r1", 2, "Zweite Sektion", "Ausfuehrlicher Abschnittstext fuer den Test."
        )
    mock_save.assert_called_once()
    persisted = mock_save.call_args[0][1]
    return next(s for s in persisted["sections"] if s["section_index"] == 2)


def test_die_persistierte_map_traegt_die_gedeckelten_kernaussagen() -> None:
    """Der Weg, der tatsaechlich schreibt: ``high`` neben einem ``low``-Claim wird ``low``."""
    section = _persist_section_two(
        claims=[_claim_dict("low")],
        takeaways=[
            _takeaway("high", scope="evidence"),
            _takeaway("medium"),
            _takeaway("low"),
        ],
    )
    saved = section["structured_metadata"]["key_takeaways"]
    assert [t["confidence"] for t in saved] == ["low", "low", "low"]
    assert saved[0]["confidence_scope"] == "evidence"  # seed-gebundener Claim


def test_die_persistierte_map_laesst_ohne_claim_keine_kernaussagen_confidence_stehen() -> None:
    section = _persist_section_two(
        claims=[],
        takeaways=[_takeaway("high", scope="evidence"), _takeaway("medium")],
    )
    saved = section["structured_metadata"]["key_takeaways"]
    assert [t["confidence"] for t in saved] == [None, None]
    assert saved[0]["confidence_scope"] == "simulation_consensus"


def test_der_deckel_sieht_die_claims_nach_der_reparatur() -> None:
    """Ein seed-only ``medium``-Claim verletzt ``agent_grounded_for_medium`` (ADR-0002).

    Die Persistenz stuft ihn auf ``low`` ab oder verschiebt ihn in die
    Hypothesen. Massgeblich ist, was danach uebrig ist — nicht der Entwurf.
    """
    section = _persist_section_two(
        claims=[_claim_dict("medium")],
        takeaways=[_takeaway("high")],
    )
    remaining = [c["confidence_label"] for c in section["claims"]]
    saved = section["structured_metadata"]["key_takeaways"][0]["confidence"]
    assert saved == (remaining[0] if remaining else None)
    assert remaining in ([], ["low"])
