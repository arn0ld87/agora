"""Verarbeitung eines einzelnen Report-Abschnitts (Issue #1212)."""

from __future__ import annotations

import sys
from typing import Any, Dict

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

logger = get_logger('agora.report_agent')


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
    restore_fn = getattr(pipe_mod, "_restore_persisted_section", _restore_persisted_section) if pipe_mod else _restore_persisted_section
    remove_orphan_fn = getattr(pipe_mod, "_remove_orphan_markdown", _remove_orphan_markdown) if pipe_mod else _remove_orphan_markdown
    gen_content_fn = getattr(pipe_mod, "_generate_content", _generate_content) if pipe_mod else _generate_content
    val_quotes_fn = getattr(pipe_mod, "_validate_quotes_with_repair", _validate_quotes_with_repair) if pipe_mod else _validate_quotes_with_repair
    verify_prose_fn = getattr(pipe_mod, "_verify_prose_facts", _verify_prose_facts) if pipe_mod else _verify_prose_facts
    extract_meta_fn = getattr(pipe_mod, "_extract_metadata", _extract_metadata) if pipe_mod else _extract_metadata
    apply_meta_fn = getattr(pipe_mod, "_apply_metadata", _apply_metadata) if pipe_mod else _apply_metadata

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
            return restore_fn(
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
        remove_orphan_fn(ctx, section_index=section_index, title=section.title)

    base_progress = ctx.base_progress_for(section_index)
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
    # Issue #1324: an den Agenten durchreichen — ``_save_evidence_section``
    # baut das Section-Dict und ist die einzige Stelle, die in die
    # Evidenzkarte schreibt. Derselbe Weg wie ``_pending_section_metadata``.
    if unbound_refs:
        pending = getattr(agent, "_pending_unbound_evidence_refs", None)
        if pending is None:
            pending = {}
            agent._pending_unbound_evidence_refs = pending
        pending[section_index] = unbound_refs
    content = verify_prose_fn(
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
