from __future__ import annotations

import ast
from pathlib import Path

SOURCE = Path("backend/app/services/graph_tools.py")

source = SOURCE.read_text(encoding="utf-8")
lines = source.splitlines(keepends=True)
tree = ast.parse(source)
service = next(
    node
    for node in tree.body
    if isinstance(node, ast.ClassDef) and node.name == "GraphToolsService"
)
methods = {
    node.name: node
    for node in service.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}


def span(name: str) -> tuple[int, int]:
    node = methods[name]
    starts = [node.lineno]
    starts.extend(dec.lineno for dec in getattr(node, "decorator_list", []))
    return min(starts) - 1, node.end_lineno


extract_names = [
    "_clean_tool_call_response",
    "_load_agent_profiles",
    "_select_agents_for_interview",
    "_generate_interview_questions",
    "_generate_interview_summary",
]

remove_lines: set[int] = set()
for name in extract_names:
    start, end = span(name)
    remove_lines.update(range(start, end))

first_start, _ = span(extract_names[0])
wrappers = '''    @staticmethod
    def _clean_tool_call_response(response: str) -> str:
        """Delegate response cleanup to the focused interview helper module."""
        return _interview_helpers.clean_tool_call_response(response)

    def _load_agent_profiles(self, simulation_id: str) -> List[Dict[str, Any]]:
        """Load persisted agent profiles through the focused helper module."""
        return _interview_helpers.load_agent_profiles(
            simulation_id,
            service_dir=os.path.dirname(__file__),
        )

    def _select_agents_for_interview(
        self,
        profiles: List[Dict[str, Any]],
        interview_requirement: str,
        simulation_requirement: str,
        max_agents: int,
        panel_tracker: Optional[InterviewPanelTracker] = None,
    ) -> tuple:
        """Delegate LLM-backed panel selection while preserving the public method."""
        return _interview_helpers.select_agents_for_interview(
            profiles=profiles,
            interview_requirement=interview_requirement,
            simulation_requirement=simulation_requirement,
            max_agents=max_agents,
            llm=self.llm,
            panel_tracker=panel_tracker,
        )

    def _generate_interview_questions(
        self,
        interview_requirement: str,
        simulation_requirement: str,
        selected_agents: List[Dict[str, Any]],
    ) -> List[str]:
        """Delegate interview-question generation to the focused helper module."""
        return _interview_helpers.generate_interview_questions(
            interview_requirement=interview_requirement,
            simulation_requirement=simulation_requirement,
            selected_agents=selected_agents,
            llm=self.llm,
        )

    def _generate_interview_summary(
        self,
        interviews: List[AgentInterview],
        interview_requirement: str,
    ) -> str:
        """Delegate interview summarisation to the focused helper module."""
        return _interview_helpers.generate_interview_summary(
            interviews=interviews,
            interview_requirement=interview_requirement,
            llm=self.llm,
        )
'''

facade_parts: list[str] = []
for idx, line in enumerate(lines):
    if idx == first_start:
        facade_parts.append(wrappers)
    if idx not in remove_lines:
        facade_parts.append(line)
facade = "".join(facade_parts)

if "import os\n" not in facade:
    facade = facade.replace("import json\n", "import json\nimport os\n", 1)
import_marker = "import app.services.graph.insight_forge_tool as _forge\n"
if import_marker not in facade:
    raise RuntimeError("graph helper import marker not found")
facade = facade.replace(
    import_marker,
    import_marker + "from .graph import interview_helpers as _interview_helpers\n",
    1,
)
facade = facade.rstrip() + "\n"
SOURCE.write_text(facade, encoding="utf-8")

print(f"graph_tools.py: {len(facade.splitlines())} LOC")
