"""Section-, Outline- und Report-Level Contracts für Report-Contract v2 (Pydantic v2).

Ausgelagert aus ``report_contract.py`` — alle Symbole werden dort vollständig
re-exportiert.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .report_claim_contract import IndexedReportClaimModel
from .report_evidence_contract import _STRICT, ClaimType


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
    # Issue #1400: Typ des Ursprungs-Claims. Eine unbelegte Empfehlung landet
    # hier, ist aber keine Hypothese ueber die Welt — der Typ macht das lesbar.
    claim_type: Optional[ClaimType] = None

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
    # Issue #1319: verweist auf die Hypothese, aus der diese Datenluecke
    # entstanden ist (``if not supporting_ids:``-Zweig in agent.py). Optional,
    # weil der zweite Erzeuger (medium/high ohne Evidence, P2.1) keine
    # begleitende Hypothese anlegt.
    hypothesis_id: Optional[str] = Field(
        default=None, pattern=r"^hypothesis_\d{2,}$"
    )

    # Sub-Slice 05.7: Pre-Validator (gleiche Begründung wie Hypothesis).
    _coerce_claim_text = field_validator("claim_text", mode="before")(
        _coerce_text_to_max_1000
    )


class ReportSectionUnverifiedStatementModel(BaseModel):
    """Issue #1356: eine im Fließtext belassene, unbelegte Faktenaussage.

    Bis #1356 wurde alles entfernt, was die Prüfung nicht bestand — auch das,
    was sie mangels passender Quelle nur nicht *entscheiden* konnte. Ein
    vollständiger Referenzlauf verlor so 28 Aussagen, die weit überwiegende
    Mehrheit davon belegt. Seither bleibt der Satz stehen und trägt sichtbar
    ``[Beleg fehlt]``; dieses Modell hält dieselbe Information maschinenlesbar,
    damit Frontend und Audit nicht am Markerstring parsen müssen.

    Abgrenzung zu ``ReportSectionHypothesisModel``: die Hypothese ist die
    *herausgelöste* Behauptung samt Vorschlag, wie sie zu belegen wäre. Dieses
    Modell beschreibt, was im gelesenen Text mit welcher Einschränkung
    stehengeblieben ist. Beide Slots werden befüllt.
    """

    model_config = _STRICT

    statement_text: str = Field(min_length=1, max_length=1000)
    verdict: str = Field(min_length=1, max_length=32)
    reason: str = Field(min_length=1, max_length=200)


class ReportSectionModel(BaseModel):
    model_config = _STRICT
    section_index: int = Field(ge=1)
    section_title: str = Field(min_length=3)
    section_summary: str = Field(min_length=1)
    claims: list[IndexedReportClaimModel] = Field(default_factory=list)
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
    # Issue #1324: Evidence-Refs, die der Abschnitt zitiert, die aber in keiner
    # Bindung auftauchen. Sie wurden bisher nur geloggt — im persistierten
    # Artefakt war damit nicht nachvollziehbar, welcher Beleg fehlt, obwohl
    # genau das den Statuswechsel auf ``incomplete`` erklärt. max_length=200
    # deckelt fehlerhafte LLM-Outputs, wie bei ``hypotheses_appendix``.
    unbound_evidence_refs: list[str] = Field(default_factory=list, max_length=200)
    # Issue #1356: Aussagen, die im Fließtext stehen geblieben sind, für die
    # sich aber kein Beleg fand. Sie tragen dort den sichtbaren Marker; hier
    # steht dieselbe Information strukturiert. max_length wie bei
    # ``hypotheses_appendix`` als Deckel gegen fehlerhafte Outputs.
    unverified_statements: list[ReportSectionUnverifiedStatementModel] = Field(
        default_factory=list, max_length=200
    )


class ReportSectionKind(str, Enum):
    """Stabile semantische Rolle eines Report-Abschnitts (#1832).

    Der Abschnittstitel ist frei formuliert; nachgelagerte Consumer
    (DTO-Auswahl, Zitat-Validierung) lesen ausschliesslich diesen Wert und
    matchen nie den Titel. ``generic`` ist der sichere Default fuer alles,
    was keine der spezifischen Rollen erfuellt, und fuer Bestandsdaten.
    """

    stakeholder_voices = "stakeholder_voices"
    segment_table = "segment_table"
    persona_table = "persona_table"
    multiplier_analysis = "multiplier_analysis"
    friction_points = "friction_points"
    trust_signals = "trust_signals"
    change_recommendations = "change_recommendations"
    project_impact = "project_impact"
    positioning = "positioning"
    content_ideas = "content_ideas"
    data_gaps = "data_gaps"
    generic = "generic"


class ReportOutlineSectionModel(BaseModel):
    model_config = ConfigDict(**_STRICT, str_strip_whitespace=True)
    # #1832/Review: min_length=3 spiegelt ReportSectionModel.section_title —
    # ein kuerzerer Titel wuerde in der Evidenz-Persistenz failen, obwohl die
    # Planung ihn akzeptiert haette (Contract-Drift).
    title: str = Field(min_length=3)
    description: str = Field(min_length=1, max_length=2000)
    section_kind: ReportSectionKind = Field(
        default=ReportSectionKind.generic,
        description=(
            "Stabile semantische Rolle des Abschnitts. Consumer (DTO-Auswahl, "
            "Zitat-Validierung) lesen sie statt den Titel zu matchen; der "
            "Titel bleibt frei formulierbar. Unbekannte oder fehlende Angaben "
            "fallen auf 'generic' zurueck."
        ),
    )


class ReportOutlineModel(BaseModel):
    """Freie modellgeplante Gliederung; fachliche Abdeckung prueft der Workflow."""

    model_config = ConfigDict(**_STRICT, str_strip_whitespace=True)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    sections: list[ReportOutlineSectionModel] = Field(min_length=1, max_length=15)

    @model_validator(mode="after")
    def reject_duplicate_titles(self) -> "ReportOutlineModel":
        normalized = [" ".join(section.title.split()).casefold() for section in self.sections]
        if len(set(normalized)) != len(normalized):
            raise ValueError("ReportOutlineModel enthält doppelte normalisierte Abschnittstitel")
        return self


class ReportStatus(str, Enum):
    """Spiegelt models/report.py:ReportStatus 1:1."""
    pending = "pending"
    planning = "planning"
    generating = "generating"
    INCOMPLETE = "incomplete"
    completed = "completed"
    failed = "failed"


class RunDegradationModel(BaseModel):
    """Ein Qualitätsmangel des Report*laufs*, nicht eines einzelnen Claims.

    Der Referenzlauf ``report_cc2ef45da5e9`` ging als ``completed`` hinaus,
    obwohl die Simulation ``failed`` war, nur 45 von 48 Runden vorlagen und
    von acht angeforderten Interviews keines zustande kam. Der
    ``degradation_log`` blieb leer — er kennt nur Claim-Degradierungen, und
    für den Zustand des Laufs war schlicht niemand zuständig.

    Abgrenzung: ``EvidenceDegradationModel`` protokolliert die Abstufung eines
    Claims, ``PipelineDegradationModel`` den Ausfall eines Vorverarbeitungs-
    schritts. Dieses Modell steht dazwischen — es beschreibt, worauf der
    fertige Bericht beruht.
    """

    model_config = _STRICT

    component: Literal[
        "simulation",
        # Issue #1419: Personas, die nach gescheiterten LLM-Versuchen als
        # regelbasierte Platzhalter in die Simulation gingen. Ihre Beitraege
        # stehen im Bericht wie echte Stimmen — additiv ergaenzt, damit ein
        # Report darueber Auskunft geben kann.
        "persona_generation",
        "interview_agents",
        "section_generation",
        "section_metadata",
        # Fehlende Analyseaspekte im fertigen Berichtstext (Issue #1302).
        # Der ``requirement_checker`` schrieb diesen Wert seit seiner
        # Einfuehrung, der Vertrag kannte ihn nicht — der Zod-Spiegel wies
        # jede Antwort mit einem solchen Eintrag ab.
        "requirement_checker",
        "contract_export",
        # Issue #1479: die LLM-Outline-Planung scheiterte, ``plan_outline``
        # griff auf das feste Ersatzschema zurueck — additiv ergaenzt, damit
        # der Bericht das ausweisen kann (severity="warning").
        "outline_planning",
        # Issue #1479: die Section-Schleife erreichte nach einem
        # Nutzer-Abbruch (Cancel) nicht mehr alle Outline-Sections —
        # additiv ergaenzt, blockierend (severity="blocking").
        "run_cancellation",
        # Issue #1778: zu wenige Stimmen beziehen in der Simulation Stellung
        # zur Streitfrage (Positionierungsquote unter der Schwelle) —
        # additiv ergänzt (severity="warning").
        "simulation_positioning",
    ]
    reason: str = Field(
        min_length=1,
        description="Maschinenlesbarer Kurzgrund, z. B. '45_of_48_rounds'.",
    )
    detail: str = Field(default="", description="Menschenlesbare Erläuterung.")
    severity: Literal["warning", "blocking"] = "warning"


class SimulationSnapshotModel(BaseModel):
    """Stand der Simulation zum Startzeitpunkt der Reportgenerierung (Issue #1192).

    Ein Report darf starten, während die zugrunde liegende Simulation noch
    läuft — dann analysiert er aber einen Zwischenstand. Ohne diesen Snapshot
    ist einem fertigen Report nicht anzusehen, ob er auf zehn abgeschlossenen
    Runden beruht oder auf vieren. Erfasst wird der Stand *beim Start*, nicht
    beim Abschluss: das ist der Datenbestand, den der Agent tatsächlich
    gesehen hat.
    """

    model_config = _STRICT
    #: Zum Startzeitpunkt abgeschlossene Runden.
    rounds_completed: int = Field(ge=0)
    #: Geplante Gesamtrundenzahl; 0 wenn der Runner sie nicht kennt.
    total_rounds: int = Field(default=0, ge=0)
    #: Lief die Simulation beim Start der Reportgenerierung noch?
    simulation_running: bool = False
    #: Laufstatus der Simulation ("completed", "failed", "running", …).
    #: Additiv, Default ``None`` — Snapshots von vor der Einführung tragen ihn
    #: nicht, und "unbekannt" ist ehrlicher als ein erfundener Wert.
    simulation_status: Optional[str] = None
    #: ISO-8601-Zeitpunkt der Erfassung.
    captured_at: Optional[str] = None


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
    # Issue #1192: additiv, Default None — vor dieser Änderung persistierte
    # Reports kennen das Feld nicht und müssen weiter validieren.
    simulation_snapshot: Optional[SimulationSnapshotModel] = None
    #: Qualitätsmängel des Laufs, auf dem dieser Bericht beruht. Additiv mit
    #: Default leer — Bestandsreports bleiben gültig.
    run_degradations: list[RunDegradationModel] = Field(default_factory=list)
    #: Erzeugungsherkunft dieser Fassung (Issue #1804, Etappe 5). Additiv mit
    #: Default ``None``. Belegt aus dem Berichts-Job der RunRegistry
    #: (``metadata.llm_model``, ``metadata.llm_provider.provider_id``), also aus
    #: der gelockten Route, die tatsächlich lief — nie aus Workspace-Defaults.
    #: Leer bei Berichten ohne Job oder ohne Angabe im Job; ``GET /api/report/<id>``
    #: und ``/list`` füllen sie, der Export und die Metadatei tragen sie nicht.
    llm_model: Optional[str] = Field(default=None, max_length=200)
    llm_provider_id: Optional[str] = Field(default=None, max_length=100)
    #: ``run_id`` des jüngsten Berichts-Jobs; Schlüssel für
    #: ``GET /api/runs/<run_id>/llm-routing`` (Stufe ``report_generation``).
    generation_run_id: Optional[str] = Field(default=None, max_length=100)

    @property
    def degraded(self) -> bool:
        """Ist der Bericht auf einem beeinträchtigten Lauf entstanden?

        Der Statuswert allein beantwortet das nicht: ``INCOMPLETE`` sagt, dass
        etwas fehlt, aber nicht was. Diese Eigenschaft ist die Frage, die ein
        Leser tatsächlich stellt.
        """
        return bool(self.run_degradations)
