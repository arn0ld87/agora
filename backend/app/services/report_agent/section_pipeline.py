"""Verarbeitung eines einzelnen Report-Abschnitts (Issue #1212).

Der Abschnitts-Durchlauf lag als 188-Zeilen-Schleife in
:func:`app.services.report_agent.workflow.generate_report`. Er ist damit nur
über den Weg testbar gewesen, den ``tests/services/test_partial_report.py``
gegangen ist: 21 ``patch()``-Aufrufe auf Modulnamen in ``workflow``.

Hier steht derselbe Ablauf hinter einem Interface aus drei Teilen:

``SectionContext``
    Alles, was der Ablauf über seine Umgebung braucht — Daten und Seams. Die
    Seams sind Felder mit Default-Bindung an die echten Implementierungen,
    dasselbe Options-Muster wie in ``frontend/src/composables/useReportGeneration.ts``
    (Issue #1206). Ein Test setzt Fakes in den Kontext, statt Modulnamen zu patchen.

``process_section``
    Der Ablauf selbst: Wiederherstellung, Generierung, Zitatprüfung,
    Fließtext-Verifikation, Metadaten, Claim-Extraktion und Evidence-Binding.

``SectionResult``
    Das Ergebnis, beobachtbar statt als Seiteneffekt verstreut — einschließlich
    dessen, was das Evidence-Gate gebunden und was es verworfen hat.

Abschnittsübergreifender Zustand bleibt bewusst draußen: Cancel-Prüfung,
Akkumulation der fertigen Abschnitte und die Statusableitung des Gesamtreports
gehören zur Orchestrierung in ``generate_report``.

Dieses Modul importiert weder ``workflow`` noch ``agent`` — die Importrichtung
läuft ``agent`` → ``workflow`` → ``section_pipeline``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ...contracts.report_v3 import DEFAULT_REPORT_MODE, ReportMode
from ...utils.logger import get_logger
from .evidence import validate_quote_anchors
from .manager import ReportManager
from .output_contract import is_fallback_content
from .postprocess_timing import PostprocessPhaseTracker
from .attribution_guard import (
    attribution_findings,
    correct_attribution,
    profile_from_evidence_index,
)
from .text_verification import verify_prose

logger = get_logger('agora.report_agent')

# M11.8e — Section-Typen, die Persona-Zitate enthalten können/sollen.
# Für diese Sections wird validate_quote_anchors mit strict-Repair-Retry ausgeführt.
# Meta-Sections (Plan, Executive Summary, Datenlücken) sind ausgenommen.
_QUOTE_REQUIRED_SECTION_KEYWORDS = frozenset({
    "persona",
    "personas",
    "zielgrupp",
    "segment",
    "multipli",
    "multiplier",
    "friction",
    "reibung",
    "trust",
    "vertrauen",
    "interview",
    "reaktion",
    "reaction",
})


def _section_expects_quotes(section_title: str) -> bool:
    """Gibt True zurück wenn der Abschnittstyp Persona-Zitate erwarten lässt."""
    lower = section_title.lower()
    return any(kw in lower for kw in _QUOTE_REQUIRED_SECTION_KEYWORDS)


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


def _restore_persisted_section(
    agent: Any,
    section: Any,
    ctx: SectionContext,
    *,
    section_index: int,
    persisted_entry: Dict[str, Any],
) -> SectionResult:
    """Übernimmt einen bereits persistierten Abschnitt unverändert.

    Der Aufrufer prüft vorher, ob Evidence vorhanden ist. Siehe process_section().

    Issue #1479 (Codex-Review Runde 3, Finding 1): ``generation_failed`` steht
    bereits in der persistierten Evidence — ein Resume baut aber einen neuen
    Aufruf mit einer leeren ``failed_section_indices``-Liste, und diese
    Funktion gab den Fehlschlag bisher nicht weiter. Ein zuvor gescheiterter,
    beim Resume nur restaurierter Abschnitt verschwand damit aus der
    Fehlerliste, und ein sonst vollständiger Rest-Lauf konnte den Report auf
    COMPLETED heben, obwohl der Abschnitt weiterhin Fallback-Text enthält.
    """
    section.content = ctx.report_manager._clean_section_content(
        ctx.persisted_section_contents[section_index], section.title
    )
    generation_failed = bool(persisted_entry.get("generation_failed", False))
    return SectionResult(
        section_index=section_index,
        title=section.title,
        content=section.content,
        failed=generation_failed,
        evidence=SectionEvidenceOutcome(generation_failed=generation_failed),
        restored=True,
    )


def _remove_orphan_markdown(
    ctx: SectionContext, *, section_index: int, title: str
) -> None:
    """Entfernt eine verwaiste Markdown-Datei, bevor die Sektion neu generiert wird.

    Codex-Review PR #1475, Finding 1: ``process_section`` schreibt bei einer
    Regeneration zuerst neue Evidence, dann neues Markdown (Commit-Marker).
    Bliebe die alte, evidence-lose Markdown-Datei bis dahin liegen, sähe ein
    Absturz zwischen beiden Schritten sowohl die neue Evidence als auch das
    ALTE Markdown auf der Platte — ein nächster Resume würde das alte Markdown
    gegen die neue Evidence restaurieren, obwohl beide aus unterschiedlichem
    Inhalt stammen.
    Einfachste Lösung statt einer Bindung beider Artefakte über einen
    Generations-Identifier: die Waise sofort entfernen. Ohne Evidence-Eintrag
    darf ohnehin niemand dem alten Inhalt vertrauen, ein Identifier-Abgleich
    wäre hier reiner Mehraufwand für dasselbe Ergebnis.

    Codex-Review PR #1475, Runde 2, Finding 1: ein ``OSError`` beim Entfernen
    wird NICHT mehr geschluckt — er propagiert an ``process_section`` und
    damit VOR dem Schreiben neuer Evidence. Ein geschluckter Fehler ließe die
    Waise liegen, während ``_save_evidence_section`` trotzdem neue Evidence
    persistiert — exakt die Inkonsistenz, die dieser Slice beseitigen soll
    (das nachfolgende ``os.replace`` scheitert unter denselben
    Rechteproblemen typischerweise ebenfalls). Die Sektion scheitert damit
    sauber, statt stillschweigend inkonsistent zu werden.

    CodeRabbit-Review PR #1475, Runde 3, Finding 2: eine ``FileNotFoundError``
    ist die eine Ausnahme davon. Der DELETE-Endpunkt löscht den Report-Ordner
    per ``shutil.rmtree`` und kann ``stale_path`` genau zwischen der
    ``os.path.exists``-Prüfung oben und diesem ``os.remove`` entfernen
    (TOCTOU). In dem Fall ist der gewünschte Endzustand — keine Waise mehr
    auf der Platte — bereits erreicht, also wird das als Erfolg gewertet.
    ``PermissionError`` und jeder andere ``OSError`` propagieren weiterhin
    unverändert (siehe Finding 1 oben).
    """
    stale_path = ctx.report_manager._get_section_path(ctx.report_id, section_index)
    if not os.path.exists(stale_path):
        return
    try:
        os.remove(stale_path)
    except FileNotFoundError:
        logger.info(
            "section %d (%r): verwaiste Markdown-Datei bereits entfernt (%s)",
            section_index,
            title,
            stale_path,
        )
        return
    logger.info(
        "section %d (%r): verwaiste Markdown-Datei entfernt (%s)",
        section_index,
        title,
        stale_path,
    )


def _generate_content(
    agent: Any,
    section: Any,
    ctx: SectionContext,
    *,
    section_index: int,
    base_progress: int,
) -> str:
    """Meldet den Start und erzeugt den Abschnittsinhalt."""
    generating_message = (
        f"Generating section: {section.title} "
        f"({section_index}/{ctx.total_sections})"
    )
    ctx.report_manager.update_progress(
        ctx.report_id,
        "generating",
        base_progress,
        generating_message,
        current_section=section.title,
        completed_sections=ctx.completed_section_titles,
    )
    if ctx.progress_callback:
        ctx.progress_callback("generating", base_progress, generating_message)

    def _section_progress(stage: str, prog: int, msg: str) -> None:
        if ctx.progress_callback:
            ctx.progress_callback(
                stage,
                base_progress + int(prog * 0.7 / ctx.total_sections),
                msg,
            )

    return ctx.generate_section(
        agent,
        section=section,
        outline=ctx.outline,
        previous_sections=ctx.previous_sections,
        progress_callback=_section_progress if ctx.progress_callback else None,
        section_index=section_index,
        report_id=ctx.report_id,
    )


def _validate_quotes_with_repair(
    agent: Any,
    section: Any,
    ctx: SectionContext,
    content: str,
    *,
    section_index: int,
) -> tuple[str, bool, List[str]]:
    """Prüft Persona-Zitate und versucht bei Verstoß genau einen Repair-Retry.

    M11.8e + P4.1 — nur für Abschnittstypen, die Zitate erwarten:
    ``explorative`` überspringt die Prüfung, ``balanced`` repariert
    best-effort, ``strict`` protokolliert den gescheiterten Repair prominent.
    In keinem Modus wird der Abschnitt verworfen.

    Liefert ``(Inhalt, quote_validation_failed, ungebundene Evidence-Refs)``.

    Issue #1324: Die ungebundenen Refs standen bisher nur im Log. Ein Leser
    des Artefakts sah damit nicht, welcher Beleg zitiert, aber nie gebunden
    wurde — genau die Information, die den ``incomplete``-Status erklärt.
    """
    if not _section_expects_quotes(section.title) or ctx.report_mode == "explorative":
        return content, False, []

    evidence_map_for_validation = agent.evidence_map or {}
    persona_ids_for_validation: List[str] = getattr(agent, "persona_ids", []) or []
    quote_result = ctx.validate_quotes(
        content,
        evidence_map_for_validation,
        persona_ids_for_validation,
    )
    if quote_result.valid:
        return content, False, []

    logger.warning(
        "quote_anchor_validation: section=%d title=%r mode=%s — "
        "invalid quotes detected, attempting repair retry. "
        "invalid_quotes=%r unbound_refs=%r",
        section_index,
        section.title,
        ctx.report_mode,
        quote_result.invalid_quotes,
        quote_result.unbound_evidence_refs,
    )
    repair_content = ctx.generate_section(
        agent,
        section=section,
        outline=ctx.outline,
        previous_sections=ctx.previous_sections,
        progress_callback=None,
        section_index=section_index,
        report_id=ctx.report_id,
    )
    repair_result = ctx.validate_quotes(
        repair_content,
        evidence_map_for_validation,
        persona_ids_for_validation,
    )
    if repair_result.valid:
        logger.info(
            "quote_anchor_validation: section=%d repair successful",
            section_index,
        )
        return repair_content, False, []

    # Repair fehlgeschlagen — Section trotzdem weiter, Flag setzen
    log_fn = logger.error if ctx.report_mode == "strict" else logger.warning
    log_fn(
        "quote_anchor_validation: section=%d mode=%s repair retry also failed. "
        "Setting quote_validation_failed=True. "
        "repair_invalid_quotes=%r repair_unbound=%r",
        section_index,
        ctx.report_mode,
        repair_result.invalid_quotes,
        repair_result.unbound_evidence_refs,
    )
    return repair_content, True, list(repair_result.unbound_evidence_refs)


def _correct_attribution(
    agent: Any,
    section: Any,
    content: str,
    *,
    section_index: int,
) -> str:
    """Stellt Zuschreibungen richtig, für die es keine Belege gibt.

    Im Referenzlauf ``report_cc2ef45da5e9`` trug einer von 13 validierten
    Claims Simulations-Evidence, und der Text schrieb durchgehend "Die
    Simulation zeigt …". Ersetzt wird nur die Zeugenformel, nie der Satz —
    die Aussage bleibt, ihre Herkunft wird richtiggestellt.

    Läuft **vor** der Faktenprüfung: der Sanitizer arbeitet dann auf dem Text,
    der auch ausgeliefert wird, und seine Satzgrenzen stimmen mit denen des
    Endergebnisses überein.
    """
    index = (getattr(agent, "evidence_map", None) or {}).get("evidence_index") or {}
    profile = profile_from_evidence_index(index)
    findings = attribution_findings(content, profile)
    if not findings:
        return content

    logger.warning(
        "section %d (%r): %d Zuschreibung(en) ohne Grundlage — %s",
        section_index,
        getattr(section, "title", ""),
        len(findings),
        "; ".join(finding["kind"] for finding in findings),
    )
    return correct_attribution(content, profile)


def _verify_prose_facts(
    agent: Any,
    section: Any,
    ctx: SectionContext,
    content: str,
    *,
    section_index: int,
) -> str:
    """Prüft die Faktenaussagen des sichtbaren Fließtexts (P0).

    Quantitative Aussagen, denen eine Quelle widerspricht, werden entfernt.
    Aussagen ohne auffindbaren Beleg bleiben stehen und werden markiert —
    beide wandern zusätzlich in die Hypothesen (Issue #1356).
    """
    if ctx.is_fallback(content):
        return content
    content = _correct_attribution(agent, section, content, section_index=section_index)
    verified = ctx.verify_prose_fn(content, agent._prose_evidence_pool())
    if not verified.changed:
        return content
    logger.warning(
        "section %d (%r): %d widersprochene Faktenaussage(n) entfernt, "
        "%d unbelegte im Text markiert — beide als Hypothese geführt.",
        section_index,
        section.title,
        len(verified.rejected),
        len(verified.unverified),
    )
    agent._record_prose_hypotheses(section_index, verified.flagged)
    agent._record_unverified_statements(section_index, verified.unverified)
    return verified.content


def _extract_metadata(
    agent: Any,
    section: Any,
    ctx: SectionContext,
    content: str,
    *,
    section_index: int,
    base_progress: int,
) -> Dict[str, Any]:
    """Strukturierte Metadaten-Extraktion via strict-schema chat_json (M11.8d).

    Fehler blockieren nicht die Hauptgenerierung (``generate_section_metadata``
    gibt bei Exception ``{}`` zurück).
    """
    # Issue #1187: macht die bislang unsichtbare Metadaten-Extraktion
    # sichtbar/messbar — keine Verhaltensaenderung an section_meta selbst.
    metadata_phase_tracker = ctx.phase_tracker_factory(
        ctx.report_id,
        section_index=section_index,
        section_title=section.title,
        base_progress=base_progress,
        completed_sections=ctx.completed_section_titles,
        report_logger=agent.report_logger,
        # eigene, in Tests patchbare Namensbindung durchreichen
        # (siehe postprocess_timing.PostprocessPhaseTracker).
        report_manager=ctx.report_manager,
    )
    with metadata_phase_tracker.phase("section_metadata"):
        return ctx.generate_metadata(
            agent,
            section_title=section.title,
            section_content=content,
            section_index=section_index,
        )


def _apply_metadata(
    agent: Any,
    section: Any,
    section_meta: Dict[str, Any],
    *,
    section_index: int,
) -> None:
    """Schreibt die Metadaten an Section und Agent (P0-6)."""
    if section_meta and agent.report_logger and hasattr(
        agent.report_logger, "log_section_metadata"
    ):
        agent.report_logger.log_section_metadata(
            section_title=section.title,
            section_index=section_index,
            metadata=section_meta,
        )
    if not section_meta:
        return
    # P0-6: Die extrahierten Struktur-Daten sind ab hier die kanonische
    # Quelle für ReportV3 — vorher endeten sie im Logger.
    if not hasattr(section, "metadata") or section.metadata is None:
        section.metadata = {}
    section.metadata["structured_metadata"] = section_meta
    agent._record_section_metadata(section_index, section_meta)


def process_section(
    agent: Any,
    section: Any,
    ctx: SectionContext,
    *,
    section_index: int,
) -> SectionResult:
    """Verarbeitet genau einen Abschnitt und liefert das Ergebnis.

    Reihenfolge — jeder Schritt hängt vom vorigen ab:

    1. Liegt der Abschnitt schon auf der Platte, wird er übernommen (Resume).
    2. Generierung des Inhalts.
    3. Zitatprüfung mit einem Repair-Retry, wenn der Typ Zitate erwartet.
    4. Fließtext-Verifikation: ungedeckte Faktenaussagen werden Hypothesen.
    5. Fallback-Erkennung — fehlgeschlagene Abschnitte liefern Fehlertext und
       dürfen weder Metadaten noch Claims noch Evidence erzeugen (P0-7).
    6. Metadaten-Extraktion.
    7. Persistenz des Abschnitts, dann Claim-Extraktion und Evidence-Binding.

    Der Aufrufer bleibt für abschnittsübergreifenden Zustand zuständig:
    Cancel-Prüfung, Akkumulation und Statusableitung des Gesamtreports.
    """
    if section_index in ctx.persisted_section_contents:
        # Prüfe ob Evidence vorhanden ist — Markdown ohne Evidence wird
        # als unvollständig behandelt und neu generiert (verhindert Orphans).
        persisted_sections = (agent.evidence_map or {}).get("sections") or []
        persisted_entry = next(
            (
                s
                for s in persisted_sections
                if isinstance(s, dict) and s.get("section_index") == section_index
            ),
            None,
        )
        if persisted_entry is not None:
            return _restore_persisted_section(
                agent,
                section,
                ctx,
                section_index=section_index,
                persisted_entry=persisted_entry,
            )
        logger.warning(
            "section %d (%r): Markdown auf Platte, aber Evidence fehlt — "
            "Sektion wird neu generiert",
            section_index,
            section.title,
        )
        # Finding 1 (Codex-Review PR #1475): die Waise muss weg, BEVOR unten
        # neue Evidence geschrieben wird — sonst überlebt sie einen Absturz
        # zwischen Evidence- und Markdown-Schreiben als stille Inkonsistenz.
        _remove_orphan_markdown(ctx, section_index=section_index, title=section.title)

    base_progress = ctx.base_progress_for(section_index)
    content = _generate_content(
        agent, section, ctx, section_index=section_index, base_progress=base_progress
    )
    content, quote_validation_failed, unbound_refs = _validate_quotes_with_repair(
        agent, section, ctx, content, section_index=section_index
    )
    if quote_validation_failed:
        if not hasattr(section, "metadata") or section.metadata is None:
            section.metadata = {}
        section.metadata["quote_validation_failed"] = True
    # Issue #1324: an den Agenten durchreichen — ``_save_evidence_section``
    # baut das Section-Dict und ist die einzige Stelle, die in die
    # Evidenzkarte schreibt. Derselbe Weg wie ``_pending_section_metadata``.
    if unbound_refs:
        pending = getattr(agent, "_pending_unbound_evidence_refs", None)
        if pending is None:
            pending = {}
            agent._pending_unbound_evidence_refs = pending
        pending[section_index] = unbound_refs
    content = _verify_prose_facts(
        agent, section, ctx, content, section_index=section_index
    )

    # Fehlgeschlagene Sections liefern Fehlertext, keinen Inhalt: keine
    # Metadaten-Extraktion, keine Claims, keine Evidence daraus.
    section_failed = ctx.is_fallback(content)
    if section_failed:
        logger.warning(
            "section %d (%r): Fallback-Inhalt erkannt — Metadaten- und "
            "Claim-Extraktion werden übersprungen.",
            section_index,
            section.title,
        )
        section_meta: Dict[str, Any] = {}
    else:
        section_meta = _extract_metadata(
            agent,
            section,
            ctx,
            content,
            section_index=section_index,
            base_progress=base_progress,
        )
    _apply_metadata(agent, section, section_meta, section_index=section_index)

    section.content = content
    # Reihenfolge: Evidence ZUERST, dann Markdown.
    # Die Markdown-Datei ist der Commit-Marker — existiert sie, existiert auch
    # die Evidence. Bei Crashes dazwischen wird keine Orphan-Datei hinterlassen.
    # Issue #1316: Die Claim-Extraktion sah bislang exakt dasselbe ``content``
    # wie ``save_section`` — nur reinigt ``save_section`` intern, die
    # Extraktion nicht. Rohes <simulated_quote>-Markup landete damit in den
    # Claim-Kandidaten. ``prepare_content_for_evidence`` rendert die Zitate,
    # lässt Überschriften aber als ``#`` stehen: der Heading-Umbau zu
    # Fettschrift ist eine Darstellungsfrage des Dateipfads und würde der
    # Extraktion das Signal nehmen, an dem sie Überschriften erkennt.
    evidence = agent._save_evidence_section(
        ctx.report_id,
        section_index,
        section.title,
        ctx.report_manager.prepare_content_for_evidence(content),
    )
    # Markdown wird erst NACH Evidence geschrieben — das ist das Commit-Signal
    ctx.report_manager.save_section(ctx.report_id, section_index, section)

    return SectionResult(
        section_index=section_index,
        title=section.title,
        content=content,
        failed=section_failed,
        quote_validation_failed=quote_validation_failed,
        metadata=section_meta or {},
        evidence=evidence if isinstance(evidence, SectionEvidenceOutcome)
        else SectionEvidenceOutcome(generation_failed=section_failed),
    )
