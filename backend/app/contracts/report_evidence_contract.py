"""Evidence-Level Contracts für Report-Contract v2 (Pydantic v2).

Ausgelagert aus ``report_contract.py`` — alle Symbole werden dort vollständig
re-exportiert.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)

from .document_manifest_contract import DocumentRole
from .report_evidence_types import (
    ConfidenceLabel,
    ClaimType,
    EvidenceType,
    EvidenceSourceKind,
    SIMULATION_SOURCE_KINDS,
    SEED_DOC_ANCHOR_PREFIX,
    EvidenceGraphOrigin,
    EntailmentVerdict,
    MIN_ACTION_VOICES_FOR_MEDIUM,
    _STRICT,
    _reject_graph_origin_as_document_fact,
    counts_for_confidence,
    has_two_action_voices,
)


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
    # Stufe 1 des Bindings: Cosine-Similarity. Beantwortet "gleiches Thema?",
    # nicht "belegt?". Alias von match_score, bewusst eigenes Feld, damit der
    # Retrieval-Wert nicht länger als Beleggrad gelesen wird.
    retrieval_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    # Stufe 2: Urteil aus evidence_entailment. supports_claim ist genau dann
    # True, wenn entailment == "SUPPORTED".
    entailment: Optional[EntailmentVerdict] = None
    entailment_reason: Optional[str] = Field(default=None, max_length=500)
    supports_claim: Optional[bool] = None
    # True bei entailment == "CONTRADICTED". Wird von
    # detect_contradiction_penalty als Widerspruchs-Signal ausgewertet.
    contradicts_claim: Optional[bool] = None




    # MAI-14: Sentiment des Quellen-Snippets (-1 = negativ, 0 = neutral, +1 = positiv).
    # None = nicht bestimmt. Wird von confidence_calculator._has_contradiction
    # genutzt, um widersprüchliche Sentiment-Vektoren zu erkennen.
    sentiment_score: Optional[float] = Field(
        default=None,
        ge=-1.0,
        le=1.0,
        description="Sentiment des Quellen-Snippets (-1 negativ, 0 neutral, +1 positiv).",
    )
    # Issue #1363: Haltung der befragten Persona zum *Gegenstand der
    # Interviewfragen*, von -1.0 (klar ablehnend) bis 1.0 (klar zustimmend).
    #
    # Bewusst getrennt von ``sentiment_score``: jenes beschreibt den Tenor des
    # konkreten Snippets, dieses die Position der Person zum Thema. Der
    # Unterschied ist nicht akademisch. ``_has_contradiction`` wertet die
    # Sentiment-Spanne der Belege *eines Claims* aus; zwei Personas koennen
    # beide "Schulung ist noetig" sagen — zustimmende Snippets — und dabei
    # gegensaetzlich zum Rollout stehen. Fielde die Themenhaltung in
    # ``sentiment_score``, wuerde genau der Claim abgewertet, ueber den sie
    # einig sind.
    #
    # ``None`` heisst "nicht erhoben", nicht "neutral".
    topic_stance: Optional[float] = Field(
        default=None,
        ge=-1.0,
        le=1.0,
        description=(
            "Haltung der befragten Persona zum Gegenstand der Interviewfragen "
            "(-1 ablehnend, 0 unentschieden, +1 zustimmend). Nicht der Tenor "
            "des Snippets — dafuer steht sentiment_score."
        ),
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
    #: Stimme: eindeutiger Schlüssel der Persona, von der der Beleg stammt.
    #: Form ``agent:<agent_id>``. ``None`` bei Belegen ohne Persona (Seed, Graph, Web).
    voice_key: Optional[str] = Field(default=None, max_length=64, pattern=r"^agent:\d+$")
    # Issue #1248: Kontrolliertes Rollenfamilien-Label aus dem Entitaetstyp der
    # Quellentitaet. Der Jobtitel oben bleibt Anzeigetext; gezaehlt wird dieses
    # Feld. Optional, weil Artefakte aus Laeufen vor diesem Slice es nicht
    # tragen — dort faellt der Vergleich auf den Jobtitel zurueck.
    persona_role_family: Optional[str] = Field(
        default=None, min_length=1, max_length=120
    )
    # Issue #1240: Textsorte des Quelldokuments. Szenario-, Frage- und
    # Erwartungstext stuetzen keinen Claim (``classify_evidence``), bleiben
    # aber als Kontext sichtbar. ``None`` = unbekannt/Altbestand.
    document_role: Optional[DocumentRole] = None
    # ADR-0022 (#1808): Herkunft aus Handarbeit im Graphen. ``None`` =
    # extrahiert bzw. Altbestand. Gesetzt zählt das Item für keine
    # Confidence-Stufe (``ReportClaimModel.graph_origin_carries_no_confidence``).
    graph_origin: Optional[EvidenceGraphOrigin] = None

    @model_validator(mode="after")
    def graph_origin_is_never_a_document_fact(self) -> "EvidenceItemModel":
        _reject_graph_origin_as_document_fact(
            self.graph_origin, self.source_kind, self.source_id_anchor
        )
        return self

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

    @model_validator(mode="after")
    def agent_quote_rejects_seed_doc_anchor(self) -> "EvidenceItemModel":
        # Issue #1300: Ein seed_doc:-Anker (ADR-0013) behauptet, der Inhalt
        # stamme aus einer Seed-Dokument-Passage. Fuer eine simulierte
        # Persona-Aussage aus einem Interview ist das eine erfundene Quelle —
        # Referenz ist die ev_-Evidence-ID des Interview-Records.
        if (
            self.source_kind == EvidenceSourceKind.agent_quote
            and self.source_id_anchor
            and self.source_id_anchor.startswith(SEED_DOC_ANCHOR_PREFIX)
        ):
            raise ValueError(
                "source_kind=agent_quote darf keinen seed_doc:-Anker tragen — "
                "Interview-Evidence referenziert sich ueber ihre ev_-Evidence-ID, "
                "nicht ueber eine Dokumentherkunft (Issue #1300)."
            )
        return self


EVIDENCE_ID_PATTERN = r"^ev_[0-9a-f]{32}$"

#: UUID eines Wissensgraph-Knotens (Issue #1804, ``origin_node_uuids``).
_NODE_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class EvidenceRecordModel(BaseModel):
    """Claim-unabhaengiger, kanonisch adressierbarer Quellen-Datensatz."""

    model_config = _STRICT

    evidence_id: str = Field(pattern=EVIDENCE_ID_PATTERN)
    producer_key: str = Field(min_length=1, max_length=500)
    type: EvidenceType
    source: str = Field(min_length=1)
    snippet: str = Field(min_length=1, max_length=2000)
    value: Optional[str | int | float | bool] = None
    tool_name: Optional[str] = None
    query: Optional[str] = None
    raw: Optional[Any] = None
    agent_log_ref: Optional[AgentLogRef] = None
    quote: Optional[str] = Field(default=None, min_length=1, max_length=500)
    source_id_anchor: Optional[str] = Field(default=None, min_length=1, max_length=200)
    sentiment_score: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    #: Issue #1363 — siehe EvidenceRecordModel.topic_stance.
    topic_stance: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    source_kind: EvidenceSourceKind = EvidenceSourceKind.inferred
    source_model: Optional[str] = Field(default=None, max_length=200)
    persona_stakeholder_group: Optional[str] = Field(
        default=None, min_length=1, max_length=200
    )
    #: Stimme (Issue #1778, Schritt 1.2), siehe EvidenceItemModel.voice_key.
    voice_key: Optional[str] = Field(default=None, max_length=64, pattern=r"^agent:\d+$")
    # Issue #1248, siehe EvidenceItemModel.
    persona_role_family: Optional[str] = Field(
        default=None, min_length=1, max_length=120
    )
    # Issue #1240, siehe EvidenceItemModel.
    document_role: Optional[DocumentRole] = None
    # ADR-0022 (#1808), siehe EvidenceItemModel.
    graph_origin: Optional[EvidenceGraphOrigin] = None
    #: Sprungkennung zum Beitrag im Feed (Issue #1804, Etappe 5), Format wie
    #: ``GET /api/simulation/<id>/feed-snapshot``: ``<platform>:<id>`` bzw.
    #: ``<platform>:comment:<id>``. Wird nur beim Ausliefern aus ``raw`` und
    #: ``producer_key`` abgeleitet (``services/evidence_origin.py``), nie
    #: gespeichert: ``exclude_if`` lässt ein ungesetztes Feld aus jedem Dump
    #: heraus, damit persistierte Maps byte-identisch bleiben (ein Rollback auf
    #: eine ältere Fassung würde unbekannte Schlüssel mit ``extra=forbid``
    #: ablehnen).
    origin_post_id: Optional[str] = Field(
        default=None,
        max_length=64,
        pattern=r"^(twitter|reddit):(comment:)?\d+$",
        exclude_if=lambda value: value is None,
    )
    #: Knoten-UUIDs im Wissensgraphen, aus denen der Beleg stammt (``entity_summary``).
    #: Selbe Regeln wie ``origin_post_id``. Kanten-UUIDs kennt kein Beleg: für
    #: ``graph_fact`` und ``relationship_chain`` trägt ``raw`` nur den Faktentext.
    origin_node_uuids: Optional[list[str]] = Field(
        default=None,
        min_length=1,
        max_length=20,
        exclude_if=lambda value: value is None,
    )

    @field_validator("origin_node_uuids")
    @classmethod
    def origin_node_uuids_are_uuids(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return value
        bad = [item for item in value if not _NODE_UUID_RE.match(item)]
        if bad:
            raise ValueError(f"origin_node_uuids enthaelt Nicht-UUIDs: {bad[:3]}")
        return value

    @model_validator(mode="after")
    def graph_origin_is_never_a_document_fact(self) -> "EvidenceRecordModel":
        _reject_graph_origin_as_document_fact(
            self.graph_origin, self.source_kind, self.source_id_anchor
        )
        return self

    @model_validator(mode="after")
    def reject_inference_in_evidence(self) -> "EvidenceRecordModel":
        if self.type.value in FORBIDDEN_EVIDENCE_TYPES:
            raise ValueError(
                f"EvidenceType '{self.type.value}' ist nur im audit_trail erlaubt."
            )
        return self

    @model_validator(mode="after")
    def agent_quote_needs_stakeholder_group(self) -> "EvidenceRecordModel":
        if self.source_kind == EvidenceSourceKind.agent_quote and not self.persona_stakeholder_group:
            raise ValueError(
                "source_kind=agent_quote verlangt persona_stakeholder_group."
            )
        return self

    @model_validator(mode="after")
    def agent_quote_rejects_seed_doc_anchor(self) -> "EvidenceRecordModel":
        # Issue #1300, Spiegel von EvidenceItemModel.agent_quote_rejects_seed_doc_anchor.
        if (
            self.source_kind == EvidenceSourceKind.agent_quote
            and self.source_id_anchor
            and self.source_id_anchor.startswith(SEED_DOC_ANCHOR_PREFIX)
        ):
            raise ValueError(
                "source_kind=agent_quote darf keinen seed_doc:-Anker tragen — "
                "Interview-Evidence referenziert sich ueber ihre ev_-Evidence-ID, "
                "nicht ueber eine Dokumentherkunft (Issue #1300)."
            )
        return self


class ClaimEvidenceBindingModel(BaseModel):
    """Claim-relative Bewertung einer Referenz auf ``EvidenceRecordModel``."""

    model_config = _STRICT

    evidence_id: str = Field(pattern=EVIDENCE_ID_PATTERN)
    match_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    retrieval_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    entailment: Optional[EntailmentVerdict] = None
    entailment_reason: Optional[str] = Field(default=None, max_length=500)
    supports_claim: Optional[bool] = None
    contradicts_claim: Optional[bool] = None


__all__ = [
    "AgentLogRef",
    "ClaimEvidenceBindingModel",
    "ClaimType",
    "ConfidenceLabel",
    "EVIDENCE_ID_PATTERN",
    "EntailmentVerdict",
    "EvidenceGraphOrigin",
    "EvidenceItemModel",
    "EvidenceRecordModel",
    "EvidenceSourceKind",
    "EvidenceType",
    "FORBIDDEN_EVIDENCE_TYPES",
    "MIN_ACTION_VOICES_FOR_MEDIUM",
    "SEED_DOC_ANCHOR_PREFIX",
    "SIMULATION_SOURCE_KINDS",
    "_NODE_UUID_RE",
    "_STRICT",
    "_reject_graph_origin_as_document_fact",
    "counts_for_confidence",
    "has_two_action_voices",
]


__all__ = [
    "AgentLogRef",
    "ClaimEvidenceBindingModel",
    "ClaimType",
    "ConfidenceLabel",
    "EVIDENCE_ID_PATTERN",
    "EntailmentVerdict",
    "EvidenceGraphOrigin",
    "EvidenceItemModel",
    "EvidenceRecordModel",
    "EvidenceSourceKind",
    "EvidenceType",
    "FORBIDDEN_EVIDENCE_TYPES",
    "MIN_ACTION_VOICES_FOR_MEDIUM",
    "SEED_DOC_ANCHOR_PREFIX",
    "SIMULATION_SOURCE_KINDS",
    "_NODE_UUID_RE",
    "_STRICT",
    "_reject_graph_origin_as_document_fact",
    "counts_for_confidence",
    "has_two_action_voices",
]
