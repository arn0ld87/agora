"""
Agent Tool Registry for OASIS Simulation Subprocess

Provides tools that simulation agents can call during their decision-making loop.
Runs independently in the subprocess with direct Neo4j access.

Tools available:
- search_graph: Hybrid search (vector + BM25) in the knowledge graph
- get_entity_detail: Get detailed info about a specific entity by name
- get_related_entities: Find entities related to a topic or name
- get_simulation_context: Get current simulation state (time, active agents)
- get_recent_posts: Get recent posts from the simulation database
"""

import json
import os
import re
import sqlite3
import sys
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

# Allow importing backend modules (run scripts already do sys.path.insert)
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.abspath(os.path.join(_scripts_dir, '..'))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# Load .env for Neo4j credentials
from dotenv import load_dotenv
_project_root = os.path.abspath(os.path.join(_backend_dir, '..'))
_env_file = os.path.join(_project_root, '.env')
if os.path.exists(_env_file):
    load_dotenv(_env_file)

# Import backend storage (needs NEO4J_URI / NEO4J_PASSWORD in env)
from app.storage import Neo4jStorage
from app.storage.embedding_service import EmbeddingService


@dataclass
class ToolResult:
    """Result of a tool execution"""
    success: bool
    data: Any = None
    error: str = ""

    def to_text(self) -> str:
        """Convert to text for LLM consumption"""
        if not self.success:
            return f"Tool error: {self.error}"
        if isinstance(self.data, str):
            return self.data
        try:
            return json.dumps(self.data, ensure_ascii=False, indent=2)
        except:
            return str(self.data)


class AgentToolRegistry:
    """
    Tool registry for simulation agents.

    Initialized with Neo4jStorage (read-only operations).
    Each tool returns a ToolResult that can be fed back to the LLM.
    """

    def __init__(self, neo4j_storage: Optional[Neo4jStorage] = None,
                 simulation_dir: Optional[str] = None,
                 graph_id: Optional[str] = None):
        self.storage = neo4j_storage
        self.simulation_dir = simulation_dir
        self.graph_id = graph_id
        self._embedding_service = None

        # Lazy-init embedding service for search
        if self.storage and not self.storage._embedding:
            self.storage._embedding = EmbeddingService()

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "AgentToolRegistry":
        """Create registry from simulation_config.json plus runtime environment.

        Secrets are intentionally read only from the environment. Simulation
        config files are persisted artifacts and must not carry passwords or API
        keys.
        """
        neo4j_uri = config.get("neo4j_uri") or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        neo4j_secret = os.environ.get("NEO4J_PASSWORD", "")
        neo4j_user = config.get("neo4j_user") or os.environ.get("NEO4J_USER", "neo4j")
        graph_id = config.get("graph_id")
        simulation_dir = os.path.dirname(config.get("config_path", ""))

        storage = None
        if neo4j_uri and neo4j_secret:
            try:
                storage = Neo4jStorage(
                    uri=neo4j_uri,
                    user=neo4j_user,
                    password=neo4j_secret
                )
                print(f"[AgentToolRegistry] Neo4j connected: {neo4j_uri}")
            except Exception as e:
                print(f"[AgentToolRegistry] Neo4j connection failed: {e}")
        else:
            print("[AgentToolRegistry] No Neo4j credentials, tools will be disabled")

        return cls(
            neo4j_storage=storage,
            simulation_dir=simulation_dir,
            graph_id=graph_id
        )

    @property
    def available_tools(self) -> List[Dict[str, Any]]:
        """Return tool descriptions for LLM prompt"""
        tools = []
        if self.storage:
            tools = [
                {
                    "name": "search_graph",
                    "description": (
                        "Search the knowledge graph for facts, entities, and relationships. "
                        "Uses hybrid scoring (vector + keyword). Returns relevant facts and entities."
                    ),
                    "parameters": {
                        "query": "Search query string (e.g. 'Trump tariffs', 'EU response')",
                        "limit": "Maximum results (default 10, max 30)"
                    }
                },
                {
                    "name": "get_entity_detail",
                    "description": "Get detailed information about a specific entity by exact name.",
                    "parameters": {
                        "entity_name": "Exact name of the entity (e.g. 'Donald Trump')"
                    }
                },
                {
                    "name": "get_related_entities",
                    "description": "Find entities related to a topic or name via graph relationships.",
                    "parameters": {
                        "topic": "Topic or entity name to explore",
                        "limit": "Maximum related entities (default 10)"
                    }
                },
            ]

        tools.append({
            "name": "web_fetch",
            "description": (
                "Fetch and read the text content of a web page. "
                "Use this to read websites, blog posts, or any URL relevant to the topic."
            ),
            "parameters": {
                "url": "Full URL to fetch (e.g. 'https://alexle135.de/blog')",
                "max_chars": "Maximum characters to return (default 2000, max 4000)"
            }
        })
        tools.append({
            "name": "web_search",
            "description": (
                "Search the web via DuckDuckGo. Returns titles, URLs, and snippets. "
                "Use to find recent information about a topic or person."
            ),
            "parameters": {
                "query": "Search query string",
                "num_results": "Number of results to return (default 5, max 10)"
            }
        })
        tools.append({
            "name": "get_simulation_context",
            "description": "Get current simulation state: simulated time, active agents, recent events.",
            "parameters": {}
        })

        if self.simulation_dir:
            tools.append({
                "name": "get_recent_posts",
                "description": "Get recent posts from this simulation (last N posts).",
                "parameters": {
                    "limit": "Number of recent posts to retrieve (default 10, max 50)"
                }
            })

        return tools

    @property
    def tools_description_text(self) -> str:
        """Formatted tool descriptions for prompt injection"""
        lines = ["Available Tools:"]
        for tool in self.available_tools:
            params = ", ".join([f"{k}: {v}" for k, v in tool.get("parameters", {}).items()])
            lines.append(f"- {tool['name']}: {tool['description']}")
            if params:
                lines.append(f"  Parameters: {params}")
        return "\n".join(lines)

    def execute(self, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        """Execute a tool by name"""
        method = getattr(self, tool_name, None)
        if method is None:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")
        try:
            data = method(**parameters)
            return ToolResult(success=True, data=data)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    # ── Tool Implementations ──

    def search_graph(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """Hybrid search in the knowledge graph"""
        if not self.storage or not self.graph_id:
            return {"error": "Graph storage not available"}

        limit = min(int(limit), 30)

        try:
            # Use storage.search (hybrid vector + BM25)
            results = self.storage.search(
                graph_id=self.graph_id,
                query=query,
                limit=limit,
                scope="both"
            )

            facts = []
            entities = []
            relationships = []

            # Parse results
            if hasattr(results, 'edges'):
                edge_list = results.edges
            elif isinstance(results, dict) and 'edges' in results:
                edge_list = results['edges']
            else:
                edge_list = []

            for edge in edge_list[:limit]:
                if isinstance(edge, dict):
                    fact = edge.get('fact', '')
                    if fact:
                        facts.append(fact)
                    rel = {
                        "source": edge.get('source_node_name', edge.get('source_node_uuid', ''))[:8],
                        "target": edge.get('target_node_name', edge.get('target_node_uuid', ''))[:8],
                        "type": edge.get('name', ''),
                        "fact": fact
                    }
                    relationships.append(rel)

            if hasattr(results, 'nodes'):
                node_list = results.nodes
            elif isinstance(results, dict) and 'nodes' in results:
                node_list = results['nodes']
            else:
                node_list = []

            for node in node_list[:limit]:
                if isinstance(node, dict):
                    entities.append({
                        "name": node.get('name', ''),
                        "type": ", ".join([l for l in node.get('labels', []) if l not in ('Entity', 'Node')]),
                        "summary": node.get('summary', '')[:200]
                    })

            return {
                "query": query,
                "facts_found": len(facts),
                "facts": facts[:limit],
                "entities": entities[:limit],
                "relationships": relationships[:limit]
            }

        except Exception as e:
            return {"error": f"Search failed: {e}"}

    def get_entity_detail(self, entity_name: str) -> Dict[str, Any]:
        """Get detailed info about an entity by name"""
        if not self.storage or not self.graph_id:
            return {"error": "Graph storage not available"}

        try:
            # Search for the entity
            results = self.storage.search(
                graph_id=self.graph_id,
                query=entity_name,
                limit=5,
                scope="nodes"
            )

            nodes = []
            if hasattr(results, 'nodes'):
                nodes = results.nodes
            elif isinstance(results, dict) and 'nodes' in results:
                nodes = results['nodes']

            for node in nodes:
                if isinstance(node, dict):
                    name = node.get('name', '')
                    if name.lower() == entity_name.lower():
                        labels = [l for l in node.get('labels', []) if l not in ('Entity', 'Node')]
                        return {
                            "name": name,
                            "type": labels[0] if labels else "Unknown",
                            "summary": node.get('summary', ''),
                            "attributes": node.get('attributes', {})
                        }

            return {"error": f"Entity '{entity_name}' not found"}

        except Exception as e:
            return {"error": f"Lookup failed: {e}"}

    def get_related_entities(self, topic: str, limit: int = 10) -> Dict[str, Any]:
        """Find entities related to a topic"""
        if not self.storage or not self.graph_id:
            return {"error": "Graph storage not available"}

        limit = min(int(limit), 20)

        try:
            # Search for topic
            results = self.storage.search(
                graph_id=self.graph_id,
                query=topic,
                limit=limit * 2,
                scope="both"
            )

            related = []
            seen = set()

            # Collect from nodes
            node_list = []
            if hasattr(results, 'nodes'):
                node_list = results.nodes
            elif isinstance(results, dict) and 'nodes' in results:
                node_list = results['nodes']

            for node in node_list:
                if isinstance(node, dict):
                    name = node.get('name', '')
                    if name and name not in seen:
                        seen.add(name)
                        labels = [l for l in node.get('labels', []) if l not in ('Entity', 'Node')]
                        related.append({
                            "name": name,
                            "type": labels[0] if labels else "Unknown",
                            "summary": (node.get('summary', '') or '')[:150]
                        })

            # Collect from edges
            edge_list = []
            if hasattr(results, 'edges'):
                edge_list = results.edges
            elif isinstance(results, dict) and 'edges' in results:
                edge_list = results['edges']

            for edge in edge_list:
                if isinstance(edge, dict):
                    fact = edge.get('fact', '')
                    if fact and fact not in seen:
                        seen.add(fact)
                        related.append({
                            "name": fact[:80],
                            "type": "fact",
                            "summary": fact
                        })

            return {
                "topic": topic,
                "related_count": len(related),
                "related": related[:limit]
            }

        except Exception as e:
            return {"error": f"Related search failed: {e}"}

    def web_fetch(self, url: str, max_chars: int = 2000) -> Dict[str, Any]:
        """Fetch a web page and return its readable text content."""
        max_chars = min(int(max_chars), 4000)
        try:
            resp = requests.get(
                url,
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0 (compatible; AgoraAgent/1.0)"},
                allow_redirects=True,
            )
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" not in content_type and "text/plain" not in content_type:
                return {"error": f"Unsupported content type: {content_type}"}

            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = soup.get_text(separator="\n")
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            truncated = len(text) > max_chars
            return {
                "url": url,
                "chars_returned": min(len(text), max_chars),
                "truncated": truncated,
                "content": text[:max_chars],
            }
        except requests.exceptions.Timeout:
            return {"error": "Request timed out after 10 seconds"}
        except requests.exceptions.RequestException as e:
            return {"error": f"HTTP error: {e}"}
        except Exception as e:
            return {"error": f"Fetch failed: {e}"}

    def web_search(self, query: str, num_results: int = 5) -> Dict[str, Any]:
        """Search the web via Tavily API (optimized for LLM agents)."""
        num_results = min(int(num_results), 10)
        api_key = os.environ.get("TAVILY_API_KEY", "")
        if not api_key:
            return {"error": "TAVILY_API_KEY not set in environment"}
        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "max_results": num_results,
                    "search_depth": "basic",
                    "include_answer": False,
                    "include_raw_content": False,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", "")[:300],
                    "score": round(r.get("score", 0), 3),
                }
                for r in data.get("results", [])
            ]
            return {"query": query, "results_found": len(results), "results": results}
        except requests.exceptions.Timeout:
            return {"error": "Tavily search timed out after 15 seconds"}
        except Exception as e:
            return {"error": f"Search failed: {e}"}

    def get_simulation_context(self) -> Dict[str, Any]:
        """Get current simulation state"""
        context = {
            "simulation_time": "unknown",
            "active_agents": 0,
            "note": "Simulation context available after first round"
        }

        # Try to read env_status.json
        if self.simulation_dir:
            env_status_path = os.path.join(self.simulation_dir, "env_status.json")
            if os.path.exists(env_status_path):
                try:
                    with open(env_status_path, 'r', encoding='utf-8') as f:
                        status = json.load(f)
                    context["status"] = status.get("status", "unknown")
                    context["timestamp"] = status.get("timestamp", "unknown")
                except Exception:
                    pass

        return context

    def get_recent_posts(self, limit: int = 10) -> Dict[str, Any]:
        """Get recent posts from simulation database"""
        if not self.simulation_dir:
            return {"error": "Simulation directory not available"}

        limit = min(int(limit), 50)
        db_path = os.path.join(self.simulation_dir, "twitter_simulation.db")

        if not os.path.exists(db_path):
            # Try Reddit DB
            db_path = os.path.join(self.simulation_dir, "reddit_simulation.db")
            if not os.path.exists(db_path):
                return {"error": "No simulation database found"}

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Get recent posts (CREATE_POST actions)
            cursor.execute("""
                SELECT user_id, info, created_at
                FROM trace
                WHERE action = 'create_post'
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))

            posts = []
            for row in cursor.fetchall():
                user_id, info_json, created_at = row
                try:
                    info = json.loads(info_json) if info_json else {}
                    content = info.get("content", info.get("text", info_json))
                    posts.append({
                        "agent_id": user_id,
                        "content": content[:300] if isinstance(content, str) else str(content)[:300],
                        "timestamp": created_at
                    })
                except Exception:
                    pass

            conn.close()
            return {
                "posts_found": len(posts),
                "posts": posts
            }

        except Exception as e:
            return {"error": f"Database query failed: {e}"}


# ── Prompt Builder ──

def build_agent_prompt_with_tools(
    agent_name: str,
    agent_role: str,
    agent_bio: str,
    observation: str,
    available_actions: List[str],
    tools: AgentToolRegistry,
    language: str = "de"
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

    Returns:
        Prompt string ready for LLM
    """
    action_names = ", ".join(available_actions)

    lang_instruction = "German" if language == "de" else "English"

    prompt = f"""You are {agent_name}, a {agent_role}.

Bio: {agent_bio[:300]}

## Current Situation
{observation[:800]}

## Available Actions
You can perform one of these actions: {action_names}

{tools.tools_description_text}

## Tool Usage Rules (IMPORTANT)
1. You SHOULD call a tool FIRST to gather real information before posting.
   Especially use `web_search` or `web_fetch` when the topic mentions
   a specific website, blog, company, or person — never invent facts.
   Only skip tools if the situation is a trivial LIKE_POST or DO_NOTHING.
2. To call a tool, use EXACTLY this format (must appear on its own):
<tool_call>
{{"name": "tool_name", "parameters": {{"param": "value"}}}}
</tool_call>
3. You can call up to the configured tool-call limit in sequence. After each
   tool result, you will see the output and can call another tool or decide.
4. Only AFTER you have gathered information, output your FINAL ACTION:
<action>
{{"action": "ACTION_NAME", "content": "Your post content or action details"}}
</action>

## Response Language
ALWAYS respond in {lang_instruction}.

## Example Flow
<tool_call>
{{"name": "search_graph", "parameters": {{"query": "current economic policy", "limit": 5}}}}
</tool_call>

[Tool results appear here...]

<action>
{{"action": "CREATE_POST", "content": "Based on the latest data, I think..."}}
</action>

Now decide your action."""

    return prompt


def parse_tool_calls(response: str) -> List[Dict[str, Any]]:
    """Parse <tool_call> blocks from LLM response"""
    import re
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
    import re
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


# ── Async Action Loop ──

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
        language: str = "de"
    ) -> Any:
        """
        Decide agent action with optional tool use.

        Returns an OASIS ManualAction or LLMAction.
        """
        from camel.agents import ChatAgent
        from oasis import ManualAction, ActionType, LLMAction

        # Build initial prompt with tools
        prompt = build_agent_prompt_with_tools(
            agent_name=agent_name or getattr(agent, 'username', 'Agent'),
            agent_role=agent_role or getattr(agent, 'profession', 'Unknown'),
            agent_bio=agent_bio or getattr(agent, 'bio', ''),
            observation=observation,
            available_actions=available_actions,
            tools=self.tools,
            language=language
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
                print(f"[ToolAwareActionLoop] LLM call failed: {e}")
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
                print(f"[ToolUse] Agent calling {tool_name}({params})", flush=True)
                result = self.tools.execute(tool_name, params)
                status = "OK" if result.success else f"ERROR: {result.error}"
                print(f"[ToolUse]   -> {status}", flush=True)
                tool_results.append({
                    "tool": tool_name,
                    "result": result.to_text()
                })
                tool_calls_count += 1

            # Build observation from tool results
            tool_observation = "\n\n".join([
                f"=== {r['tool']} result ===\n{r['result']}"
                for r in tool_results
            ])

            messages.append({"role": "assistant", "content": response_text})
            messages.append({
                "role": "user",
                "content": (
                    f"Tool results:\n{tool_observation}\n\n"
                    "Based on these results, decide your action. "
                    "Output your final action as JSON in <action> tags."
                )
            })

        # Max iterations reached, fallback
        return LLMAction()

    def _create_manual_action(self, action_data: Dict[str, Any], available_actions: List[str]) -> Any:
        """Convert parsed action JSON to OASIS ManualAction"""
        from oasis import ManualAction, ActionType

        action_name = action_data.get("action", "DO_NOTHING").upper()
        content = action_data.get("content", "")

        # Map action name to ActionType
        action_type_map = {
            "CREATE_POST": ActionType.CREATE_POST,
            "LIKE_POST": ActionType.LIKE_POST,
            "REPOST": ActionType.REPOST,
            "FOLLOW": ActionType.FOLLOW,
            "DO_NOTHING": ActionType.DO_NOTHING,
            "QUOTE_POST": ActionType.QUOTE_POST,
            "COMMENT": ActionType.CREATE_POST,  # Reddit uses CREATE_POST for comments
        }

        action_type = action_type_map.get(action_name, ActionType.DO_NOTHING)

        # For actions that need content
        if action_type in (ActionType.CREATE_POST, ActionType.QUOTE_POST) and content:
            return ManualAction(
                action_type=action_type,
                action_args={"content": content}
            )
        elif action_type == ActionType.LIKE_POST:
            return ManualAction(action_type=action_type, action_args={})
        elif action_type == ActionType.REPOST:
            return ManualAction(action_type=action_type, action_args={"content": content or ""})
        else:
            return ManualAction(action_type=ActionType.DO_NOTHING, action_args={})


# ── Convenience: wrap for sync use ──

def create_tool_aware_loop(model, config: Dict[str, Any], max_tool_calls: int = 3) -> Optional[ToolAwareActionLoop]:
    """Create a ToolAwareActionLoop from simulation config"""
    registry = AgentToolRegistry.from_config(config)
    if not registry.storage:
        return None
    return ToolAwareActionLoop(model=model, tools=registry, max_tool_calls=max_tool_calls)


# ── Native CAMEL FunctionTools (preferred path) ──
#
# These build standalone callables with docstrings CAMEL/OASIS can introspect
# into an OpenAI function schema. CAMEL then drives native function calling
# through the model's /v1/chat/completions `tools` parameter — no ReACT
# prompt-parsing needed.


def build_camel_function_tools(config: Dict[str, Any]) -> List[Any]:
    """Return a list of FunctionTool instances bound to a shared AgentToolRegistry.

    Uses closures over the registry so each tool call reuses the same Neo4j
    connection and Tavily key, but presents itself to CAMEL as a plain
    Python function (name + docstring + type hints → OpenAI function schema).
    """
    try:
        from camel.toolkits import FunctionTool
    except ImportError:
        print("[agent_tools] camel.toolkits.FunctionTool not available")
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
        print(f"[FunctionTool] >>> web_search({query!r}, {num_results})", flush=True)
        data = registry.web_search(query=query, num_results=num_results)
        print(f"[FunctionTool] <<< web_search returned {data.get('results_found','?')} results", flush=True)
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


def attach_tools_to_agents(agent_graph, tools: List[Any]) -> int:
    """Inject the given FunctionTools into every SocialAgent in an AgentGraph.

    OASIS's `generate_*_agent_graph` does not expose a `tools` parameter,
    but the underlying CAMEL ChatAgent has `add_tool()`. This helper walks
    the graph and attaches each tool to each agent, and extends the agent's
    system_message with a Tool-Use instruction — otherwise the base persona
    prompt doesn't mention the tools and the LLM skips them.

    Returns the number of (agent × tool) bindings successfully attached.
    """
    if not tools or agent_graph is None:
        return 0
    attached = 0
    try:
        agents_iter = agent_graph.get_agents()
    except Exception as e:
        print(f"[attach_tools] get_agents failed: {e}")
        return 0
    for agent_id, agent in agents_iter:
        for tool in tools:
            try:
                agent.add_tool(tool)
                attached += 1
            except Exception as e:
                print(f"[attach_tools] agent {agent_id} add_tool failed: {e}")
                break
        # Extend system_message so the persona actively uses the tools.
        try:
            sm = getattr(agent, "system_message", None)
            if sm is not None and hasattr(sm, "content"):
                if TOOL_USE_INSTRUCTION.strip() not in sm.content:
                    sm.content = sm.content + TOOL_USE_INSTRUCTION
                    # CAMEL serialized the original system message into memory
                    # during ChatAgent.__init__ via init_messages(). Updating
                    # only the live BaseMessage object is not enough because
                    # ChatHistoryMemory stores dict snapshots, not references.
                    original_sm = getattr(agent, "_original_system_message", None)
                    if original_sm is not None and hasattr(original_sm, "content"):
                        if TOOL_USE_INSTRUCTION.strip() not in original_sm.content:
                            original_sm.content = original_sm.content + TOOL_USE_INSTRUCTION
                    if hasattr(agent, "init_messages"):
                        agent.init_messages()
        except Exception as e:
            print(f"[attach_tools] agent {agent_id} prompt patch failed: {e}")
        # OASIS SocialAgent defaults to max_iteration=1 — meaning the LLM gets
        # exactly one turn, so it can either call a research tool OR a social
        # action, never both. Raise it so research → action can happen in one
        # perform_action_by_llm() cycle.
        try:
            if hasattr(agent, "max_iteration"):
                agent.max_iteration = max(getattr(agent, "max_iteration", 1) or 1, 4)
        except Exception as e:
            print(f"[attach_tools] agent {agent_id} max_iteration patch failed: {e}")

    # Sanity: dump the tool names on the first agent after patching.
    try:
        first_id, first_agent = next(iter(agent_graph.get_agents()))
        all_names = []
        for attr in ("tools", "_tools", "_all_tools"):
            tlist = getattr(first_agent, attr, None)
            if tlist:
                for t in tlist:
                    n = getattr(t, "func", None)
                    n = getattr(n, "__name__", None) if n else getattr(t, "__name__", str(t))
                    all_names.append(n)
                break
        print(f"[attach_tools] sanity: agent {first_id} now has {len(all_names)} tools: {all_names}", flush=True)
        print(f"[attach_tools] sanity: agent {first_id} max_iteration = {getattr(first_agent, 'max_iteration', '?')}", flush=True)
    except Exception as e:
        print(f"[attach_tools] sanity dump failed: {e}")

    return attached
