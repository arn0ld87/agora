"""Einzelschritte der Abschnittsverarbeitung (Issue #1212)."""

from __future__ import annotations

import os
from typing import Any, Dict, List

from ...utils.logger import get_logger
from .attribution_guard import (
    attribution_findings,
    correct_attribution,
    profile_from_evidence_index,
    resolve_section_evidence_records,
)
from .section_pipeline_types import (
    SectionContext,
    SectionEvidenceOutcome,
    SectionResult,
    _section_expects_quotes,
)

logger = get_logger('agora.report_agent')


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
    quote_validation_failed = bool(persisted_entry.get("quote_validation_failed", False))
    metadata = dict(
        persisted_entry.get("structured_metadata")
        or persisted_entry.get("metadata")
        or {}
    )
    unbound_evidence_refs = list(
        persisted_entry.get("unbound_evidence_refs") or []
    )

    if metadata:
        if not hasattr(section, "metadata") or section.metadata is None:
            section.metadata = {}
        section.metadata["structured_metadata"] = metadata
        if hasattr(agent, "_record_section_metadata"):
            agent._record_section_metadata(section_index, metadata)

    if quote_validation_failed:
        if not hasattr(section, "metadata") or section.metadata is None:
            section.metadata = {}
        section.metadata["quote_validation_failed"] = True

    if unbound_evidence_refs:
        pending = getattr(agent, "_pending_unbound_evidence_refs", None)
        if pending is None:
            pending = {}
            agent._pending_unbound_evidence_refs = pending
        pending[section_index] = unbound_evidence_refs

    evidence_map = getattr(agent, "evidence_map", None)
    if isinstance(evidence_map, dict):
        evidence_outcome = SectionEvidenceOutcome.from_persisted_section(
            evidence_map,
            section_index,
            gate_decisions=[],
            generation_failed=generation_failed,
        )
    else:
        evidence_outcome = SectionEvidenceOutcome(generation_failed=generation_failed)

    return SectionResult(
        section_index=section_index,
        title=section.title,
        content=section.content,
        failed=generation_failed,
        quote_validation_failed=quote_validation_failed,
        metadata=metadata,
        evidence=evidence_outcome,
        unbound_evidence_refs=unbound_evidence_refs,
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
    import sys
    # Falls tests os.remove in section_pipeline mocken
    pipe_mod = sys.modules.get("app.services.report_agent.section_pipeline")
    os_remove_fn = getattr(pipe_mod, "os", os).remove if pipe_mod else os.remove

    stale_path = ctx.report_manager._get_section_path(ctx.report_id, section_index)
    if not os.path.exists(stale_path):
        return
    try:
        os_remove_fn(stale_path)
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
    if not _section_expects_quotes(section.title, getattr(section, "kind", None)) or ctx.report_mode == "explorative":
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
    ev_map = getattr(agent, "evidence_map", None) or {}
    index = ev_map.get("evidence_index") or {}
    active_sec_ev = getattr(agent, "_active_section_evidence", None)
    if isinstance(active_sec_ev, (list, dict)):
        combined_sec_ev: List[Any] = (
            list(active_sec_ev.values())
            if isinstance(active_sec_ev, dict)
            else list(active_sec_ev)
        )
        for global_refs in (
            ev_map.get("global_evidence_refs"),
            getattr(agent, "global_evidence_refs", None),
        ):
            if isinstance(global_refs, (list, tuple, set)):
                combined_sec_ev.extend(global_refs)
            elif isinstance(global_refs, dict):
                combined_sec_ev.extend(global_refs.values())
        evidence_source = resolve_section_evidence_records(combined_sec_ev, index)
    else:
        evidence_source = index
    profile = profile_from_evidence_index(evidence_source)
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
    import sys
    pipe_mod = sys.modules.get("app.services.report_agent.section_pipeline")
    corr_fn = getattr(pipe_mod, "_correct_attribution", _correct_attribution) if pipe_mod else _correct_attribution
    content = corr_fn(agent, section, content, section_index=section_index)
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
    metadata_phase_tracker = ctx.phase_tracker_factory(
        ctx.report_id,
        section_index=section_index,
        section_title=section.title,
        base_progress=base_progress,
        completed_sections=ctx.completed_section_titles,
        report_logger=agent.report_logger,
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
    if not hasattr(section, "metadata") or section.metadata is None:
        section.metadata = {}
    section.metadata["structured_metadata"] = section_meta
    agent._record_section_metadata(section_index, section_meta)
