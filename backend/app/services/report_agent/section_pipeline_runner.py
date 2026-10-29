"""Verarbeitung eines einzelnen Report-Abschnitts (Issue #1212 / Deep Module #1475)."""

from __future__ import annotations

import inspect
import sys
from typing import Any, Callable, Dict, List, Optional

from ...utils.logger import get_logger
from .section_pipeline_types import (
    SectionContext,
    SectionEvidenceOutcome,
    SectionExecutionState,
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

_PENDING_AGENT_ATTRS = (
    "_pending_section_claims",
    "_pending_structured_metadata",
    "_pending_structured_attempt_counts",
    "_pending_unbound_evidence_refs",
    "_pending_quote_validation_failed",
    "_pending_section_metadata",
    "_pending_prose_hypotheses",
    "_pending_unverified_statements",
)


def _cleanup_pending_state(agent: Any, section_index: int) -> None:
    """Räumt temporäre _pending_*-Attribute am Agenten nach der Sektionsverarbeitung auf."""
    for attr in _PENDING_AGENT_ATTRS:
        try:
            val = getattr(agent, attr, None)
            if isinstance(val, dict):
                val.pop(section_index, None)
            elif val is not None and not callable(val):
                setattr(agent, attr, None)
        except AttributeError, KeyError, TypeError:
            pass


def _resolve_pipeline_hook(name: str, default_fn: Callable[..., Any]) -> Callable[..., Any]:
    """Löst einen Pipeline-Schritt über die section_pipeline-Fassade auf (für Test-Monkeypatching)."""
    pipe_mod = sys.modules.get("app.services.report_agent.section_pipeline")
    if pipe_mod is not None:
        return getattr(pipe_mod, name, default_fn)
    return default_fn


def _try_restore_persisted_section(
    agent: Any,
    section: Any,
    ctx: SectionContext,
    *,
    section_index: int,
    restore_fn: Any = None,
    remove_orphan_fn: Any = None,
) -> Optional[SectionResult]:
    """Prüft, ob der Abschnitt bereits auf Platte vorliegt und Evidence besitzt."""
    if section_index not in ctx.persisted_section_contents:
        return None

    effective_restore = restore_fn or _resolve_pipeline_hook(
        "_restore_persisted_section", _restore_persisted_section
    )
    effective_remove_orphan = remove_orphan_fn or _resolve_pipeline_hook(
        "_remove_orphan_markdown", _remove_orphan_markdown
    )

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
        return effective_restore(
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
    effective_remove_orphan(ctx, section_index=section_index, title=section.title)
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
    state: Optional[SectionExecutionState] = None,
) -> SectionResult:
    """Führt Metadaten und Referenzen für das finale SectionResult zusammen."""
    if state is None:
        state = SectionExecutionState.from_agent_pending(
            agent,
            section_index=section_index,
            title=section.title,
            content=content,
        )
    state.content = content
    state.section_failed = section_failed
    state.quote_validation_failed = quote_validation_failed
    if section_meta and not state.raw_metadata:
        state.raw_metadata = dict(section_meta)
    if unbound_refs:
        state.unbound_evidence_refs = list(unbound_refs)
    if isinstance(evidence, SectionEvidenceOutcome):
        state.evidence_outcome = evidence
    return state.to_section_result(agent, section)


def _supports_section_state_kwarg(save_fn: Any) -> bool:
    """Prüft, ob ``_save_evidence_section`` das explizite ``section_state``-Argument deklariert."""
    target = save_fn
    side_effect = getattr(save_fn, "side_effect", None)
    if callable(side_effect):
        target = side_effect
    try:
        sig = inspect.signature(target)
    except TypeError, ValueError:
        return False
    return "section_state" in sig.parameters


def _persist_section_atomically(
    agent: Any,
    section: Any,
    ctx: SectionContext,
    state: SectionExecutionState,
) -> SectionEvidenceOutcome:
    """Persistiert zuerst Evidence (evidence_map.json) und erst danach Markdown (Commit-Marker).

    Invariante (#1475):
    - ``section_NN.md`` ist der Commit-Marker auf der Platte.
    - Existiert ``section_NN.md``, ist sein Eintrag in ``evidence_map.json`` bereits
      validiert und atomar gefsynct.
    """
    section.content = state.content
    prepared_content = ctx.report_manager.prepare_content_for_evidence(state.content)
    save_fn = agent._save_evidence_section
    if _supports_section_state_kwarg(save_fn):
        evidence = save_fn(
            ctx.report_id,
            state.section_index,
            section.title,
            prepared_content,
            section_state=state,
        )
    else:
        evidence = save_fn(
            ctx.report_id,
            state.section_index,
            section.title,
            prepared_content,
        )
    ctx.report_manager.save_section(ctx.report_id, state.section_index, section)
    outcome = (
        evidence
        if isinstance(evidence, SectionEvidenceOutcome)
        else SectionEvidenceOutcome(generation_failed=state.section_failed)
    )
    state.evidence_outcome = outcome
    state.sync_from_agent_hooks(agent)
    return outcome


class SectionGenerationPipeline:
    """Deep Module für die vollständige Verarbeitung und atomare Persistenz eines Report-Abschnitts.

    Kapselt die Stufenfolge, den expliziten ``SectionExecutionState`` und die
    Commit-Marker-Invariante (``evidence_map.json`` vor ``section_NN.md``) inklusive
    garantiertem ``finally``-Cleanup.
    """

    def __init__(self, ctx: SectionContext) -> None:
        self.ctx = ctx

    def run(self, agent: Any, section: Any, *, section_index: int) -> SectionResult:
        """Führt den kompletten Abschnittsdurchlauf für ``section_index`` aus."""
        ctx = self.ctx
        restore_fn = _resolve_pipeline_hook(
            "_restore_persisted_section", _restore_persisted_section
        )
        remove_orphan_fn = _resolve_pipeline_hook(
            "_remove_orphan_markdown", _remove_orphan_markdown
        )
        gen_content_fn = _resolve_pipeline_hook("_generate_content", _generate_content)
        val_quotes_fn = _resolve_pipeline_hook(
            "_validate_quotes_with_repair", _validate_quotes_with_repair
        )
        verify_prose_fn = _resolve_pipeline_hook("_verify_prose_facts", _verify_prose_facts)
        extract_meta_fn = _resolve_pipeline_hook("_extract_metadata", _extract_metadata)
        apply_meta_fn = _resolve_pipeline_hook("_apply_metadata", _apply_metadata)

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
        state = SectionExecutionState.from_agent_pending(
            agent,
            section_index=section_index,
            title=section.title,
        )
        try:
            raw_content = gen_content_fn(
                agent, section, ctx, section_index=section_index, base_progress=base_progress
            )
            validated_content, quote_validation_failed, unbound_refs = val_quotes_fn(
                agent, section, ctx, raw_content, section_index=section_index
            )
            state.record_quote_validation(
                agent,
                section,
                content=validated_content,
                quote_validation_failed=quote_validation_failed,
                unbound_refs=unbound_refs,
            )
            state.content = verify_prose_fn(
                agent, section, ctx, state.content, section_index=section_index
            )
            state.sync_from_agent_hooks(agent)

            state.section_failed = ctx.is_fallback(state.content)
            if state.section_failed:
                logger.warning(
                    "section %d (%r): Fallback-Inhalt erkannt — Metadaten- und "
                    "Claim-Extraktion werden übersprungen.",
                    section_index,
                    section.title,
                )
                state.raw_metadata = {}
            else:
                state.raw_metadata = extract_meta_fn(
                    agent,
                    section,
                    ctx,
                    state.content,
                    section_index=section_index,
                    base_progress=base_progress,
                )
            apply_meta_fn(agent, section, state.raw_metadata, section_index=section_index)

            _persist_section_atomically(agent, section, ctx, state)
            return state.to_section_result(agent, section)
        finally:
            _cleanup_pending_state(agent, section_index)


def process_section(
    agent: Any,
    section: Any,
    ctx: SectionContext,
    *,
    section_index: int,
) -> SectionResult:
    """Verarbeitet genau einen Abschnitt über ``SectionGenerationPipeline``."""
    return SectionGenerationPipeline(ctx).run(agent, section, section_index=section_index)


run_section_pipeline = process_section

__all__ = [
    "SectionExecutionState",
    "SectionGenerationPipeline",
    "process_section",
    "run_section_pipeline",
    "_cleanup_pending_state",
    "_persist_section_atomically",
    "_resolve_final_section_result",
    "_try_restore_persisted_section",
]
