# ruff: noqa: F401, E402, F811
"""Was der Bericht über die Qualität seiner eigenen Grundlage sagen muss.

Fassade für Run-Degradation, Ereignis-Logging und Qualitätsprüfungen.
Re-exportiert alle Symbole für Rückwärtskompatibilität.
"""

from __future__ import annotations

from .run_degradation_collector import (
    ENV_POSITIONING_RATIO_MIN,
    SIMULATION_LLM_FAILURE_BLOCKING_RATIO,
    SIMULATION_LLM_FAILURE_WARNING_RATIO,
    _UNHEALTHY_SIMULATION_STATUSES,
    _as_ratio,
    _cancellation_degradations,
    _entry,
    _interview_degradations,
    _outline_degradations,
    _persona_degradations,
    _positioning_degradations,
    _simulation_degradations,
    _simulation_llm_failure_degradations,
    _stance_unavailable_degradations,
    _STANCE_UNAVAILABLE_DETAILS,
    apply_run_degradation_downgrade,
    assert_run_invariants,
    collect_run_degradations,
    resolve_positioning_ratio_min,
    stance_analysis_unavailable,
)
from .run_degradation_events import (
    RunEventLog,
    clear_fallback_outline_used,
    events_for,
    mark_fallback_outline_used,
    mark_forced_final,
    mark_metadata_failure,
    mark_work_traces_removed,
)

__all__ = [
    "ENV_POSITIONING_RATIO_MIN",
    "RunEventLog",
    "SIMULATION_LLM_FAILURE_BLOCKING_RATIO",
    "SIMULATION_LLM_FAILURE_WARNING_RATIO",
    "apply_run_degradation_downgrade",
    "assert_run_invariants",
    "clear_fallback_outline_used",
    "collect_run_degradations",
    "events_for",
    "mark_fallback_outline_used",
    "mark_forced_final",
    "mark_metadata_failure",
    "mark_work_traces_removed",
    "resolve_positioning_ratio_min",
    "stance_analysis_unavailable",
]
