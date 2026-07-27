"""
Report-Contract v2 (Pydantic v2) — Single Source of Truth.

Code-verifiziert gegen:
- backend/app/models/report.py (Dataclass-Quellen)
- backend/app/services/report_agent.py (Z. 184/567/1127: schema_version-Drift)
- backend/app/api/report.py (Z. 379: EXPORT_SCHEMA_VERSION = 1)
- backend/app/services/oasis_profile_generator.py (OasisAgentProfile-Felder)
- backend/tests/api/test_response_schemas.py (Schema-Erwartungen)

Layer 3 (Task 12): EvidenceItemModel erhaelt quote + source_id_anchor fuer
Original-Zitat-Provenance. Section-Builder leitet beide per _attach_provenance ab.

Aufruf zum Schema-Dump: python -m app.contracts.dump_schemas
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# Strenger Default für Vertrags-Modelle
_STRICT = ConfigDict(extra="forbid", populate_by_name=True)


class ConfidenceLabel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    verified = "verified"


class EvidenceType(str, Enum):
    """Übernommen aus report_agent.py — bestehende Typen plus model_generated_inference."""
    graph_fact = "graph_fact"
    graph_metric = "graph_metric"
    graph_metric_status = "graph_metric_status"
    relationship_chain = "relationship_chain"
    entity_summary = "entity_summary"
    agent_action = "agent_action"
    agent_interview = "agent_interview"
    web_search_result = "web_search_result"
    web_fetch = "web_fetch"
    # NICHT als evidence verwenden, nur in audit_trail (siehe report_agent.py S5-Kommentar)
    model_generated_inference = "model_generated_inference"


class EvidenceSourceKind(str, Enum):
    """ADR-0002 Anker 3 — Quellengattung pro Evidence-Item.

    Wird von den Cross-Stakeholder-/Inferred-Validators auf
    ``ReportClaimModel`` ausgewertet (Sub-Slice M11.7b, Anker 4 + 5).
    Drift-Guard: Diese Werte sind im Prompt-Block
    ``backend/app/services/report_prompts/sections.py`` referenziert (Anker 1).

    Erweiterung (Report-Trust-Slice): ``agent_action`` und ``web_source``
    ergänzen die ursprünglichen vier Werte. Das ist additiv und verschärft
    ADR-0002, statt es zu schwächen — vorher liefen Agentenaktionen und
    Web-Treffer über den Default ``seed_corpus`` und verschmolzen damit
    Seed-Dokument, Simulation und Recherche zu einer einzigen Quellengattung.
    Für die Confidence-Anker gilt weiterhin: nur ``agent_quote`` zählt als
    Stakeholder-Stimme, nur ``seed_corpus`` als Dokumentfakt.
    """
    seed_corpus = "seed_corpus"
    agent_quote = "agent_quote"
    agent_action = "agent_action"
    graph_relation = "graph_relation"
    web_source = "web_source"
    inferred = "inferred"


#: Quellengattungen, die aus der Simulation stammen — nie ein Seed-Fakt.
SIMULATION_SOURCE_KINDS: frozenset[EvidenceSourceKind] = frozenset({
    EvidenceSourceKind.agent_quote,
    EvidenceSourceKind.agent_action,
})


# Diese Typen sind im audit_trail erlaubt, nicht im evidence-Array
FORBIDDEN_EVIDENCE_TYPES = {"model_generated_inference", "section_synthesis"}


class AgentLogRef(BaseModel):
    model_config = _STRICT
    section_index: int = Field(ge=0)
    action: str
    tool_name: Optional[str] = None


class EvidenceItemModel(BaseModel):
    """Bestehende EvidenceItem-Felder aus report_agent.py, jetzt typsicher."""
    model_config = _STRICT

    type: EvidenceType
    source: str = Field(min_length=1)
    snippet: str = Field(min_length=1, max_length=2000)
    value: Optional[str | int | float | bool] = None
    tool_name: Optional[str] = None
    query: Optional[str] = None
    raw: Optional[Any] = None
    agent_log_ref: Optional[AgentLogRef] = None
    # Layer 3 (Task 12): quote — Original-Zitat zur Section-Anbindung.
    # Wörtlicher Auszug aus der Quelle (kein Summary, keine Paraphrase).
    # None = nicht ableitbar. Frontend rendert das als zitiertes
    # Originalzitat unter dem Claim.
    quote: Optional[str] = Field(default=None, min_length=1, max_length=500)
    # Layer 3 (Task 12): Stabiler Anker fuer Frontend-Scroll-To-Source.
    # Format ist absichtlich offen, damit verschiedene Quellen-Klassen
    # (agent-log, web, knowledge-graph) ihre eigene Anker-Konvention
    # mitbringen koennen — Beispiele:
    #   "agent-log-42#post-1234"
    #   "web:https://example.com/x#:~:text=Originalsatz"
    #   "kg:entity:9b2f-...."
    source_id_anchor: Optional[str] = Field(default=None, min_length=1, max_length=200)
    match_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    supports_claim: Optional[bool] = None
    # MAI-14: Sentiment des Quellen-Snippets (-1 = negativ, 0 = neutral, +1 = positiv).
    # None = nicht bestimmt. Wird von confidence_calculator._has_contradiction
    # genutzt, um widersprüchliche Sentiment-Vektoren zu erkennen.
    sentiment_score: Optional[float] = Field(
        default=None,
        ge=-1.0,
        le=1.0,
        description="Sentiment des Quellen-Snippets (-1 negativ, 0 neutral, +1 positiv).",
    )
    # ADR-0002 Anker 3 (Sub-Slice M11.7b): Der Default war seed_corpus und hat
    # damit jedes Item ohne explizite Angabe zum Dokumentfakt erklärt —
    # inklusive Agentenaktionen und Web-Treffern. Der Default ist jetzt
    # `inferred`: unbekannte Herkunft ist abgeleitet, nicht belegt. Alte
    # Fixtures ohne das Feld laden weiterhin, verlieren aber ihren
    # unverdienten Seed-Status (reject_inferred_in_high_confidence greift).
    source_kind: EvidenceSourceKind = EvidenceSourceKind.inferred
    # Slice 8 (User-Bericht 2026-05-16): welches LLM-Modell hat dieses
    # Evidence-Item extrahiert. None = nicht erfasst (Backward-Compat für
    # bestehende evidence.json). Format "<provider>/<model_id>", z. B.
    # "ollama/qwen2.5:32b" — bewusst frei, weil Provider-IDs evolvieren.
    source_model: str | None = Field(
        default=None,
        max_length=200,
        description="Provider+Modell, das diese Evidence-Zeile extrahiert hat (Slice 8).",
    )
    # Pflicht nur fuer source_kind=agent_quote — durchgesetzt im Validator
    # ``agent_quote_needs_stakeholder_group``. Die Cross-Stakeholder-Regel
    # auf ReportClaimModel zaehlt unterschiedliche Werte dieses Feldes.
    persona_stakeholder_group: Optional[str] = Field(
        default=None, min_length=1, max_length=200
    )

    @model_validator(mode="after")
    def reject_inference_in_evidence(self) -> "EvidenceItemModel":
        # S5-Regel aus report_agent.py: model_generated_inference darf NICHT
        # als evidence stehen, nur im audit_trail
        if self.type.value in FORBIDDEN_EVIDENCE_TYPES:
            raise ValueError(
                f"EvidenceType '{self.type.value}' ist nur im audit_trail erlaubt, "
                f"nicht im evidence-Array (siehe report_agent.py S5-Kommentar)."
            )
        return self

    @model_validator(mode="after")
    def agent_quote_needs_stakeholder_group(self) -> "EvidenceItemModel":
        # ADR-0002 Anker 3 (Sub-Slice M11.7b): agent_quote ohne Stakeholder-Gruppe
        # waere fuer den Cross-Stakeholder-Validator unbrauchbar — also hart
        # ablehnen, statt spaeter mit leerem Set zu arbeiten.
        if self.source_kind == EvidenceSourceKind.agent_quote and not self.persona_stakeholder_group:
            raise ValueError(
                "source_kind=agent_quote verlangt persona_stakeholder_group."
            )
        return self


class ReportClaimModel(BaseModel):
    model_config = _STRICT

    claim_id: str = Field(pattern=r"^claim_\d{2,}$")
    claim_text: str = Field(min_length=8)
    confidence_label: ConfidenceLabel
    confidence_score: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceItemModel] = Field(default_factory=list, max_length=10)
    audit_trail: list[dict[str, Any]] = Field(default_factory=list)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def non_low_claims_need_evidence(self) -> "ReportClaimModel":
        # P2.1: Jeder Claim oberhalb von low braucht mindestens einen
        # nachvollziehbaren Evidence-Anker. Low-Orphans bleiben fuer alte
        # Artefakte lesbar, werden beim Schreiben aber in hypotheses/data_gaps
        # geroutet.
        if self.confidence_label != ConfidenceLabel.low and not self.evidence:
            raise ValueError(
                f"Label '{self.confidence_label.value}' verlangt mindestens "
                "eine Evidence mit nachvollziehbarem Anker."
            )
        return self

    @model_validator(mode="after")
    def verified_needs_strong_match(self) -> "ReportClaimModel":
        # Schwelle aus confidence_calculator.py-Kommentar: verified nur ab match_score >= 0.85
        if self.confidence_label == ConfidenceLabel.verified:
            top = max((e.match_score or 0.0) for e in self.evidence) if self.evidence else 0.0
            if top < 0.85:
                raise ValueError(
                    f"Label 'verified' verlangt mindestens eine Evidence mit "
                    f"match_score >= 0.85. Top: {top:.2f}"
                )
        return self

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
        groups = {
            e.persona_stakeholder_group
            for e in self.evidence
            if e.source_kind == EvidenceSourceKind.agent_quote
            and e.supports_claim
            and e.persona_stakeholder_group
        }
        if len(groups) < 2:
            raise ValueError(
                f"Label '{self.confidence_label.value}' verlangt unterstützende "
                f"agent_quote-Evidence (supports_claim=True) aus mindestens 2 "
                f"unterschiedlichen Stakeholder-Gruppen. "
                f"Gefunden: {sorted(groups) if groups else '∅'}."
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


def _coerce_text_to_max_1000(value: Any) -> Any:
    """Sub-Slice 05.7 — Pre-Validator-Coercion für hypothesis_text / claim_text.

    Live-Smoke zeigte, dass LLMs (nemotron, deepseek-v4-flash) bei
    ReACT-Loops manchmal komplette Markdown-Tabellen in ``hypothesis_text``
    bzw. ``claim_text`` stopfen (Layer-2 / DTO-Verständnis-Bug am Modell).
    Pydantic warf dann ``string_too_long``, was den ganzen Report-Save
    abriss — Datenverlust, statt grazile Degradation.

    Coercion-Regel (Layer-0-Limit max_length=1000 BLEIBT erhalten):
    1. Wenn ``len(value) > 1000`` und Newline/Pipe vor Position 1000 → bei
       erstem ``\\n`` bzw. ``|`` abschneiden (typisches Tabellen-Marker).
    2. Sonst hart auf 1000 chars truncieren, suffix ``…`` markieren.
    3. Warning loggen, damit Prompt-Engineering-Feedback sichtbar bleibt.

    Layer-0-Anker NICHT betroffen (ADR-0002): kein Hedge-Word-Snapshot,
    kein EvidenceSourceKind-Enum, kein cross_stakeholder-Validator, kein
    reject_inferred-Validator. Die Coercion ist defensiv für UI-/Storage-
    Konsistenz, nicht für Evidence-Semantik.
    """
    if not isinstance(value, str) or len(value) <= 1000:
        return value

    # Tabellen-Marker früh erkennen
    cut_idx = 1000
    for marker in ("\n|", "\n", "|"):
        idx = value.find(marker)
        if 0 < idx < cut_idx:
            cut_idx = idx
            break

    truncated = value[:cut_idx].rstrip()
    # Sicherheits-Cap: nach Newline-Cut kann das Ergebnis noch > 1000 sein,
    # wenn der erste Newline nach Position 1000 lag (Loop oben überspringt das).
    if len(truncated) > 999:
        truncated = truncated[:999].rstrip() + "…"
    import logging as _logging
    _logging.getLogger("agora.report_contract").warning(
        "evidence-coercion: text truncated from %d to %d chars "
        "(LLM-Halluzination: vermutlich Markdown-Tabelle in Single-Statement-Slot)",
        len(value),
        len(truncated),
    )
    return truncated


class ReportSectionHypothesisModel(BaseModel):
    """ADR-0002 hypothesis slot — reasoning without evidence, not a claim.

    Hypothesen duerfen nicht in ``claims[]`` formuliert werden, weil sie keine
    Evidence tragen. Dieses DTO macht den separaten Slot maschinenlesbar, ohne
    die bestehenden Claim-/Evidence-Validatoren zu schwaechen.
    """

    model_config = _STRICT

    hypothesis_id: str = Field(pattern=r"^hypothesis_\d{2,}$")
    hypothesis_text: str = Field(min_length=8, max_length=1000)
    rationale: str = Field(min_length=8, max_length=1000)
    suggested_evidence: list[str] = Field(default_factory=list, max_length=5)

    # Sub-Slice 05.7: Pre-Validator vor max_length, damit LLM-Bloat
    # (komplette Markdown-Tabellen) truncated wird statt ValidationError.
    _coerce_hypothesis_text = field_validator("hypothesis_text", mode="before")(
        _coerce_text_to_max_1000
    )
    _coerce_rationale = field_validator("rationale", mode="before")(
        _coerce_text_to_max_1000
    )


class ReportSectionDataGapModel(BaseModel):
    """P2.1: Maschinenlesbare Luecke fuer nicht belegbare Claim-Kandidaten."""

    model_config = _STRICT

    gap_id: str = Field(pattern=r"^gap_\d{2,}$")
    claim_text: str = Field(min_length=8, max_length=1000)
    gap_reason: str = Field(min_length=1, max_length=200)
    suggested_fix: Optional[str] = Field(default=None, min_length=1, max_length=500)

    # Sub-Slice 05.7: Pre-Validator (gleiche Begründung wie Hypothesis).
    _coerce_claim_text = field_validator("claim_text", mode="before")(
        _coerce_text_to_max_1000
    )


class ReportSectionModel(BaseModel):
    model_config = _STRICT
    section_index: int = Field(ge=1)
    section_title: str = Field(min_length=3)
    section_summary: str = Field(min_length=1)
    claims: list[ReportClaimModel] = Field(default_factory=list)
    hypotheses: list[ReportSectionHypothesisModel] = Field(default_factory=list)
    # Slice 3 (Issue #495): Hypothesen-Appendix — Überhang nach dem Cap von 5.
    # Frontend kann diesen Slot optional ausklappen. max_length=50 verhindert
    # unbegrenzte Persistenz bei fehlerhaften LLM-Outputs.
    hypotheses_appendix: list[ReportSectionHypothesisModel] = Field(
        default_factory=list, max_length=50
    )
    data_gaps: list[ReportSectionDataGapModel] = Field(default_factory=list)
    # P0-6: Von `generate_section_metadata` extrahierte ReportV3-Strukturdaten
    # (Personas, Segmente, Reibungspunkte …). Sie landeten bisher nur im
    # Report-Logger, weshalb ReportV3 leer blieb, während der Prosa-Report die
    # Inhalte zeigte. Hier persistiert, damit `build_report_v3` sie übernimmt.
    # Bewusst untypisiert: die Einzel-DTOs werden in `metadata_merge` validiert,
    # ein einzelner ungültiger Eintrag darf die Section-Persistenz nicht kippen.
    structured_metadata: dict[str, Any] = Field(default_factory=dict)
    # P0-7: True, wenn der Abschnitt nur Fallback-/Fehlertext enthält.
    generation_failed: bool = False


class ReportOutlineSectionModel(BaseModel):
    model_config = _STRICT
    title: str = Field(min_length=3)
    # max_length=2000 (war 500): deutsche Persona-Reaktions-Outlines können
    # naturgemäß mehr Text brauchen als englische; 500 brach den realen
    # gpt-5.4-nano-Outline-Pfad (Smoke-Live 2026-05-15). Quote/suggested_fix
    # bleiben bei 500, weil sie strukturell kürzere Texttypen sind.
    description: str = Field(min_length=1, max_length=2000)


class ReportOutlineModel(BaseModel):
    model_config = _STRICT
    title: str = Field(min_length=3)
    summary: str = Field(min_length=1)
    # M11.4b-Followup-2: max_length auf 15 angehoben (war 5).
    # planning.py M11.8a entfernte den Section-Cap bei min=2/max=5 im LLM-Prompt,
    # aber ReportOutlineModel blieb auf max_length=5 — ließ 11 Pflichtabschnitte
    # im Stub-Modus (und bei echten Providern mit vollständigem Outline) fehlschlagen.
    # 15 bietet großzügigen Puffer für alle 11 Pflichtabschnitte + Spielraum.
    sections: list[ReportOutlineSectionModel] = Field(min_length=1, max_length=15)

    @model_validator(mode="after")
    def require_default_sections(self) -> "ReportOutlineModel":
        from app.services.report_agent.contract_validator import validate_required_sections
        from app.services.report_prompts import DEFAULT_REPORT_SECTIONS

        required_titles = [title for title, _ in DEFAULT_REPORT_SECTIONS]
        outline_titles = [section.title for section in self.sections]
        missing = validate_required_sections(outline_titles, required_titles)
        if missing:
            raise ValueError(
                "ReportOutlineModel fehlt Pflichtabschnitte: "
                + ", ".join(missing)
            )
        return self


class ReportStatus(str, Enum):
    """Spiegelt models/report.py:ReportStatus 1:1."""
    pending = "pending"
    planning = "planning"
    generating = "generating"
    INCOMPLETE = "incomplete"
    completed = "completed"
    failed = "failed"


class ReportModel(BaseModel):
    """Spiegelt models/report.py:Report — aber als Pydantic mit Validierung."""
    model_config = _STRICT
    schema_version: Literal[2] = 2
    report_id: str = Field(min_length=1)
    simulation_id: str = Field(min_length=1)
    graph_id: str = Field(min_length=1)
    simulation_requirement: str = Field(min_length=1)
    status: ReportStatus
    outline: Optional[ReportOutlineModel] = None
    markdown_content: str = ""
    missing_sections: list[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    has_evidence: bool = False
    evidence_sections: int = Field(default=0, ge=0)
    red_team_findings: list[str] = Field(default_factory=list, max_length=10)


class EvidenceMapModel(BaseModel):
    """Persistierte Evidence-Map. Ablöse für die rohen Dicts in report_agent.py."""
    model_config = _STRICT
    schema_version: Literal[2] = 2
    report_id: str = Field(min_length=1)
    simulation_id: str = Field(min_length=1)
    global_evidence: list[EvidenceItemModel] = Field(default_factory=list)
    sections: list[ReportSectionModel] = Field(default_factory=list)


class ReportContractModel(BaseModel):
    """Wurzel — was tatsächlich beim Export rausgeht."""
    model_config = _STRICT
    schema_version: Literal[2] = 2
    exported_at: datetime
    report: ReportModel
    evidence: Optional[EvidenceMapModel] = None
