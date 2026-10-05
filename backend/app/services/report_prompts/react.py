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

#: Issue #1778: Die Beitragssuche läuft zu Beginn jedes Abschnitts einmal durch
#: das System. Im Abnahmelauf ``report_89d20c11edc1`` rief der Report-Agent sie
#: nur in zwei von sieben Abschnitten auf; 3,5 % des gelesenen Werkzeugtexts
#: stammten aus Beiträgen, 59 % aus Interviews.
REACT_PREFETCHED_POSTS_TEMPLATE = """\


═══ Tool search_simulation_actions Returned (run by the system for this section) ═══
{result}

═══════════════════════════════════════════════════════════════
These posts are what the agents wrote publicly during the simulation. They are evidence
of the same standing as interview answers.
- Report what was said publicly as plain statements in your running text (who argued
  what, where positions met or diverged) and anchor each with its Evidence ID.
- Do not confine posts to quote blocks: a quote block illustrates a statement, it does
  not replace it.
- Call search_simulation_actions with your own keywords to find further posts.
Tool calls used so far: {tool_calls_count}/{max_tool_calls}.
═══════════════════════════════════════════════════════════════"""

REACT_INSUFFICIENT_TOOLS_MSG = (
    "[Notice] Coverage gap: the evidence available so far ({tool_calls_count} tool calls) "
    "does not cover the statements of your draft. "
    "Call a tool to retrieve the missing evidence for this section, then output Final Answer. {unused_hint}"
)

REACT_INSUFFICIENT_TOOLS_MSG_ALT = (
    "Coverage gap: the evidence available so far ({tool_calls_count} tool calls) "
    "does not cover this section. "
    "Please call a tool to retrieve the missing evidence. {unused_hint}"
)

REACT_TOOL_LIMIT_MSG = (
    "Tool call count has reached the limit ({tool_calls_count}/{max_tool_calls}), cannot call tools anymore. "
    'Please immediately start with "Final Answer:" and output section content based on acquired information.'
)

REACT_UNUSED_TOOLS_HINT = "\n💡 You haven't used yet: {unused_list}, suggest trying different tools to get multi-perspective information"

REACT_FORCE_FINAL_MSG = "Tool call limit reached, please directly output Final Answer: and generate section content."
