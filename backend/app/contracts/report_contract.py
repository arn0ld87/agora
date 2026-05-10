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

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    Drift-Guard: Genau diese 4 Werte sind im Prompt-Block
    ``backend/app/services/report_prompts.py`` referenziert (Anker 1).
    """
    seed_corpus = "seed_corpus"
    agent_quote = "agent_quote"
    graph_relation = "graph_relation"
    inferred = "inferred"


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
    # ADR-0002 Anker 3 (Sub-Slice M11.7b): Default seed_corpus sichert die
    # Backward-Compat fuer alte Fixtures, die das Feld nicht mitschicken.
    source_kind: EvidenceSourceKind = EvidenceSourceKind.seed_corpus
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


class ReportSectionModel(BaseModel):
    model_config = _STRICT
    section_index: int = Field(ge=1)
    section_title: str = Field(min_length=3)
    section_summary: str = Field(min_length=1)
    claims: list[ReportClaimModel] = Field(default_factory=list, min_length=1)
    hypotheses: list[ReportSectionHypothesisModel] = Field(default_factory=list)


class ReportOutlineSectionModel(BaseModel):
    model_config = _STRICT
    title: str = Field(min_length=3)
    description: str = Field(min_length=1, max_length=500)


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


class ReportStatus(str, Enum):
    """Spiegelt models/report.py:ReportStatus 1:1."""
    pending = "pending"
    planning = "planning"
    generating = "generating"
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
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    has_evidence: bool = False
    evidence_sections: int = Field(default=0, ge=0)


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
