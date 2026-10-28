"""Claim- und Ledger-Level Contracts für Report-Contract v2 (Pydantic v2).

Ausgelagert aus ``report_contract.py`` — alle Symbole werden dort vollständig
re-exportiert.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from .report_evidence_contract import (
    EVIDENCE_ID_PATTERN,
    MIN_ACTION_VOICES_FOR_MEDIUM,
    _STRICT,
    ClaimEvidenceBindingModel,
    ClaimType,
    ConfidenceLabel,
    EntailmentVerdict,
    EvidenceItemModel,
    EvidenceSourceKind,
    counts_for_confidence,
    has_two_action_voices,
)


def _stakeholder_group_key(value: Optional[str]) -> str:
    """Vergleichsschluessel fuer ``persona_stakeholder_group`` (Issue #1160 C).

    Der Cross-Stakeholder-Validator zaehlt unterschiedliche Werte dieses
    Feldes. Ohne Normalisierung gelten ``"Buerger"``, ``"buerger"`` und
    ``"Buerger "`` als drei Gruppen — ein ``high``-Label liesse sich damit
    aus einer einzigen Stakeholder-Gruppe erzeugen, indem dieselbe
    Bezeichnung unterschiedlich geschrieben wird.

    Normalisiert wird ausschliesslich fuer den Vergleich (casefold +
    Whitespace-Kollaps, Sign-off 2026-08-09). Der gespeicherte Wortlaut
    bleibt unveraendert, damit Anzeige und Export weiterhin die Schreibweise
    der Quelle zeigen. Eine kontrollierte Taxonomie ist ausdruecklich nicht
    Teil dieser Aenderung.

    Das ist eine Verschaerfung von ADR-0002 Anker 4, keine Schwaechung:
    die Zahl unterscheidbarer Gruppen kann dadurch nur sinken.
    """
    if not value:
        return ""
    return " ".join(value.split()).casefold()


#: Auffangtypen, die keine Rollenfamilie bezeichnen (Issue #1248, CodeRabbit
#: PR #1260). Die Ontologie fuehrt ``Person`` und ``Organization`` bewusst als
#: breite Fallback-Typen. Sie als Rollenfamilie zu zaehlen wuerde zwei
#: voellig verschiedene Stakeholder — etwa einen Bildungstraeger und eine
#: Aufsichtsbehoerde, beide als ``Organization`` klassifiziert — zu einer
#: Stimme verschmelzen und damit die Cross-Stakeholder-Stuetzung unmoeglich
#: machen. Genau die Verwechslung von Auffangtopf und Label ist der Grund,
#: warum die Typbindung in #1247 nicht getragen hat.
#:
#: Fuer diese Typen bleibt der Berufstitel die Vergleichsgroesse — das
#: bisherige Verhalten. Das Label wirkt nur dort, wo es tatsaechlich eine
#: Rolle bezeichnet.
_GENERIC_ENTITY_TYPES: frozenset[str] = frozenset({
    "person", "organization", "entity", "node", "unknown", "other",
})


def _role_family_key(item: Any) -> str:
    """Zaehlschluessel fuer ``cross_stakeholder_for_high`` (Issue #1248).

    Bis zu diesem Slice zaehlte der Validator ``persona_stakeholder_group`` —
    einen frei formulierten Berufstitel. Normalisiert wurde nur Schreibweise
    und Whitespace, also zaehlten Wortwahl- und Genusvarianten derselben Rolle
    als verschiedene Gruppen. Gemessen an zwei Referenzlaeufen:

        4x  "Umschueler im IT-Bereich (Teilnehmer)"
        2x  "Teilnehmer einer IT-Umschulung (Retrainee)"   <- dieselbe Rolle

        "Festangestellte Dozentin fuer IT-Umschulungen und Betriebsratsmitglied"
        "Festangestellter Fachdozent fuer IT-Umschulungen und Betriebsratsmitglied"

    Der Anker verlangt zwei distinkte Gruppen fuer ``high``. Es genuegte also
    eine andere Formulierung desselben Berufs, um eine Aussage als breit
    gestuetzt einzustufen, obwohl nur eine Perspektive gesprochen hat.

    Gezaehlt wird jetzt das kontrollierte Rollenfamilien-Label. Faellt es —
    etwa bei Artefakten aus aelteren Laeufen —, bleibt der Jobtitel der
    Vergleichswert; das ist das bisherige Verhalten und nie strenger als
    vorher, aber auch nie lockerer.

    Verschaerfung von ADR-0002 Anker 4, keine Schwaechung: die Zahl
    unterscheidbarer Gruppen kann dadurch nur sinken.
    """
    family = getattr(item, "persona_role_family", None)
    if family and _stakeholder_group_key(family) not in _GENERIC_ENTITY_TYPES:
        return f"family:{_stakeholder_group_key(family)}"
    return f"title:{_stakeholder_group_key(getattr(item, 'persona_stakeholder_group', None))}"


class ReportClaimModel(BaseModel):
    model_config = _STRICT

    claim_id: str = Field(pattern=r"^claim_\d{2,}$")
    claim_text: str = Field(min_length=8)
    confidence_label: ConfidenceLabel
    confidence_score: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceItemModel] = Field(default_factory=list, max_length=10)
    audit_trail: list[dict[str, Any]] = Field(default_factory=list)
    notes: Optional[str] = None
    # Issue #1400: ``None`` = vor der Typisierung entstanden; so validieren
    # Alt-Artefakte unveraendert weiter.
    claim_type: Optional[ClaimType] = None

    @model_validator(mode="after")
    def non_low_claims_need_evidence(self) -> "ReportClaimModel":
        # P2.1: Jeder Claim oberhalb von low braucht mindestens einen
        # nachvollziehbaren Evidence-Anker. Low-Orphans bleiben fuer alte
        # Artefakte lesbar, werden beim Schreiben aber in hypotheses/data_gaps
        # geroutet.
        if self.confidence_label not in (ConfidenceLabel.speculative, ConfidenceLabel.low) and not self.evidence:
            raise ValueError(
                f"Label '{self.confidence_label.value}' verlangt mindestens "
                "eine Evidence mit nachvollziehbarem Anker."
            )
        return self


    @model_validator(mode="after")
    def verified_needs_strong_match(self) -> "ReportClaimModel":
        # Schwelle aus confidence_calculator.py-Kommentar: verified nur ab match_score >= 0.85
        if self.confidence_label != ConfidenceLabel.verified:
            return self
        top = max((e.match_score or 0.0) for e in self.evidence) if self.evidence else 0.0
        if top < 0.85:
            raise ValueError(
                f"Label 'verified' verlangt mindestens eine Evidence mit "
                f"match_score >= 0.85. Top: {top:.2f}"
            )

        # Issue #1160 B (Sign-off 2026-08-09): ``match_score`` ist ein
        # Retrieval-Wert — er beantwortet "gleiches Thema?", nicht "belegt?"
        # (siehe evidence_binder.py). Die 0.85-Schwelle bleibt notwendige,
        # ist aber keine hinreichende Bedingung mehr: das oberste Label
        # verlangt zusaetzlich ein Entailment-Urteil ``SUPPORTED`` — und
        # zwar am selben Item. Sonst koennte ein thematisch passendes, aber
        # nur ``RELATED_ONLY``-eingestuftes Item die Schwelle liefern,
        # waehrend das Entailment von einem schwach gerankten zweiten Item
        # kommt; genau diese Trennung soll das Label sichtbar machen.
        if any(
            (e.match_score or 0.0) >= 0.85 and e.entailment == EntailmentVerdict.SUPPORTED
            for e in self.evidence
        ):
            return self

        if all(e.entailment is None for e in self.evidence):
            # Bestandsdaten aus der Zeit vor der zweiten Binding-Stufe tragen
            # ueberhaupt kein ``entailment``. Die werden beim Laden auf
            # ``high`` abgestuft statt abgelehnt: der Bestand wird ehrlicher,
            # nicht unlesbar. Das Downgrade ist idempotent — beim naechsten
            # Laden greift der Validator nicht mehr, weil das Label dann
            # ``high`` lautet.
            self.confidence_label = ConfidenceLabel.high
            self.audit_trail = [
                *self.audit_trail,
                {
                    "event": "confidence_downgraded",
                    "from": ConfidenceLabel.verified.value,
                    "to": ConfidenceLabel.high.value,
                    "reason": "no_entailment_recorded",
                    "issue": "1160-B",
                },
            ]
            return self

        raise ValueError(
            "Label 'verified' verlangt eine Evidence, die match_score >= 0.85 "
            "UND entailment=SUPPORTED traegt. Vorhandene Urteile: "
            f"{sorted({e.entailment.value for e in self.evidence if e.entailment})}."
        )

    @model_validator(mode="after")
    def reject_orphan_high_confidence(self) -> "ReportClaimModel":
        # Anti-Dekorations-Regel: keine high/verified ohne supports_claim=True
        if self.confidence_label in (ConfidenceLabel.high, ConfidenceLabel.verified):
            if not any(e.supports_claim for e in self.evidence):
                raise ValueError(
                    f"Label '{self.confidence_label.value}' verlangt mindestens "
                    f"eine Evidence mit supports_claim=True."
                )
        return self

    @model_validator(mode="after")
    def cross_stakeholder_for_high(self) -> "ReportClaimModel":
        # ADR-0002 Anker 4 (Sub-Slice M11.7b): high/verified verlangt agent_quote-
        # Evidence aus mindestens 2 unterschiedlichen Stakeholder-Gruppen.
        # Nur supports_claim=True zählt — widersprechende Quotes (auch aus
        # verschiedenen Gruppen) dürfen ein high-Label nicht rechtfertigen
        # (Gemini-Followup PR #343).
        if self.confidence_label not in (ConfidenceLabel.high, ConfidenceLabel.verified):
            return self
        supporting = [
            e
            for e in self.evidence
            if e.source_kind == EvidenceSourceKind.agent_quote
            and e.supports_claim
            and e.persona_stakeholder_group
        ]
        # Issue #1160 C: verglichen wird normalisiert (siehe
        # ``_stakeholder_group_key``), gemeldet wird der Originalwortlaut —
        # sonst zeigt die Meldung zwei scheinbar verschiedene Eintraege und
        # behauptet gleichzeitig, es sei nur eine Gruppe.
        # Issue #1248: gezaehlt wird das Rollenfamilien-Label, nicht der
        # Berufstitel. Zwei Formulierungen derselben Rolle sind eine Gruppe.
        groups = {_role_family_key(e) for e in supporting}
        if len(groups) < 2:
            raw_groups = sorted({e.persona_stakeholder_group or "" for e in supporting})
            raw_families = sorted({e.persona_role_family or "" for e in supporting if e.persona_role_family})
            raise ValueError(
                f"Label '{self.confidence_label.value}' verlangt unterstützende "
                f"agent_quote-Evidence (supports_claim=True) aus mindestens 2 "
                f"unterschiedlichen Stakeholder-Rollenfamilien. Verglichen wird "
                f"das Rollenfamilien-Label, nicht der Berufstitel — zwei "
                f"Formulierungen derselben Rolle sind eine Gruppe. Verglichen "
                f"wird ohne Gross-/Kleinschreibung und ohne "
                f"Whitespace-Unterschiede. "
                f"Rollenfamilien: {raw_families if raw_families else '∅'}. "
                f"Berufstitel: {raw_groups if raw_groups else '∅'}."
            )
        return self

    @model_validator(mode="after")
    def reject_inferred_in_high_confidence(self) -> "ReportClaimModel":
        # ADR-0002 Anker 5 (Sub-Slice M11.7b): high/verified duldet keine
        # source_kind=inferred-Evidence (Anti-Halluzinations-Regel).
        if self.confidence_label not in (ConfidenceLabel.high, ConfidenceLabel.verified):
            return self
        if any(e.source_kind == EvidenceSourceKind.inferred for e in self.evidence):
            raise ValueError(
                f"Label '{self.confidence_label.value}' duldet keine source_kind=inferred-Evidence."
            )
        return self

    @model_validator(mode="after")
    def agent_grounded_for_medium(self) -> "ReportClaimModel":
        # ADR-0002 Stufe agent_grounded (Issue #906 Defekt 1): medium verlangt
        # mind. 1 agent_quote- UND mind. 1 seed_corpus-Evidence. Seed-only-Claims
        # (ausschließlich seed_corpus) müssen low lauten; reine agent_quote ohne
        # Korpusbezug sind ebenfalls nicht agent_grounded. supports_claim ist
        # für medium nicht Pflicht (nur für high/verified). ADR-0002 Z. 54 fordert
        # zusätzlich ein nicht-leeres Quote-Feld für die agent_quote-Evidence —
        # ein zusammengefasstes Interview ohne Original-Zitat trägt kein medium
        # (Codex PR-Review #961 P2). Bisher passte ein seed_only-Claim mit Label
        # medium unbeanstandet — die Regel hing nur am Modellgehorsam. Der
        # Validator ist das Auffangnetz (ADR-0002 Risiko).
        #
        # ADR-0002-Nachtrag 2026-10-10 (#1778): Alternative zur Komposition —
        # stützende agent_action-Evidence von mind. zwei verschiedenen Stimmen
        # (voice_key). high/verified bleiben unberührt (Anker 4 und 5).
        if self.confidence_label != ConfidenceLabel.medium:
            return self
        has_agent_quote = any(
            e.source_kind == EvidenceSourceKind.agent_quote and e.quote
            for e in self.evidence
        )
        has_seed_corpus = any(
            e.source_kind == EvidenceSourceKind.seed_corpus for e in self.evidence
        )
        has_action_voices = has_two_action_voices(
            (e.source_kind, e.voice_key) for e in self.evidence if e.supports_claim
        )
        if not ((has_agent_quote and has_seed_corpus) or has_action_voices):
            raise ValueError(
                f"Label 'medium' verlangt Evidence aus mind. 1 agent_quote "
                f"(mit nicht-leerem quote-Feld, ADR-0002 Z. 54) UND mind. 1 "
                f"seed_corpus (ADR-0002 Stufe agent_grounded) ODER stützende "
                f"agent_action-Evidence von mind. {MIN_ACTION_VOICES_FOR_MEDIUM} "
                f"verschiedenen Stimmen (voice_key). "
                f"Gefunden: agent_quote={has_agent_quote}, "
                f"seed_corpus={has_seed_corpus}, "
                f"zwei_aktionsstimmen={has_action_voices}."
            )
        return self

    @model_validator(mode="after")
    def graph_origin_carries_no_confidence(self) -> "ReportClaimModel":
        # ADR-0022 §4 (#1808): Evidence aus von Hand angelegten oder
        # bearbeiteten Graph-Elementen zählt für keine Confidence-Stufe. Ein
        # Claim darf sein Label behalten, wenn er die bestehenden Regeln auch
        # OHNE diese Evidence erfüllt — er darf es nie DURCH sie erreichen.
        #
        # Zusätzlicher Validator neben den ADR-0002-Ankern 4 und 5, die
        # textlich unverändert bleiben. Geprüft wird nicht mit einer zweiten,
        # gespiegelten Regelmenge, sondern mit denselben Validatoren: der Claim
        # wird ohne die Handarbeits-Evidence noch einmal validiert. Die
        # Rekursion endet sofort, weil die Kopie keine solche Evidence trägt.
        if self.confidence_label in (ConfidenceLabel.speculative, ConfidenceLabel.low):
            return self
        counted = [e for e in self.evidence if counts_for_confidence(e)]
        if len(counted) == len(self.evidence):
            return self
        excluded = len(self.evidence) - len(counted)
        try:
            without_hand_made = ReportClaimModel(
                claim_id=self.claim_id,
                claim_text=self.claim_text,
                confidence_label=self.confidence_label,
                confidence_score=self.confidence_score,
                evidence=counted,
                claim_type=self.claim_type,
            )
        except ValueError as exc:
            raise ValueError(
                f"Label '{self.confidence_label.value}' wird nur mit manueller "
                f"oder bearbeiteter Graph-Evidence erreicht ({excluded} Item(s) "
                "mit graph_origin). Solche Evidence zählt für keine "
                f"Confidence-Stufe (ADR-0022). Ohne sie: {exc}"
            ) from exc
        if without_hand_made.confidence_label != self.confidence_label:
            # ``verified_needs_strong_match`` stuft Bestand ohne Entailment
            # beim Laden auf ``high`` ab. Trägt nur die Handarbeit das
            # SUPPORTED-Urteil, ist ``verified`` ohne sie nicht gedeckt.
            raise ValueError(
                f"Label '{self.confidence_label.value}' ist ohne die manuelle "
                "oder bearbeitete Graph-Evidence nur als "
                f"'{without_hand_made.confidence_label.value}' gedeckt (ADR-0022)."
            )
        return self


class IndexedReportClaimModel(BaseModel):
    """Claim-Shape der EvidenceMap v3 mit referenzierten Bindings."""

    model_config = _STRICT

    claim_id: str = Field(pattern=r"^claim_\d{2,}$")
    claim_text: str = Field(min_length=8)
    confidence_label: ConfidenceLabel
    confidence_score: float = Field(ge=0.0, le=1.0)
    evidence: list[ClaimEvidenceBindingModel] = Field(default_factory=list, max_length=10)
    audit_trail: list[dict[str, Any]] = Field(default_factory=list)
    notes: Optional[str] = None
    claim_type: Optional[ClaimType] = None  # Issue #1400, siehe ReportClaimModel

    @model_validator(mode="after")
    def require_binding_for_non_low_claim(self) -> "IndexedReportClaimModel":
        if self.confidence_label not in (ConfidenceLabel.speculative, ConfidenceLabel.low) and not self.evidence:
            raise ValueError(
                f"Label '{self.confidence_label.value}' verlangt mindestens ein Evidence-Binding."
            )
        return self

    @model_validator(mode="after")
    def require_strong_supported_binding(self) -> "IndexedReportClaimModel":
        if self.confidence_label == ConfidenceLabel.verified:
            top = max((item.match_score or 0.0) for item in self.evidence)
            if top < 0.85:
                raise ValueError("Label 'verified' verlangt match_score >= 0.85.")
        if self.confidence_label in (ConfidenceLabel.high, ConfidenceLabel.verified):
            if not any(item.supports_claim for item in self.evidence):
                raise ValueError(
                    f"Label '{self.confidence_label.value}' verlangt supports_claim=True."
                )
        return self


class EvidenceDegradationModel(BaseModel):
    """Maschinenlesbares Protokoll einer lokalen Claim-Degradierung (Issue #1006).

    Ein einzelner ADR-0002-Verstoss kippte bisher den gesamten Report auf
    FAILED und vernichtete bereits fertige Sections. Statt den Validator zu
    lockern, wird der verletzende Claim lokal abgestuft und die Reparatur
    hier protokolliert.
    """

    model_config = _STRICT
    section_index: int
    claim_id: str
    violation: str  # Kurzbezeichner der verletzten Regel bzw. Pydantic-Fehlertyp
    action: str  # "downgraded_to_low" | "moved_to_hypotheses" | "dropped"
    detail: str  # menschenlesbare Begründung


def _reject_dangling_ledger_refs(
    ledger: "list[EvidenceCoverageEntry]", known_ids: set[str]
) -> None:
    """Jede kanonisierte Ledger-Zeile muss auf vorhandene Evidence zeigen.

    Eine Zeile, die ins Leere verweist, behauptet einen Verbleib, den es nicht
    gibt — sie wäre schlimmer als ein ehrliches ``dropped``, weil sie den
    Fakt als gesichert ausweist.
    """
    dangling = sorted(
        {
            entry.canonical_evidence_id
            for entry in ledger
            if entry.canonical_evidence_id
            and entry.canonical_evidence_id not in known_ids
        }
    )
    if dangling:
        raise ValueError(
            "evidence_coverage_ledger verweist auf unbekannte Evidence: "
            + ", ".join(dangling)
        )


class EvidenceCoverageEntry(BaseModel):
    """Was aus einem quantitativen Tool-Fakt geworden ist.

    Im Referenzlauf ``report_cc2ef45da5e9`` lagen 31 %, 67 %, 83 %, 91 %, 6 %
    und "sieben Fälle" in den Tool-Ergebnissen vor und fehlten anschließend im
    kanonischen Evidence-Index. Kein Log, keine Meldung — die Zahlen waren
    einfach weg, und der Bericht führte sie folgerichtig als unbelegt.

    Ein Fakt darf verworfen werden. Er darf nur nicht *still* verworfen werden:
    jeder Eintrag hier trägt entweder eine kanonische Evidence-ID oder einen
    Grund, warum es keine gibt. Das macht den Unterschied zwischen einem
    Dedup-Treffer und einem Extraktionsfehler nachträglich auflösbar.
    """

    model_config = _STRICT

    source_result_id: str = Field(
        min_length=1,
        description="Tool-Ergebnis, aus dem der Fakt stammt (producer_key oder Tool-Name).",
    )
    fact: str = Field(min_length=1, description="Der Fakt im Wortlaut der Quelle.")
    status: Literal["canonicalized", "dropped"]
    normalized_value: float | None = None
    unit: str | None = None
    canonical_evidence_id: str | None = Field(
        default=None,
        pattern=EVIDENCE_ID_PATTERN,
        description="Die kanonische Evidence — Pflicht bei status='canonicalized'.",
    )
    reason: str | None = Field(
        default=None,
        description="Warum verworfen — Pflicht bei status='dropped'.",
    )

    @model_validator(mode="after")
    def validate_status_consistency(self) -> "EvidenceCoverageEntry":
        """Genau eines von beiden — der Status ist keine Geschmacksfrage.

        Ein Eintrag mit ID *und* Grund wäre nicht mehr lesbar: kanonisiert
        oder verworfen, beides zugleich beschreibt keinen Verbleib.
        """
        if self.status == "dropped":
            if not (self.reason or "").strip():
                raise ValueError("status='dropped' verlangt einen reason")
            if self.canonical_evidence_id:
                raise ValueError(
                    "status='dropped' verträgt keine canonical_evidence_id"
                )
            return self
        if not (self.canonical_evidence_id or "").strip():
            raise ValueError("status='canonicalized' verlangt eine canonical_evidence_id")
        if (self.reason or "").strip():
            raise ValueError("status='canonicalized' verträgt keinen reason")
        return self
