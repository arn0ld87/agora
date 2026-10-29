"""
Action, lifecycle, export, and query implementations for the Run registry API.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from collections.abc import Mapping
from typing import Any

from flask import Response, jsonify, make_response, request
from pydantic import ValidationError

from ..contracts.job_lease_contract import JobLease
from ..contracts.runs_contract import (
    RunsFilterQuery,
)
from ..services.run_export import select_run_export_files
from ..services.run_read_model import (
    attach_summary as _attach_summary,
    build_runs_list_response,
    resolve_run_usage,
)
from ..services.sim.cancel_flag import request_cancel as _request_cancel
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner
from ..utils.api_responses import json_error, json_success
from ..utils.artifact_locator import ArtifactLocator
from ..utils.logger import get_logger
from ..utils.validation import validate_run_id, validate_simulation_id

from .runs_replay import (
    _parse_status_param,
    _replay_simulation_run,
)
from .runs_restart import (
    _restart_simulation_prepare,
    _resume_or_restart_graph_build,
)
from .runs_resume import (
    _resume_or_restart_simulation_run,
    _resume_report_generate,
)

logger = get_logger("agora.api.runs")


def _runs_mod():
    import sys

    mod = sys.modules.get("app.api.runs")
    if mod is not None:
        return mod
    from . import runs

    return runs


def _simulation_artifacts(simulation_id: str):
    return ArtifactLocator.existing_paths(
        {
            "simulation": ArtifactLocator.simulation_artifacts(simulation_id),
        }
    )


def _get_run_or_404(run_id: str):
    if not validate_run_id(run_id):
        return None, json_error("Invalid run_id format", status=400)
    run = _runs_mod().run_registry.get_run(run_id)
    if not run:
        return None, json_error(f"Run does not exist: {run_id}", status=404)
    return run, None


#: Nur diese Registry-Status gelten fuer den Lease-Guard als "laeuft noch"
_LEASE_GUARD_ACTIVE_STATUSES = {"pending", "processing"}


def _reject_if_lease_active(run: Mapping[str, Any]):
    """409, wenn ``run`` nicht-terminal ist UND eine gueltige Lease traegt."""
    if run.get("status") not in _LEASE_GUARD_ACTIVE_STATUSES:
        return None

    lease = JobLease.from_metadata(run.get("metadata"))
    if lease is None or lease.is_expired():
        return None

    return json_error(
        f"Run {run.get('run_id')} has an active job lease "
        f"(owner_pid={lease.owner_pid}) — resume is blocked until the lease "
        "expires or the run reaches a terminal status",
        status=409,
        code="job_lease_active",
    )


def _get_run_by_run_or_simulation_id(identifier: str):
    """Löst ``run_``- *oder* ``sim_``-IDs zu einem Run auf."""
    mod = _runs_mod()
    if validate_simulation_id(identifier):
        run = mod.run_registry.get_latest_by_linked_id(
            "simulation_id", identifier, run_type="simulation_run"
        )
        if not run:
            return None, json_error(f"Run does not exist for simulation: {identifier}", status=404)
        return run, None
    return _get_run_or_404(identifier)


def _linked_or_entity_id(run: Mapping[str, Any], linked_key: str, label: str) -> str:
    linked_ids = run.get("linked_ids")
    value = linked_ids.get(linked_key) if isinstance(linked_ids, Mapping) else None
    if value is None:
        value = run.get("entity_id")
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"Run is missing {label} linkage")


def execute_list_runs():
    mod = _runs_mod()
    raw_params: dict = {
        "limit": request.args.get("limit", 50, type=int),
        "offset": request.args.get("offset", 0, type=int),
        "simulation_id": request.args.get("simulation_id"),
        "since": request.args.get("since"),
        "aggregate": request.args.get("aggregate"),
    }
    status_list = _parse_status_param(request.args)
    if status_list is not None:
        raw_params["status"] = status_list

    raw_params = {k: v for k, v in raw_params.items() if v is not None}

    filter_cls = getattr(mod, "RunsFilterQuery", RunsFilterQuery)
    try:
        fq = filter_cls.model_validate(raw_params)
    except ValidationError as exc:
        return json_error(
            "Invalid runs filter",
            status=400,
            code="validation_error",
            extra={"details": exc.errors()},
        )

    runs = mod.run_registry.list_runs(
        project_id=request.args.get("project"),
        run_type=request.args.get("run_type"),
        statuses=[str(s) for s in fq.status] if fq.status else None,
        branch=request.args.get("branch"),
        entity_id=request.args.get("entity_id"),
        simulation_id=fq.simulation_id,
        since=fq.since.isoformat() if fq.since else None,
        limit=fq.limit,
        offset=fq.offset,
    )

    counts = None
    if fq.aggregate == "status":
        counts = mod.run_registry.aggregate_by_status(
            project_id=request.args.get("project"),
            run_type=request.args.get("run_type"),
            simulation_id=fq.simulation_id,
        )

    attach_fn = getattr(mod, "_attach_summary", _attach_summary)
    response = build_runs_list_response(
        runs,
        status_counts=counts,
        attach_summary_fn=attach_fn,
    )
    return json_success(
        response.model_dump(mode="json"),
        count=response.total,
    )


def execute_get_run_usage(run_id: str):
    run, error = _get_run_or_404(run_id)
    if error:
        return error

    usage = resolve_run_usage(run, require_events_for_fallback=False)
    return json_success(usage.model_dump(mode="json"))


def execute_stop_run(run_id: str):
    mod = _runs_mod()
    run, error = getattr(mod, "_get_run_or_404", _get_run_or_404)(run_id)
    if error:
        return error

    if run.get("run_type") != "simulation_run":
        return json_error("Stop is only supported for simulation_run in this version", status=409)

    simulation_id = run.get("linked_ids", {}).get("simulation_id")
    if not simulation_id:
        return json_error("Run is missing simulation_id linkage", status=409)

    try:
        runner_cls = getattr(mod, "SimulationRunner", SimulationRunner)
        run_state = runner_cls.stop_simulation(simulation_id)
        mgr_cls = getattr(mod, "SimulationManager", SimulationManager)
        manager = mgr_cls()
        sim_state = manager.get_simulation(simulation_id)
        if sim_state:
            try:
                manager._set_status(sim_state, SimulationStatus.STOPPED)
            except Exception:  # noqa: BLE001
                sim_state.status = SimulationStatus.STOPPED
                manager._save_simulation_state(sim_state)
        artifacts_fn = getattr(mod, "_simulation_artifacts", _simulation_artifacts)
        mod.run_registry.update_run(
            run_id,
            status="stopped",
            progress=run_state.to_dict().get("progress_percent", 0),
            message="Simulation stopped",
            message_key="run.simulation_stopped",
            artifacts=artifacts_fn(simulation_id),
            resume_capability={"available": True, "action": "restart", "label": "Restart run"},
        )
        return json_success(mod.run_registry.get_run(run_id))
    except Exception as exc:  # noqa: BLE001
        return json_error(str(exc), status=400)


def execute_cancel_run(run_id: str):
    mod = _runs_mod()
    lookup_fn = getattr(mod, "_get_run_by_run_or_simulation_id", _get_run_by_run_or_simulation_id)
    run, error = lookup_fn(run_id)
    if error:
        return error

    resolved_run_id = run.get("run_id") or run_id
    current_status = run.get("status", "")
    if current_status == "pending":
        cancel_fn = getattr(mod, "_request_cancel", _request_cancel)
        cancel_fn(resolved_run_id)
        registry_cls = getattr(mod, "RunRegistry", None)
        registry_inst = registry_cls() if registry_cls else mod.run_registry
        registry_inst.update_run(
            resolved_run_id,
            status="failed",
            message="Vom Nutzer abgebrochen, bevor die Simulation gestartet war",
            message_key="run.cancelled_before_start",
        )
        return make_response(
            jsonify({"success": True, "status": "cancelled", "run_id": resolved_run_id}),
            200,
        )

    if current_status != "processing":
        return json_error(
            f"Run is not in 'processing' state (current: {current_status!r}). "
            "Cancel is only valid for active runs.",
            status=400,
            code="run_not_active",
        )

    simulation_id = (run.get("linked_ids") or {}).get("simulation_id")
    if run.get("run_type") == "simulation_run" and not simulation_id:
        return json_error("Run is missing simulation_id linkage", status=409)

    cancel_fn = getattr(mod, "_request_cancel", _request_cancel)
    cancel_fn(resolved_run_id)
    registry_cls = getattr(mod, "RunRegistry", None)
    registry_inst = registry_cls() if registry_cls else mod.run_registry
    registry_inst.update_run(
        resolved_run_id,
        message="Cancel requested — finishing current stage before stopping",
        message_key="run.cancel_requested",
    )

    logger.info(
        "cancel_run: cancel flag set for run_id=%s run_type=%s simulation_id=%s",
        resolved_run_id,
        run.get("run_type"),
        simulation_id,
    )
    body = jsonify({"success": True, "status": "cancel_requested", "run_id": resolved_run_id})
    return make_response(body, 202)


def execute_replay_run(run_id: str):
    mod = _runs_mod()
    run, error = getattr(mod, "_get_run_or_404", _get_run_or_404)(run_id)
    if error:
        return error

    if run.get("run_type") != "simulation_run":
        return json_error(
            f"Replay is only supported for simulation_run in this version "
            f"(run_type={run.get('run_type')!r})",
            status=409,
        )

    manifest_path = os.path.join(ArtifactLocator.run_dir(run_id), "manifest.json")
    if not os.path.exists(manifest_path):
        return json_error(
            f"Run {run_id} has no manifest — replay requires a manifest",
            status=400,
            code="no_manifest",
        )

    from ..contracts.run_manifest_contract import RunManifest

    with open(manifest_path, encoding="utf-8") as f:
        original_manifest = RunManifest.model_validate(json.load(f))

    overrides = None
    if request.is_json and request.get_json(silent=True):
        body = request.get_json(silent=True) or {}
        from ..contracts.run_manifest_contract import ReplayRequest

        try:
            overrides = ReplayRequest.model_validate(body).overrides if body else None
        except ValidationError as exc:
            return json_error(
                "Invalid replay request body",
                status=400,
                code="validation_error",
                extra={"details": exc.errors()},
            )
        except TypeError:
            return json_error("Request body must be a JSON object", status=400)

    if overrides is not None and overrides.seed_document_id is not None:
        return json_error(
            "seed_document_id-Overrides werden noch nicht unterstützt — "
            "es gibt keinen Mechanismus, einen Branch mit einem neuen "
            "Ausgangsdokument neu vorzubereiten.",
            status=400,
            code="seed_document_override_unsupported",
        )

    if overrides is not None and overrides.random_seed is not None:
        return json_error(
            "random_seed-Overrides werden noch nicht unterstützt — es gibt "
            "kein Runtime-Konzept für einen deterministischen Zufalls-Seed, "
            "der an die Simulation durchgereicht werden könnte.",
            status=400,
            code="random_seed_override_unsupported",
        )

    replay_fn = getattr(mod, "_replay_simulation_run", _replay_simulation_run)
    result = replay_fn(run, run_id, overrides, original_manifest)
    if not isinstance(result, dict):
        return result

    body = jsonify(result)
    return make_response(body, 202)


def execute_get_run_manifest(run_id: str):
    run, error = _get_run_or_404(run_id)
    if error:
        return error

    manifest_path = os.path.join(ArtifactLocator.run_dir(run_id), "manifest.json")
    if not os.path.exists(manifest_path):
        return json_error(
            f"Run {run_id} has no manifest",
            status=404,
            code="no_manifest",
        )

    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)

    return json_success(data)


def execute_export_run(run_id: str):
    run, error = _get_run_or_404(run_id)
    if error:
        return error

    run_dir = ArtifactLocator.run_dir(run_id)
    manifest_path = os.path.join(run_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        return json_error(
            f"Run {run_id} has no manifest — export requires a manifest",
            status=400,
            code="no_manifest",
        )

    report = select_run_export_files(run_id, run_dir)
    if report.skipped:
        logger.info(
            "run export skipped files outside the allowlist",
            extra={
                "run_id": run_id,
                "skipped": [entry.model_dump(mode="json") for entry in report.skipped],
            },
        )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_posix in report.exported:
            zf.write(os.path.join(run_dir, rel_posix), rel_posix)
        zf.writestr(
            "export-report.json",
            json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True),
        )

    buf.seek(0)
    return Response(
        buf.getvalue(),
        mimetype="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=agora-run-{run_id}.zip",
        },
    )


def execute_resume_run(run_id: str):
    mod = _runs_mod()
    run, error = getattr(mod, "_get_run_or_404", _get_run_or_404)(run_id)
    if error:
        return error

    lease_error = getattr(mod, "_reject_if_lease_active", _reject_if_lease_active)(run)
    if lease_error:
        return lease_error

    run_type = run.get("run_type")
    if run_type == "graph_build":
        fn = getattr(mod, "_resume_or_restart_graph_build", _resume_or_restart_graph_build)
        data = fn(run)
    elif run_type == "simulation_prepare":
        fn = getattr(mod, "_restart_simulation_prepare", _restart_simulation_prepare)
        data = fn(run)
    elif run_type == "simulation_run":
        fn = getattr(mod, "_resume_or_restart_simulation_run", _resume_or_restart_simulation_run)
        result = fn(run)
        if not isinstance(result, dict):
            return result
        data = result
    elif run_type == "report_generate":
        fn = getattr(mod, "_resume_report_generate", _resume_report_generate)
        result = fn(run)
        if not isinstance(result, dict):
            return result
        return json_success(result)
    else:
        return json_error(f"Unsupported run type: {run_type}", status=409)
    return json_success(data)
