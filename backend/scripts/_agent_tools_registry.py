"""
Agent tool registry and executions for simulation agents.
"""

from dataclasses import dataclass
import json
import logging
import os
import re
import sqlite3
from typing import Dict, Any, List, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


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
        except (TypeError, ValueError):
            return str(self.data)


class AgentToolRegistry:
    """
    Tool registry for simulation agents.

    Initialized with Neo4jStorage (read-only operations).
    Each tool returns a ToolResult that can be fed back to the LLM.
    """

    def __init__(self, neo4j_storage: Optional[Any] = None,
                 simulation_dir: Optional[str] = None,
                 graph_id: Optional[str] = None):
        self.storage = neo4j_storage
        self.simulation_dir = simulation_dir
        self.graph_id = graph_id
        self._embedding_service = None

        # Lazy-init embedding service for search
        if self.storage and not self.storage._embedding:
            from app.storage.embedding_service import EmbeddingService

            self.storage._embedding = EmbeddingService()

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "AgentToolRegistry":
        """Create registry from simulation_config.json plus runtime environment.

        Secrets are intentionally read only from the environment. Simulation
        config files are persisted artifacts and must not carry passwords or API
        keys.
        """
        neo4j_uri = os.environ.get("NEO4J_URI") or config.get("neo4j_uri") or "bolt://localhost:7687"
        neo4j_secret = os.environ.get("NEO4J_PASSWORD", "")
        neo4j_user = os.environ.get("NEO4J_USER") or config.get("neo4j_user") or "neo4j"
        graph_id = config.get("graph_id")
        simulation_dir = os.path.dirname(config.get("config_path", ""))

        storage = None
        if neo4j_uri and neo4j_secret:
            try:
                from app.storage import Neo4jStorage

                storage = Neo4jStorage(
                    uri=neo4j_uri,
                    user=neo4j_user,
                    password=neo4j_secret
                )
                from urllib.parse import urlparse

                _parsed = urlparse(neo4j_uri)
                _safe_uri = f"{_parsed.scheme}://{_parsed.hostname or '?'}:{_parsed.port or '?'}"
                logger.info("[AgentToolRegistry] Neo4j connected: %s", _safe_uri)
            except Exception as e:
                logger.warning("[AgentToolRegistry] Neo4j connection failed: %s", e)
        else:
            logger.info("[AgentToolRegistry] No Neo4j credentials, tools will be disabled")

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
            results = self.storage.search(
                graph_id=self.graph_id,
                query=query,
                limit=limit,
                scope="both"
            )

            facts = []
            entities = []
            relationships = []

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
                        "type": ", ".join([
                            label for label in node.get('labels', [])
                            if label not in ('Entity', 'Node')
                        ]),
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
                        labels = [
                            label for label in node.get('labels', [])
                            if label not in ('Entity', 'Node')
                        ]
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
            results = self.storage.search(
                graph_id=self.graph_id,
                query=topic,
                limit=limit * 2,
                scope="both"
            )

            related = []
            seen = set()

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
                        labels = [
                            label for label in node.get('labels', [])
                            if label not in ('Entity', 'Node')
                        ]
                        related.append({
                            "name": name,
                            "type": labels[0] if labels else "Unknown",
                            "summary": (node.get('summary', '') or '')[:150]
                        })

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
        """Fetch a web page and return its readable text content.

        The URL comes straight from the model, so it is untrusted input. All
        network access therefore goes through ``app.security.outbound_http``,
        which rejects non-public targets, revalidates every redirect hop and
        pins the connection to the address it actually validated. Never call
        ``requests`` directly here — that is exactly the hole this replaced.
        """
        max_chars = min(int(max_chars), 4000)
        try:
            from app.security.outbound_http import (
                OutboundHttpError,
                OutboundRequestBlocked,
                fetch,
            )
        except ImportError as e:
            logger.error("Outbound HTTP guard unavailable: %s", e)
            return {"error": f"Outbound HTTP guard unavailable: {e}"}

        try:
            result = fetch(url)
        except OutboundRequestBlocked as e:
            logger.warning("web_fetch blocked by outbound policy: %s", e.reason)
            return {"error": f"Blocked by outbound policy: {e.reason}"}
        except OutboundHttpError as e:
            logger.info("web_fetch got HTTP %s", e.status)
            return {"error": f"HTTP {e.status}"}
        except Exception as e:
            logger.warning("web_fetch failed: %s", type(e).__name__)
            return {"error": f"Fetch failed: {e}"}

        soup = BeautifulSoup(result.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return {
            "url": result.url,
            "chars_returned": min(len(text), max_chars),
            "truncated": len(text) > max_chars or result.truncated,
            "content": text[:max_chars],
        }

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
            db_path = os.path.join(self.simulation_dir, "reddit_simulation.db")
            if not os.path.exists(db_path):
                return {"error": "No simulation database found"}

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

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
