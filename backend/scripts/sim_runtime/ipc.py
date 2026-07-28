"""File- und Redis-IPC für die OASIS-Single-Platform-Runner.

Inhaltlich eins-zu-eins aus ``run_twitter_simulation.py`` bzw.
``run_reddit_simulation.py`` extrahiert; die beiden Implementierungen waren
bis auf den DB-Dateinamen in ``_get_interview_result`` identisch.

Verhaltenserhalt:

* Datei-IPC-Layout (``ipc_commands`` / ``ipc_responses`` / ``env_status.json``)
  bleibt unverändert.
* Command-Deduplizierung gegen den Redis-Bus (``seen_command_ids``) bleibt.
* Response-Format (Felder, Reihenfolge, ``ensure_ascii=False``, ``indent=2``)
  bleibt.
* Close-Env liefert ``False`` aus ``_execute_command`` / ``process_commands``,
  Interview/Batch-Interview liefern ``True``.

Oasis-Symbole (``ManualAction``, ``ActionType.INTERVIEW``) werden vom Runner
injeziert, statt sie auf Modul-Ebene zu importieren. Dadurch bleibt
``sim_runtime.ipc`` ohne die torch-abhängige Oasis-Laufzeit importierbar und
ist im Test-Tree mit Fakes charakterisierbar. Das injizierte Verhalten ist
identisch mit dem bisherigen Modul-Level-Import.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# IPC-related constants (früher Modul-Level in den Runner-Skripten).
IPC_COMMANDS_DIR = "ipc_commands"
IPC_RESPONSES_DIR = "ipc_responses"
ENV_STATUS_FILE = "env_status.json"


class CommandType:
    """Command type constants"""

    INTERVIEW = "interview"
    BATCH_INTERVIEW = "batch_interview"
    CLOSE_ENV = "close_env"


class IPCHandler:
    """IPC command handler"""

    def __init__(
        self,
        simulation_dir: str,
        env: Any,
        agent_graph: Any,
        *,
        db_filename: str,
        interview_action_type: Any,
        manual_action_cls: Any,
        redis_bridge: Any = None,
    ) -> None:
        self.simulation_dir = simulation_dir
        self.env = env
        self.agent_graph = agent_graph
        self.commands_dir = os.path.join(simulation_dir, IPC_COMMANDS_DIR)
        self.responses_dir = os.path.join(simulation_dir, IPC_RESPONSES_DIR)
        self.status_file = os.path.join(simulation_dir, ENV_STATUS_FILE)
        self._running = True
        # Issue #17: Redis bridge runs alongside file polling. Both paths
        # call _execute_command(); seen_command_ids dedupes the dispatch.
        self.redis_bridge = redis_bridge
        self.seen_command_ids: set = set()

        # Injizierte Oasis-Symbole — bisher Modul-Level-Import in den Runnern.
        self.db_filename = db_filename
        self.interview_action_type = interview_action_type
        self.manual_action_cls = manual_action_cls

        # Ensure directories exist
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)

    def update_status(self, status: str) -> None:
        """Update environment status"""
        with open(self.status_file, 'w', encoding='utf-8') as f:
            json.dump({
                "status": status,
                "timestamp": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)

    def poll_command(self) -> Optional[Dict[str, Any]]:
        """Poll for pending commands"""
        if not os.path.exists(self.commands_dir):
            return None

        # Get command files (sorted by time)
        command_files = []
        for filename in os.listdir(self.commands_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.commands_dir, filename)
                command_files.append((filepath, os.path.getmtime(filepath)))

        command_files.sort(key=lambda x: x[1])

        for filepath, _ in command_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

        return None

    async def send_response(
        self,
        command_id: str,
        status: str,
        result: Dict = None,
        error: str = None,
    ) -> None:
        """Send response: write file (legacy path) and mirror to Redis (issue #17)."""
        response = {
            "command_id": command_id,
            "status": status,
            "result": result,
            "error": error,
            "timestamp": datetime.now().isoformat()
        }

        response_file = os.path.join(self.responses_dir, f"{command_id}.json")
        with open(response_file, 'w', encoding='utf-8') as f:
            json.dump(response, f, ensure_ascii=False, indent=2)

        # Delete command file (best-effort; bridge-only commands have none)
        command_file = os.path.join(self.commands_dir, f"{command_id}.json")
        try:
            os.remove(command_file)
        except OSError:
            pass

        # Issue #17: mirror to Redis if the bridge is active. File response
        # stays as the rolling-upgrade fallback.
        if self.redis_bridge is not None and self.redis_bridge.active:
            await self.redis_bridge.publish_response(command_id, response)

    async def handle_interview(self, command_id: str, agent_id: int, prompt: str) -> bool:
        """
        Handle single Agent interview command

        Returns:
            True means success, False means failure
        """
        try:
            # Get Agent
            agent = self.agent_graph.get_agent(agent_id)

            # Create Interview action
            interview_action = self.manual_action_cls(
                action_type=self.interview_action_type,
                action_args={"prompt": prompt}
            )

            # Execute Interview
            actions = {agent: interview_action}
            await self.env.step(actions)

            # Get result from database
            result = self._get_interview_result(agent_id)

            await self.send_response(command_id, "completed", result=result)
            print(f"  Interview completed: agent_id={agent_id}")
            return True

        except Exception as e:
            error_msg = str(e)
            print(f"  Interview failed: agent_id={agent_id}, error={error_msg}")
            await self.send_response(command_id, "failed", error=error_msg)
            return False

    async def handle_batch_interview(self, command_id: str, interviews: List[Dict]) -> bool:
        """
        Handle batch interview command

        Args:
            interviews: [{"agent_id": int, "prompt": str}, ...]
        """
        try:
            # Build action dictionary
            actions = {}
            agent_prompts = {}  # Record prompt for each agent

            for interview in interviews:
                agent_id = interview.get("agent_id")
                prompt = interview.get("prompt", "")

                try:
                    agent = self.agent_graph.get_agent(agent_id)
                    actions[agent] = self.manual_action_cls(
                        action_type=self.interview_action_type,
                        action_args={"prompt": prompt}
                    )
                    agent_prompts[agent_id] = prompt
                except Exception as e:
                    print(f"  Warning: Unable to get Agent {agent_id}: {e}")

            if not actions:
                await self.send_response(command_id, "failed", error="No valid Agents")
                return False

            # Execute batch Interview
            await self.env.step(actions)

            # Get all results
            results = {}
            for agent_id in agent_prompts.keys():
                result = self._get_interview_result(agent_id)
                results[agent_id] = result

            await self.send_response(command_id, "completed", result={
                "interviews_count": len(results),
                "results": results
            })
            print(f"  Batch Interview completed: {len(results)} Agents")
            return True

        except Exception as e:
            error_msg = str(e)
            print(f"  batchInterview failed: {error_msg}")
            await self.send_response(command_id, "failed", error=error_msg)
            return False

    def _get_interview_result(self, agent_id: int) -> Dict[str, Any]:
        """Get the latest Interview result from database"""
        db_path = os.path.join(self.simulation_dir, self.db_filename)

        result = {
            "agent_id": agent_id,
            "response": None,
            "timestamp": None
        }

        if not os.path.exists(db_path):
            return result

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # query latestInterviewrecord
            cursor.execute("""
                SELECT user_id, info, created_at
                FROM trace
                WHERE action = ? AND user_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (self.interview_action_type.value, agent_id))

            row = cursor.fetchone()
            if row:
                user_id, info_json, created_at = row
                try:
                    info = json.loads(info_json) if info_json else {}
                    result["response"] = info.get("response", info)
                    result["timestamp"] = created_at
                except json.JSONDecodeError:
                    result["response"] = info_json

            conn.close()

        except Exception as e:
            print(f"  Failed to read Interview result: {e}")

        return result

    async def _execute_command(
        self, command_id: str, command_type: str, args: Dict[str, Any]
    ) -> bool:
        """Run a deduped command and return False iff the env must shut down."""
        if command_type == CommandType.INTERVIEW:
            await self.handle_interview(
                command_id,
                args.get("agent_id", 0),
                args.get("prompt", "")
            )
            return True

        elif command_type == CommandType.BATCH_INTERVIEW:
            await self.handle_batch_interview(
                command_id,
                args.get("interviews", [])
            )
            return True

        elif command_type == CommandType.CLOSE_ENV:
            print("Received close environment command")
            await self.send_response(
                command_id, "completed", result={"message": "Environment will close"}
            )
            return False

        else:
            await self.send_response(
                command_id, "failed", error=f"Unknown command type: {command_type}"
            )
            return True

    async def process_commands(self) -> bool:
        """Poll the file IPC layer for pending commands and dispatch."""
        command = self.poll_command()
        if not command:
            return True

        command_id = command.get("command_id")
        # Dedup against the Redis bridge: if the bus already dispatched this
        # command, just clean up the lingering file and move on.
        if command_id in self.seen_command_ids:
            try:
                os.remove(os.path.join(self.commands_dir, f"{command_id}.json"))
            except OSError:
                pass
            return True
        self.seen_command_ids.add(command_id)

        command_type = command.get("command_type")
        args = command.get("args", {})

        print(f"\n[file] Received IPC command: {command_type}, id={command_id}")
        return await self._execute_command(command_id, command_type, args)

    async def dispatch_bus_event(self, event: Dict[str, Any]) -> None:
        """Bridge callback: dispatch a Redis-delivered command event.

        Event shape: {type, simulation_id, payload, correlation_id, ts}.
        Returns nothing — close-env shutdown is handled out-of-band by the
        existing wait loop reacting to env_status / shutdown_event.
        """
        command_id = event.get("correlation_id") or event.get("command_id")
        if not command_id:
            return
        if command_id in self.seen_command_ids:
            return  # File polling beat us to it
        self.seen_command_ids.add(command_id)

        command_type = event.get("type")
        args = event.get("payload") or {}
        print(f"\n[redis] Received IPC command: {command_type}, id={command_id}")
        await self._execute_command(command_id, command_type, args)