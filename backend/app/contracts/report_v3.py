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

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .provider_types import ProviderType
from .report_contract import EvidenceRecordModel


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
    # Issue #1160 A (Sign-off 2026-08-09): Geltungsbereich der Confidence.
    # Ein Claim, den ausschliesslich simulierte Stakeholder stuetzen, kann
    # dasselbe Label tragen wie ein quellengebundener — die Skala allein
    # unterscheidet das nicht. Das Feld macht den Unterschied im Report
    # sichtbar, ohne die Label-Semantik anzutasten (additiv, kein
    # ADR-0002-Eingriff). ``None`` = nicht erfasst, damit report-v3.json aus
    # der Zeit vor dieser Aenderung weiter validiert.
    #
    # ``empirical`` wird nie automatisch vergeben: Agora erhebt keine realen
    # empirischen Daten. Der Wert bleibt fuer manuell kuratierte Reports.
    confidence_scope: Literal["simulation_consensus", "evidence", "empirical"] | None = None


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


class Threshold(BaseModel):
    """Operative Zahl mit ausgewiesener Herkunft (Issue #1160 E).

    Zahlen wie „>90 % Traffic-Baseline" oder „14-Tage-Rankinggrenze" sehen im
    Fließtext alle gleich aus — egal ob sie aus dem Auftragsdokument stammen,
    aus gemessenen Daten, aus einer Norm, aus einer Betreiberentscheidung oder
    daraus, dass ein Sprachmodell sie plausibel fand. Der Leser kann sie nicht
    unterscheiden und behandelt im Zweifel alle gleich verbindlich.

    ``origin`` ist eine **eigene Dimension neben** ``EvidenceSourceKind`` und
    wird ausdrücklich nicht mit ihr vermischt: die Quellengattung beschreibt,
    woher ein *Beleg* kommt, ``origin`` beschreibt, wie eine *Zahl* zustande
    kam. Eine Vermischung würde ADR-0002 Anker 3 verwässern.
    """

    model_config = _STRICT

    id: str = Field(min_length=1)
    label: str = Field(
        min_length=1,
        description="Wofür die Zahl gilt, z. B. 'Traffic-Baseline' oder 'Rankinggrenze'",
    )
    value: float = Field(description="Der Zahlenwert selbst")
    unit: str = Field(
        min_length=1,
        description="Einheit, z. B. 'percent', 'days', 'eur', 'count'",
    )
    purpose: Literal["alert", "target", "limit", "baseline"] = Field(
        description=(
            "Rolle der Zahl: alert (löst eine Reaktion aus) | target (angestrebt) "
            "| limit (darf nicht überschritten werden) | baseline (Ausgangswert)"
        )
    )
    origin: Literal[
        "document_requirement",
        "empirical_data",
        "external_standard",
        "operator_policy",
        "model_proposal",
        "simulation_proposal",
    ] = Field(
        description=(
            "Herkunft der Zahl. document_requirement: steht so im Auftrags- oder "
            "Seed-Dokument. empirical_data: aus gemessenen Daten abgeleitet. "
            "external_standard: aus Norm, Gesetz oder Branchenstandard. "
            "operator_policy: Festlegung des Betreibers. model_proposal: vom "
            "Sprachmodell vorgeschlagen, ohne Quelle. simulation_proposal: aus "
            "dem Verhalten der simulierten Agenten abgeleitet. Im Zweifel "
            "model_proposal — eine Zahl ohne belegbare Herkunft ist ein "
            "Vorschlag, keine Anforderung."
        )
    )
    evidence_status: Literal["verified", "derived", "heuristic"] = Field(
        default="heuristic",
        description=(
            "verified: durch eine Evidence-Referenz belegt. derived: aus belegten "
            "Werten berechnet. heuristic: plausibel, aber unbelegt."
        ),
    )
    evidence_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def verified_needs_an_evidence_ref(self) -> "Threshold":
        """``verified`` ohne Beleg wäre genau die Behauptung, die #1160 E adressiert.

        Ein Modell, das eine Zahl erfindet und sie als belegt markiert, wäre
        schlimmer als eines, das sie ehrlich als ``heuristic`` ausweist — der
        Leser verlässt sich dann auf einen Beleg, den es nicht gibt.
        """
        if self.evidence_status == "verified" and not self.evidence_refs:
            raise ValueError(
                "evidence_status='verified' verlangt mindestens eine evidence_ref."
            )
        return self


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
    "red_team",
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
    provider: ProviderType = Field(description="z. B. 'ollama', 'openai', 'google'")
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

    schema_version=4 ist als Literal festgelegt — verhindert Versions-Drift
    analog zu ReportContractModel(schema_version=2).
    """

    model_config = _STRICT

    schema_version: Literal[4] = 4
    report_id: str = Field(min_length=1)
    generated_at: datetime
    evidence_index: dict[str, EvidenceRecordModel] = Field(default_factory=dict)
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
    # Issue #1160 E: operative Zahlen mit ausgewiesener Herkunft. Additiv,
    # Default leer — Bestandsreports ohne den Slot laden unveraendert.
    thresholds: list[Threshold] = Field(default_factory=list)
    # Slice 8 (2026-05-16): Modell-Provenance pro Pipeline-Stage. Default
    # leer → backward-kompatibel zu Reports vor v3.1 (alte Fixtures laden ok).
    model_attribution: list[ModelAttribution] = Field(
        default_factory=list,
        description="Welches LLM-Modell hat welche Stage produziert.",
    )
    # Slice 5 (2026-05-17): Red-Team-Findings aus echo_chamber_review-Stage.
    # max_length=10 begrenzt die Anzahl der Befunde; leer = kein Echo-Problem erkannt.
    red_team_findings: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Befunde der Red-Team-Review-Stage (max. 10).",
    )

    @model_validator(mode="after")
    def validate_evidence_cross_references(self) -> "ReportV3":
        known_ids = set(self.evidence_index)
        mismatched = [
            key
            for key, record in self.evidence_index.items()
            if key != record.evidence_id
        ]
        if mismatched:
            raise ValueError(
                "evidence_index-Key stimmt nicht mit evidence_id ueberein: "
                + ", ".join(sorted(mismatched))
            )

        collections = (
            self.personas,
            self.claims,
            self.multipliers,
            self.friction_points,
            self.trust_signals,
            self.change_recommendations,
            self.project_impacts,
            self.positioning_variants,
            self.content_ideas,
        )
        for collection in collections:
            for item in collection:
                unknown = sorted(set(item.evidence_refs) - known_ids)
                if unknown:
                    raise ValueError(
                        f"evidence_refs von {item.id} enthalten unbekannte Evidence: "
                        + ", ".join(unknown)
                    )
        return self
