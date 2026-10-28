"""Tool-aware action loop and CAMEL FunctionTools for OASIS agents."""

import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Relative / absolute import handling
try:
    from ._agent_tools_untrusted import (
        wrap_untrusted,
        UNTRUSTED_DATA_INSTRUCTION,
        _TOOL_RESULT_UNTRUSTED_LIMIT,
    )
    from ._agent_tools_prompt import (
        build_agent_prompt_with_tools,
        parse_action,
        parse_tool_calls,
    )
    from ._agent_tools_registry import AgentToolRegistry
    from ._sim_common import is_workspace_credential_scope
except ImportError:
    from _agent_tools_untrusted import (
        wrap_untrusted,
        UNTRUSTED_DATA_INSTRUCTION,
        _TOOL_RESULT_UNTRUSTED_LIMIT,
    )
    from _agent_tools_prompt import (
        build_agent_prompt_with_tools,
        parse_action,
        parse_tool_calls,
    )
    from _agent_tools_registry import AgentToolRegistry
    from _sim_common import is_workspace_credential_scope


class ToolAwareActionLoop:
    """
    ReACT-style action loop for OASIS agents.

    Replaces LLMAction() with a custom loop that allows agents to call tools
    before deciding their final action.
    """

    def __init__(self, model, tools: AgentToolRegistry, max_tool_calls: int = 3):
        self.model = model
        self.tools = tools
        self.max_tool_calls = max_tool_calls

    async def decide_action(
        self,
        agent,
        observation: str,
        available_actions: List[str],
        agent_name: str = "",
        agent_role: str = "",
        agent_bio: str = "",
        language: str = "de",
        stance: Optional[str] = None,
        sentiment_bias: Optional[float] = None,
        posts_per_hour: Optional[float] = None,
        comments_per_hour: Optional[float] = None,
        contested_statement: Optional[str] = None,
    ) -> Any:
        """
        Decide agent action with optional tool use.

        Returns an OASIS ManualAction or LLMAction.
        """
        from oasis import LLMAction

        # Build initial prompt with tools
        prompt = build_agent_prompt_with_tools(
            agent_name=agent_name or getattr(agent, 'username', 'Agent'),
            agent_role=agent_role or getattr(agent, 'profession', 'Unknown'),
            agent_bio=agent_bio or getattr(agent, 'bio', ''),
            observation=observation,
            available_actions=available_actions,
            tools=self.tools,
            language=language,
            stance=stance,
            sentiment_bias=sentiment_bias,
            posts_per_hour=posts_per_hour,
            comments_per_hour=comments_per_hour,
            contested_statement=contested_statement,
        )

        messages = [{"role": "user", "content": prompt}]
        tool_calls_count = 0

        for iteration in range(self.max_tool_calls + 1):
            # Call LLM
            try:
                # Use the model directly (camel model interface)
                response = self.model.run(messages=messages)
                # response is typically a string or has .content
                if hasattr(response, 'content'):
                    response_text = response.content
                elif hasattr(response, 'msgs') and response.msgs:
                    response_text = response.msgs[0].content
                else:
                    response_text = str(response)
            except Exception as e:
                logger.warning("[ToolAwareActionLoop] LLM call failed: %s", e)
                # Fallback to standard LLMAction
                return LLMAction()

            # Check for action
            action_data = parse_action(response_text)
            if action_data and not parse_tool_calls(response_text):
                # Final action found, no more tool calls
                return self._create_manual_action(action_data, available_actions)

            # Check for tool calls
            tool_calls = parse_tool_calls(response_text)
            if not tool_calls or tool_calls_count >= self.max_tool_calls:
                # No tool calls or limit reached, try to extract action anyway
                if action_data:
                    return self._create_manual_action(action_data, available_actions)
                # Give up and return LLMAction
                return LLMAction()

            # Execute tool calls
            tool_results = []
            for call in tool_calls:
                tool_name = call.get("name", "")
                params = call.get("parameters", {})
                logger.info("[ToolUse] Agent calling %s(%s)", tool_name, params)
                result = self.tools.execute(tool_name, params)
                status = "OK" if result.success else f"ERROR: {result.error}"
                logger.info("[ToolUse]   -> %s", status)
                tool_results.append({
                    "tool": tool_name,
                    "result": result.to_text()
                })
                tool_calls_count += 1

            # Build observation from tool results — each result is untrusted
            # (web_search/web_fetch surface arbitrary external content), so
            # it is wrapped individually with its tool name as the source.
            tool_observation = "\n\n".join([
                wrap_untrusted(r["tool"], r["result"], _TOOL_RESULT_UNTRUSTED_LIMIT)
                for r in tool_results
            ])

            messages.append({"role": "assistant", "content": response_text})
            messages.append({
                "role": "user",
                "content": (
                    f"{UNTRUSTED_DATA_INSTRUCTION}\n"
                    f"Tool results:\n{tool_observation}\n\n"
                    "Based on these results, decide your action. "
                    "Output your final action as JSON in <action> tags."
                )
            })

        # Max iterations reached, fallback
        return LLMAction()

    def _create_manual_action(self, action_data: Dict[str, Any], available_actions: List[str]) -> Any:
        """Convert parsed action JSON to an OASIS ManualAction.

        The prompt contract (see ``build_agent_prompt_with_tools``) asks the
        model to supply target IDs as ``post_id`` / ``comment_id`` / ``agent_id``
        and free text as ``content``. OASIS' platform functions, however,
        expect action-specific kwargs (``followee_id`` for FOLLOW,
        ``mutee_id`` for MUTE, ``quote_content`` for QUOTE_POST — see
        ``oasis/social_agent/agent_action.py``). This method maps the prompt
        contract onto those kwarg names and, when ``available_actions`` is
        non-empty, rejects any action the platform does not offer.

        Any action whose required payload field is missing falls back to
        ``DO_NOTHING`` — otherwise OASIS would raise a ``TypeError`` at
        ``env.step`` time, which surfaces as a silent no-op in the simulation
        log. That mismatch was the root cause of #1215 (B1/B2): pairwise
        actions were emitted but never executed because their target IDs
        were discarded here.
        """
        from oasis import ManualAction, ActionType

        action_name = action_data.get("action", "DO_NOTHING").upper()
        post_id = action_data.get("post_id")
        comment_id = action_data.get("comment_id")
        agent_id = action_data.get("agent_id")
        content = action_data.get("content", "")

        action_type_map = {
            "CREATE_POST": ActionType.CREATE_POST,
            "LIKE_POST": ActionType.LIKE_POST,
            "DISLIKE_POST": ActionType.DISLIKE_POST,
            "REPOST": ActionType.REPOST,
            "QUOTE_POST": ActionType.QUOTE_POST,
            "FOLLOW": ActionType.FOLLOW,
            "MUTE": ActionType.MUTE,
            "CREATE_COMMENT": ActionType.CREATE_COMMENT,
            "LIKE_COMMENT": ActionType.LIKE_COMMENT,
            "DISLIKE_COMMENT": ActionType.DISLIKE_COMMENT,
            "DO_NOTHING": ActionType.DO_NOTHING,
        }

        action_type = action_type_map.get(action_name, ActionType.DO_NOTHING)

        def _noop() -> ManualAction:
            return ManualAction(action_type=ActionType.DO_NOTHING, action_args={})

        # Reject actions the platform does not offer — the prompt lists them
        # as "Available Actions", and emitting a non-listed action would no-op
        # at the OASIS level anyway (e.g. DISLIKE_* on Twitter).
        if available_actions and action_name not in available_actions:
            return _noop()

        if action_type == ActionType.CREATE_POST:
            if not content:
                return _noop()
            return ManualAction(
                action_type=action_type, action_args={"content": content}
            )
        if action_type == ActionType.QUOTE_POST:
            if post_id is None:
                return _noop()
            return ManualAction(
                action_type=action_type,
                action_args={"post_id": post_id, "quote_content": content},
            )
        if action_type == ActionType.CREATE_COMMENT:
            if post_id is None or not content:
                return _noop()
            return ManualAction(
                action_type=action_type,
                action_args={"post_id": post_id, "content": content},
            )
        if action_type in (ActionType.LIKE_POST, ActionType.DISLIKE_POST, ActionType.REPOST):
            if post_id is None:
                return _noop()
            return ManualAction(action_type=action_type, action_args={"post_id": post_id})
        if action_type in (ActionType.LIKE_COMMENT, ActionType.DISLIKE_COMMENT):
            if comment_id is None:
                return _noop()
            return ManualAction(action_type=action_type, action_args={"comment_id": comment_id})
        if action_type == ActionType.FOLLOW:
            if agent_id is None:
                return _noop()
            return ManualAction(action_type=action_type, action_args={"followee_id": agent_id})
        if action_type == ActionType.MUTE:
            if agent_id is None:
                return _noop()
            return ManualAction(action_type=action_type, action_args={"mutee_id": agent_id})
        return _noop()


# ── Convenience: wrap for sync use ──

def create_tool_aware_loop(model, config: Dict[str, Any], max_tool_calls: int = 3) -> Optional[ToolAwareActionLoop]:
    """Create a ToolAwareActionLoop from simulation config"""
    registry = AgentToolRegistry.from_config(config)
    if not registry.storage:
        return None
    return ToolAwareActionLoop(model=model, tools=registry, max_tool_calls=max_tool_calls)


# ── Native CAMEL FunctionTools (preferred path) ──

def build_camel_function_tools(config: Dict[str, Any]) -> List[Any]:
    """Return a list of FunctionTool instances bound to a shared AgentToolRegistry.

    Uses closures over the registry so each tool call reuses the same Neo4j
    connection and Tavily key, but presents itself to CAMEL as a plain
    Python function (name + docstring + type hints → OpenAI function schema).

    A workspace-scoped (JWT/BYOK) run gets no tools at all (#1688): the
    operator's ``TAVILY_API_KEY`` (``web_search``) must never be reachable
    through a visitor's simulation, and the visitor brought no Tavily key of
    their own to use instead. ``web_fetch``/``search_graph`` carry no
    external credential, but disabling the whole set here — not just the
    Tavily-backed one — keeps this a single, auditable gate instead of a
    per-tool allowlist that the next tool addition could miss.
    """
    if is_workspace_credential_scope():
        logger.info(
            "[agent_tools] workspace-scoped run — no FunctionTools attached "
            "(web_search/web_fetch/search_graph disabled)"
        )
        return []
    try:
        from camel.toolkits import FunctionTool
    except ImportError:
        logger.info("[agent_tools] camel.toolkits.FunctionTool not available")
        return []

    registry = AgentToolRegistry.from_config(config)

    def web_search(query: str, num_results: int = 5) -> str:
        """Search the web for current information using Tavily.

        Use this to find up-to-date facts about websites, people, companies,
        events, or any topic where real-world knowledge matters.

        Args:
            query: The search query string.
            num_results: How many search results to return (default 5, max 10).

        Returns:
            JSON string with `results` list containing title, url and snippet
            for each hit.
        """
        logger.info("[FunctionTool] >>> web_search(%r, %s)", query, num_results)
        data = registry.web_search(query=query, num_results=num_results)
        logger.info("[FunctionTool] <<< web_search returned %s results", data.get("results_found", "?"))
        return json.dumps(data, ensure_ascii=False)

    def web_fetch(url: str, max_chars: int = 2000) -> str:
        """Fetch and read the text content of a web page.

        Use this after `web_search` to read the full content of an interesting
        result, or directly when you know the URL (blog post, profile page,
        documentation).

        Args:
            url: The full URL to fetch (must start with http:// or https://).
            max_chars: Maximum characters of body text to return (default 2000, max 4000).

        Returns:
            JSON string with `url`, `chars_returned`, `truncated` and `content` fields.
        """
        data = registry.web_fetch(url=url, max_chars=max_chars)
        return json.dumps(data, ensure_ascii=False)

    def search_graph(query: str, limit: int = 10) -> str:
        """Search the internal knowledge graph (facts extracted from the
        uploaded source document) via hybrid vector + BM25 scoring.

        Use this for facts that were established in the source document —
        prefer `web_search` for anything requiring fresh or external info.

        Args:
            query: Search query string.
            limit: Maximum number of results (default 10, max 30).

        Returns:
            JSON string with matching facts, entities and relationships.
        """
        data = registry.search_graph(query=query, limit=limit)
        return json.dumps(data, ensure_ascii=False)

    tools = [FunctionTool(web_search), FunctionTool(web_fetch)]
    if registry.storage:
        tools.append(FunctionTool(search_graph))
    return tools


TOOL_USE_INSTRUCTION = (
    "\n\n## Research Tools\n"
    "You have access to `web_search`, `web_fetch` and `search_graph` tools.\n"
    "Before posting about any specific website, company, person or topic you\n"
    "are not certain about, CALL web_search (and optionally web_fetch on a\n"
    "relevant result) to gather real information first. Only skip research\n"
    "for trivial actions like LIKE_POST or DO_NOTHING, or when you are simply\n"
    "reacting to another agent's post."
)
