"""IPC command handler for parallel simulation runner."""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

try:
    from oasis import ActionType, ManualAction
except ImportError:
    from oasis.social_platform.typing import ActionType  # type: ignore[import-not-found]
    ManualAction = None  # type: ignore[assignment]

try:
    from .sim_runtime.budget_guard import SubprocessBudgetGuard
    from .sim_runtime.ipc import report_attribution
except ImportError:
    from sim_runtime.budget_guard import SubprocessBudgetGuard
    from sim_runtime.ipc import report_attribution

IPC_COMMANDS_DIR = "ipc_commands"
IPC_RESPONSES_DIR = "ipc_responses"
ENV_STATUS_FILE = "env_status.json"

class CommandType:
    """Command type constants"""
    INTERVIEW = "interview"
    BATCH_INTERVIEW = "batch_interview"
    CLOSE_ENV = "close_env"


class ParallelIPCHandler:
    """
    Dual-platform IPC command handler
    
    Manage environments of both platforms, handle Interview commands
    """
    
    def __init__(
        self,
        simulation_dir: str,
        twitter_env=None,
        twitter_agent_graph=None,
        reddit_env=None,
        reddit_agent_graph=None,
        redis_bridge=None,
        budget_guard: Optional[SubprocessBudgetGuard] = None,
    ):
        self.simulation_dir = simulation_dir
        self.twitter_env = twitter_env
        self.twitter_agent_graph = twitter_agent_graph
        self.reddit_env = reddit_env
        self.reddit_agent_graph = reddit_agent_graph
        # Tech-Review Slice B4c: ohne Guard bucht kein Interview-Kommando
        # dieses Handlers seinen Verbrauch auf einen Report-Run — derselbe
        # Mechanismus wie ``sim_runtime.ipc.IPCHandler`` (#1478 Codex P1).
        self.budget_guard = budget_guard

        self.commands_dir = os.path.join(simulation_dir, IPC_COMMANDS_DIR)
        self.responses_dir = os.path.join(simulation_dir, IPC_RESPONSES_DIR)
        self.status_file = os.path.join(simulation_dir, ENV_STATUS_FILE)

        # Issue #17: Redis bridge runs alongside file polling. Both paths
        # call _execute_command(); seen_command_ids dedupes the dispatch.
        self.redis_bridge = redis_bridge
        self.seen_command_ids: set = set()

        # Ensure directory exists
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)
    
    def update_status(self, status: str):
        """Update environment status"""
        with open(self.status_file, 'w', encoding='utf-8') as f:
            json.dump({
                "status": status,
                "twitter_available": self.twitter_env is not None,
                "reddit_available": self.reddit_env is not None,
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
        budget_exceeded: Optional[Dict[str, Any]] = None,
    ):
        """Send response: write file (legacy path) and mirror to Redis (issue #17).

        ``budget_exceeded`` (#1478 Codex P1, Runde 7): additiv gegenueber dem
        bisherigen Response-Format. Ein hartes Report-Budget, das waehrend
        ``env.step()`` erreicht wird, ist kein generischer Interview-Fehler,
        sondern das Ende des Report-Laufs — ``error`` allein (ein Freitext)
        war fuer den Flask-Prozess nicht sicher von einem gewoehnlichen
        Interview-Fehler unterscheidbar, ohne den Fehlertext zu parsen. Dieses
        Feld traegt ``dimension``/``observed``/``threshold`` strukturiert und
        bleibt ``None`` fuer jede andere Fehlerursache — bestehende Consumer,
        die das Feld nicht kennen, ignorieren es unveraendert.
        """
        response = {
            "command_id": command_id,
            "status": status,
            "result": result,
            "error": error,
            "budget_exceeded": budget_exceeded,
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
    
    def _get_env_and_graph(self, platform: str):
        """
        Get environment and agent_graph for specified platform
        
        Args:
            platform: Platform name ("twitter" or "reddit")
            
        Returns:
            (env, agent_graph, platform_name) or (None, None, None)
        """
        if platform == "twitter" and self.twitter_env:
            return self.twitter_env, self.twitter_agent_graph, "twitter"
        elif platform == "reddit" and self.reddit_env:
            return self.reddit_env, self.reddit_agent_graph, "reddit"
        else:
            return None, None, None
    
    async def _interview_single_platform(
        self, agent_id: int, prompt: str, platform: str, report_run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute Interview on a single platform

        Returns:
            Dictionary containing result, or dictionary containing error.
            If BudgetExceededError is raised, returns a dict with
            "budget_exceeded" containing structured dimension/observed/threshold.
        """
        from app.services.run_budget import BudgetExceededError

        env, agent_graph, actual_platform = self._get_env_and_graph(platform)

        if not env or not agent_graph:
            return {"platform": platform, "error": f"{platform}platform unavailable"}

        try:
            agent = agent_graph.get_agent(agent_id)
            interview_action = ManualAction(
                action_type=ActionType.INTERVIEW,
                action_args={"prompt": prompt}
            )
            actions = {agent: interview_action}
            # Tech-Review Slice B4c: physische Modellaufrufe waehrend dieses
            # Interviews auf den Report-Run buchen statt (unsichtbar) auf die
            # laufende Simulation — siehe sim_runtime.ipc.report_attribution.
            with report_attribution(self.budget_guard, report_run_id):
                await env.step(actions)

            result = self._get_interview_result(agent_id, actual_platform)
            result["platform"] = actual_platform
            return result

        except BudgetExceededError as e:
            # Structure the budget exceeded error for the caller to handle
            return {
                "platform": platform,
                "error": str(e),
                "budget_exceeded": {
                    "dimension": e.dimension,
                    "observed": e.observed,
                    "threshold": e.threshold,
                },
            }
        except Exception as e:
            return {"platform": platform, "error": str(e)}

    async def handle_interview(
        self,
        command_id: str,
        agent_id: int,
        prompt: str,
        platform: str = None,
        report_run_id: Optional[str] = None,
    ) -> bool:
        """
        Handle single Agent interview command

        Args:
            command_id: Command ID
            agent_id: Agent ID
            prompt: Interview question
            platform: Specify platform (optional)
                - "twitter": Interview only Twitter platform
                - "reddit": Interview only Reddit platform
                - None/unspecified: Interview both platforms simultaneously, return integrated result
            report_run_id: Report-Run, dessen Budget dieses Interview belastet
                (Tech-Review Slice B4c; siehe sim_runtime.ipc.IPCHandler).

        Returns:
            True means success, False means failure
        """
        # If platform is specified, only interview that platform
        if platform in ("twitter", "reddit"):
            result = await self._interview_single_platform(agent_id, prompt, platform, report_run_id)

            if "error" in result:
                budget_exceeded = result.get("budget_exceeded")
                await self.send_response(command_id, "failed", error=result["error"], budget_exceeded=budget_exceeded)
                if budget_exceeded:
                    print(f"  Interview failed (budget exceeded): agent_id={agent_id}, platform={platform}, error={result['error']}")
                else:
                    print(f"  Interview failed: agent_id={agent_id}, platform={platform}, error={result['error']}")
                return False
            else:
                await self.send_response(command_id, "completed", result=result)
                print(f"  Interview completed: agent_id={agent_id}, platform={platform}")
                return True

        # Platform not specified: interview both platforms simultaneously
        if not self.twitter_env and not self.reddit_env:
            await self.send_response(command_id, "failed", error="No available simulation environment")
            return False

        results = {
            "agent_id": agent_id,
            "prompt": prompt,
            "platforms": {}
        }
        success_count = 0
        budget_exceeded_info: Optional[Dict[str, Any]] = None

        # Interview both platforms in parallel
        tasks = []
        platforms_to_interview = []

        if self.twitter_env:
            tasks.append(self._interview_single_platform(agent_id, prompt, "twitter", report_run_id))
            platforms_to_interview.append("twitter")

        if self.reddit_env:
            tasks.append(self._interview_single_platform(agent_id, prompt, "reddit", report_run_id))
            platforms_to_interview.append("reddit")
        
        # Execute in parallel
        platform_results = await asyncio.gather(*tasks)
        
        # Detect budget_exceeded BEFORE success_count aggregation
        # If any platform hit a hard budget, that takes precedence — the Run
        # must end stopped/termination_reason=budget_* (never soften).
        for platform_name, platform_result in zip(platforms_to_interview, platform_results):
            results["platforms"][platform_name] = platform_result
            if "error" not in platform_result:
                success_count += 1
            elif budget_exceeded_info is None and platform_result.get("budget_exceeded"):
                # First budget_exceeded wins — Run ends with that dimension
                budget_exceeded_info = platform_result["budget_exceeded"]
        
        if budget_exceeded_info:
            # Budget exceeded on at least one platform: report structured abort
            errors = [f"{p}: {r.get('error', 'Unknown error')}" for p, r in results["platforms"].items()]
            await self.send_response(
                command_id, "failed", error="; ".join(errors), budget_exceeded=budget_exceeded_info
            )
            print(f"  Interview failed (budget exceeded): agent_id={agent_id}, dimension={budget_exceeded_info['dimension']}")
            return False

        if success_count > 0:
            await self.send_response(command_id, "completed", result=results)
            print(f"  Interview completed: agent_id={agent_id}, success_platforms={success_count}/{len(platforms_to_interview)}")
            return True
        else:
            errors = [f"{p}: {r.get('error', 'Unknown error')}" for p, r in results["platforms"].items()]
            await self.send_response(command_id, "failed", error="; ".join(errors))
            print(f"  Interview failed: agent_id={agent_id}, All platforms failed")
            return False
    
    async def handle_batch_interview(
        self,
        command_id: str,
        interviews: List[Dict],
        platform: str = None,
        report_run_id: Optional[str] = None,
    ) -> bool:
        """
        Handle batch interview command

        Args:
            command_id: Command ID
            interviews: [{"agent_id": int, "prompt": str, "platform": str(optional)}, ...]
            platform: default platform (can be overridden by each interview item)
                - "twitter": Interview only Twitter platform
                - "reddit": Interview only Reddit platform
                - None/unspecified: Interview both platforms simultaneously for each Agent
            report_run_id: Report-Run, dessen Budget dieser Batch belastet
                (Tech-Review Slice B4c; siehe sim_runtime.ipc.IPCHandler).
        """
        from app.services.run_budget import BudgetExceededError

        # Group by platform
        twitter_interviews = []
        reddit_interviews = []
        both_platforms_interviews = []  # Need to interview both platforms simultaneously
        
        for interview in interviews:
            item_platform = interview.get("platform", platform)
            if item_platform == "twitter":
                twitter_interviews.append(interview)
            elif item_platform == "reddit":
                reddit_interviews.append(interview)
            else:
                # Platform not specified: interview both platforms
                both_platforms_interviews.append(interview)
        
        # Split both_platforms_interviews to two platforms
        if both_platforms_interviews:
            if self.twitter_env:
                twitter_interviews.extend(both_platforms_interviews)
            if self.reddit_env:
                reddit_interviews.extend(both_platforms_interviews)
        
        results = {}
        budget_exceeded_info: Optional[Dict[str, Any]] = None
        
        # Handle Twitter platform interview
        if twitter_interviews and self.twitter_env:
            try:
                twitter_actions = {}
                for interview in twitter_interviews:
                    agent_id = interview.get("agent_id")
                    prompt = interview.get("prompt", "")
                    try:
                        agent = self.twitter_agent_graph.get_agent(agent_id)
                        twitter_actions[agent] = ManualAction(
                            action_type=ActionType.INTERVIEW,
                            action_args={"prompt": prompt}
                        )
                    except Exception as e:
                        print(f"  Warning: Unable to get Twitter Agent {agent_id}: {e}")
                
                if twitter_actions:
                    with report_attribution(self.budget_guard, report_run_id):
                        await self.twitter_env.step(twitter_actions)

                    for interview in twitter_interviews:
                        agent_id = interview.get("agent_id")
                        result = self._get_interview_result(agent_id, "twitter")
                        result["platform"] = "twitter"
                        results[f"twitter_{agent_id}"] = result
            except BudgetExceededError as e:
                budget_exceeded_info = {
                    "dimension": e.dimension,
                    "observed": e.observed,
                    "threshold": e.threshold,
                }
                print(f"  Twitter batch Interview failed (budget exceeded): {e}")
            except Exception as e:
                print(f"  Twitter batch Interview failed: {e}")
        
        # Handle Reddit platform interview
        if reddit_interviews and self.reddit_env:
            try:
                reddit_actions = {}
                for interview in reddit_interviews:
                    agent_id = interview.get("agent_id")
                    prompt = interview.get("prompt", "")
                    try:
                        agent = self.reddit_agent_graph.get_agent(agent_id)
                        reddit_actions[agent] = ManualAction(
                            action_type=ActionType.INTERVIEW,
                            action_args={"prompt": prompt}
                        )
                    except Exception as e:
                        print(f"  Warning: Unable to get Reddit Agent {agent_id}: {e}")
                
                if reddit_actions:
                    with report_attribution(self.budget_guard, report_run_id):
                        await self.reddit_env.step(reddit_actions)

                    for interview in reddit_interviews:
                        agent_id = interview.get("agent_id")
                        result = self._get_interview_result(agent_id, "reddit")
                        result["platform"] = "reddit"
                        results[f"reddit_{agent_id}"] = result
            except BudgetExceededError as e:
                # First budget_exceeded wins — Run ends with that dimension
                if budget_exceeded_info is None:
                    budget_exceeded_info = {
                        "dimension": e.dimension,
                        "observed": e.observed,
                        "threshold": e.threshold,
                    }
                print(f"  Reddit batch Interview failed (budget exceeded): {e}")
            except Exception as e:
                print(f"  Reddit batch Interview failed: {e}")
        
        if budget_exceeded_info:
            # Budget exceeded on at least one platform: report structured abort
            await self.send_response(
                command_id, "failed", error="Budget exceeded during batch interview", budget_exceeded=budget_exceeded_info
            )
            print(f"  Batch Interview failed (budget exceeded): dimension={budget_exceeded_info['dimension']}")
            return False
        
        if results:
            await self.send_response(command_id, "completed", result={
                "interviews_count": len(results),
                "results": results
            })
            print(f"  Batch Interview completed: {len(results)} Agents")
            return True
        else:
            await self.send_response(command_id, "failed", error="No successful interviews")
            return False
    
    def _get_interview_result(self, agent_id: int, platform: str) -> Dict[str, Any]:
        """Get the latest Interview result from database"""
        db_path = os.path.join(self.simulation_dir, f"{platform}_simulation.db")
        
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
            
            # Query the latest Interview record
            cursor.execute("""
                SELECT user_id, info, created_at
                FROM trace
                WHERE action = ? AND user_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (ActionType.INTERVIEW.value, agent_id))
            
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
                args.get("prompt", ""),
                args.get("platform"),
                report_run_id=args.get("report_run_id"),
            )
            return True

        elif command_type == CommandType.BATCH_INTERVIEW:
            await self.handle_batch_interview(
                command_id,
                args.get("interviews", []),
                args.get("platform"),
                report_run_id=args.get("report_run_id"),
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
        """Bridge callback: dispatch a Redis-delivered command event."""
        command_id = event.get("correlation_id") or event.get("command_id")
        if not command_id:
            return
        if command_id in self.seen_command_ids:
            return
        self.seen_command_ids.add(command_id)

        command_type = event.get("type")
        args = event.get("payload") or {}
        print(f"\n[redis] Received IPC command: {command_type}, id={command_id}")
        await self._execute_command(command_id, command_type, args)

