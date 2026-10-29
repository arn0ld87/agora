"""Verarbeitung eines einzelnen Report-Abschnitts (Issue #1212)."""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from ...utils.logger import get_logger
from .section_pipeline_types import (
    SectionContext,
    SectionEvidenceOutcome,
    SectionResult,
)
from .section_pipeline_steps import (
    _apply_metadata,
    _extract_metadata,
    _generate_content,
    _remove_orphan_markdown,
    _restore_persisted_section,
    _validate_quotes_with_repair,
    _verify_prose_facts,
)

logger = get_logger("agora.report_agent")


def _cleanup_pending_state(agent: Any, section_index: int) -> None:
    """Räumt temporäre _pending_*-Attribute am Agenten nach der Sektionsverarbeitung auf."""
    pending_attrs = (
        "_pending_section_claims",
        "_pending_structured_metadata",
        "_pending_structured_attempt_counts",
        "_pending_unbound_evidence_refs",
        "_pending_quote_validation_failed",
        "_pending_section_metadata",
        "_pending_prose_hypotheses",
        "_pending_unverified_statements",
    )
    for attr in pending_attrs:
        try:
            val = getattr(agent, attr, None)
            if isinstance(val, dict):
                val.pop(section_index, None)
            elif val is not None and not callable(val):
                setattr(agent, attr, None)
        except AttributeError, KeyError, TypeError:
            pass


def _try_restore_persisted_section(
    agent: Any,
    section: Any,
    ctx: SectionContext,
    *,
    section_index: int,
    restore_fn: Any,
    remove_orphan_fn: Any,
) -> Optional[SectionResult]:
    """Prüft, ob der Abschnitt bereits auf Platte vorliegt und Evidence besitzt."""
    if section_index not in ctx.persisted_section_contents:
        return None

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
        return restore_fn(
            agent,
            section,
            ctx,
            section_index=section_index,
            persisted_entry=persisted_entry,
        )
    logger.warning(
        "section %d (%r): Markdown auf Platte, aber Evidence fehlt — Sektion wird neu generiert",
        section_index,
        section.title,
    )
    remove_orphan_fn(ctx, section_index=section_index, title=section.title)
    return None


def _resolve_final_section_result(
    agent: Any,
    section: Any,
    *,
    section_index: int,
    content: str,
    section_failed: bool,
    quote_validation_failed: bool,
    section_meta: Dict[str, Any],
    evidence: Any,
    unbound_refs: List[str],
) -> SectionResult:
    """Führt Metadaten und Referenzen für das finale SectionResult zusammen."""
    filtered_meta = section_meta
    pending_meta_dict = getattr(agent, "_pending_section_metadata", None)
    if isinstance(pending_meta_dict, dict) and section_index in pending_meta_dict:
        filtered_meta = pending_meta_dict[section_index]
        if hasattr(section, "metadata") and isinstance(section.metadata, dict):
            section.metadata["structured_metadata"] = filtered_meta

    final_unbound_refs = list(unbound_refs or [])
    pending_unbound_dict = getattr(agent, "_pending_unbound_evidence_refs", None)
    if (
        not final_unbound_refs
        and isinstance(pending_unbound_dict, dict)
        and section_index in pending_unbound_dict
    ):
        final_unbound_refs = list(pending_unbound_dict[section_index] or [])

    return SectionResult(
        section_index=section_index,
        title=section.title,
        content=content,
        failed=section_failed,
        quote_validation_failed=quote_validation_failed,
        metadata=filtered_meta or {},
        evidence=evidence
        if isinstance(evidence, SectionEvidenceOutcome)
        else SectionEvidenceOutcome(generation_failed=section_failed),
        unbound_evidence_refs=final_unbound_refs,
    )


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
    pipe_mod = sys.modules.get("app.services.report_agent.section_pipeline")
    restore_fn = (
        getattr(pipe_mod, "_restore_persisted_section", _restore_persisted_section)
        if pipe_mod
        else _restore_persisted_section
    )
    remove_orphan_fn = (
        getattr(pipe_mod, "_remove_orphan_markdown", _remove_orphan_markdown)
        if pipe_mod
        else _remove_orphan_markdown
    )
    gen_content_fn = (
        getattr(pipe_mod, "_generate_content", _generate_content) if pipe_mod else _generate_content
    )
    val_quotes_fn = (
        getattr(pipe_mod, "_validate_quotes_with_repair", _validate_quotes_with_repair)
        if pipe_mod
        else _validate_quotes_with_repair
    )
    verify_prose_fn = (
        getattr(pipe_mod, "_verify_prose_facts", _verify_prose_facts)
        if pipe_mod
        else _verify_prose_facts
    )
    extract_meta_fn = (
        getattr(pipe_mod, "_extract_metadata", _extract_metadata) if pipe_mod else _extract_metadata
    )
    apply_meta_fn = (
        getattr(pipe_mod, "_apply_metadata", _apply_metadata) if pipe_mod else _apply_metadata
    )

    restored = _try_restore_persisted_section(
        agent,
        section,
        ctx,
        section_index=section_index,
        restore_fn=restore_fn,
        remove_orphan_fn=remove_orphan_fn,
    )
    if restored is not None:
        return restored

    base_progress = ctx.base_progress_for(section_index)
    try:
        content = gen_content_fn(
            agent, section, ctx, section_index=section_index, base_progress=base_progress
        )
        content, quote_validation_failed, unbound_refs = val_quotes_fn(
            agent, section, ctx, content, section_index=section_index
        )
        if quote_validation_failed:
            if not hasattr(section, "metadata") or section.metadata is None:
                section.metadata = {}
            section.metadata["quote_validation_failed"] = True
        pending_quotes = getattr(agent, "_pending_quote_validation_failed", None)
        if pending_quotes is None:
            pending_quotes = {}
            agent._pending_quote_validation_failed = pending_quotes
        pending_quotes[section_index] = bool(quote_validation_failed)
        # Issue #1324: an den Agenten durchreichen — ``_save_evidence_section``
        # baut das Section-Dict und ist die einzige Stelle, die in die
        # Evidenzkarte schreibt. Derselbe Weg wie ``_pending_section_metadata``.
        if unbound_refs:
            pending = getattr(agent, "_pending_unbound_evidence_refs", None)
            if pending is None:
                pending = {}
                agent._pending_unbound_evidence_refs = pending
            pending[section_index] = unbound_refs
        content = verify_prose_fn(agent, section, ctx, content, section_index=section_index)

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
            section_meta = extract_meta_fn(
                agent,
                section,
                ctx,
                content,
                section_index=section_index,
                base_progress=base_progress,
            )
        apply_meta_fn(agent, section, section_meta, section_index=section_index)

        section.content = content
        # Reihenfolge: Evidence ZUERST, dann Markdown.
        # Die Markdown-Datei ist der Commit-Marker — existiert sie, existiert auch
        # die Evidence. Bei Crashes dazwischen wird keine Orphan-Datei hinterlassen.
        evidence = agent._save_evidence_section(
            ctx.report_id,
            section_index,
            section.title,
            ctx.report_manager.prepare_content_for_evidence(content),
        )
        # Markdown wird erst NACH Evidence geschrieben — das ist das Commit-Signal
        ctx.report_manager.save_section(ctx.report_id, section_index, section)

        return _resolve_final_section_result(
            agent,
            section,
            section_index=section_index,
            content=content,
            section_failed=section_failed,
            quote_validation_failed=quote_validation_failed,
            section_meta=section_meta,
            evidence=evidence,
            unbound_refs=unbound_refs,
        )
    finally:
        _cleanup_pending_state(agent, section_index)


run_section_pipeline = process_section

__all__ = [
    "process_section",
    "run_section_pipeline",
    "_cleanup_pending_state",
]
