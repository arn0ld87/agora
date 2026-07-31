"""Basis-Runner für OASIS-Single-Platform-Simulationen (Twitter/Reddit).

Verhaltensneutral aus ``run_twitter_simulation.py`` und
``run_reddit_simulation.py`` extrahiert: beide Runner-Klassen waren bis auf
Plattform-Konfiguration (verfügbare Actions, Profile-Dateiname, DB-Dateiname,
``oasis.DefaultPlatformType``, Graph-Generator) und das Handling von
``initial_actions`` (Reddit appended an bestehende Listen, Twitter
überschreibt) identisch.

Plattform-spezifische Werte werden über Klassen-Attribute und die
Template-Method ``_assign_initial_action`` injiziert; die Entry-Points
(``run_twitter_simulation.py`` / ``run_reddit_simulation.py``) definieren
dünne Subklassen plus Modul-Setup (Profiling, Parser, ``main``).

Erhaltungsregeln (verbatim aus der Refactor-Spec):

* Gib niemals Secrets in Logs aus.
* Vererbe keine zusätzlichen Environment-Variablen an OASIS-Subprozesse.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import signal
import sys
from datetime import datetime
from typing import Any, Dict, List

# _sim_common: Paket- und Direktaufruf-Import-Muster wie die Runner-Skripte.
# Nur die in den Runner-Methoden genutzten Symbole; Modul-Level-Side-Effects
# (Tracing/Logging/Env-Load/Profiling) bleiben in den Entry-Points.
try:
    from ._sim_common import (
        build_camel_completion_params,
        compute_start_hour_offset,
        detect_oasis_platform,
        preflight_model_probe,
    )
except ImportError:  # direct script execution
    from _sim_common import (
        build_camel_completion_params,
        compute_start_hour_offset,
        detect_oasis_platform,
        preflight_model_probe,
    )

# IPC layer (CommandType, constants, IPCHandler) — zentral in sim_runtime.ipc.
try:
    from .sim_runtime.ipc import IPCHandler
except ImportError:  # direct script execution
    from sim_runtime.ipc import IPCHandler

# CAMEL/Oasis — harte Abhängigkeit wie in den Runner-Skripten.
from camel.models import ModelFactory  # noqa: E402
from camel.types import ModelPlatformType  # noqa: E402
import oasis  # noqa: E402
from oasis import ActionType, LLMAction, ManualAction  # noqa: E402

# Agent tools (optional — nur geladen, wenn enable_agent_tools gesetzt ist).
# Die Entry-Points behalten ihren eigenen agent_tools-Import als
# Modul-Attribut-Quelle (AgentToolRegistry/ToolAwareActionLoop); dieser
# Import hier versorgt nur die in ``run`` genutzten Symbole.
try:
    from agent_tools import create_tool_aware_loop
    AGENT_TOOLS_AVAILABLE = True
except ImportError:
    create_tool_aware_loop = None  # type: ignore[assignment]
    AGENT_TOOLS_AVAILABLE = False

# Global variables: for signal handling (von den Entry-Point-``main``
# Funktionen gesetzt; ``run`` liest ``_shutdown_event``).
_shutdown_event = None
_cleanup_done = False

logger = logging.getLogger(__name__)


def setup_signal_handlers():
    """
    Set signal handlers to ensure proper exit when receiving SIGTERM/SIGINT
    Give program a chance to clean up resources properly (close database, environment, etc.)
    """
    def signal_handler(signum, frame):
        global _cleanup_done
        sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        print(f"\nReceived {sig_name} signal, exiting...")
        if not _cleanup_done:
            _cleanup_done = True
            if _shutdown_event:
                _shutdown_event.set()
        else:
            # Force exit only after receiving signal repeatedly
            print("Force exit...")
            sys.exit(1)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


class SinglePlatformRunner:
    """Single-platform OASIS simulation runner (Twitter/Reddit).

    Subclasses setzen die Plattform-Konfiguration via Klassen-Attribute und
    überschreiben ggf. ``_assign_initial_action`` für plattform-spezifisches
    Initial-Posts-Handling.
    """

    # --- Plattform-Konfiguration (von Subklasse zu setzen) ---
    PLATFORM_NAME: str = ""        # "Twitter" / "Reddit" — für Banner-Prints
    PLATFORM_SLUG: str = ""        # "twitter" / "reddit" — für Log-Strings
    PROFILE_FILENAME: str = ""     # "twitter_profiles.csv" / "reddit_profiles.json"
    DB_FILENAME: str = ""          # "twitter_simulation.db" / "reddit_simulation.db"
    PLATFORM_TYPE: Any = None      # oasis.DefaultPlatformType.TWITTER / REDDIT
    AVAILABLE_ACTIONS: List[Any] = []
    AVAILABLE_ACTION_NAMES: List[str] = []
    GRAPH_GENERATOR: Any = None    # generate_twitter_agent_graph / generate_reddit_agent_graph

    def __init__(self, config_path: str, wait_for_commands: bool = True):
        """
        Initialize simulation runner

        Args:
            config_path: Configuration file path (simulation_config.json)
            wait_for_commands: Whether to wait for commands after simulation completes (default True)
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.simulation_dir = os.path.dirname(config_path)
        self.wait_for_commands = wait_for_commands
        self.env = None
        self.agent_graph = None
        self.ipc_handler = None
        self.tool_loop = None
        self.redis_bridge = None  # Issue #17: optional Redis Pub/Sub listener

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration file"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _get_profile_path(self) -> str:
        """Get Profile file path (platform-spezifischer Dateiname)"""
        return os.path.join(self.simulation_dir, self.PROFILE_FILENAME)

    def _get_db_path(self) -> str:
        """Get database path"""
        return os.path.join(self.simulation_dir, self.DB_FILENAME)

    def _create_model(self):
        """
        Create LLM model

        Unified use of configuration in project root .env file (highest priority)：
        - LLM_API_KEY: API key
        - LLM_BASE_URL: API base URL
        - LLM_MODEL_NAME: Model name
        """
        # Read configuration from .env first
        llm_api_key = os.environ.get("LLM_API_KEY", "")
        llm_base_url = os.environ.get("LLM_BASE_URL", "")
        llm_model = os.environ.get("LLM_MODEL_NAME", "")

        # If not in .env, use config as fallback
        if not llm_model:
            llm_model = self.config.get("llm_model", "qwen3-coder-next:cloud")

        platform = detect_oasis_platform(llm_model, llm_base_url)
        think_on = os.environ.get("OLLAMA_THINKING", "false").lower() in ("1", "true", "yes")
        ctx_limit = int(os.environ.get("LLM_CONTEXT_LIMIT", "262144"))
        completion_max_tokens = int(os.environ.get("LLM_MAX_OUTPUT_TOKENS", "16384"))

        print(
            f"LLM configuration: model={llm_model}, "
            f"base_url={llm_base_url[:40] if llm_base_url else 'default'}..., "
            f"platform={platform.value}",
            flush=True,
        )

        model_cfg: dict = build_camel_completion_params(
            model=llm_model,
            completion_max_tokens=completion_max_tokens,
        )

        if platform == ModelPlatformType.GEMINI:
            # Gemini-3 requires thought_signature echo in multi-turn tool calls.
            # Route via CAMEL's GeminiModel; do NOT touch OPENAI_BASE_URL.
            os.environ["GOOGLE_API_KEY"] = llm_api_key or os.environ.get("GOOGLE_API_KEY", "")
            return ModelFactory.create(
                model_platform=ModelPlatformType.GEMINI,
                model_type=llm_model,
                model_config_dict=model_cfg,
            )

        elif platform == ModelPlatformType.OLLAMA:
            # Ollama Cloud no longer serves OpenAI-compat /v1.
            # CAMEL's OllamaModel speaks the native /api/chat endpoint.
            # Build extra_body inline: we already dispatched via the provider
            # SSoT (detect_oasis_platform), so re-running the _is_ollama_route
            # gate inside build_camel_extra_body() would be redundant detection.
            # (Since #670 that gate also delegates to the SSoT and no longer
            # mis-classifies :latest models or ollama.com URLs.)
            os.environ["OPENAI_API_KEY"] = llm_api_key or "dummy"  # CAMEL guard
            extra_body: dict = {"think": think_on}
            if ctx_limit is not None:
                extra_body["options"] = {"num_ctx": ctx_limit}
            model_cfg["extra_body"] = extra_body
            return ModelFactory.create(
                model_platform=ModelPlatformType.OLLAMA,
                model_type=llm_model,
                url=llm_base_url or None,
                api_key=llm_api_key or None,
                model_config_dict=model_cfg,
            )

        else:
            # OPENAI — real OpenAI, Anthropic compat gateways, Qwen Cloud, etc.
            # No extra_body: think/num_ctx are Ollama-only and would 400 here.
            if llm_api_key:
                os.environ["OPENAI_API_KEY"] = llm_api_key

            if not os.environ.get("OPENAI_API_KEY"):
                raise ValueError(
                    "Missing API Key configuration, please set LLM_API_KEY in .env file in project root"
                )

            if llm_base_url:
                os.environ["OPENAI_BASE_URL"] = llm_base_url
                os.environ["OPENAI_API_BASE"] = llm_base_url
                os.environ["OPENAI_API_BASE_URL"] = llm_base_url

            return ModelFactory.create(
                model_platform=ModelPlatformType.OPENAI,
                model_type=llm_model,
                model_config_dict=model_cfg,
                url=llm_base_url or None,
                api_key=llm_api_key or None,
            )

    def _get_active_agents_for_round(
        self,
        env,
        current_hour: int,
        round_num: int
    ) -> List:
        """
        Decide which Agents to activate this round based on time and configuration

        Args:
            env: OASISenvironment
            current_hour: current simulationhours（0-23）
            round_num: Current roundnumber

        Returns:
            activatedAgentlist
        """
        time_config = self.config.get("time_config", {})
        agent_configs = self.config.get("agent_configs", [])

        # Base activation count
        base_min = time_config.get("agents_per_hour_min", 5)
        base_max = time_config.get("agents_per_hour_max", 20)

        # Adjust by time period
        peak_hours = time_config.get("peak_hours", [9, 10, 11, 14, 15, 20, 21, 22])
        off_peak_hours = time_config.get("off_peak_hours", [0, 1, 2, 3, 4, 5])

        if current_hour in peak_hours:
            multiplier = time_config.get("peak_activity_multiplier", 1.5)
        elif current_hour in off_peak_hours:
            multiplier = time_config.get("off_peak_activity_multiplier", 0.3)
        else:
            multiplier = 1.0

        target_count = int(random.uniform(base_min, base_max) * multiplier)

        # Calculate activation probability based on each Agent's configuration
        candidates = []
        for cfg in agent_configs:
            agent_id = cfg.get("agent_id", 0)
            active_hours = cfg.get("active_hours", list(range(8, 23)))
            activity_level = cfg.get("activity_level", 0.5)

            # Check if in active time
            if current_hour not in active_hours:
                continue

            # Calculate probability based on activity level
            if random.random() < activity_level:
                candidates.append(agent_id)

        # Random selection
        selected_ids = random.sample(
            candidates,
            min(target_count, len(candidates))
        ) if candidates else []

        # Convert to Agent objects
        active_agents = []
        for agent_id in selected_ids:
            try:
                agent = env.agent_graph.get_agent(agent_id)
                active_agents.append((agent_id, agent))
            except Exception:
                pass

        return active_agents

    def _assign_initial_action(self, initial_actions: Dict, agent: Any, content: str) -> None:
        """Assign an initial CREATE_POST action for ``agent``.

        Default (Twitter-Verhalten): überschreibt eine bestehende Zuweisung.
        Reddit überschreibt diese Methode, um an eine bestehende Liste zu
        appenden statt zu überschreiben.
        """
        initial_actions[agent] = ManualAction(
            action_type=ActionType.CREATE_POST,
            action_args={"content": content}
        )

    async def run(self, max_rounds: int = None):
        """Run single-platform simulation

        Args:
            max_rounds: Maximum simulation rounds (optional, used to truncate long simulations)
        """
        print("=" * 60)
        print(f"OASIS {self.PLATFORM_NAME} Simulation")
        print(f"Configuration file: {self.config_path}")
        print(f"Simulation ID: {self.config.get('simulation_id', 'unknown')}")
        print(f"Wait mode: {'Enabled' if self.wait_for_commands else 'Disabled'}")
        print("=" * 60)

        # Load time configuration
        time_config = self.config.get("time_config", {})
        total_hours = time_config.get("total_simulation_hours", 72)
        minutes_per_round = time_config.get("minutes_per_round", 30)

        # Calculate total rounds
        total_rounds = (total_hours * 60) // minutes_per_round

        # If maximum rounds specified, truncate
        if max_rounds is not None and max_rounds > 0:
            original_rounds = total_rounds
            total_rounds = min(total_rounds, max_rounds)
            if total_rounds < original_rounds:
                print(f"\nRounds truncated: {original_rounds} -> {total_rounds} (max_rounds={max_rounds})")

        start_hour_offset = compute_start_hour_offset(self.config, total_rounds, minutes_per_round)
        if start_hour_offset != 0:
            print(f"Short run: shifting simulated clock to start at hour {start_hour_offset:02d}:00 (active-hour overlap)")

        print("\nSimulation parameters:")
        print(f"  - Total simulation duration: {total_hours}hours")
        print(f"  - Time per round: {minutes_per_round}minutes")
        print(f"  - Total rounds: {total_rounds}")
        if max_rounds:
            print(f"  - Maximum rounds limit: {max_rounds}")
        print(f"  - Number of Agents: {len(self.config.get('agent_configs', []))}")

        # Create model
        print("\nInitialize LLM model...")
        model = self._create_model()
        # Budget-Guard (Issue #764): Usage-Recording in den gemeinsamen
        # Run-Ledger + harte Limits an Runden-Grenzen. Aktiv sobald
        # AGORA_RUN_ID gesetzt ist; Hard-Limits nur mit budget_config.json.
        budget_guard = None
        try:
            try:
                from .budget_guard import SubprocessBudgetGuard
            except ImportError:  # direct script execution
                from sim_runtime.budget_guard import SubprocessBudgetGuard
            budget_guard = SubprocessBudgetGuard.from_environment(self.simulation_dir)
            if budget_guard is not None:
                model = budget_guard.wrap_model(model)
                print("[budget-guard] usage recording active"
                      + (f" (enforcement={budget_guard.enforcement})" if budget_guard.budget_config else ""))
        except Exception as exc:  # noqa: BLE001 — Guard ist Zusatz, kein Blocker
            print(f"[budget-guard] setup failed ({exc}); continuing without", flush=True)
            budget_guard = None
        # Preflight: ein einzelner Probe-Call vor dem Fan-out fängt permanente
        # Auth-/Routing-Fehler (401/403/404) mit klarer Root-Cause ab.
        preflight_model_probe(model)

        # Load Agent graph
        print("Load Agent Profile...")
        profile_path = self._get_profile_path()
        if not os.path.exists(profile_path):
            print(f"Error: Profile file does not exist: {profile_path}")
            return

        self.agent_graph = await self.GRAPH_GENERATOR(
            profile_path=profile_path,
            model=model,
            available_actions=self.AVAILABLE_ACTIONS,
        )

        # Memory-Token-Limit auch ohne Tool-Attach hochziehen — sonst kappt
        # CAMELs ScoreBasedContextCreator-Default bei 8192.
        try:
            from agent_tools import enforce_memory_token_limit
            enforce_memory_token_limit(self.agent_graph)
        except Exception as e:
            print(f"enforce_memory_token_limit ({self.PLATFORM_SLUG}-single) failed: {e}", flush=True)

        # Databasepath
        db_path = self._get_db_path()
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"Old database deleted: {db_path}")

        # Create environment
        print("Create OASIS environment...")
        self.env = oasis.make(
            agent_graph=self.agent_graph,
            platform=self.PLATFORM_TYPE,
            database_path=db_path,
            semaphore=30,  # Limit maximum concurrent LLM requests to prevent API overload
        )

        await self.env.reset()
        print("Environment initialization complete\n")

        # Initialize IPC handler
        self.ipc_handler = IPCHandler(
            self.simulation_dir,
            self.env,
            self.agent_graph,
            db_filename=self.DB_FILENAME,
            interview_action_type=ActionType.INTERVIEW,
            manual_action_cls=ManualAction,
        )
        self.ipc_handler.update_status("running")

        # Issue #17: optionaler Redis-Listener parallel zum File-Polling.
        redis_url = os.environ.get("REDIS_URL")
        if redis_url:
            try:
                from subprocess_redis_bridge import RedisIPCBridge
                sim_id = os.path.basename(self.simulation_dir.rstrip("/"))
                self.redis_bridge = RedisIPCBridge(
                    simulation_id=sim_id,
                    redis_url=redis_url,
                    on_command=self.ipc_handler.dispatch_bus_event,
                )
                started = await self.redis_bridge.start()
                if started:
                    self.ipc_handler.redis_bridge = self.redis_bridge
                    print(f"[IPC] Redis bridge active on {redis_url} for sim {sim_id}")
                else:
                    self.redis_bridge = None
            except Exception as exc:
                print(f"[IPC] Redis bridge setup failed ({exc}); falling back to file IPC")
                self.redis_bridge = None

        # Execute initial events
        event_config = self.config.get("event_config", {})
        initial_posts = event_config.get("initial_posts", [])

        if initial_posts:
            print(f"Execute initial events ({len(initial_posts)}initial posts)...")
            initial_actions = {}
            for post in initial_posts:
                agent_id = post.get("poster_agent_id", 0)
                content = post.get("content", "")
                try:
                    agent = self.env.agent_graph.get_agent(agent_id)
                    self._assign_initial_action(initial_actions, agent, content)
                except Exception as e:
                    print(f"  Warning: Unable to create for Agent {agent_id}Create initial posts: {e}")

            if initial_actions:
                await self.env.step(initial_actions)
                print(f"  Published {len(initial_actions)} initial posts")

        print("\nStart simulation loop...")
        start_time = datetime.now()

        # Initialize tool-aware action loop if enabled
        enable_tools = self.config.get("enable_agent_tools", False)
        if enable_tools and AGENT_TOOLS_AVAILABLE:
            print("[ToolUse] Agent tools enabled — initializing tool registry...")
            self.config["config_path"] = self.config_path
            self.tool_loop = create_tool_aware_loop(
                model=model,
                config=self.config,
                max_tool_calls=self.config.get("max_tool_calls_per_action", 2)
            )
            if self.tool_loop:
                print("[ToolUse] Tool registry ready")
            else:
                print("[ToolUse] Tool registry initialization failed (check Neo4j credentials)")
        elif enable_tools and not AGENT_TOOLS_AVAILABLE:
            print("[ToolUse] WARNING: enable_agent_tools=true but agent_tools.py could not be imported")

        budget_abort_info = None
        for round_num in range(total_rounds):
            # Honour pause flag from Flask (Phase 4 — soft-pause between rounds).
            try:
                from app.services.simulation_ipc import wait_while_paused, read_control_state
                wait_while_paused(self.simulation_dir)
                if read_control_state(self.simulation_dir).get("stop_requested"):
                    print(f"  Stop requested via control_state.json — exiting after round {round_num}")
                    break
            except Exception:
                pass

            # Budget-Guard (Issue #764): harte Limits an der Runden-Grenze,
            # BEVOR weitere planbare Modellaufrufe entstehen. Die laufende
            # Runde wurde zuvor sauber abgeschlossen; Teilresultate bleiben
            # in der SQLite-DB erhalten.
            if budget_guard is not None:
                try:
                    budget_abort_info = budget_guard.check_round_boundary(round_num)
                except Exception as exc:  # noqa: BLE001 — Check-Fehler stoppt die Sim nicht
                    print(f"[budget-guard] round check failed ({exc})", flush=True)
                    budget_abort_info = None
                if budget_abort_info is not None:
                    print(
                        f"  [budget-guard] hard budget exceeded "
                        f"({budget_abort_info['dimension']}: "
                        f"{budget_abort_info['observed']} >= {budget_abort_info['threshold']}) "
                        f"— stopping before round {round_num + 1}",
                        flush=True,
                    )
                    break

            # Calculate current simulation time
            simulated_minutes = round_num * minutes_per_round
            simulated_hour = (start_hour_offset + simulated_minutes // 60) % 24
            simulated_day = simulated_minutes // (60 * 24) + 1

            # Get Agents activated this round
            active_agents = self._get_active_agents_for_round(
                self.env, simulated_hour, round_num
            )

            if not active_agents:
                continue

            # Build actions
            if self.tool_loop and enable_tools:
                # Tool-aware action loop
                actions = {}
                for agent_id, agent in active_agents:
                    try:
                        # Get observation from OASIS environment
                        observation = ""
                        if hasattr(self.env, 'get_observation'):
                            observation = self.env.get_observation(agent)
                        elif hasattr(agent, 'observation'):
                            observation = str(agent.observation)

                        # Get agent profile info
                        agent_name = getattr(agent, 'username', f"Agent_{agent_id}")
                        agent_role = getattr(agent, 'profession', 'Unknown')
                        agent_bio = getattr(agent, 'bio', '')

                        action = await self.tool_loop.decide_action(
                            agent=agent,
                            observation=observation,
                            available_actions=self.AVAILABLE_ACTION_NAMES,
                            agent_name=agent_name,
                            agent_role=agent_role,
                            agent_bio=agent_bio,
                            language=self.config.get("language", "de")
                        )
                        actions[agent] = action
                    except Exception as e:
                        print(f"  [ToolUse] Agent {agent_id} tool loop failed: {e}")
                        actions[agent] = LLMAction()
            else:
                # Standard OASIS action
                actions = {
                    agent: LLMAction()
                    for _, agent in active_agents
                }

            # Execute action
            await self.env.step(actions)

            # Print progress
            if (round_num + 1) % 10 == 0 or round_num == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                progress = (round_num + 1) / total_rounds * 100
                print(f"  [Day {simulated_day}, {simulated_hour:02d}:00] "
                      f"Round {round_num + 1}/{total_rounds} ({progress:.1f}%) "
                      f"- {len(active_agents)} agents active "
                      f"- elapsed: {elapsed:.1f}s")

        total_elapsed = (datetime.now() - start_time).total_seconds()
        print("\nSimulation loop completed!")
        print(f"  - Total time: {total_elapsed:.1f}seconds")
        print(f"  - Database: {db_path}")

        # Whether to enter wait mode
        # Bei Budgetabbruch nicht in den Wait-Mode gehen: der Run soll
        # deterministisch enden, damit der Backend-Monitor den Abbruchgrund
        # (budget_abort.json) übernehmen kann (Issue #764).
        if self.wait_for_commands and budget_abort_info is None:
            print("\n" + "=" * 60)
            print("Enter wait mode - environment keeps running")
            print("Supported commands: interview, batch_interview, close_env")
            print("=" * 60)

            self.ipc_handler.update_status("alive")

            # Command wait loop (using global _shutdown_event)
            try:
                while not _shutdown_event.is_set():
                    should_continue = await self.ipc_handler.process_commands()
                    if not should_continue:
                        break
                    try:
                        await asyncio.wait_for(_shutdown_event.wait(), timeout=0.5)
                        break  # Received exit signal
                    except asyncio.TimeoutError:
                        pass
            except KeyboardInterrupt:
                print("\nReceived interrupt signal")
            except asyncio.CancelledError:
                print("\nTask was cancelled")
            except Exception as e:
                print(f"\nError processing command: {e}")

            print("\nClose environment...")

        # Close environment
        self.ipc_handler.update_status("stopped")
        if self.redis_bridge is not None:
            await self.redis_bridge.stop()
            self.redis_bridge = None
        await self.env.close()

        print("Environment closed")
        print("=" * 60)