"""Gemeinsame 409-Antwort für gesperrte Graphen (Issue #1808, ADR-0022 §6).

Sitzt neben den Graph-Endpunkten, weil sie sowohl die neuen
Bearbeitungs-Endpunkte als auch die bestehenden Endpunkte zum Löschen und
Zurücksetzen verwenden. Die Ermittlung selbst liegt in
``app.services.graph_lock``.
"""

from __future__ import annotations

from ..services.graph_lock import GraphLockedError
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import json_error


def graph_locked_response(error: GraphLockedError):
    """HTTP 409, Code ``graph_locked``, mit der Liste der nutzenden Simulationen."""
    state = error.state
    return json_error(
        ApiErrorCode.GRAPH_LOCKED,
        status=409,
        extra={"used_by": [user.model_dump(mode="json") for user in state.used_by]},
    )


__all__ = ["graph_locked_response"]
