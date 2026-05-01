"""
Tool-Schema für den Report-Agent.

Issue #47 (EPIC-07-ST-03): Tool-Schema und Tool-Execution trennen.

Dieses Modul kapselt die statischen Tool-Beschreibungen, die der
``ReportAgent`` an den LLM weiterreicht. Die Konstanten lebten ursprünglich
direkt in ``services/report_agent.py``; sie wurden hierher gezogen, damit
Schema-Pflege (Beschreibung, Parameter-Hinweise) unabhängig von der
Tool-Execution-Logik passieren kann und damit ``report_agent.py`` weiter
schrumpft (Domain-Cleanup-Pfad v0.9.0).

Re-Export im konsumierenden Modul hält bestehende Aufrufstellen stabil.
"""

TOOL_DESC_INSIGHT_FORGE = """\
[Deep Insight Retrieval - Powerful Retrieval Tool]
This is our powerful retrieval function, designed for deep analysis. It will:
1. Automatically decompose your question into multiple sub-questions
2. Retrieve information from the simulated knowledge graph from multiple dimensions
3. Integrate results from semantic search, entity analysis, and relationship chain tracking
4. Return the most comprehensive and deep retrieval content

[Use Cases]
- Need to deeply analyze a topic
- Need to understand multiple aspects of an event
- Need to obtain rich materials to support report sections

[Return Content]
- Relevant facts in original text (can be directly cited)
- Core entity insights
- Relationship chain analysis"""

TOOL_DESC_PANORAMA_SEARCH = """\
[Breadth Search - Get Complete Overview]
This tool is used to get a complete panoramic view of simulation results, especially suitable for understanding the evolution of events. It will:
1. Retrieve all relevant nodes and relationships
2. Distinguish between current valid facts and historical/expired facts
3. Help you understand how events have evolved

[Use Cases]
- Need to understand the complete development trajectory of an event
- Need to compare public sentiment changes across different stages
- Need to get comprehensive entity and relationship information

[Return Content]
- Current valid facts (latest simulation results)
- Historical/expired facts (evolution records)
- All involved entities"""

TOOL_DESC_QUICK_SEARCH = """\
[Simple Search - Quick Retrieval]
A lightweight quick retrieval tool suitable for simple and direct information queries.

[Use Cases]
- Need to quickly find specific information
- Need to verify a fact
- Simple information retrieval

[Return Content]
- List of facts most relevant to the query"""

TOOL_DESC_INTERVIEW_AGENTS = """\
[Deep Interview - Real Agent Interview (Dual Platform)]
Call the OASIS simulation environment's interview API to conduct real interviews with running simulation agents!
This is not an LLM simulation, but calls the real interview interface to get original responses from simulation agents.
By default, interview on Twitter and Reddit simultaneously to get more comprehensive perspectives.

Function Flow:
1. Automatically read character profile files to understand all simulation agents
2. Intelligently select agents most relevant to the interview topic (e.g., students, media, officials)
3. Automatically generate interview questions
4. Call /api/simulation/interview/batch interface to conduct real interviews on dual platforms
5. Integrate all interview results and provide multi-perspective analysis

[Use Cases]
- Need to understand event perspectives from different role angles (How do students view it? How does media view it? What does the official say?)
- Need to collect diverse opinions and positions
- Need to get real responses from simulation agents (from OASIS simulation environment)
- Want to make the report more vivid, including "interview records"

[Return Content]
- Identity information of interviewed agents
- Interview responses from each agent on Twitter and Reddit platforms
- Key quotes (can be directly cited)
- Interview summary and perspective comparison

[Important] This feature requires the OASIS simulation environment to be running!"""


__all__ = [
    "TOOL_DESC_INSIGHT_FORGE",
    "TOOL_DESC_PANORAMA_SEARCH",
    "TOOL_DESC_QUICK_SEARCH",
    "TOOL_DESC_INTERVIEW_AGENTS",
]
