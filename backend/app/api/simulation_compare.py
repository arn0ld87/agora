"""Branch-comparison API für vollständig simulierte SimulationBranches.

GET /api/simulation/<sim_id>/compare?branch_a=<id>&branch_b=<id>[&window_size_rounds=<int>]

Liefert eine Pydantic-validierte BranchComparison-JSON-Response mit Metriken
beider Branches und signierten Deltas (B − A).

Closes #66 (Sub-Slice 24)
"""

from __future__ import annotations

import time

from flask import request
from pydantic import ValidationError

from . import simulation_bp
from ..contracts.branch_comparison import BranchComparison
from ..services.compare_service import (
    BranchIncompleteError,
    BranchNotFoundError,
    CompareService,
)
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.logger import get_logger
from ..utils.validation import validate_simulation_id

logger = get_logger("agora.api.simulation_compare")


@simulation_bp.route("/<sim_id>/compare", methods=["GET"])
@handle_api_errors
def compare_branches(sim_id: str):
    """Vergleicht zwei vollständig simulierte Branches einer Simulation.

    Query params:
    * ``branch_a`` (erforderlich) — ID Branch A
    * ``branch_b`` (erforderlich) — ID Branch B
    * ``window_size_rounds`` (optional, int > 0) — Sliding Window für Netzwerk-Metriken
    """
    if not validate_simulation_id(sim_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            status=400,
            message="Invalid simulation_id format",
        )

    branch_a = (request.args.get("branch_a") or "").strip()
    branch_b = (request.args.get("branch_b") or "").strip()

    if not branch_a or not branch_b:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message="branch_a und branch_b sind erforderliche Query-Parameter",
        )

    if branch_a == branch_b:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message="branch_a und branch_b müssen verschieden sein",
            extra={"branch_a": branch_a, "branch_b": branch_b},
        )

    # Branch-IDs haben dasselbe Format wie sim_ids (sim_[hex12])
    if not validate_simulation_id(branch_a):
        return json_error(
            ApiErrorCode.INVALID_ID,
            status=400,
            message="Invalid branch_a format",
        )
    if not validate_simulation_id(branch_b):
        return json_error(
            ApiErrorCode.INVALID_ID,
            status=400,
            message="Invalid branch_b format",
        )

    window = request.args.get("window_size_rounds", type=int)

    service = _get_compare_service()
    started = time.perf_counter()

    try:
        comparison = service.compare_branches(
            simulation_id=sim_id,
            branch_a_id=branch_a,
            branch_b_id=branch_b,
            window_size_rounds=window,
        )
    except BranchNotFoundError as exc:
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message=str(exc),
            extra={"simulation_id": sim_id, "branch_id": exc.branch_id},
        )
    except BranchIncompleteError as exc:
        return json_error(
            "Branch nicht abgeschlossen",
            status=422,
            code="incomplete_state",
            extra={
                "branch_id": exc.branch_id,
                "simulation_status": exc.status,
                "requires": ["completed"],
            },
        )
    except ValidationError as exc:
        # z. B. branch_a_id == branch_b_id (vom Pydantic-Validator in BranchComparison)
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message=str(exc),
        )

    compute_ms = round((time.perf_counter() - started) * 1000, 1)

    # Layer-0-Boundary: Pydantic-Strict-Validation der Response
    validated = BranchComparison.model_validate(comparison.model_dump())

    return json_success(
        {"comparison": validated.model_dump(mode="json")},
        timing={"compute_ms": compute_ms},
    )


def _get_compare_service() -> CompareService:
    """Wiring der CompareService-Dependencies.

    Erlaubt Test-Override via ``current_app.extensions["compare_service"]``.
    """
    from flask import current_app

    override = current_app.extensions.get("compare_service") if current_app else None
    if override is not None:
        return override

    from ..services.compare_service import CompareService as _CS
    from ..services.network_analytics import NetworkAnalyticsService
    from ..services.report_agent import ReportManager
    from ..services.simulation_manager import SimulationManager
    from ..storage.neo4j_storage import Neo4jStorage

    return _CS(
        network_analytics=NetworkAnalyticsService(),
        report_reader=ReportManager(),
        neo4j_storage=Neo4jStorage(),
        simulation_manager=SimulationManager(),
    )
