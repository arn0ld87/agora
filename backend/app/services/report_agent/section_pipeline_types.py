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
