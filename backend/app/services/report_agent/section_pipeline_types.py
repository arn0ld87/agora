"""Typen und Datenstrukturen für die Abschnitts-Pipeline (Issue #1212)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ...contracts.report_contract import ReportSectionKind
from ...contracts.report_v3 import DEFAULT_REPORT_MODE, ReportMode
from .evidence import validate_quote_anchors
from .section_kinds import (
    coerce_section_kind,
    legacy_kind_for_quotes,
    section_kind_expects_quotes,
)
from .manager import ReportManager
from .output_contract import is_fallback_content
from .postprocess_timing import PostprocessPhaseTracker
from .text_verification import verify_prose


def _section_expects_quotes(section_title: str, section_kind: str | None = None) -> bool:
    """Gibt True zurück wenn der Abschnittstyp Persona-Zitate erwarten lässt.

    #1832: Massgeblich ist der stabile ``section_kind`` (ReportSectionKind) aus
    der modellgeplanten Outline — der Titel ist frei formuliert. Nur für
    Bestandsdaten ohne spezifische Rolle (``generic``) greift die historische
    Titel-Keyword-Heuristik; beides lebt in :mod:`.section_kinds`.
    """
    kind = coerce_section_kind(section_kind)
    if kind is ReportSectionKind.generic:
        kind = legacy_kind_for_quotes(section_title)
    return section_kind_expects_quotes(kind)


@dataclass
class SectionEvidenceOutcome:
    """Ergebnis von Claim-Extraktion und Evidence-Binding eines Abschnitts.

    Rückgabewert von ``ReportAgent._save_evidence_section``. Die Methode
    persistiert unverändert in die Evidenzkarte; dieser Wert macht zusätzlich
    beobachtbar, *was* dabei gebunden und *was* vom Gate verworfen wurde.

    Ohne das ist die Bindung nur über die persistierte Karte prüfbar — genau
    die Blindstelle, an der die Evidence-Durchreichung viermal nachgebessert
    wurde (#929, #1006, #1147, #1151) und die Issue #1209 Befund 6 adressiert.
    """

    claims: List[Dict[str, Any]] = field(default_factory=list)
    hypotheses: List[Dict[str, Any]] = field(default_factory=list)
    hypotheses_appendix: List[Dict[str, Any]] = field(default_factory=list)
    data_gaps: List[Dict[str, Any]] = field(default_factory=list)
    gate_decisions: List[Dict[str, Any]] = field(default_factory=list)
    generation_failed: bool = False
    quote_validation_failed: bool = False

    @classmethod
    def from_persisted_section(
        cls,
        evidence_map: Dict[str, Any],
        section_index: int,
        *,
        gate_decisions: List[Dict[str, Any]],
        generation_failed: bool,
    ) -> "SectionEvidenceOutcome":
        """Liest das Ergebnis aus der bereits validierten Evidenzkarte.

        Bewusst aus der persistierten Karte und nicht aus den lokalen Listen
        des Aufrufers: die Reparaturläufe bei ``ValidationError`` können
        Einträge herabstufen oder entfernen. Der Rückgabewert zeigt damit, was
        tatsächlich in der Karte steht — nicht, was vor der Validierung
        gedacht war.
        """
        sections = evidence_map.get("sections") or []
        entry: Dict[str, Any] = next(
            (
                s
                for s in sections
                if isinstance(s, dict) and s.get("section_index") == section_index
            ),
            {},
        )
        return cls(
            claims=list(entry.get("claims") or []),
            hypotheses=list(entry.get("hypotheses") or []),
            hypotheses_appendix=list(entry.get("hypotheses_appendix") or []),
            data_gaps=list(entry.get("data_gaps") or []),
            gate_decisions=list(gate_decisions),
            generation_failed=generation_failed,
            quote_validation_failed=bool(entry.get("quote_validation_failed", False)),
        )


@dataclass
class SectionResult:
    """Was bei der Verarbeitung eines Abschnitts herausgekommen ist."""

    section_index: int
    title: str
    content: str
    #: Abschnitt lag bereits auf der Platte und wurde übernommen, nicht erzeugt.
    restored: bool = False
    #: Generierung lieferte Fallback-Text statt Bericht (P0-7).
    failed: bool = False
    #: Zitatprüfung inklusive Repair-Retry blieb erfolglos (M11.8e).
    quote_validation_failed: bool = False
    #: Strukturierte Metadaten aus ``generate_section_metadata`` (M11.8d).
    metadata: Dict[str, Any] = field(default_factory=dict)
    #: Claim-Extraktion und Evidence-Binding.
    evidence: SectionEvidenceOutcome = field(default_factory=SectionEvidenceOutcome)
    #: Ungebundene Evidence-Referenzen der Sektion (Issue #1324 / Befund 3.2).
    unbound_evidence_refs: List[str] = field(default_factory=list)

    @property
    def bound_claims(self) -> List[Dict[str, Any]]:
        """Claims, die das Evidence-Gate passiert haben."""
        return self.evidence.claims

    @property
    def hypotheses(self) -> List[Dict[str, Any]]:
        """Aussagen, die das Gate zu Hypothesen herabgestuft hat."""
        return self.evidence.hypotheses

    @property
    def gate_decisions(self) -> List[Dict[str, Any]]:
        """Gate-Entscheidungen mit Verstoß, Aktion und Begründung."""
        return self.evidence.gate_decisions

    @property
    def markdown(self) -> str:
        """Abschnitt als Markdown-Block, wie er in den Gesamtreport geht."""
        return f"## {self.title}\n\n{self.content}"


@dataclass
class SectionExecutionState:
    """Expliziter Laufzeitzustand eines einzelnen Abschnitts während der Pipeline.

    Bündelt alle Zwischenartefakte eines Sektions-Durchlaufs (Inhalt,
    Zitatprüfungs-Status, ungebundene Evidence-Refs, Fließtext-Hypothesen,
    unverifizierte Aussagen, Roh- und gefilterte Struktur-Metadaten sowie
    das Evidence-Outcome) an einer Stelle statt über verstreute
    ``agent._pending_*``-Dicts.

    Für Abwärtskompatibilität mit bestehenden Tests und Legacy-Hooks
    synchronisiert ``sync_to_agent`` / ``from_agent_pending`` bei Bedarf
    mit den ``_pending_*``-Attributen am Agenten.
    """

    section_index: int
    title: str
    content: str = ""
    section_failed: bool = False
    quote_validation_failed: bool = False
    unbound_evidence_refs: List[str] = field(default_factory=list)
    prose_hypotheses: List[Any] = field(default_factory=list)
    unverified_statements: List[Dict[str, Any]] = field(default_factory=list)
    raw_metadata: Dict[str, Any] = field(default_factory=dict)
    filtered_metadata: Optional[Dict[str, Any]] = None
    evidence_outcome: Optional[SectionEvidenceOutcome] = None

    @classmethod
    def from_agent_pending(
        cls,
        agent: Any,
        *,
        section_index: int,
        title: str,
        content: str = "",
    ) -> "SectionExecutionState":
        """Initialisiert den Zustand und übernimmt evtl. vorab gesetzte _pending_*-Einträge."""
        pending_meta = (getattr(agent, "_pending_section_metadata", None) or {}).get(
            section_index, {}
        )
        pending_unbound = (getattr(agent, "_pending_unbound_evidence_refs", None) or {}).get(
            section_index, []
        )
        pending_quote_failed = bool(
            (getattr(agent, "_pending_quote_validation_failed", None) or {}).get(
                section_index, False
            )
        )
        pending_prose = (getattr(agent, "_pending_prose_hypotheses", None) or {}).get(
            section_index, []
        )
        pending_unverified = (getattr(agent, "_pending_unverified_statements", None) or {}).get(
            section_index, []
        )
        return cls(
            section_index=section_index,
            title=title,
            content=content,
            quote_validation_failed=pending_quote_failed,
            unbound_evidence_refs=list(pending_unbound or []),
            prose_hypotheses=list(pending_prose or []),
            unverified_statements=list(pending_unverified or []),
            raw_metadata=dict(pending_meta) if isinstance(pending_meta, dict) else {},
        )

    def record_quote_validation(
        self,
        agent: Any,
        section: Any,
        *,
        content: str,
        quote_validation_failed: bool,
        unbound_refs: List[str],
    ) -> None:
        """Speichert das Ergebnis der Zitatprüfung im State und spiegelt es an Section/Agent."""
        self.content = content
        self.quote_validation_failed = bool(quote_validation_failed)
        if unbound_refs:
            self.unbound_evidence_refs = list(unbound_refs)

        if self.quote_validation_failed:
            if not hasattr(section, "metadata") or section.metadata is None:
                section.metadata = {}
            section.metadata["quote_validation_failed"] = True

        pending_quotes = getattr(agent, "_pending_quote_validation_failed", None)
        if pending_quotes is None:
            pending_quotes = {}
            agent._pending_quote_validation_failed = pending_quotes
        pending_quotes[self.section_index] = self.quote_validation_failed

        if self.unbound_evidence_refs:
            pending = getattr(agent, "_pending_unbound_evidence_refs", None)
            if pending is None:
                pending = {}
                agent._pending_unbound_evidence_refs = pending
            pending[self.section_index] = list(self.unbound_evidence_refs)

    def sync_from_agent_hooks(self, agent: Any) -> None:
        """Übernimmt durch Agent-Hooks (_record_prose_hypotheses etc.) geschriebene Werte."""
        prose_entries = (getattr(agent, "_pending_prose_hypotheses", None) or {}).get(
            self.section_index
        )
        if prose_entries is not None:
            self.prose_hypotheses = list(prose_entries)
        unverified_entries = (getattr(agent, "_pending_unverified_statements", None) or {}).get(
            self.section_index
        )
        if unverified_entries is not None:
            self.unverified_statements = list(unverified_entries)
        pending_meta = (getattr(agent, "_pending_section_metadata", None) or {}).get(
            self.section_index
        )
        if isinstance(pending_meta, dict):
            self.filtered_metadata = dict(pending_meta)
        pending_unbound = (getattr(agent, "_pending_unbound_evidence_refs", None) or {}).get(
            self.section_index
        )
        if pending_unbound and not self.unbound_evidence_refs:
            self.unbound_evidence_refs = list(pending_unbound)

    def resolve_effective_metadata(self, agent: Any, section: Any = None) -> Dict[str, Any]:
        """Liefert die finalen (gefilterten) Metadaten und synchronisiert section.metadata."""
        self.sync_from_agent_hooks(agent)
        effective = (
            self.filtered_metadata
            if self.filtered_metadata is not None
            else (self.raw_metadata or {})
        )
        if (
            self.filtered_metadata is not None
            and section is not None
            and hasattr(section, "metadata")
            and isinstance(section.metadata, dict)
        ):
            section.metadata["structured_metadata"] = effective
        return effective or {}

    def resolve_effective_unbound_refs(self, agent: Any) -> List[str]:
        """Liefert die finalen ungebundenen Evidence-Referenzen des Abschnitts."""
        self.sync_from_agent_hooks(agent)
        return list(self.unbound_evidence_refs or [])

    def to_section_result(self, agent: Any, section: Any) -> SectionResult:
        """Erzeugt das unveränderliche SectionResult aus dem aktuellen Pipeline-Zustand."""
        effective_meta = self.resolve_effective_metadata(agent, section)
        effective_unbound = self.resolve_effective_unbound_refs(agent)
        outcome = (
            self.evidence_outcome
            if isinstance(self.evidence_outcome, SectionEvidenceOutcome)
            else SectionEvidenceOutcome(generation_failed=self.section_failed)
        )
        return SectionResult(
            section_index=self.section_index,
            title=self.title,
            content=self.content,
            failed=self.section_failed,
            quote_validation_failed=self.quote_validation_failed,
            metadata=effective_meta,
            evidence=outcome,
            unbound_evidence_refs=effective_unbound,
        )



# --- Seam-Signaturen -------------------------------------------------------
# Der Aufrufer bindet die echten Implementierungen; Tests setzen Fakes.

SectionGenerator = Callable[..., str]
MetadataGenerator = Callable[..., Dict[str, Any]]
QuoteValidator = Callable[..., Any]
ProseVerifier = Callable[..., Any]
FallbackDetector = Callable[[str], bool]


@dataclass
class SectionContext:
    """Umgebung eines Abschnitts-Durchlaufs: Daten und Seams.

    Die Seam-Felder haben Defaults auf die echten Implementierungen. Ein
    Aufrufer, der eigene Namensbindungen patchbar halten muss (``generate_report``
    tut das für ``workflow``-Globals), überschreibt sie beim Bauen des Kontexts.
    """

    report_id: str
    outline: Any
    total_sections: int
    #: Wird von ``_safe_generate_section_react`` gebunden — kein Default, weil
    #: die Implementierung in ``workflow`` liegt und ein Import zyklisch wäre.
    generate_section: SectionGenerator
    generate_metadata: MetadataGenerator
    report_mode: ReportMode = DEFAULT_REPORT_MODE
    #: Bereits fertige Abschnitte als Markdown — Kontext für die Generierung.
    #: Der Aufrufer erweitert die Liste; ``process_section`` liest sie nur.
    previous_sections: List[str] = field(default_factory=list)
    #: Bereits fertige Abschnittstitel, für Fortschrittsmeldungen.
    completed_section_titles: List[str] = field(default_factory=list)
    #: Auf der Platte vorgefundene Abschnitte: ``section_index`` → Inhalt.
    persisted_section_contents: Dict[int, str] = field(default_factory=dict)
    progress_callback: Optional[Callable[[str, int, str], None]] = None
    # Seams mit Default-Bindung
    validate_quotes: QuoteValidator = validate_quote_anchors
    verify_prose_fn: ProseVerifier = verify_prose
    is_fallback: FallbackDetector = is_fallback_content
    report_manager: Any = ReportManager
    phase_tracker_factory: Any = PostprocessPhaseTracker

    def base_progress_for(self, section_index: int) -> int:
        """Fortschritt zu Beginn eines Abschnitts (20 % … 90 %)."""
        if self.total_sections <= 0:
            return 20
        return 20 + int(((section_index - 1) / self.total_sections) * 70)
