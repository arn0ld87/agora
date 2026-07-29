"""
OASIS Reddit simulation preset script
This script reads parameters from config file to execute simulation, achieving full automation

Features:
- Keep environment running after simulation completes, enter wait mode
- Support Interview commands via IPC
- Support single Agent interview and batch interview
- Support remote environment shutdown command

Usage:
    python run_reddit_simulation.py --config /path/to/simulation_config.json
    python run_reddit_simulation.py --config /path/to/simulation_config.json --no-wait  # Close immediately after completion
"""

import asyncio
import logging
import os
import sys

# Global variables: for signal handling
_shutdown_event = None
_cleanup_done = False

# Add project paths
try:
    from ._sim_common import (
        apply_camel_context_floor,
        build_camel_completion_params,
        build_single_platform_parser,
        compute_start_hour_offset,
        detect_oasis_platform,
        init_runner_tracing,
        init_runner_logging,
        install_bert_memory_profile,
        install_max_tokens_warning_filter,
        install_memory_sampler,
        install_script_paths,
        load_project_env,
        make_default_memory_sink,
        preflight_model_probe,
        resolve_runtime_paths,
        setup_oasis_logging,
    )
except ImportError:  # direct script execution
    from _sim_common import (
        apply_camel_context_floor,
        build_camel_completion_params,
        build_single_platform_parser,
        compute_start_hour_offset,
        detect_oasis_platform,
        init_runner_tracing,
        init_runner_logging,
        install_bert_memory_profile,
        install_max_tokens_warning_filter,
        install_memory_sampler,
        install_script_paths,
        load_project_env,
        make_default_memory_sink,
        preflight_model_probe,
        resolve_runtime_paths,
        setup_oasis_logging,
    )

_runtime_paths = resolve_runtime_paths(__file__)
install_script_paths(_runtime_paths)
init_runner_tracing("agora-oasis-runner")
init_runner_logging("agora-oasis-runner")
load_project_env(__file__)
install_max_tokens_warning_filter()


def _noop_memory_stop() -> None:
    """No-Op-Placeholder, bis ``_install_runtime_profile()`` das echte Stop setzt."""


# Modul-Level-Default; wird in ``_install_runtime_profile()`` überschrieben.
# Bleibt no-op, solange das Modul nur importiert wird (z.B. durch Tests).
_memory_stop = _noop_memory_stop


def _install_runtime_profile() -> None:
    """BERT-Memory-Profil + Sampler + Camel-Context-Floor installieren.

    Bewusst lazy statt auf Modul-Ebene: ein Modul-Import in Tests darf nicht
    ``transformers``/``torch`` laden. Der torch-Import crasht auf
    Python 3.14/aarch64 in Kombination mit anderen C-Extensions im
    pytest-Sammelprozess (Segfault in ``libtorch_python.so initModule``).
    Siehe HANDOVER-2026-07-25 Aufgabe 3.
    """
    global _memory_stop
    _bert_profile = install_bert_memory_profile()
    _memory_stop = install_memory_sampler(make_default_memory_sink(_runtime_paths.project_root))
    logging.getLogger("agora.run_reddit_simulation").info("bert-memory profile = %s", _bert_profile)
    _camel_context_floor = apply_camel_context_floor()
    logging.getLogger("agora.run_reddit_simulation").info("context-patch token_limit floor = %s", _camel_context_floor)

if __name__ == '__main__' and any(arg in sys.argv for arg in ('-h', '--help')):
    build_single_platform_parser('OASIS Reddit Simulation').parse_args()
    sys.exit(0)


try:
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType
    # ScoreBasedContextCreator-Floor wird in apply_camel_context_floor() oben
    # gesetzt. CAMELs Default-token_limit (8192) wuerde sonst bei 8 k Tokens
    # truncen, unabhaengig von OLLAMA_NUM_CTX und vom realen Modell-Context.
    import oasis
    from oasis import (
        ActionType,
        LLMAction,
        ManualAction,
        generate_reddit_agent_graph
    )
except ImportError as e:
    print(f"Error: Missing dependency {e}")
    print("Please install first: pip install oasis-ai camel-ai")
    sys.exit(1)


# IPC layer (CommandType, constants, IPCHandler) wird zentral in
# ``sim_runtime.ipc`` gehalten und hier nur noch importiert — die
# Twitter- und Reddit-Runner teilen sich damit eine Implementierung.
# Re-Export hält die alten Modul-Attribute kompatibel.
try:
    from .sim_runtime.ipc import (  # noqa: E402
        CommandType,
        ENV_STATUS_FILE,
        IPC_COMMANDS_DIR,
        IPC_RESPONSES_DIR,
        IPCHandler,
    )
except ImportError:  # direct script execution
    from sim_runtime.ipc import (  # noqa: E402
        CommandType,
        ENV_STATUS_FILE,
        IPC_COMMANDS_DIR,
        IPC_RESPONSES_DIR,
        IPCHandler,
    )


# Import agent tools (optional — only loaded when enable_agent_tools is set)
try:
    from agent_tools import (
        AgentToolRegistry,
        ToolAwareActionLoop,
        create_tool_aware_loop
    )
    AGENT_TOOLS_AVAILABLE = True
except ImportError as _e:
    AGENT_TOOLS_AVAILABLE = False


# Basis-Runner (SinglePlatformRunner) + signal handling. _shutdown_event wird
# in ``main()`` auf dem Basis-Modul gesetzt, weil ``run`` dort das Modul-Global
# liest (nicht das lokale Entry-Point-Global).
try:
    from .sim_runtime import platform_runner as _platform_runner  # noqa: E402
except ImportError:  # direct script execution
    import sim_runtime.platform_runner as _platform_runner  # noqa: E402

SinglePlatformRunner = _platform_runner.SinglePlatformRunner
setup_signal_handlers = _platform_runner.setup_signal_handlers


class RedditSimulationRunner(SinglePlatformRunner):
    """Reddit simulation runner — dünne Subklasse der SinglePlatformRunner-Basis.

    Einzige Verhaltensdifferenz zu Twitter: ``_assign_initial_action`` appended
    an eine bestehende Action-Liste pro Agent statt sie zu überschreiben
    (Reddit erlaubt mehrere Initial-Posts desselben Agents).
    """

    # Reddit available actions (INTERVIEW not included, INTERVIEW can only be triggered manually via ManualAction)
    AVAILABLE_ACTIONS = [
        ActionType.LIKE_POST,
        ActionType.DISLIKE_POST,
        ActionType.CREATE_POST,
        ActionType.CREATE_COMMENT,
        ActionType.LIKE_COMMENT,
        ActionType.DISLIKE_COMMENT,
        ActionType.SEARCH_POSTS,
        ActionType.SEARCH_USER,
        ActionType.TREND,
        ActionType.REFRESH,
        ActionType.DO_NOTHING,
        ActionType.FOLLOW,
        ActionType.MUTE,
    ]

    AVAILABLE_ACTION_NAMES = [
        "LIKE_POST", "DISLIKE_POST", "CREATE_POST", "CREATE_COMMENT",
        "LIKE_COMMENT", "DISLIKE_COMMENT", "SEARCH_POSTS", "SEARCH_USER",
        "TREND", "REFRESH", "DO_NOTHING", "FOLLOW", "MUTE"
    ]

    PLATFORM_NAME = "Reddit"
    PLATFORM_SLUG = "reddit"
    PROFILE_FILENAME = "reddit_profiles.json"
    DB_FILENAME = "reddit_simulation.db"
    PLATFORM_TYPE = oasis.DefaultPlatformType.REDDIT
    GRAPH_GENERATOR = staticmethod(generate_reddit_agent_graph)

    def _assign_initial_action(self, initial_actions, agent, content: str) -> None:
        """Reddit: mehrere Initial-Posts pro Agent → append an Liste statt überschreiben."""
        if agent in initial_actions:
            if not isinstance(initial_actions[agent], list):
                initial_actions[agent] = [initial_actions[agent]]
            initial_actions[agent].append(ManualAction(
                action_type=ActionType.CREATE_POST,
                action_args={"content": content}
            ))
        else:
            initial_actions[agent] = ManualAction(
                action_type=ActionType.CREATE_POST,
                action_args={"content": content}
            )


async def main():
    parser = build_single_platform_parser('OASIS Reddit Simulation')
    args = parser.parse_args()

    # Create shutdown event at the start of main function — auf dem Basis-Modul,
    # weil ``SinglePlatformRunner.run`` dort ``_shutdown_event`` liest.
    _platform_runner._shutdown_event = asyncio.Event()

    _install_runtime_profile()

    if not os.path.exists(args.config):
        print(f"Error: Configuration file does not exist: {args.config}")
        sys.exit(1)

    # Initialize logging configuration (use fixed file names, clean up old logs)
    simulation_dir = os.path.dirname(args.config) or "."
    setup_oasis_logging(os.path.join(simulation_dir, "log"))

    runner = RedditSimulationRunner(
        config_path=args.config,
        wait_for_commands=not args.no_wait
    )
    await runner.run(max_rounds=args.max_rounds)


if __name__ == "__main__":
    setup_signal_handlers()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram interrupted")
    except SystemExit:
        pass
    finally:
        _memory_stop()
        print("Simulation process exited")