"""Read-only enrichment for run list/detail representations.

Extracted from :mod:`app.api.runs` so HTTP/run-control orchestration no longer
owns project/simulation lookup logic.  This module deliberately performs no
writes; failures in optional enrichment stay best-effort exactly as in the
legacy API implementation.
"""

from __future__ import annotations

from flask import current_app

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
            files = getattr(project, "files", []) or []
            names: list = []
            for entry in files:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("original_filename") or entry.get("filename")
                if name:
                    names.append(name)
            if names:
                summary["document_name"] = (
                    names[0] if len(names) == 1 else f"{names[0]} (+{len(names) - 1})"
                )
            if not summary["graph_name"] and getattr(project, "name", None):
                summary["graph_name"] = project.name
            if not summary["graph_id"] and getattr(project, "graph_id", None):
                summary["graph_id"] = project.graph_id

    simulation_id = linked.get("simulation_id")
    if simulation_id:
        sim_entry = _resolve_simulation_summary(simulation_id, sim_cache)
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

    return summary


def attach_summary(run: dict, sim_cache: dict, project_cache: dict) -> dict:
    """Return a shallow run copy with the derived ``summary`` attached."""
    enriched = dict(run)
    enriched["summary"] = build_run_summary(
        run, sim_cache=sim_cache, project_cache=project_cache
    )
    return enriched
