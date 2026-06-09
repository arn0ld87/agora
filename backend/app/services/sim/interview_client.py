"""
Interview / IPC helpers for OASIS simulation runs.

Extracted from ``simulation_runner.py`` (M11 Phase 5 PR 4).
``simulation_runner.py`` keeps thin delegation class-methods for backward-compat.

Design constraints:
- No import of ``simulation_runner.py`` (avoids circular import).
- ``cls.RUN_STATE_DIR`` is passed as explicit keyword ``run_state_dir``.
- ``resolve_default_store`` is called lazily (no Flask app context needed at import).
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

from ...utils.logger import get_logger
from ..artifact_store import resolve_default_store
from ..simulation_ipc import SimulationIPCClient

logger = get_logger("agora.interview_client")


def _store():
    """Return the active SimulationArtifactStore (lazy, no app-context required)."""
    return resolve_default_store()


# ---------------------------------------------------------------------------
# Env-status helpers
# ---------------------------------------------------------------------------


def check_env_alive(simulation_id: str, *, run_state_dir: str) -> bool:
    """Return ``True`` if the simulation environment is alive (accepts Interview commands)."""
    sim_dir = os.path.join(run_state_dir, simulation_id)
    if not os.path.exists(sim_dir):
        return False
    ipc_client = SimulationIPCClient(sim_dir)
    return ipc_client.check_env_alive()


def get_env_status_detail(simulation_id: str) -> Dict[str, Any]:
    """Return detailed status dict for a simulation environment (reads ``env_status`` artifact)."""
    default_status: Dict[str, Any] = {
        "status": "stopped",
        "twitter_available": False,
        "reddit_available": False,
        "timestamp": None,
    }
    store = _store()
    status = store.read_json(simulation_id, "env_status", default=None)
    if not status:
        return default_status
    return {
        "status": status.get("status", "stopped"),
        "twitter_available": status.get("twitter_available", False),
        "reddit_available": status.get("reddit_available", False),
        "timestamp": status.get("timestamp"),
    }


# ---------------------------------------------------------------------------
# Interview helpers
# ---------------------------------------------------------------------------


def interview_agent(
    simulation_id: str,
    agent_id: int,
    prompt: str,
    platform: Optional[str] = None,
    timeout: float = 60.0,
    *,
    run_state_dir: str,
) -> Dict[str, Any]:
    """Interview a single agent via IPC.

    Raises:
        ValueError: Simulation does not exist or environment not running.
        TimeoutError: IPC response timed out.
    """
    sim_dir = os.path.join(run_state_dir, simulation_id)
    if not os.path.exists(sim_dir):
        raise ValueError(f"Simulation does not exist: {simulation_id}")

    ipc_client = SimulationIPCClient(sim_dir)
    if not ipc_client.check_env_alive():
        raise ValueError(
            f"Simulation environment not running or closed, cannot execute Interview: {simulation_id}"
        )

    logger.info(
        f"Send Interview command: simulation_id={simulation_id}, agent_id={agent_id}, platform={platform}"
    )
    response = ipc_client.send_interview(
        agent_id=agent_id, prompt=prompt, platform=platform, timeout=timeout
    )

    if response.status.value == "completed":
        return {
            "success": True,
            "agent_id": agent_id,
            "prompt": prompt,
            "result": response.result,
            "timestamp": response.timestamp,
        }
    return {
        "success": False,
        "agent_id": agent_id,
        "prompt": prompt,
        "error": response.error,
        "timestamp": response.timestamp,
    }


def interview_agents_batch(
    simulation_id: str,
    interviews: List[Dict[str, Any]],
    platform: Optional[str] = None,
    timeout: float = 120.0,
    *,
    run_state_dir: str,
) -> Dict[str, Any]:
    """Batch-interview multiple agents via IPC.

    Raises:
        ValueError: Simulation does not exist or environment not running.
        TimeoutError: IPC response timed out.
    """
    sim_dir = os.path.join(run_state_dir, simulation_id)
    if not os.path.exists(sim_dir):
        raise ValueError(f"Simulation does not exist: {simulation_id}")

    ipc_client = SimulationIPCClient(sim_dir)
    if not ipc_client.check_env_alive():
        raise ValueError(
            f"Simulation environment not running or closed, cannot execute Interview: {simulation_id}"
        )

    logger.info(
        f"Send batch Interview command: simulation_id={simulation_id}, count={len(interviews)}, platform={platform}"
    )
    response = ipc_client.send_batch_interview(
        interviews=interviews, platform=platform, timeout=timeout
    )

    if response.status.value == "completed":
        return {
            "success": True,
            "interviews_count": len(interviews),
            "result": response.result,
            "timestamp": response.timestamp,
        }
    return {
        "success": False,
        "interviews_count": len(interviews),
        "error": response.error,
        "timestamp": response.timestamp,
    }


def interview_all_agents(
    simulation_id: str,
    prompt: str,
    platform: Optional[str] = None,
    timeout: float = 180.0,
    *,
    run_state_dir: str,
) -> Dict[str, Any]:
    """Interview all agents in a simulation using the same prompt.

    Reads agent IDs from the ``simulation_config`` artifact and delegates to
    :func:`interview_agents_batch`.

    Raises:
        ValueError: Simulation / config missing, or no agents in config.
    """
    sim_dir = os.path.join(run_state_dir, simulation_id)
    if not os.path.exists(sim_dir):
        raise ValueError(f"Simulation does not exist: {simulation_id}")

    store = _store()
    if not store.exists(simulation_id, "simulation_config"):
        raise ValueError(f"Simulation config does not exist: {simulation_id}")

    config = store.read_json(simulation_id, "simulation_config", default=None)
    if not config:
        raise ValueError(f"Simulation config is unreadable: {simulation_id}")

    agent_configs = config.get("agent_configs", [])
    if not agent_configs:
        raise ValueError(f"No agents in simulation config: {simulation_id}")

    interviews = [
        {"agent_id": ac.get("agent_id"), "prompt": prompt}
        for ac in agent_configs
        if ac.get("agent_id") is not None
    ]

    logger.info(
        f"Send global Interview command: simulation_id={simulation_id}, agent_count={len(interviews)}, platform={platform}"
    )
    return interview_agents_batch(
        simulation_id=simulation_id,
        interviews=interviews,
        platform=platform,
        timeout=timeout,
        run_state_dir=run_state_dir,
    )


def close_simulation_env(
    simulation_id: str,
    timeout: float = 30.0,
    *,
    run_state_dir: str,
) -> Dict[str, Any]:
    """Send a close-environment command to a running simulation.

    Raises:
        ValueError: Simulation directory does not exist.
    """
    sim_dir = os.path.join(run_state_dir, simulation_id)
    if not os.path.exists(sim_dir):
        raise ValueError(f"Simulation does not exist: {simulation_id}")

    ipc_client = SimulationIPCClient(sim_dir)
    if not ipc_client.check_env_alive():
        return {"success": True, "message": "Environment already closed"}

    logger.info(f"Send close environment command: simulation_id={simulation_id}")
    try:
        response = ipc_client.send_close_env(timeout=timeout)
        return {
            "success": response.status.value == "completed",
            "message": "Close environment command sent",
            "result": response.result,
            "timestamp": response.timestamp,
        }
    except TimeoutError:
        return {
            "success": True,
            "message": (
                "Close environment command sent (timeout waiting for response, "
                "environment may be closing)"
            ),
        }


# ---------------------------------------------------------------------------
# Interview history (SQLite)
# ---------------------------------------------------------------------------


def _get_interview_history_from_db(
    db_path: str,
    platform_name: str,
    agent_id: Optional[int] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Read interview history records from a single platform SQLite database."""
    if not os.path.exists(db_path):
        return []

    results: List[Dict[str, Any]] = []
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        if agent_id is not None:
            cursor.execute(
                """
                SELECT user_id, info, created_at
                FROM trace
                WHERE action = 'interview' AND user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (agent_id, limit),
            )
        else:
            cursor.execute(
                """
                SELECT user_id, info, created_at
                FROM trace
                WHERE action = 'interview'
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )

        for user_id, info_json, created_at in cursor.fetchall():
            try:
                info = json.loads(info_json) if info_json else {}
            except json.JSONDecodeError:
                info = {"raw": info_json}
            results.append(
                {
                    "agent_id": user_id,
                    "response": info.get("response", info),
                    "prompt": info.get("prompt", ""),
                    "timestamp": created_at,
                    "platform": platform_name,
                }
            )
        conn.close()
    except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.error(f"Failed to read Interview history ({platform_name}): {e}")

    return results


def get_interview_history(
    simulation_id: str,
    platform: Optional[str] = None,
    agent_id: Optional[int] = None,
    limit: int = 100,
    *,
    run_state_dir: str,
) -> List[Dict[str, Any]]:
    """Return interview history for a simulation from per-platform SQLite DBs.

    ``platform`` may be ``"reddit"``, ``"twitter"``, or ``None`` (both).
    When both platforms are queried, the combined result is capped at *limit*.
    """
    sim_dir = os.path.join(run_state_dir, simulation_id)

    platforms = [platform] if platform in ("reddit", "twitter") else ["twitter", "reddit"]

    results: List[Dict[str, Any]] = []
    for p in platforms:
        db_path = os.path.join(sim_dir, f"{p}_simulation.db")
        results.extend(
            _get_interview_history_from_db(
                db_path=db_path,
                platform_name=p,
                agent_id=agent_id,
                limit=limit,
            )
        )

    results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    if len(platforms) > 1 and len(results) > limit:
        results = results[:limit]
    return results
