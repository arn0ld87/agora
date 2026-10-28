"""
Prompt building and response action/tool parsing for agent tools.
"""

import json
import re
from typing import Dict, Any, List, Optional

try:
    from ._agent_tools_untrusted import wrap_untrusted, UNTRUSTED_DATA_INSTRUCTION
    from ._agent_tools_stance import build_stance_section
except ImportError:
    from _agent_tools_untrusted import wrap_untrusted, UNTRUSTED_DATA_INSTRUCTION
    from _agent_tools_stance import build_stance_section


def build_agent_prompt_with_tools(
    agent_name: str,
    agent_role: str,
    agent_bio: str,
    observation: str,
    available_actions: List[str],
    tools: Any,
    language: str = "de",
    stance: Optional[str] = None,
    sentiment_bias: Optional[float] = None,
    posts_per_hour: Optional[float] = None,
    comments_per_hour: Optional[float] = None,
    contested_statement: Optional[str] = None,
) -> str:
    """
    Build a prompt that instructs the agent to use tools before acting.

    Args:
        agent_name: Agent's display name
        agent_role: Agent's profession/role
        agent_bio: Short bio
        observation: Current environment observation (from OASIS)
        available_actions: List of action types the agent can take
        tools: Tool registry (for descriptions)
        language: Response language ('de' or 'en')
        stance: Persona attitude ("supportive"/"opposing"/"neutral"/"observer")
            from AgentActivityConfig. ``None`` for legacy configs without it —
            the "Deine Haltung" section is then omitted, not defaulted.
        sentiment_bias: -1.0..1.0 intensity of ``stance``.
        posts_per_hour: Expected own-post frequency, used relative to
            ``comments_per_hour`` to describe posting tendency.
        comments_per_hour: Expected reaction frequency.
        contested_statement: Streitfrage des Laufs (#1778). When set, the
            stance sentence refers to this statement.

    Returns:
        Prompt string ready for LLM
    """
    action_names = ", ".join(available_actions)

    lang_instruction = "German" if language == "de" else "English"

    stance_section = build_stance_section(
        stance,
        sentiment_bias,
        agent_role,
        posts_per_hour,
        comments_per_hour,
        contested_statement,
    )
    stance_block = f"\n{stance_section}" if stance_section else ""

    prompt = f"""You are {agent_name}, a {agent_role}.

Bio: {agent_bio[:300]}
{stance_block}
## Current Situation
{UNTRUSTED_DATA_INSTRUCTION}
{wrap_untrusted("timeline", observation, 1500)}

## Available Actions
You can perform one of these actions: {action_names}

{tools.tools_description_text}

## Tool Usage Rules (IMPORTANT)
1. Call a tool FIRST only when your action will assert a new fact you do not
   already have (a name, number, date, or claim not already visible in your
   timeline) — especially when the topic mentions a specific website, blog,
   company, or person. Never invent facts; use `web_search` or `web_fetch`
   to verify them instead. An opinion-only contribution (your own
   assessment, agreement, or disagreement, without a new factual claim)
   does not require a tool call.
   For trivial reactions where the observation already shows the target
   (LIKE_POST, DISLIKE_POST, DISLIKE_COMMENT, LIKE_COMMENT, FOLLOW, MUTE,
   REPOST, QUOTE_POST, DO_NOTHING), skip tools and output the action directly.
2. To call a tool, use EXACTLY this format (must appear on its own):
<tool_call>
{{"name": "tool_name", "parameters": {{"param": "value"}}}}
</tool_call>
3. You can call up to the configured tool-call limit in sequence. After each
   tool result, you will see the output and can call another tool or decide.
4. Only AFTER you have gathered information, output your FINAL ACTION in <action> tags with the appropriate parameters.
   If the action is a pairwise action, you MUST provide the target ID in your JSON payload:
   - For LIKE_POST, DISLIKE_POST, REPOST, CREATE_COMMENT, QUOTE_POST, you MUST specify "post_id" (integer) of the post you are targeting.
   - For CREATE_COMMENT, also specify "content" (string) for the comment's content.
   - For QUOTE_POST, also specify "content" (string) for the quote's content.
   - For LIKE_COMMENT, DISLIKE_COMMENT, you MUST specify "comment_id" (integer) of the comment you are targeting.
   - For FOLLOW, MUTE, you MUST specify "agent_id" (integer) of the user you want to follow or mute.

<action>
{{
  "action": "ACTION_NAME",
  "content": "Your post or comment content (if applicable)",
  "post_id": 123,
  "comment_id": 456,
  "agent_id": 789
}}
</action>

## Interaction and Conflict (IMPORTANT)
Do not be overly polite, agreeable, or passive. In real-world social media, users frequently express dissent, disagreement, or opposition.
If a post, comment, or opinion on your timeline contradicts your bio, beliefs, professional role, or political alignment, you should actively dissent — but ONLY via an action that is listed in "Available Actions" above. For example:
- DISLIKE via DISLIKE_POST or DISLIKE_COMMENT, or
- reply via CREATE_COMMENT with clear disagreement, criticism, or alternative viewpoints.
If none of these conflict actions are listed in "Available Actions", choose another listed action (e.g. DO_NOTHING) rather than emitting an action that is not available — the parser will drop unavailable actions anyway.
Ensure your actions and text content realistically reflect conflicts, concerns, or opposition exactly as your persona would in the real world.

## Response Language
ALWAYS respond in {lang_instruction}.

## Example Flow
<tool_call>
{{"name": "search_graph", "parameters": {{"query": "current economic policy", "limit": 5}}}}
</tool_call>

[Tool results appear here...]

<action>
{{
  "action": "CREATE_POST",
  "content": "Based on the latest data, I think..."
}}
</action>

Now decide your action."""

    return prompt


def parse_tool_calls(response: str) -> List[Dict[str, Any]]:
    """Parse <tool_call> blocks from LLM response"""
    tool_calls = []
    pattern = r'<tool_call>\s*(\{.*?\})\s*</tool_call>'
    for match in re.finditer(pattern, response, re.DOTALL):
        try:
            data = json.loads(match.group(1))
            if "name" in data and "parameters" in data:
                tool_calls.append(data)
        except json.JSONDecodeError:
            pass
    return tool_calls


def parse_action(response: str) -> Optional[Dict[str, Any]]:
    """Parse <action> block from LLM response"""
    pattern = r'<action>\s*(\{.*?\})\s*</action>'
    match = re.search(pattern, response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Fallback: try to find raw JSON with "action" key
    pattern2 = r'\{\s*"action"\s*:[^}]+\}'
    match2 = re.search(pattern2, response)
    if match2:
        try:
            return json.loads(match2.group())
        except json.JSONDecodeError:
            pass

    return None
