"""Preflight checks for CLI-based LLM sessions (Issue #1834).

Verifies readiness of local CLI-backed provider sessions (such as `codex_cli`)
prior to launching execution workloads (simulation rounds, report generation).
Prevents cryptic mid-execution failures such as permission denied on session
mounts or missing credentials, reporting transparent error codes and actionable
remediation messages without silent provider fallbacks.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from ..contracts.provider_types import PROVIDER_CODEX_CLI
from ..llm.providers.codex_cli import (
    codex_cli_readiness,
    verify_codex_cli_session_ready,
)

if TYPE_CHECKING:
    from ..contracts.llm_routing_contract import ResolvedRoute

logger = logging.getLogger(__name__)


def verify_cli_session_preflight(
    provider_id: str,
    *,
    stage: Optional[str] = None,
    run_id: Optional[str] = None,
) -> None:
    """Preflight-Pruefung fuer CLI-basierte LLM-Provider vor dem Workload-Start.

    Prueft die Verfuegbarkeit und Schreibrechte des Session-Verzeichnisses.
    Wirft ``LlmProviderError`` mit ``code="provider_unavailable"``, falls die
    Session nicht vollstaendig betriebsbereit ist.

    Args:
        provider_id: ID des Providers (z. B. "codex_cli").
        stage: Name der Workflow-Stage (z. B. "report_generation").
        run_id: Optionale ID des Laufs fuer Kontext-Logging.
    """
    if provider_id == PROVIDER_CODEX_CLI:
        readiness = codex_cli_readiness()
        logger.info(
            "CLI session preflight check provider=%s stage=%s run_id=%s ready=%s state=%s",
            provider_id,
            stage or "unknown",
            run_id or "none",
            readiness.ready,
            readiness.credentials,
        )
        verify_codex_cli_session_ready()


def verify_route_cli_preflight(
    route: "ResolvedRoute",
    *,
    run_id: Optional[str] = None,
) -> None:
    """Convenience-Preflight fuer eine bereits aufgeloeste ``ResolvedRoute``."""
    verify_cli_session_preflight(
        route.provider_id,
        stage=route.stage,
        run_id=run_id,
    )


__all__ = [
    "verify_cli_session_preflight",
    "verify_route_cli_preflight",
]
