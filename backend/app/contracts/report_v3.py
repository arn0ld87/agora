"""
Report-Contract v3 (Pydantic v2) — Pflichtabschnitt-DTOs.

11 thematische Abschnitt-DTOs + ReportV3-Container.
Vorbereitung für M11.8d (Strict-Schema-Forced-Output) und M11.8e (Quote/Evidence-Anchors).

Wording-Glossar v1 (docs/glossary.md):
  VERBOTEN: prediction, rehearsal, god's eye view, future prediction
  ERLAUBT: Simulation, Szenarienanalyse, Reaktionsmuster, Einschätzung
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


_STRICT = ConfigDict(extra="forbid", str_strip_whitespace=True)

CLAIM_MIN_EVIDENCE_FOR_CLAIM: int = 2
"""Reviewer-Floor (report_4fe2dacd80ba): Claims mit <2 Evidence-Items werden
in `_finalize_section_claims` zur Hypothesis geroutet, statt als Claim
durchzulaufen. ADR-0002-konform — verschärft, schwächt nicht."""


ReportMode = Literal["strict", "balanced", "explorative"]
"""Vertrauensmodus für den Report-Output (PLAN.md §5.1, Slice P4.1).

- ``strict``: Claims ohne Evidence-Anker werden gedroppt (nicht in Hypotheses).
  Quote-Anchor-Validator hart. ``confidence_label="low"``-Claims werden gedroppt.
- ``balanced`` (Default): Phase-2-Verhalten — Hypotheses-Routing für
  Evidence-lose Claims, Low-Confidence sichtbar markiert.
- ``explorative``: alle Claims/Quotes durch, sichtbar als ``EXPLORATIVE``-Banner
  im Report-Header — für Brainstorming-/Discovery-Kontexte.
"""


DEFAULT_REPORT_MODE: ReportMode = "balanced"


class Persona(BaseModel):
    """Zielgruppen-Persona mit DACH-orientierter Demografie."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    voice_register: Literal["formal-de", "neutral-de", "technical-de", "skeptisch-de"]
    alter_range: str = Field(min_length=1, description="z. B. '35–50'")
    beruf: str = Field(min_length=1)
    region: str = Field(min_length=1, description="z. B. 'Bayern', 'DACH', 'Nordrhein-Westfalen'")
    bildungsgrad: str | None = None
    haushaltseinkommen: str | None = None
    needs: list[str] = Field(default_factory=list)
    values: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class Segment(BaseModel):
    """Markt-/Zielgruppensegment, das mehrere Personas bündelt."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    beschreibung: str = Field(min_length=1)
    persona_ids: list[str] = Field(default_factory=list)
    kontaktwahrscheinlichkeit_prozent: float | None = Field(
        default=None, ge=0.0, le=100.0
    )


class Claim(BaseModel):
    """Evidenz-gestützter Befund aus der Szenarienanalyse."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    statement: str = Field(min_length=8)
    evidence_refs: list[str] = Field(min_length=1, description="Pflicht: mind. 1 Evidenz-Anker")
    confidence: Literal["speculative", "low", "medium", "high", "verified"]
    persona_ids: list[str] = Field(default_factory=list)
    aggregation_basis: Literal["seed", "persona", "aggregat", "datenluecke"]


class Multiplier(BaseModel):
    """Wachstums- oder Wirkungshebel entlang der Customer-Journey-Stufen."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kategorie: Literal["awareness", "consideration", "conversion", "retention"]
    reichweite_score: int = Field(ge=1, le=10)
    evidence_refs: list[str] = Field(default_factory=list)


class FrictionPoint(BaseModel):
    """Hindernis oder Reibungspunkt, der Adoption oder Akzeptanz verringert."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    beschreibung: str = Field(min_length=1)
    severity: Literal["low", "medium", "high"]
    affected_persona_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class TrustSignal(BaseModel):
    """Vertrauenssignal nach Cialdini-Kategorien (DACH-kontext)."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    beschreibung: str = Field(min_length=1)
    signal_type: Literal[
        "social_proof",
        "authority",
        "consistency",
        "reciprocity",
        "scarcity",
        "liking",
    ]
    evidence_refs: list[str] = Field(default_factory=list)


class ChangeRecommendation(BaseModel):
    """Konkrete Handlungsempfehlung mit Priorität und Umsetzungsaufwand."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    titel: str = Field(min_length=1)
    beschreibung: str = Field(min_length=1)
    priority: Literal["low", "medium", "high"]
    aufwand: Literal["S", "M", "L"]
    evidence_refs: list[str] = Field(default_factory=list)


class ProjectImpact(BaseModel):
    """Einschätzung der Auswirkung des Projekts auf Segmente."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    beschreibung: str = Field(min_length=1)
    affected_segments: list[str] = Field(default_factory=list)
    confidence: Literal["speculative", "low", "medium", "high", "verified"]
    evidence_refs: list[str] = Field(default_factory=list)


class PositioningVariant(BaseModel):
    """Positionierungs-Variante für eine spezifische Persona-Gruppe."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    titel: str = Field(min_length=1)
    claim_text: str = Field(min_length=1)
    ziel_persona_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class ContentIdea(BaseModel):
    """Content-Idee mit Format-Empfehlung und Persona-Bezug."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    titel: str = Field(min_length=1)
    format: Literal["blog", "video", "podcast", "social", "whitepaper", "webinar", "other"]
    persona_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class DataGap(BaseModel):
    """Datenlücke, die Einschätzungsqualität einschränkt."""

    model_config = _STRICT

    id: str = Field(min_length=1)
    beschreibung: str = Field(min_length=1)
    severity: Literal["low", "medium", "high"]
    suggested_fixes: list[str] = Field(default_factory=list)


class Hypothesis(BaseModel):
    """Hypothese ohne harte Evidence — separater Slot in ReportV3.

    Abgrenzung zu DataGap:
    - DataGap = strukturelle Datenlücke, die Einschätzungsqualität limitiert.
    - Hypothesis = inhaltliche Behauptung ohne Beleg, mit Rationale.
    """

    model_config = _STRICT

    id: str = Field(min_length=1)
    hypothesis_text: str = Field(min_length=1)
    rationale: str = ""
    suggested_evidence: list[str] = Field(default_factory=list)
    origin_section_index: int | None = None
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)


ModelAttributionStage = Literal[
    "ontology",
    "graph_extraction",
    "simulation",
    "report_outline",
    "report_section",
    "report_synthesis",
    "evidence_extraction",
    "interview",
    "other",
]
"""Slice 8 (2026-05-16): kanonische Stage-Labels für model_attribution.

Lose enumeriert — neue Pipeline-Stages können den Wert frei wählen, aber
typische Bezeichner sind festgeschrieben, damit die Frontend-Provenance-
Tabelle stabile Gruppierungen rendert.
"""


class ModelAttribution(BaseModel):
    """Welches LLM-Modell hat welche Pipeline-Stage produziert.

    Slice 8 (User-Bericht 2026-05-16): "Es hinterlegt nirgendwo welches Modell
    für welchen Teil der Erstellung zuständig war." Pro abgeschlossener Stage
    ein Eintrag — Frontend rendert sie als ausklappbare Provenance-Sektion.
    Felder absichtlich optional (außer stage/provider/model_id), damit nicht
    jeder Provider Tokens/Latency liefert.
    """

    model_config = _STRICT

    stage: ModelAttributionStage
    provider: str = Field(min_length=1, description="z. B. 'ollama', 'openai', 'gemini'")
    model_id: str = Field(min_length=1, description="Backend-Modell-ID, z. B. 'qwen2.5:32b'")
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    latency_ms: float | None = Field(default=None, ge=0.0)
    started_at: datetime | None = None
    note: str | None = Field(
        default=None,
        max_length=200,
        description="Optionaler Hinweis (z. B. 'fallback nach timeout').",
    )


class ReportV3(BaseModel):
    """
    Container für alle 11 Pflichtabschnitte des strukturierten Reports v3.

    schema_version=3 ist als Literal festgelegt — verhindert Versions-Drift
    analog zu ReportContractModel(schema_version=2).
    """

    model_config = _STRICT

    schema_version: Literal[3] = 3
    report_id: str = Field(min_length=1)
    generated_at: datetime
    report_mode: ReportMode = Field(
        default=DEFAULT_REPORT_MODE,
        description="Vertrauensmodus (PLAN.md §5.1). Default 'balanced'.",
    )
    personas: list[Persona] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    multipliers: list[Multiplier] = Field(default_factory=list)
    friction_points: list[FrictionPoint] = Field(default_factory=list)
    trust_signals: list[TrustSignal] = Field(default_factory=list)
    change_recommendations: list[ChangeRecommendation] = Field(default_factory=list)
    project_impacts: list[ProjectImpact] = Field(default_factory=list)
    positioning_variants: list[PositioningVariant] = Field(default_factory=list)
    content_ideas: list[ContentIdea] = Field(default_factory=list)
    data_gaps: list[DataGap] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    # Slice 8 (2026-05-16): Modell-Provenance pro Pipeline-Stage. Default
    # leer → backward-kompatibel zu Reports vor v3.1 (alte Fixtures laden ok).
    model_attribution: list[ModelAttribution] = Field(
        default_factory=list,
        description="Welches LLM-Modell hat welche Stage produziert.",
    )
