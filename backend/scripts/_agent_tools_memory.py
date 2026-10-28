"""Memory limit enforcement and FunctionTools injection for OASIS SocialAgents."""

import json
import logging
import os
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from .agent_memory import cap_memory_token_limit, next_memory_token_limit
    from ._agent_tools_loop import TOOL_USE_INSTRUCTION
except ImportError:
    from agent_memory import cap_memory_token_limit, next_memory_token_limit
    from _agent_tools_loop import TOOL_USE_INSTRUCTION


def _role_value(role: Any) -> str:
    return str(getattr(role, "value", role) or "").lower()


def _message_has_tool_calls(message: Any) -> bool:
    if isinstance(message, dict):
        meta_dict = message.get("meta_dict") or message
    else:
        meta_dict = getattr(message, "meta_dict", None) or {}
    tool_calls = meta_dict.get("tool_calls") if isinstance(meta_dict, dict) else None
    return bool(tool_calls)


def _message_content(message: Any) -> Any:
    if isinstance(message, dict):
        return message.get("content")
    return getattr(message, "content", None)


def _sanitize_memory_records(records: List[Any]) -> List[Any]:
    sanitized = []
    for record in records:
        if isinstance(record, dict):
            role = _role_value(record.get("role_at_backend"))
            message = record.get("message", {})
        else:
            role = _role_value(getattr(record, "role_at_backend", None))
            message = getattr(record, "message", None)

        if (
            role == "assistant"
            and _message_content(message) is None
            and not _message_has_tool_calls(message)
        ):
            continue
        sanitized.append(record)
    return sanitized


def _install_empty_assistant_memory_sanitizer(agent_id: Any, memory: Any) -> None:
    if memory is None or getattr(memory, "_agora_empty_assistant_sanitizer", False):
        return
    if not hasattr(memory, "write_records"):
        return

    original_write_records = memory.write_records

    def write_records_with_sanitizer(records):
        record_list = list(records)
        sanitized_records = _sanitize_memory_records(record_list)
        dropped_count = len(record_list) - len(sanitized_records)
        if dropped_count:
            logger.info(
                "[attach_tools] agent %s dropped %s empty assistant memory record(s)",
                agent_id,
                dropped_count,
            )
        if not sanitized_records:
            return None
        return original_write_records(sanitized_records)

    memory.write_records = write_records_with_sanitizer
    memory._agora_empty_assistant_sanitizer = True


# Heuristische Default-Mappings fuer haeufige Cloud-/lokale Modellfamilien.
_MODEL_CONTEXT_HEURISTICS: Tuple[Tuple[str, int], ...] = (
    ("gemini-3", 1_048_576),       # Gemini 3 Pro / Flash: ~1M Tokens
    ("gemini-2.5", 1_048_576),
    ("gemini-2", 1_048_576),
    ("deepseek-v3", 131_072),      # DeepSeek-V3 / V3.1 / V3.2: 128k
    ("deepseek-v4", 1_048_576),    # DeepSeek-V4 (laut Vendor-Stand 2026)
    ("deepseek-r1", 131_072),
    ("qwen3-coder", 262_144),      # Qwen3-Coder / -Coder-Next: 256k
    ("qwen3", 131_072),
    ("qwen2.5", 131_072),
    ("llama-3.3", 131_072),
    ("llama3.3", 131_072),
    ("llama-3.1", 131_072),
    ("gpt-oss", 131_072),          # gpt-oss-Cloud-Familie: 128k
    ("gpt-4.1", 1_048_576),
    ("gpt-4o", 131_072),
    ("claude-opus-4", 200_000),
    ("claude-sonnet-4", 200_000),
    ("claude-haiku-4", 200_000),
    ("nemotron", 131_072),         # nvidia nemotron-3-nano:30b u. ä.
)


def _heuristic_context_limit(model_name: str) -> Optional[int]:
    """Best-effort Substring-Match fuer bekannte Modellfamilien."""
    if not model_name:
        return None
    needle = model_name.lower()
    for prefix, limit in _MODEL_CONTEXT_HEURISTICS:
        if prefix in needle:
            return limit
    return None


def _resolve_memory_token_limit(model_name: Optional[str] = None) -> int:
    try:
        from app.config import Config
        default_limit_fallback = str(Config.LLM_CONTEXT_LIMIT)
        base_overrides = dict(getattr(Config, "LLM_MODEL_CONTEXT_LIMITS", {}) or {})
    except ImportError:
        default_limit_fallback = "8192"
        base_overrides = {}

    raw_overrides = os.environ.get("LLM_MODEL_CONTEXT_LIMITS_JSON", "").strip()
    overrides: Dict[str, Any] = base_overrides
    if raw_overrides:
        try:
            parsed = json.loads(raw_overrides)
        except json.JSONDecodeError as exc:
            logger.warning("[attach_tools] invalid LLM_MODEL_CONTEXT_LIMITS_JSON ignored: %s", exc)
        else:
            if isinstance(parsed, dict):
                overrides.update(parsed)
    default_limit = int(os.environ.get("LLM_CONTEXT_LIMIT", default_limit_fallback))
    override = overrides.get(model_name or "")
    if override is not None:
        try:
            return int(override)
        except (TypeError, ValueError):
            pass
    heuristic = _heuristic_context_limit(model_name or "")
    if heuristic is not None:
        return max(heuristic, default_limit)
    return default_limit


def enforce_memory_token_limit(agent_graph) -> int:
    """Hebe creator._token_limit jedes Agents auf das resolved Memory-Budget."""
    if agent_graph is None:
        return 0
    try:
        agents_iter = agent_graph.get_agents()
    except Exception as exc:  # pragma: no cover — Defensive Hook
        logger.warning("[enforce_memory_token_limit] get_agents failed: %s", exc)
        return 0

    patched = 0
    for agent_id, agent in agents_iter:
        try:
            model_backend = getattr(agent, "model_backend", None)
            model_name = str(getattr(model_backend, "model_type", "") or "")
            ctx_limit = _resolve_memory_token_limit(model_name)
            memory = getattr(agent, "memory", None)
            if memory is None or not hasattr(memory, "get_context_creator"):
                continue
            creator = memory.get_context_creator()
            if creator is None or not hasattr(creator, "_token_limit"):
                continue
            old_limit = getattr(creator, "token_limit", None)
            new_limit = next_memory_token_limit(old_limit, ctx_limit)
            if new_limit is not None:
                creator._token_limit = new_limit
                patched += 1
                logger.info(
                    "[enforce_memory_token_limit] agent %s: %s -> %s (model=%s)",
                    agent_id,
                    old_limit,
                    new_limit,
                    model_name or "?",
                )
        except Exception as exc:
            logger.warning(
                "[enforce_memory_token_limit] agent %s patch failed: %s",
                agent_id,
                exc,
            )
    return patched


def attach_tools_to_agents(agent_graph, tools: List[Any]) -> int:
    """Inject the given FunctionTools into every SocialAgent in an AgentGraph."""
    if not tools or agent_graph is None:
        return 0
    attached = 0
    try:
        agents_iter = agent_graph.get_agents()
    except Exception as e:
        logger.warning("[attach_tools] get_agents failed: %s", e)
        return 0
    for agent_id, agent in agents_iter:
        for tool in tools:
            try:
                agent.add_tool(tool)
                attached += 1
            except Exception as e:
                logger.warning("[attach_tools] agent %s add_tool failed: %s", agent_id, e)
                break
        try:
            sm = getattr(agent, "system_message", None)
            if sm is not None and hasattr(sm, "content"):
                if TOOL_USE_INSTRUCTION.strip() not in sm.content:
                    sm.content = sm.content + TOOL_USE_INSTRUCTION
                    original_sm = getattr(agent, "_original_system_message", None)
                    if original_sm is not None and hasattr(original_sm, "content"):
                        if TOOL_USE_INSTRUCTION.strip() not in original_sm.content:
                            original_sm.content = original_sm.content + TOOL_USE_INSTRUCTION
                    if hasattr(agent, "init_messages"):
                        agent.init_messages()
        except Exception as e:
            logger.warning("[attach_tools] agent %s prompt patch failed: %s", agent_id, e)

        try:
            if hasattr(agent, "max_iteration"):
                agent.max_iteration = max(getattr(agent, "max_iteration", 1) or 1, 4)
        except Exception as e:
            logger.warning("[attach_tools] agent %s max_iteration patch failed: %s", agent_id, e)

        try:
            _install_empty_assistant_memory_sanitizer(agent_id, getattr(agent, "memory", None))
        except Exception as e:
            logger.warning("[attach_tools] agent %s memory sanitizer patch failed: %s", agent_id, e)

        try:
            model_name = str(getattr(getattr(agent, "model_backend", None), "model_type", "") or "")
            ctx_limit = cap_memory_token_limit(_resolve_memory_token_limit(model_name))
            memory = getattr(agent, "memory", None)
            if memory and hasattr(memory, "get_context_creator"):
                creator = memory.get_context_creator()
                if creator is not None:
                    old_limit = getattr(creator, "token_limit", None)
                    if hasattr(creator, "_token_limit"):
                        creator._token_limit = ctx_limit
                        logger.info(
                            "[attach_tools] agent %s context limit: %s -> %s (model=%s)",
                            agent_id,
                            old_limit,
                            ctx_limit,
                            model_name or "?",
                        )
                    else:
                        logger.info(
                            "[attach_tools] agent %s context creator has no _token_limit; "
                            "skip memory patch (type=%s)",
                            agent_id,
                            type(creator).__name__,
                        )
        except Exception as e:
            logger.warning("[attach_tools] agent %s token_limit patch failed: %s", agent_id, e)

    try:
        first_id, first_agent = next(iter(agent_graph.get_agents()))
        tool_dict = getattr(first_agent, "tool_dict", None) or getattr(first_agent, "_internal_tools", {}) or {}
        all_names = list(tool_dict.keys()) if isinstance(tool_dict, dict) else []
        creator = None
        memory = getattr(first_agent, "memory", None)
        if memory and hasattr(memory, "get_context_creator"):
            creator = memory.get_context_creator()
        memory_limit = getattr(creator, "token_limit", "?") if creator is not None else "?"
        model_cfg = getattr(getattr(first_agent, "model_backend", None), "model_config_dict", {}) or {}
        logger.info("[attach_tools] sanity: agent %s now has %s tools: %s", first_id, len(all_names), all_names)
        logger.info("[attach_tools] sanity: agent %s max_iteration = %s", first_id, getattr(first_agent, "max_iteration", "?"))
        logger.info("[attach_tools] sanity: agent %s memory_token_limit = %s", first_id, memory_limit)
        logger.info(
            "[attach_tools] sanity: agent %s completion_max_tokens = %s",
            first_id,
            model_cfg.get("max_completion_tokens", model_cfg.get("max_tokens", "?")),
        )
    except Exception as e:
        logger.warning("[attach_tools] sanity dump failed: %s", e)

    return attached
