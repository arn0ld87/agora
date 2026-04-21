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
import sqlite3
import sys
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

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

## Tool Usage Rules
1. You MAY call tools BEFORE deciding your action to gather information.
2. To call a tool, use EXACTLY this format:
<tool_call>
{{"name": "tool_name", "parameters": {{"param": "value"}}}}
</tool_call>
3. You can call up to the configured tool-call limit in sequence. After each tool result, you will see the output.
4. When you have enough information, output your FINAL ACTION as JSON:
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
                result = self.tools.execute(
                    call.get("name", ""),
                    call.get("parameters", {})
                )
                tool_results.append({
                    "tool": call.get("name"),
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
