"""MAI-08: ReACT-Loop-Templates."""

REACT_OBSERVATION_TEMPLATE = """\
Observation (Retrieval Result):

═══ Tool {tool_name} Returned ═══
{result}

═══════════════════════════════════════════════════════════════
Called tools {tool_calls_count}/{max_tool_calls} times (Used: {used_tools_str}){unused_hint}
- If information is sufficient: Start with "Final Answer:" and output section content (must quote the above original text)
- If more information is needed: Call a tool to continue retrieving
═══════════════════════════════════════════════════════════════"""

REACT_INSUFFICIENT_TOOLS_MSG = (
    "[Notice] You have only called {tool_calls_count} tools, need at least {min_tool_calls}. "
    "Please call tools again to get more simulation data, then output Final Answer. {unused_hint}"
)

REACT_INSUFFICIENT_TOOLS_MSG_ALT = (
    "Currently called {tool_calls_count} tools, need at least {min_tool_calls}. "
    "Please call tools to get simulation data. {unused_hint}"
)

REACT_TOOL_LIMIT_MSG = (
    "Tool call count has reached the limit ({tool_calls_count}/{max_tool_calls}), cannot call tools anymore. "
    'Please immediately start with "Final Answer:" and output section content based on acquired information.'
)

REACT_UNUSED_TOOLS_HINT = "\n💡 You haven't used yet: {unused_list}, suggest trying different tools to get multi-perspective information"

REACT_FORCE_FINAL_MSG = "Tool call limit reached, please directly output Final Answer: and generate section content."
