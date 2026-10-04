"""Basis-Runner für OASIS-Single-Platform-Simulationen (Twitter/Reddit).

Verhaltensneutral aus ``run_twitter_simulation.py`` und
``run_reddit_simulation.py`` extrahiert: beide Runner-Klassen waren bis auf
Plattform-Konfiguration (verfügbare Actions, Profile-Dateiname, DB-Dateiname,
``oasis.DefaultPlatformType``, Graph-Generator) identisch.

Das Handling von ``initial_actions`` war ursprünglich ebenfalls verschieden —
Reddit appendete an bestehende Listen, Twitter überschrieb. Das war kein
Plattformunterschied, sondern ein Defekt: Twitter verwarf dadurch still
Seed-Posts desselben Agenten (Issue #1245). ``_assign_initial_action`` liegt
seitdem als gemeinsame Implementierung in dieser Basisklasse und ist **kein**
Erweiterungspunkt mehr.

Plattform-spezifische Werte werden über Klassen-Attribute injiziert; die Entry-Points
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
        seed_simulation_rng,
    )
except ImportError:  # direct script execution
    from _sim_common import (
        build_camel_completion_params,
        compute_start_hour_offset,
        detect_oasis_platform,
        preflight_model_probe,
        seed_simulation_rng,
    )

# Issue #1423: CLI-Transport (codex_cli). Der Fallback zeigt auf
# ``sim_runtime.codex_cli_model``, NICHT auf ``codex_cli_model``: bei direkter
# Skriptausfuehrung liegt ``scripts/`` im ``sys.path``, nicht
# ``scripts/sim_runtime/``. Ein nackter Modulname schlaegt dort mit
# ``ModuleNotFoundError`` fehl — anders als bei ``_sim_common``, das eine Ebene
# hoeher liegt. Dieselbe Form nutzt der ``sim_runtime.ipc``-Import unten.
try:
    from .codex_cli_model import CodexCliModel, cli_transport_active
    from .claude_cli_model import ClaudeCliModel, claude_cli_transport_active
except ImportError:  # direct script execution
    from sim_runtime.codex_cli_model import CodexCliModel, cli_transport_active
    from sim_runtime.claude_cli_model import ClaudeCliModel, claude_cli_transport_active

# IPC layer (CommandType, constants, IPCHandler) — zentral in sim_runtime.ipc.
try:
    from .sim_runtime.ipc import IPCHandler
except ImportError:  # direct script execution
    from sim_runtime.ipc import IPCHandler

# Rundengrenzen-Kontrolle (Tech-Review Slice B4c): Pause/Stop/Budget an einer
# Stelle statt inline in der Runden-Schleife dieser Klasse.
try:
    from .run_control import RoundAction, RoundBoundaryControl
except ImportError:  # direct script execution
    from sim_runtime.run_control import RoundAction, RoundBoundaryControl

# Aktivitaets-Untergrenzen und geteilte Runden-Auswahl (#1713 Slice S4).
from app.services.simulation_activity_policy import (
    TWITTER_FOLLOWING_POST_COUNT,
    TWITTER_MAX_REC_POST_LEN,
    TWITTER_REFRESH_REC_POST_COUNT,
    select_active_agent_ids,
)

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

# Action-Log (#1713): der Single-Platform-Pfad schrieb bisher nie
# ``actions.jsonl`` — ``action_logger``/``oasis_action_ingest`` liegen wie
# ``agent_tools`` auf Ebene ``scripts/`` und sind dort bare-importierbar.
from action_logger import PlatformActionLogger
from agent_memory import describe_memory_policy, prune_graph_memories
from oasis_action_ingest import (
    fetch_new_actions_from_db,
    get_agent_names_from_config,
    get_max_trace_rowid,
)

# Global variables: for signal handling (von den Entry-Point-``main``
# Funktionen gesetzt; ``run`` liest ``_shutdown_event``).
_shutdown_event = None
_cleanup_done = False

logger = logging.getLogger(__name__)


async def agent_observation(agent: Any) -> str:
    """Timeline-/Umgebungstext, den OASIS dem Agenten als Situation zeigt.

    camel-oasis 0.2.5 hat weder ``OasisEnv.get_observation`` noch
    ``SocialAgent.observation``; die Observation entsteht asynchron ueber
    ``agent.env.to_text_prompt()`` (``SocialEnvironment``). Die fruehere
    Abfrage dieser nicht existierenden Attribute lieferte immer ``""`` —
    der Tool-Loop sah die Timeline nie (#1224, Codex-Finding PR #1559).
    Der Text ist untrusted und wird in ``build_agent_prompt_with_tools``
    gekapselt.
    """
    env = getattr(agent, "env", None)
    to_text_prompt = getattr(env, "to_text_prompt", None)
    if to_text_prompt is None:
        return ""
    result = to_text_prompt()
    if asyncio.iscoroutine(result):
        result = await result
    return str(result or "")


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

    Subclasses setzen die Plattform-Konfiguration via Klassen-Attribute.
    ``_assign_initial_action`` ist bewusst nicht zu überschreiben: die
    Kollisionsbehandlung für mehrere Seed-Posts desselben Agenten gilt für
    beide Plattformen gleich (Issue #1245).
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
        # Issue #1160 F: Vor der ersten Zufallsentscheidung seeden — die faellt
        # in ``get_active_agents_for_round``, also lange nach ``__init__``, aber
        # OASIS und CAMEL greifen ihrerseits frueher auf ``random`` zu. Der
        # Fallback auf den Verzeichnisnamen deckt Bestands-Konfigurationen ohne
        # ``simulation_id`` ab; ohne ihn haetten die einen konstanten Seed und
        # waeren untereinander nicht mehr unterscheidbar.
        self.random_seed = seed_simulation_rng(
            self.config, fallback=os.path.basename(self.simulation_dir.rstrip("/"))
        )
        self.wait_for_commands = wait_for_commands
        self.env = None
        self.agent_graph = None
        self.ipc_handler = None
        self.tool_loop = None
        self.redis_bridge = None  # Issue #17: optional Redis Pub/Sub listener
        self.action_logger = None  # Issue #1713: gesetzt in run()

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

        # Issue #1423: CLI-Transport (codex_cli) hat weder base_url noch
        # api_key — die URL-basierte Plattform-Erkennung darunter hat nichts
        # zu mustern und liefe in den OPENAI-Zweig, der das geroutete Modell
        # an das geerbte LLM_BASE_URL schickt. Das Signal kommt aus
        # ``build_route_subprocess_env`` und ist damit an der Registry
        # entschieden, nicht an einer zweiten Heuristik.
        if claude_cli_transport_active():
            print(f"LLM configuration: model={llm_model}, transport=cli (claude)", flush=True)
            return ClaudeCliModel(
                model_type=llm_model, api_key=os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
            )
        if cli_transport_active():
            print(f"LLM configuration: model={llm_model}, transport=cli (codex)", flush=True)
            return CodexCliModel(model_type=llm_model)

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

        # Geteilte Auswahl-Logik mit run_parallel_simulation.py (#1713 Slice S4).
        selected_ids = select_active_agent_ids(time_config, agent_configs, current_hour)

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

        Issue #1245 (CodeRabbit PR #1256): Die Standardimplementierung
        ueberschrieb eine bestehende Zuweisung — mehrere Seed-Posts desselben
        Agenten kollabierten auf den letzten, still und ohne Warnung. Das galt
        fuer jeden Lauf mit ``platform="twitter"``, der ueber
        ``run_twitter_simulation.py`` und diesen Runner geht; der Fix im
        Parallel-Skript erreichte diesen Pfad nicht.

        Kollisionsbehandlung gehoert nicht auf eine Plattform, sondern in die
        Basis: ``env.step`` akzeptiert je Agent einen Einzelwert oder eine
        Liste. Ohne Kollision entsteht weiterhin kein zusaetzliches Wrapping.
        """
        action = ManualAction(
            action_type=ActionType.CREATE_POST,
            action_args={"content": content}
        )
        existing = initial_actions.get(agent)
        if existing is None:
            initial_actions[agent] = action
        elif isinstance(existing, list):
            existing.append(action)
        else:
            initial_actions[agent] = [existing, action]

    def _log_round_actions(
        self,
        db_path: str,
        round_num: int,
        agent_names: Dict[int, str],
        last_rowid: int,
        simulated_minutes_after: int,
    ) -> tuple[int, int]:
        """Liest die seit ``last_rowid`` neuen Trace-Zeilen, loggt sie mit
        ``round_num`` und schliesst die Runde ab (#1713).

        Extrahiert aus ``run()`` als eigene Methode, damit sich der
        Single-Platform-Action-Log-Pfad ohne vollen OASIS-Env-Aufbau testen
        laesst — vorher schrieb dieser Runner nie ``actions.jsonl``.

        Returns:
            (actions_logged, new_last_rowid)
        """
        actual_actions, new_last_rowid = fetch_new_actions_from_db(
            db_path, last_rowid, agent_names
        )
        for action_data in actual_actions:
            self.action_logger.log_action(
                round_num=round_num,
                agent_id=action_data['agent_id'],
                agent_name=action_data['agent_name'],
                action_type=action_data['action_type'],
                action_args=action_data['action_args'],
            )
        self.action_logger.log_round_end(
            round_num, len(actual_actions), simulated_minutes=simulated_minutes_after
        )
        return len(actual_actions), new_last_rowid

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
        logger.info(describe_memory_policy())

        # Databasepath
        db_path = self._get_db_path()
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"Old database deleted: {db_path}")

        # Create environment
        print("Create OASIS environment...")
        if self.PLATFORM_TYPE == oasis.DefaultPlatformType.TWITTER:
            # Issue #1713 Slice S4: OASIS-Default haelt den Twitter-Feed sehr
            # eng (siehe simulation_activity_policy.py Docstring) — eigenes
            # Platform-Objekt statt DefaultPlatformType.TWITTER, damit
            # refresh_rec_post_count/max_rec_post_len/following_post_count
            # ueber die im OASIS-Paket vorgesehenen Parameter greifen.
            platform_arg: Any = oasis.Platform(
                db_path=db_path,
                recsys_type="twhin-bert",
                refresh_rec_post_count=TWITTER_REFRESH_REC_POST_COUNT,
                max_rec_post_len=TWITTER_MAX_REC_POST_LEN,
                following_post_count=TWITTER_FOLLOWING_POST_COUNT,
            )
        else:
            platform_arg = self.PLATFORM_TYPE
        self.env = oasis.make(
            agent_graph=self.agent_graph,
            platform=platform_arg,
            database_path=db_path,
            semaphore=30,  # Limit maximum concurrent LLM requests to prevent API overload
        )

        await self.env.reset()
        print("Environment initialization complete\n")

        # Action-Log (#1713): ein Logger je Plattform, wie im Parallel-Runner.
        self.action_logger = PlatformActionLogger(self.PLATFORM_SLUG, self.simulation_dir)
        self.action_logger.log_simulation_start(self.config)
        agent_names = get_agent_names_from_config(self.config)
        total_actions = 0
        last_rowid = 0  # Track last processed row in Database (siehe run_parallel_simulation.py)

        # Initialize IPC handler
        self.ipc_handler = IPCHandler(
            self.simulation_dir,
            self.env,
            self.agent_graph,
            db_filename=self.DB_FILENAME,
            interview_action_type=ActionType.INTERVIEW,
            manual_action_cls=ManualAction,
            # Issue #1320: derselbe Schluesselraum wie im Parallel-Runner.
            platform_key=self.PLATFORM_NAME.lower(),
            # #1478 Codex P1, Runde 6: Report-Interviews pruefen/verbuchen
            # ihre physischen Modellaufrufe ueber denselben Guard wie die
            # Simulationsrunden — ohne ihn bleibt ein Interview-Kommando mit
            # ``report_run_id`` unbewacht (nullcontext in ``IPCHandler``).
            budget_guard=budget_guard,
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

        # Log round 0 start (initial event phase) — regardless of whether
        # there are initial posts, gleiches Muster wie run_parallel_simulation.py.
        self.action_logger.log_round_start(0, 0)
        initial_action_count = 0

        if initial_posts:
            print(f"Execute initial events ({len(initial_posts)}initial posts)...")
            initial_actions = {}
            for post in initial_posts:
                agent_id = post.get("poster_agent_id", 0)
                content = post.get("content", "")
                try:
                    agent = self.env.agent_graph.get_agent(agent_id)
                    self._assign_initial_action(initial_actions, agent, content)
                    self.action_logger.log_action(
                        round_num=0,
                        agent_id=agent_id,
                        agent_name=agent_names.get(agent_id, f"Agent_{agent_id}"),
                        action_type="CREATE_POST",
                        action_args={"content": content},
                    )
                    total_actions += 1
                    initial_action_count += 1
                except Exception as e:
                    print(f"  Warning: Unable to create for Agent {agent_id}Create initial posts: {e}")

            if initial_actions:
                await self.env.step(initial_actions)
                # Issue #1245: Posts und distinkte Agenten getrennt ausweisen.
                # len(initial_actions) zaehlt Dict-Eintraege, also Agenten —
                # bei kollabierten Seed-Posts meldete die Zeile einen Erfolg,
                # der den Defekt verdeckte.
                published = sum(
                    len(value) if isinstance(value, list) else 1
                    for value in initial_actions.values()
                )
                print(
                    f"  Published {published} initial post"
                    f"{'' if published == 1 else 's'} from {len(initial_actions)} "
                    f"distinct agent{'' if len(initial_actions) == 1 else 's'}"
                )
                # Initial-Posts sind bereits oben geloggt — last_rowid auf den
                # aktuellen DB-Stand ziehen, sonst liest Runde 1 dieselben
                # Trace-Zeilen erneut (#1713, wie run_parallel_simulation.py).
                last_rowid = get_max_trace_rowid(db_path)

        self.action_logger.log_round_end(0, initial_action_count)

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

        # Issue #1713 Slice S6: Haltung/Beitragsneigung nachschlagbar je Agent,
        # damit sie im Tool-Loop in den Prompt gelangen statt nur in der
        # Config zu stehen (Befund 7: Konsens/Echo nach einer Runde).
        agent_configs_by_id = {
            cfg.get("agent_id"): cfg for cfg in self.config.get("agent_configs", [])
        }

        round_control = RoundBoundaryControl(self.simulation_dir, budget_guard)
        budget_abort_info = None
        for round_num in range(total_rounds):
            decision = round_control.check(round_num)
            if decision.action == RoundAction.STOP:
                break
            if decision.action == RoundAction.BUDGET_ABORT:
                budget_abort_info = decision.budget_abort_info
                break

            # Calculate current simulation time
            simulated_minutes = round_num * minutes_per_round
            simulated_hour = (start_hour_offset + simulated_minutes // 60) % 24
            simulated_day = simulated_minutes // (60 * 24) + 1

            # Get Agents activated this round
            active_agents = self._get_active_agents_for_round(
                self.env, simulated_hour, round_num
            )

            # Log round start regardless of active agents (siehe Parallel-Runner)
            self.action_logger.log_round_start(round_num + 1, simulated_hour)

            if not active_agents:
                self.action_logger.log_round_end(
                    round_num + 1, 0, simulated_minutes=simulated_minutes + minutes_per_round
                )
                continue

            # Build actions
            if self.tool_loop and enable_tools:
                # Tool-aware action loop
                actions = {}
                for agent_id, agent in active_agents:
                    try:
                        observation = await agent_observation(agent)

                        # Get agent profile info
                        agent_name = getattr(agent, 'username', f"Agent_{agent_id}")
                        agent_role = getattr(agent, 'profession', 'Unknown')
                        agent_bio = getattr(agent, 'bio', '')
                        agent_cfg = agent_configs_by_id.get(agent_id, {})

                        action = await self.tool_loop.decide_action(
                            agent=agent,
                            observation=observation,
                            available_actions=self.AVAILABLE_ACTION_NAMES,
                            agent_name=agent_name,
                            agent_role=agent_role,
                            agent_bio=agent_bio,
                            language=self.config.get("language", "de"),
                            stance=agent_cfg.get("stance"),
                            sentiment_bias=agent_cfg.get("sentiment_bias"),
                            posts_per_hour=agent_cfg.get("posts_per_hour"),
                            comments_per_hour=agent_cfg.get("comments_per_hour"),
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
            # #1772: Feeds frueherer Aktivierungen aus dem Agentengedaechtnis nehmen.
            prune_graph_memories(self.agent_graph, round_num=round_num + 1, log=logger.info)

            # Get actual executed actions from Database and log (#1713)
            round_actions, last_rowid = self._log_round_actions(
                db_path, round_num + 1, agent_names, last_rowid,
                simulated_minutes + minutes_per_round,
            )
            total_actions += round_actions

            # Print progress
            if (round_num + 1) % 10 == 0 or round_num == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                progress = (round_num + 1) / total_rounds * 100
                print(f"  [Day {simulated_day}, {simulated_hour:02d}:00] "
                      f"Round {round_num + 1}/{total_rounds} ({progress:.1f}%) "
                      f"- {len(active_agents)} agents active "
                      f"- elapsed: {elapsed:.1f}s")

        self.action_logger.log_simulation_end(total_rounds, total_actions)

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