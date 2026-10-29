"""Shared simulation runtime execution helpers for single- and parallel-platform runners.

Consolidates the duplicated model factory dispatch, agent-graph post-processing,
Round-0 initial post seeding, and per-round SQLite trace ingestion + Redis
``PostCreatedEvent`` emission across:
- ``sim_runtime/platform_runner.py`` (``SinglePlatformRunner``)
- ``run_parallel_simulation.py`` (``create_model``, ``run_twitter_simulation``,
  ``run_reddit_simulation``)

All external dependencies that existing unit tests monkeypatch at the caller
module level (``ModelFactory``, ``_create_gemini_model``,
``fetch_new_actions_from_db``, ``_emit_post_created_to_redis``) are accepted as
injectable callbacks so existing test seams continue to work unchanged.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from camel.models import ModelFactory
from camel.types import ModelPlatformType

try:
    from .._sim_common import (
        _emit_post_created_to_redis as _default_emit_post_created_to_redis,
        build_camel_completion_params,
        build_minimax_extra_body,
        compute_post_sim_time,
        detect_oasis_platform,
        is_workspace_credential_scope,
        resolve_camel_ollama_url,
    )
except ImportError:  # direct script execution
    from _sim_common import (
        _emit_post_created_to_redis as _default_emit_post_created_to_redis,
        build_camel_completion_params,
        build_minimax_extra_body,
        compute_post_sim_time,
        detect_oasis_platform,
        is_workspace_credential_scope,
        resolve_camel_ollama_url,
    )

try:
    from ..activation_limit import install_activation_limits_from_config
    from ..agent_feed import install_feed_comment_cap, install_stance_anchor
    from ..agent_memory import describe_memory_policy
    from ..oasis_action_ingest import (
        fetch_new_actions_from_db as _default_fetch_new_actions_from_db,
        get_agent_names_from_config,
    )
except ImportError:  # direct script execution
    from activation_limit import install_activation_limits_from_config
    from agent_feed import install_feed_comment_cap, install_stance_anchor
    from agent_memory import describe_memory_policy
    from oasis_action_ingest import (
        fetch_new_actions_from_db as _default_fetch_new_actions_from_db,
        get_agent_names_from_config,
    )

try:
    from .llm_config import resolve_model_runtime_settings
except ImportError:
    from sim_runtime.llm_config import resolve_model_runtime_settings

try:
    from .codex_cli_model import (
        CodexCliModel,
        cli_transport_active as _default_cli_transport_active,
    )
    from .claude_cli_model import (
        ClaudeCliModel,
        claude_cli_transport_active as _default_claude_cli_transport_active,
    )
except ImportError:
    from sim_runtime.codex_cli_model import (
        CodexCliModel,
        cli_transport_active as _default_cli_transport_active,
    )
    from sim_runtime.claude_cli_model import (
        ClaudeCliModel,
        claude_cli_transport_active as _default_claude_cli_transport_active,
    )

logger = logging.getLogger(__name__)


def _default_create_gemini_model(
    *,
    model_type: str,
    model_config_dict: Dict[str, Any],
    api_key: str,
) -> Any:
    try:
        try:
            from .gemini_thought_signatures import create_gemini_thought_signature_model
        except ImportError:
            from gemini_thought_signatures import create_gemini_thought_signature_model

        return create_gemini_thought_signature_model(
            model_type=model_type,
            model_config_dict=model_config_dict,
            api_key=api_key,
        )
    except Exception as exc:
        logger.warning(
            "create_gemini_thought_signature_model failed (%s: %s); falling back to ModelFactory.create",
            type(exc).__name__,
            exc,
        )
        return ModelFactory.create(
            model_platform=ModelPlatformType.GEMINI,
            model_type=model_type,
            model_config_dict=model_config_dict,
        )


def format_initial_posts_log(published_count: int, distinct_agents: int) -> str:
    """Format the Round-0 publish summary separating total posts from distinct agents."""
    post_word = "post" if published_count == 1 else "posts"
    agent_word = "agent" if distinct_agents == 1 else "agents"
    return (
        f"Published {published_count} initial {post_word} "
        f"from {distinct_agents} distinct {agent_word}"
    )


def _noop_log(msg: str) -> None:
    """Default no-op logger when caller does not supply a log callback."""


def allowed_emit_action_types(platform_slug: str) -> Tuple[str, ...]:
    """Return the trace action types that trigger a Redis ``PostCreatedEvent``."""
    if (platform_slug or "").lower() == "reddit":
        return ("CREATE_POST", "CREATE_COMMENT")
    return ("CREATE_POST", "REPOST", "QUOTE_POST")


def create_simulation_llm_model(
    config: Dict[str, Any],
    *,
    use_boost: bool = False,
    config_label_prefix: Optional[str] = None,
    model_factory: Any = ModelFactory,
    gemini_model_creator: Callable[..., Any] = _default_create_gemini_model,
    claude_cli_model_cls: Any = ClaudeCliModel,
    codex_cli_model_cls: Any = CodexCliModel,
    claude_cli_transport_check: Callable[[], bool] = _default_claude_cli_transport_active,
    cli_transport_check: Callable[[], bool] = _default_cli_transport_active,
    workspace_credential_scope_check: Callable[[], bool] = is_workspace_credential_scope,
    build_completion_params_fn: Callable[..., Dict[str, Any]] = build_camel_completion_params,
    resolve_runtime_settings_fn: Callable[[str], Dict[str, Any]] = resolve_model_runtime_settings,
    detect_platform_fn: Callable[[str, str], Any] = detect_oasis_platform,
    platform_detector: Optional[Callable[[str, str], Any]] = None,
    resolve_ollama_url_fn: Callable[[Optional[str]], str] = resolve_camel_ollama_url,
    build_minimax_extra_fn: Callable[..., Optional[Dict[str, Any]]] = build_minimax_extra_body,
) -> Any:
    """Create a CAMEL/OASIS LLM model backend for simulation agents.

    Unifies the model creation logic previously duplicated between
    ``SinglePlatformRunner._create_model`` and
    ``run_parallel_simulation.create_model``.
    """
    active_platform_detector = platform_detector or detect_platform_fn
    boost_api_key = os.environ.get("LLM_BOOST_API_KEY", "")
    boost_base_url = os.environ.get("LLM_BOOST_BASE_URL", "")
    boost_model = os.environ.get("LLM_BOOST_MODEL_NAME", "")
    has_boost_config = bool(boost_api_key) and not workspace_credential_scope_check()

    config_model = config.get("llm_model", "") or ""
    if use_boost and has_boost_config:
        llm_api_key = boost_api_key
        llm_base_url = boost_base_url
        llm_model = config_model or boost_model or os.environ.get("LLM_MODEL_NAME", "")
        config_label = config_label_prefix or "[Acceleration LLM]"
    else:
        llm_api_key = os.environ.get("LLM_API_KEY", "")
        llm_base_url = os.environ.get("LLM_BASE_URL", "")
        llm_model = config_model or os.environ.get("LLM_MODEL_NAME", "")
        config_label = config_label_prefix or "[Common LLM]"

    if not llm_model:
        llm_model = "qwen3-coder-next:cloud"

    runtime_settings = resolve_runtime_settings_fn(llm_model)

    if claude_cli_transport_check():
        print(f"{config_label} model={llm_model}, transport=cli (claude)", flush=True)
        return claude_cli_model_cls(
            model_type=llm_model, api_key=os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
        )
    if cli_transport_check():
        print(f"{config_label} model={llm_model}, transport=cli (codex)", flush=True)
        return codex_cli_model_cls(model_type=llm_model)

    platform = active_platform_detector(llm_model, llm_base_url)
    think_on = os.environ.get("OLLAMA_THINKING", "false").lower() in ("1", "true", "yes")

    print(
        f"{config_label} model={llm_model}, "
        f"base_url={llm_base_url[:40] if llm_base_url else 'default'}..., "
        f"platform={platform.value}, "
        f"completion_max_tokens={runtime_settings['completion_max_tokens']}, "
        f"memory_token_limit={runtime_settings['memory_token_limit']}, "
        f"ollama_num_ctx={runtime_settings['ollama_num_ctx']}",
        flush=True,
    )

    model_cfg: Dict[str, Any] = build_completion_params_fn(
        model=llm_model,
        completion_max_tokens=runtime_settings["completion_max_tokens"],
        base_url=llm_base_url or None,
    )

    if platform == ModelPlatformType.GEMINI:
        _gemini_key = (
            llm_api_key
            or os.environ.get("GEMINI_API_KEY", "")
            or os.environ.get("GOOGLE_API_KEY", "")
        )
        os.environ["GOOGLE_API_KEY"] = _gemini_key
        os.environ["GEMINI_API_KEY"] = _gemini_key
        return gemini_model_creator(
            model_type=llm_model,
            model_config_dict=model_cfg,
            api_key=_gemini_key,
        )

    if platform == ModelPlatformType.OLLAMA:
        os.environ["OPENAI_API_KEY"] = llm_api_key or "dummy"
        extra_body: Dict[str, Any] = {"think": think_on}
        if runtime_settings["ollama_num_ctx"] is not None:
            extra_body["options"] = {"num_ctx": runtime_settings["ollama_num_ctx"]}
        model_cfg["extra_body"] = extra_body
        return model_factory.create(
            model_platform=ModelPlatformType.OLLAMA,
            model_type=llm_model,
            url=resolve_ollama_url_fn(llm_base_url or None),
            api_key=llm_api_key or None,
            model_config_dict=model_cfg,
        )

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

    minimax_extra = build_minimax_extra_fn(model=llm_model, base_url=llm_base_url, think=think_on)
    if minimax_extra:
        model_cfg["extra_body"] = minimax_extra

    return model_factory.create(
        model_platform=ModelPlatformType.OPENAI,
        model_type=llm_model,
        model_config_dict=model_cfg,
        url=llm_base_url or None,
        api_key=llm_api_key or None,
    )


def resolve_graph_agent_names(
    config: Dict[str, Any],
    agent_graph: Any,
) -> Dict[int, str]:
    """Build ``{agent_id: agent_name}`` map from config and live agent graph."""
    agent_names = get_agent_names_from_config(config)
    if agent_graph is not None and hasattr(agent_graph, "get_agents"):
        for agent_id, agent in agent_graph.get_agents():
            if agent_id not in agent_names:
                agent_names[agent_id] = getattr(
                    agent,
                    "name",
                    getattr(getattr(agent, "user_info", None), "name", f"Agent_{agent_id}"),
                )
    return agent_names


def configure_platform_agent_graph(
    agent_graph: Any,
    config: Dict[str, Any],
    *,
    platform_slug: str,
    enable_tools: bool = False,
    agent_tools_available: bool = False,
    log: Callable[[str], None] = _noop_log,
    build_tools_fn: Optional[Callable[[Dict[str, Any]], List[Any]]] = None,
    attach_tools_fn: Optional[Callable[[Any, List[Any]], int]] = None,
    install_feed_comment_cap_fn: Callable[..., Any] = install_feed_comment_cap,
    install_stance_anchor_fn: Callable[..., Any] = install_stance_anchor,
    install_activation_limits_fn: Callable[..., Any] = install_activation_limits_from_config,
    describe_memory_policy_fn: Callable[[], str] = describe_memory_policy,
) -> Tuple[Any, Dict[int, str]]:
    """Apply post-build policies (memory cap, feed cap, stance anchor, tools, activation limits).

    Returns ``(activation_limits, agent_names)``.
    """
    if agent_tools_available:
        try:
            from agent_tools import enforce_memory_token_limit

            enforce_memory_token_limit(agent_graph)
        except Exception as exc:
            log(f"enforce_memory_token_limit ({platform_slug}) failed: {exc}")
    log(describe_memory_policy_fn())
    install_feed_comment_cap_fn(agent_graph, log=log)
    install_stance_anchor_fn(
        agent_graph,
        config.get("agent_configs", []),
        (config.get("contested_question") or {}).get("statement"),
        log=log,
    )

    if enable_tools and agent_tools_available and build_tools_fn and attach_tools_fn:
        try:
            fn_tools = build_tools_fn(config)
            attached = attach_tools_fn(agent_graph, fn_tools)
            log(
                f"Attached {len(fn_tools)} FunctionTools to "
                f"{platform_slug.capitalize()} agents ({attached} bindings)"
            )
        except Exception as exc:
            log(f"Failed to attach native FunctionTools: {exc}")

    activation_limits = install_activation_limits_fn(agent_graph, config, log=log)
    agent_names = resolve_graph_agent_names(config, agent_graph)
    return activation_limits, agent_names


async def emit_round_actions_to_redis(
    *,
    actions: Sequence[Dict[str, Any]],
    platform_slug: str,
    simulation_id: str,
    redis_url: Optional[str],
    round_num: int,
    sim_clock_anchor: datetime,
    start_hour_offset: int,
    simulated_minutes: int,
    minutes_per_round: int,
    allowed_types: Optional[Sequence[str]] = None,
    emit_fn: Optional[Callable[..., Any]] = _default_emit_post_created_to_redis,
) -> int:
    """Emit Redis ``PostCreatedEvent`` messages for qualifying actions in ``actions``."""
    if emit_fn is None or not actions:
        return 0
    target_types = (
        tuple(allowed_types)
        if allowed_types is not None
        else allowed_emit_action_types(platform_slug)
    )
    action_count = len(actions)
    emitted = 0
    for action_idx, action_data in enumerate(actions):
        if action_data.get("action_type") in target_types:
            sim_time_iso = compute_post_sim_time(
                sim_clock_anchor,
                start_hour_offset,
                simulated_minutes,
                minutes_per_round,
                action_idx,
                action_count,
            ).isoformat()
            await emit_fn(
                simulation_id=simulation_id,
                platform=platform_slug,
                action_data=action_data,
                redis_url=redis_url,
                round_num=round_num,
                sim_time_iso=sim_time_iso,
            )
            emitted += 1
    return emitted


async def execute_initial_posts_round(
    *,
    env: Any,
    config: Dict[str, Any],
    platform_slug: str,
    db_path: str,
    agent_names: Dict[int, str],
    last_rowid: int,
    action_logger: Optional[Any],
    simulation_id: str,
    redis_url: Optional[str],
    sim_clock_anchor: datetime,
    start_hour_offset: int,
    minutes_per_round: int,
    log: Callable[[str], None] = _noop_log,
    on_agent_missing: Optional[Callable[[int, Exception], None]] = None,
    build_initial_actions_fn: Optional[Callable[..., Tuple[Dict[Any, Any], int]]] = None,
    fetch_actions_fn: Callable[
        ..., Tuple[List[Dict[str, Any]], int]
    ] = _default_fetch_new_actions_from_db,
    emit_fn: Optional[Callable[..., Any]] = _default_emit_post_created_to_redis,
) -> Tuple[int, int]:
    """Execute Round-0 initial posts, log DB trace rows, and emit Redis events.

    Returns ``(new_last_rowid, initial_action_count)``.
    """
    event_config = config.get("event_config", {})
    initial_posts = event_config.get("initial_posts", [])

    if action_logger is not None:
        action_logger.log_round_start(0, 0)

    initial_action_count = 0
    if initial_posts and build_initial_actions_fn is not None:
        build_kwargs: Dict[str, Any] = {}
        if on_agent_missing is not None:
            build_kwargs["on_agent_missing"] = on_agent_missing
        initial_actions, published_count = build_initial_actions_fn(
            initial_posts, env.agent_graph, **build_kwargs
        )
        if initial_actions:
            await env.step(initial_actions)
            log(format_initial_posts_log(published_count, len(initial_actions)))
            initial_db_actions, last_rowid = fetch_actions_fn(db_path, last_rowid, agent_names)
            for action_data in initial_db_actions:
                if action_logger is not None:
                    action_logger.log_action(
                        round_num=0,
                        agent_id=action_data["agent_id"],
                        agent_name=action_data["agent_name"],
                        action_type=action_data["action_type"],
                        action_args=action_data["action_args"],
                    )
                initial_action_count += 1
            await emit_round_actions_to_redis(
                actions=initial_db_actions,
                platform_slug=platform_slug,
                simulation_id=simulation_id,
                redis_url=redis_url,
                round_num=0,
                sim_clock_anchor=sim_clock_anchor,
                start_hour_offset=start_hour_offset,
                simulated_minutes=0,
                minutes_per_round=minutes_per_round,
                allowed_types=("CREATE_POST",),
                emit_fn=emit_fn,
            )

    if action_logger is not None:
        action_logger.log_round_end(0, initial_action_count)

    return last_rowid, initial_action_count
