# ruff: noqa: F401, E402, F811
"""Verarbeitung eines einzelnen Report-Abschnitts (Issue #1212).

Fassade für die Abschnitts-Pipeline, die alle Typen, Einzelschritte und
Ausführungsfunktionen re-exportiert.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

# Re-export der externen und internen Abhängigkeiten für Kompatibilität mit Mocks
from ...contracts.report_contract import ReportSectionKind
from ...contracts.report_v3 import DEFAULT_REPORT_MODE, ReportMode
from ...utils.logger import get_logger
from .evidence import validate_quote_anchors
from .section_kinds import (
    coerce_section_kind,
    legacy_kind_for_quotes,
    section_kind_expects_quotes,
)
from .manager import ReportManager
from .output_contract import is_fallback_content
from .postprocess_timing import PostprocessPhaseTracker
from .attribution_guard import (
    attribution_findings,
    correct_attribution,
    profile_from_evidence_index,
    resolve_section_evidence_records,
)
from .text_verification import verify_prose

from .section_pipeline_types import (
    FallbackDetector,
    MetadataGenerator,
    ProseVerifier,
    QuoteValidator,
    SectionContext,
    SectionEvidenceOutcome,
    SectionGenerator,
    SectionResult,
    _section_expects_quotes,
)
from .section_pipeline_steps import (
    _apply_metadata,
    _correct_attribution,
    _extract_metadata,
    _generate_content,
    _remove_orphan_markdown,
    _restore_persisted_section,
    _validate_quotes_with_repair,
    _verify_prose_facts,
)
from .section_pipeline_runner import (
    _cleanup_pending_state,
    process_section,
    run_section_pipeline,
)

logger = get_logger('agora.report_agent')

__all__ = [
    "FallbackDetector",
    "MetadataGenerator",
    "PostprocessPhaseTracker",
    "ProseVerifier",
    "QuoteValidator",
    "ReportManager",
    "ReportMode",
    "ReportSectionKind",
    "SectionContext",
    "SectionEvidenceOutcome",
    "SectionGenerator",
    "SectionResult",
    "_apply_metadata",
    "_correct_attribution",
    "_extract_metadata",
    "_generate_content",
    "_remove_orphan_markdown",
    "_restore_persisted_section",
    "_section_expects_quotes",
    "_validate_quotes_with_repair",
    "_verify_prose_facts",
    "attribution_findings",
    "coerce_section_kind",
    "correct_attribution",
    "is_fallback_content",
    "legacy_kind_for_quotes",
    "logger",
    "os",
    "process_section",
    "run_section_pipeline",
    "_cleanup_pending_state",
    "profile_from_evidence_index",
    "resolve_section_evidence_records",
    "section_kind_expects_quotes",
    "validate_quote_anchors",
    "verify_prose",
]
