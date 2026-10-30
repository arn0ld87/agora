"""Read-only enrichment for run list/detail representations.

Extracted from :mod:`app.api.runs` so HTTP/run-control orchestration no longer
owns project/simulation lookup logic. This module deliberately performs no
writes; failures in optional enrichment stay best-effort exactly as in the
legacy API implementation.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from flask import current_app

from ..contracts.runs_contract import RunDetail, RunsAggregation, RunsListResponse
from ..models.project import ProjectManager
from ..utils.logger import get_logger
from .simulation_manager import SimulationManager

# Keep the existing logger namespace so this mechanical extraction does not
# change observable log routing/filters.
logger = get_logger("agora.api.runs")


def _resolve_simulation_summary(simulation_id: str, sim_cache: dict) -> dict:
    if simulation_id in sim_cache:
        return sim_cache[simulation_id]

    entry: dict = {"config": None, "state": None, "persona_count": None}
    try:
        manager = SimulationManager()
        entry["config"] = manager.get_simulation_config(simulation_id)
        entry["state"] = manager.get_simulation(simulation_id)
    except Exception as exc:  # pragma: no cover - defensive read path  # noqa: BLE001
        logger.debug("Could not load simulation %s for run summary: %s", simulation_id, exc)

    store = current_app.extensions.get("artifact_store") if current_app else None
    if store is not None:
        try:
            if store.exists(simulation_id, "reddit_profiles"):
                profiles = store.read_json(simulation_id, "reddit_profiles", default=[]) or []
                if isinstance(profiles, list):
                    entry["persona_count"] = len(profiles)
        except Exception as exc:  # pragma: no cover - defensive read path  # noqa: BLE001
            logger.debug("Could not read reddit_profiles for %s: %s", simulation_id, exc)

    sim_cache[simulation_id] = entry
    return entry


def _resolve_project(project_id: str, project_cache: dict):
    if project_id in project_cache:
        return project_cache[project_id]
    try:
        project = ProjectManager.get_project(project_id)
    except Exception as exc:  # pragma: no cover - defensive read path  # noqa: BLE001
        logger.debug("Could not load project %s for run summary: %s", project_id, exc)
        project = None
    project_cache[project_id] = project
    return project


def _project_document_name(project) -> str | None:
    names: list[str] = []
    for entry in getattr(project, "files", []) or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("original_filename") or entry.get("filename")
        if name:
            names.append(name)
    if not names:
        return None
    return names[0] if len(names) == 1 else f"{names[0]} (+{len(names) - 1})"


def _apply_project_summary(summary: dict, project) -> None:
    document_name = _project_document_name(project)
    if document_name:
        summary["document_name"] = document_name
    if not summary["graph_name"] and getattr(project, "name", None):
        summary["graph_name"] = project.name
    if not summary["graph_id"] and getattr(project, "graph_id", None):
        summary["graph_id"] = project.graph_id


def _apply_simulation_summary(summary: dict, sim_entry: dict) -> None:
    config = sim_entry.get("config") or {}
    state = sim_entry.get("state")
    if config:
        summary["model"] = config.get("llm_model") or summary["model"]
        if not summary["graph_id"]:
            summary["graph_id"] = config.get("graph_id")
    if state is not None:
        if not summary["graph_id"]:
            summary["graph_id"] = getattr(state, "graph_id", None)
        if not summary["branch_name"]:
            summary["branch_name"] = getattr(state, "branch_name", None)
    summary["persona_count"] = sim_entry.get("persona_count")


def build_run_summary(run: dict, *, sim_cache: dict, project_cache: dict) -> dict:
    """Derive display fields for a run manifest without persisting them.

    Read-path enrichment: model, document name, persona count, graph metadata.
    Per-request caches keep N+1 reads bounded over a list response.
    """
    linked = run.get("linked_ids", {}) or {}
    metadata = run.get("metadata", {}) or {}

    summary: dict = {
        "model": None,
        "document_name": None,
        "persona_count": None,
        "graph_id": linked.get("graph_id") or metadata.get("graph_id"),
        "graph_name": metadata.get("graph_name"),
        "branch_name": run.get("branch_label") or metadata.get("branch_name"),
    }

    project_id = linked.get("project_id") or metadata.get("project_id")
    if project_id:
        project = _resolve_project(project_id, project_cache)
        if project is not None:
            _apply_project_summary(summary, project)

    simulation_id = linked.get("simulation_id")
    if simulation_id:
        _apply_simulation_summary(
            summary,
            _resolve_simulation_summary(simulation_id, sim_cache),
        )

    return summary


def attach_summary(run: dict, sim_cache: dict, project_cache: dict) -> dict:
    """Return a shallow run copy with the derived ``summary`` attached."""
    enriched = dict(run)
    enriched["summary"] = build_run_summary(run, sim_cache=sim_cache, project_cache=project_cache)
    return enriched


def parse_status_param(args: Any) -> list[str] | None:
    """Parse ``?status=`` query param: supports multi-value and comma-separated."""
    raw_values = args.getlist("status") if hasattr(args, "getlist") else []
    if not raw_values:
        return None
    statuses: list[str] = []
    for value in raw_values:
        for part in str(value).split(","):
            stripped = part.strip()
            if stripped:
                statuses.append(stripped)
    return statuses if statuses else None


def extract_run_log_tail(
    events: list[dict[str, Any]] | None,
    *,
    max_entries: int = 20,
) -> list[str] | None:
    """Return the last up-to-``max_entries`` non-empty event messages."""
    if not events:
        return None
    tail = [
        str(event.get("message") or "") for event in events[-max_entries:] if event.get("message")
    ]
    return tail or None


def extract_run_scalar_metrics(
    metadata: Mapping[str, Any] | None,
    events: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Extract ``phase``, ``round_num``, and ``last_event_at`` scalars from run state."""
    meta = metadata or {}
    ev_list = events or []
    phase = meta.get("phase") or meta.get("stage")
    round_num = meta.get("round_num")
    if round_num is None:
        round_num = meta.get("round")
    last_event_ts = ev_list[-1].get("timestamp") if ev_list else None
    if not any(v is not None for v in (phase, round_num, last_event_ts)):
        return None
    metrics: dict[str, Any] = {}
    if phase is not None:
        metrics["phase"] = str(phase)
    if round_num is not None:
        metrics["round_num"] = int(round_num)
    if last_event_ts is not None:
        metrics["last_event_at"] = str(last_event_ts)
    return metrics


def resolve_run_usage(
    run: Mapping[str, Any],
    *,
    require_events_for_fallback: bool = False,
):
    """Load persisted ``RunUsageSummary`` or aggregate on-the-fly from call events.

    When ``require_events_for_fallback=True`` (used by ``build_run_detail``),
    legacy runs with neither a persisted ``usage_summary.json`` nor call events
    return ``None`` so ``RunDetail.usage`` stays ``None`` (= unknown in UI).
    When ``False`` (used by ``GET /api/runs/<id>/usage``), an empty summary is
    aggregated even if ``events`` is empty.
    """
    from .run_usage_ledger import (
        aggregate_usage,
        load_call_events_cached,
        load_usage_summary,
    )

    run_id = str(run["run_id"])
    usage = load_usage_summary(run_id)
    if usage is not None:
        return usage

    events = load_call_events_cached(run_id)
    if require_events_for_fallback and not events:
        return None

    return aggregate_usage(
        run_id,
        events=events,
        started_at=run.get("started_at"),
        ended_at=run.get("completed_at"),
    )


def build_run_detail(
    run: dict[str, Any],
    *,
    attach_summary_fn: Callable[[dict, dict, dict], dict] = attach_summary,
    sim_cache: dict | None = None,
    project_cache: dict | None = None,
) -> dict[str, Any]:
    """Attach summary, live scalar metrics, log tail, budget, and usage to a run dict."""
    enriched = attach_summary_fn(
        run,
        sim_cache if sim_cache is not None else {},
        project_cache if project_cache is not None else {},
    )

    metadata = run.get("metadata") or {}
    events: list[dict[str, Any]] = run.get("events") or []

    enriched["eta_seconds"] = metadata.get("eta_seconds")
    enriched["log_tail"] = extract_run_log_tail(events)
    enriched["metrics"] = extract_run_scalar_metrics(metadata, events)

    try:
        from .run_budget import get_run_budget_status

        budget_status = get_run_budget_status(run["run_id"])
        if budget_status is not None:
            enriched["budget"] = budget_status.model_dump(mode="json")

        usage = resolve_run_usage(run, require_events_for_fallback=True)
        if usage is not None:
            enriched["usage"] = usage.model_dump(mode="json")
    except Exception:  # noqa: BLE001 — enrichment must not break the read path
        logger.warning(
            "budget/usage enrichment failed for run %s",
            run.get("run_id"),
            exc_info=True,
        )
    return enriched


def build_runs_list_response(
    runs: list[dict[str, Any]],
    *,
    status_counts: Mapping[str, int] | None = None,
    attach_summary_fn: Callable[[dict, dict, dict], dict] = attach_summary,
) -> RunsListResponse:
    """Enrich a list of runs with bounded per-request caches and validate ``RunsListResponse``."""
    sim_cache: dict = {}
    project_cache: dict = {}
    enriched = [
        {
            key: value
            for key, value in attach_summary_fn(run, sim_cache, project_cache).items()
            if key != "events"
        }
        for run in runs
    ]

    aggregation = None
    if status_counts is not None:
        counts_dict = dict(status_counts)
        aggregation = RunsAggregation(
            counts=counts_dict,
            total=sum(counts_dict.values()),
        )

    return RunsListResponse(
        runs=[RunDetail.model_validate(item) for item in enriched],
        total=len(enriched),
        aggregation=aggregation,
    )
