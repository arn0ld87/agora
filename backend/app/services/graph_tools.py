"""
Graph Retrieval Tools Service
Encapsulates graph search, node retrieval, edge queries, and other tools for use by Report Agent.

Replaces zep_tools.py — all Zep Cloud calls replaced by GraphStorage.

Core Retrieval Tools (Optimized):
1. InsightForge (Deep Insight Retrieval) - Most powerful hybrid search, automatically generates sub-questions and multi-dimensional retrieval
2. PanoramaSearch (Breadth Search) - Get comprehensive view, including expired content
3. QuickSearch (Simple Search) - Quick retrieval
"""

import json
from typing import Dict, Any, List, Optional

from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient
from ..storage import GraphStorage
import app.services.graph.graph_reader as _reader
import app.services.graph.insight_forge_tool as _forge

# Re-Export der Dataclasses aus dem ausgegliederten Submodul
# (M11 Phase 5b PR 1 — siehe app/services/graph/graph_dtos.py)
# Aliased imports satisfy mypy's no-implicit-reexport check (PEP 484 §re-exports).
from .interview_stance import (
    STANCE_PROMPT_REQUIREMENT,
    split_platform_answers,
)
from .graph.graph_dtos import SearchResult as SearchResult  # noqa: PLC0414
from .graph.graph_dtos import NodeInfo as NodeInfo  # noqa: PLC0414
from .graph.graph_dtos import EdgeInfo as EdgeInfo  # noqa: PLC0414
from .graph.graph_dtos import InsightForgeResult as InsightForgeResult  # noqa: PLC0414
from .graph.graph_dtos import PanoramaResult as PanoramaResult  # noqa: PLC0414
from .graph.graph_dtos import AgentInterview as AgentInterview  # noqa: PLC0414
from .graph.graph_dtos import InterviewResult as InterviewResult  # noqa: PLC0414

logger = get_logger('agora.graph_tools')

#: Fehlertexte, die auf eine vorübergehende Störung hindeuten. Sie schalten
#: das Interview-Tool nicht ab: der ``ToolCircuitBreaker`` ist für terminale
#: Ausfälle gedacht, und ein Timeout unter Last ist keiner.
_RETRYABLE_INTERVIEW_ERROR_MARKERS = (
    "timeout",
    "timed out",
    "zeitüberschreitung",
    "zeituberschreitung",
    "temporarily",
    "rate limit",
    "too many requests",
    "connection reset",
    "try again",
)


def _is_terminal_interview_error(error_msg: object) -> bool:
    """Ist der Interview-Ausfall endgültig oder nur dieser Versuch?

    Endgültig heißt: aus dem Report-Kontext nicht wiederherstellbar — keine
    laufende Simulationsumgebung, keine persistierten Personas. Alles, was
    nach Last oder Netz klingt, darf erneut versucht werden.
    """
    lowered = str(error_msg or "").lower()
    return not any(
        marker in lowered for marker in _RETRYABLE_INTERVIEW_ERROR_MARKERS
    )


class GraphToolsService:
    """Graph Retrieval Tools Service (via GraphStorage / Neo4j).

    Basic Tools (bodies in app.services.graph.graph_reader — M11 Phase 5b PR 2):
        search_graph, get_all_nodes, get_all_edges, get_node_detail,
        get_node_edges, get_entities_by_type, get_entity_summary,
        get_graph_statistics, get_simulation_context.

    Core Tools (implemented here):
        insight_forge, panorama_search, quick_search, interview_agents.
    """

    def __init__(self, storage: GraphStorage, llm_client: Optional[LLMClient] = None):
        self.storage = storage
        self._llm_client = llm_client
        logger.info("GraphToolsService initialization complete")

    @property
    def llm(self) -> LLMClient:
        """Lazy initialization of LLM client"""
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    # ========== Basic Tools (delegating to app.services.graph.graph_reader) ==========
    #
    # Bodies live in graph_reader.py (M11 Phase 5b PR 2).
    # These thin wrappers preserve the public API so existing call-sites and
    # Monkeypatch-Stubs in tests continue to work without modification.

    def search_graph(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges",
    ) -> SearchResult:
        """Graph semantic search (hybrid: vector + BM25 via Neo4j)."""
        return _reader.search_graph(
            graph_id, query, storage=self.storage, llm=self.llm, limit=limit, scope=scope
        )

    def _local_search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges",
    ) -> SearchResult:
        """Local keyword-matching search (fallback approach)."""
        return _reader.local_search(
            graph_id, query, storage=self.storage, limit=limit, scope=scope
        )

    def get_all_nodes(self, graph_id: str) -> List[NodeInfo]:
        """Get all nodes in the graph."""
        return _reader.get_all_nodes(graph_id, storage=self.storage)

    def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> List[EdgeInfo]:
        """Get all edges in the graph (with temporal information)."""
        return _reader.get_all_edges(graph_id, storage=self.storage, include_temporal=include_temporal)

    def get_node_detail(self, node_uuid: str) -> Optional[NodeInfo]:
        """Get detailed information about a single node."""
        return _reader.get_node_detail(node_uuid, storage=self.storage)

    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[EdgeInfo]:
        """Get all edges related to a node."""
        return _reader.get_node_edges(graph_id, node_uuid, storage=self.storage)

    def get_entities_by_type(self, graph_id: str, entity_type: str) -> List[NodeInfo]:
        """Get entities by type."""
        return _reader.get_entities_by_type(graph_id, entity_type, storage=self.storage)

    def get_entity_summary(self, graph_id: str, entity_name: str) -> Dict[str, Any]:
        """Get relationship summary for a specific entity."""
        return _reader.get_entity_summary(graph_id, entity_name, storage=self.storage)

    def get_graph_statistics(self, graph_id: str) -> Dict[str, Any]:
        """Get statistics for the graph."""
        return _reader.get_graph_statistics(graph_id, storage=self.storage)

    def get_simulation_context(
        self,
        graph_id: str,
        simulation_requirement: str,
        limit: int = 30,
    ) -> Dict[str, Any]:
        """Get simulation-related context information."""
        return _reader.get_simulation_context(
            graph_id, simulation_requirement, storage=self.storage, llm=self._llm_client, limit=limit
        )

    # ========== Core Retrieval Tools (Optimized) ==========
    #
    # Bodies live in app.services.graph.insight_forge_tool (M11 Phase 5b PR 3).
    # These thin wrappers preserve the public API so existing call-sites and
    # MagicMock-Stubs in tests continue to work without modification.

    def insight_forge(
        self,
        graph_id: str,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_sub_queries: int = 5,
    ) -> InsightForgeResult:
        """Deep Insight Retrieval -- delegates to app.services.graph.insight_forge_tool."""
        return _forge.insight_forge(
            graph_id, query, simulation_requirement,
            storage=self.storage, llm=self.llm,
            report_context=report_context, max_sub_queries=max_sub_queries,
        )

    def _generate_sub_queries(
        self,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_queries: int = 5,
    ) -> List[str]:
        """Generate sub-questions -- delegates to app.services.graph.insight_forge_tool."""
        return _forge.generate_sub_queries(
            query, simulation_requirement,
            llm=self.llm, report_context=report_context, max_queries=max_queries,
        )

    def panorama_search(
        self,
        graph_id: str,
        query: str,
        include_expired: bool = True,
        limit: int = 50,
    ) -> PanoramaResult:
        """Breadth Search -- delegates to app.services.graph.insight_forge_tool."""
        return _forge.panorama_search(
            graph_id, query,
            storage=self.storage, llm=self._llm_client,
            include_expired=include_expired, limit=limit,
        )

    def quick_search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
    ) -> SearchResult:
        """Simple Search -- delegates to app.services.graph.insight_forge_tool."""
        return _forge.quick_search(
            graph_id, query,
            storage=self.storage, llm=self._llm_client, limit=limit,
        )

    def interview_agents(
        self,
        simulation_id: str,
        interview_requirement: str,
        simulation_requirement: str = "",
        max_agents: int = 5,
        custom_questions: List[str] = None
    ) -> InterviewResult:
        """
        [InterviewAgents - Deep Interview]

        Call the real OASIS interview API to interview Agents running in the simulation.
        This method does NOT use GraphStorage — it calls SimulationRunner
        and reads agent profiles from disk.
        """
        from .simulation_runner import SimulationRunner

        logger.info(f"InterviewAgents deep interview (real API): {interview_requirement[:50]}...")

        result = InterviewResult(
            interview_topic=interview_requirement,
            interview_questions=custom_questions or []
        )

        # Sub-Slice 05.6 / Issue #999 — Early-Check: ein Interview muss
        # überhaupt beantwortbar sein, bevor wir teure LLM-Calls für Selection
        # + Question-Generation auslösen (30-60s). Vorher prüfte dieser Check
        # nur die IPC-Liveness (check_env_alive), die für jede abgeschlossene
        # Simulation False ist — der Normalzustand eines Report-Laufs.
        # interviews_possible fragt zusätzlich den Direktpfad (persistierte
        # Personas) ab, den interview_agents_batch ohnehin automatisch
        # nutzt, sobald die IPC-Umgebung tot ist.
        if not SimulationRunner.interviews_possible(simulation_id):
            logger.warning(
                "Interview tool skipped for %s — neither a running IPC "
                "worker nor persisted agent personas were found. Returning "
                "terminal soft-fail.",
                simulation_id,
            )
            result.summary = (
                "Interview tool unavailable for this report run — neither a "
                "running simulation worker nor persisted agent personas "
                "were found for this simulation. Do NOT call interview_agents "
                "again. Use insight_forge, panorama_search, or quick_search to "
                "derive stakeholder perspectives from the graph instead."
            )
            result.terminal_failure = True
            result.terminal_reason = (
                "weder ein laufender Simulationsworker noch persistierte "
                "Agent-Personas vorhanden"
            )
            return result

        # Step 1: Read agent profile files
        profiles = self._load_agent_profiles(simulation_id)

        if not profiles:
            logger.warning(f"No profile files found for simulation {simulation_id}")
            result.summary = "No Agent profile files found for interview"
            return result

        result.total_agents = len(profiles)
        logger.info(f"Loaded {len(profiles)} Agent profiles")

        # Step 2: Use LLM to select Agents for interview
        selected_agents, selected_indices, selection_reasoning = self._select_agents_for_interview(
            profiles=profiles,
            interview_requirement=interview_requirement,
            simulation_requirement=simulation_requirement,
            max_agents=max_agents
        )

        result.selected_agents = selected_agents
        result.selection_reasoning = selection_reasoning
        logger.info(f"Selected {len(selected_agents)} Agents for interview: {selected_indices}")

        # Step 3: Generate interview questions
        if not result.interview_questions:
            result.interview_questions = self._generate_interview_questions(
                interview_requirement=interview_requirement,
                simulation_requirement=simulation_requirement,
                selected_agents=selected_agents
            )
            logger.info(f"Generated {len(result.interview_questions)} interview questions")

        combined_prompt = "\n".join([f"{i+1}. {q}" for i, q in enumerate(result.interview_questions)])

        INTERVIEW_PROMPT_PREFIX = (
            # Issue #1304 (S1): Der Prompt versprach zuvor "all past memories
            # and actions". Auf dem Direktpfad — dem Normalfall fuer
            # abgeschlossene Simulationen — liefert der System-Prompt die
            # eigenen Beitraege der Persona, aber keine fremden Erinnerungen.
            # Ein Versprechen, das der Kontext nicht einloest, laedt das Modell
            # zum Erfinden ein.
            "You are being interviewed. Draw on your character profile and on whatever "
            "of your own simulation activity is provided above, and directly answer the "
            "following questions in plain text.\n"
            "Response requirements:\n"
            "1. Answer directly in natural language, do not call any tools\n"
            "2. Do not return JSON format or tool call format\n"
            "3. Do not use Markdown headings (e.g., #, ##, ###)\n"
            "4. Answer the questions in order, with each answer starting with 'Question X:' (X is the question number)\n"
            "5. Separate each answer with a blank line\n"
            "6. Provide substantive answers, at least 2-3 sentences per question\n"
            # Issue #1363: Ohne eine Richtung laesst sich nichts auszaehlen.
            # ``sentiment_score`` stand im Vertrag und war im Referenzlauf bei
            # 0 von 99 Items gesetzt; damit war jede Mengenaussage ueber
            # Stakeholder strukturell unbelegbar.
            + STANCE_PROMPT_REQUIREMENT
            + "\n"
        )
        optimized_prompt = f"{INTERVIEW_PROMPT_PREFIX}{combined_prompt}"

        # Step 4: Call the real interview API
        try:
            interviews_request = []
            for agent_idx in selected_indices:
                interviews_request.append({
                    "agent_id": agent_idx,
                    "prompt": optimized_prompt
                })

            logger.info(f"Calling batch interview API (dual platform): {len(interviews_request)} Agents")

            api_result = SimulationRunner.interview_agents_batch(
                simulation_id=simulation_id,
                interviews=interviews_request,
                platform=None,
                timeout=180.0
            )

            logger.info(f"Interview API returned: {api_result.get('interviews_count', 0)} results, success={api_result.get('success')}")

            if not api_result.get("success", False):
                error_msg = api_result.get("error", "Unknown error")
                logger.warning(f"Interview API call failed: {error_msg}")
                # Sub-Slice 05.6 — Terminal-Hint statt Retry-Aufforderung.
                # Sim-Reachability ist nicht aus dem Report-Context wiederherstellbar.
                result.summary = (
                    f"Interview tool TERMINALLY UNAVAILABLE for this report run "
                    f"(reason: {error_msg}). Do NOT call interview_agents again. "
                    "Use insight_forge, panorama_search, or quick_search instead."
                )
                # Nur ein nicht wiederherstellbarer Ausfall schaltet das Tool
                # ab. Ein Timeout ist keiner — der 180-Sekunden-Deckel greift
                # bei Last, nicht bei Unerreichbarkeit, und ein einzelner
                # langsamer Batch darf nicht den ganzen Bericht um seine
                # Interviews bringen. Der Hinweistext oben bleibt in beiden
                # Fällen bestehen; er kostet nichts und rät vom Wiederholen ab.
                result.terminal_failure = _is_terminal_interview_error(error_msg)
                result.terminal_reason = str(error_msg)
                return result

            # Step 5: Parse API response
            api_data = api_result.get("result", {})
            results_dict = api_data.get("results", {}) if isinstance(api_data, dict) else {}

            for i, agent_idx in enumerate(selected_indices):
                agent = selected_agents[i]
                agent_name = agent.get("realname", agent.get("username", f"Agent_{agent_idx}"))
                agent_role = agent.get("profession", "Unknown")
                # Issue #1248: Das Rollenfamilien-Label ist der Entitaetstyp der
                # Quellentitaet — kontrolliert und pro Lauf stabil, im Gegensatz
                # zum frei formulierten Berufstitel. Kollektiv- und
                # Individual-Persona derselben Organisation tragen denselben Typ
                # und zaehlen damit als eine Familie.
                agent_role_family = (agent.get("source_entity_type") or "").strip() or None
                agent_bio = agent.get("bio", "")

                # Issue #1320: Nur Plattformen rendern, die tatsaechlich
                # geantwortet haben. Der Direktpfad (abgeschlossener Run) ist
                # bewusst single-platform — er befragt jede Persona einmal statt
                # dieselbe Frage doppelt zu stellen. Der Renderer zog das nie
                # nach und schrieb fuer die stumme Plattform einen Block mit
                # Platzhalter. Im Referenzlauf entstand so fuer 42 Interviews je
                # ein leerer ``[Twitter Platform Response]``-Block, der wie eine
                # gescheiterte Befragung aussah statt wie eine, die nie
                # stattgefunden hat.
                platform_answers: list[tuple[str, str]] = []
                for platform_label, platform_key in (
                    ("Twitter", "twitter"),
                    ("Reddit", "reddit"),
                ):
                    raw_response = results_dict.get(
                        f"{platform_key}_{agent_idx}", {}
                    ).get("response", "")
                    cleaned = self._clean_tool_call_response(raw_response)
                    if cleaned and cleaned.strip():
                        platform_answers.append((platform_label, cleaned))

                # Issue #1363: Erst die Haltungszeile abtrennen, dann rendern
                # und Zitate ziehen — sonst landet "STANCE: -0.6" im
                # persistierten Zitat und im Berichtstext.
                platform_answers, topic_stance = split_platform_answers(
                    platform_answers
                )

                if platform_answers:
                    response_text = "\n\n".join(
                        f"[{label} Platform Response]\n{text}"
                        for label, text in platform_answers
                    )
                else:
                    # Ein einzelner Platzhalter statt zweier: der Report-Agent
                    # erkennt daran weiterhin das gescheiterte Interview und
                    # verwirft es als Evidence.
                    response_text = "(No response from this platform)"

                import re
                combined_responses = " ".join(text for _label, text in platform_answers)

                clean_text = re.sub(r'#{1,6}\s+', '', combined_responses)
                clean_text = re.sub(r'\{[^}]*tool_name[^}]*\}', '', clean_text)
                clean_text = re.sub(r'[*_`|>~\-]{2,}', '', clean_text)
                clean_text = re.sub(r'Question\d+[：:]\s*', '', clean_text)
                clean_text = re.sub(r'【[^】]+】', '', clean_text)

                sentences = re.split(r'[。！？]', clean_text)
                meaningful = [
                    s.strip() for s in sentences
                    if 20 <= len(s.strip()) <= 150
                    and not re.match(r'^[\s\W，,；;：:、]+', s.strip())
                    and not s.strip().startswith(('{', 'Question'))
                ]
                meaningful.sort(key=len, reverse=True)
                key_quotes = [s + "。" for s in meaningful[:3]]

                if not key_quotes:
                    paired = re.findall(r'\u201c([^\u201c\u201d]{15,100})\u201d', clean_text)
                    paired += re.findall(r'\u300c([^\u300c\u300d]{15,100})\u300d', clean_text)
                    key_quotes = [q for q in paired if not re.match(r'^[，,；;：:、]', q)][:3]

                interview = AgentInterview(
                    agent_name=agent_name,
                    agent_role=agent_role,
                    agent_role_family=agent_role_family,
                    agent_bio=agent_bio[:1000],
                    question=combined_prompt,
                    response=response_text,
                    key_quotes=key_quotes[:5],
                    topic_stance=topic_stance,
                )
                result.interviews.append(interview)

            result.interviewed_count = len(result.interviews)

        except ValueError as e:
            logger.warning(f"Interview API call failed (environment not running?): {e}")
            # Sub-Slice 05.6 — Terminal-Hint. Der alte "please ensure ...
            # running"-String verleitete das LLM zu unendlichen Retry-Loops.
            result.summary = (
                f"Interview tool TERMINALLY UNAVAILABLE for this report run "
                f"(reason: {str(e)}). Do NOT call interview_agents again. "
                "Use insight_forge, panorama_search, or quick_search instead."
            )
            result.terminal_failure = True
            result.terminal_reason = str(e)
            return result
        except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
            logger.error(f"Interview API call exception: {e}")
            import traceback
            logger.error(traceback.format_exc())
            result.summary = f"An error occurred during the interview process: {str(e)}"
            return result

        # Step 6: Generate interview summary
        if result.interviews:
            result.summary = self._generate_interview_summary(
                interviews=result.interviews,
                interview_requirement=interview_requirement
            )

        logger.info(f"InterviewAgents complete: Interviewed {result.interviewed_count} Agents (dual platform)")
        return result

    @staticmethod
    def _clean_tool_call_response(response: str) -> str:
        """Clean JSON tool call wrappers in Agent responses and extract actual content"""
        if not response or not response.strip().startswith('{'):
            return response
        text = response.strip()
        if 'tool_name' not in text[:80]:
            return response
        import re as _re
        try:
            data = json.loads(text)
            if isinstance(data, dict) and 'arguments' in data:
                for key in ('content', 'text', 'body', 'message', 'reply'):
                    if key in data['arguments']:
                        return str(data['arguments'][key])
        except (json.JSONDecodeError, KeyError, TypeError):
            match = _re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
            if match:
                return match.group(1).replace('\\n', '\n').replace('\\"', '"')
        return response

    def _load_agent_profiles(self, simulation_id: str) -> List[Dict[str, Any]]:
        """Load Agent profile files for simulation"""
        import os
        import csv

        sim_dir = os.path.join(
            os.path.dirname(__file__),
            f'../../uploads/simulations/{simulation_id}'
        )

        profiles = []

        # Preferentially try to read Reddit JSON format
        reddit_profile_path = os.path.join(sim_dir, "reddit_profiles.json")
        if os.path.exists(reddit_profile_path):
            try:
                with open(reddit_profile_path, 'r', encoding='utf-8') as f:
                    profiles = json.load(f)
                logger.info(f"Loaded {len(profiles)} profiles from reddit_profiles.json")
                return profiles
            except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
                logger.warning(f"Failed to read reddit_profiles.json: {e}")

        # Try to read Twitter CSV format
        twitter_profile_path = os.path.join(sim_dir, "twitter_profiles.csv")
        if os.path.exists(twitter_profile_path):
            try:
                with open(twitter_profile_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        profiles.append({
                            "realname": row.get("name", ""),
                            "username": row.get("username", ""),
                            "bio": row.get("description", ""),
                            "persona": row.get("user_char", ""),
                            "profession": "Unknown"
                        })
                logger.info(f"Loaded {len(profiles)} profiles from twitter_profiles.csv")
                return profiles
            except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
                logger.warning(f"Failed to read twitter_profiles.csv: {e}")

        return profiles

    def _select_agents_for_interview(
        self,
        profiles: List[Dict[str, Any]],
        interview_requirement: str,
        simulation_requirement: str,
        max_agents: int
    ) -> tuple:
        """Use LLM to select Agents for interview"""

        agent_summaries = []
        for i, profile in enumerate(profiles):
            summary = {
                "index": i,
                "name": profile.get("realname", profile.get("username", f"Agent_{i}")),
                "profession": profile.get("profession", "Unknown"),
                "bio": profile.get("bio", "")[:200],
                "interested_topics": profile.get("interested_topics", [])
            }
            agent_summaries.append(summary)

        system_prompt = """You are a professional interview planning expert. Your task is to select the most suitable Agents for interview from the simulated Agent list based on the interview requirements.

Selection Criteria:
1. Agent's identity/profession is relevant to the interview topic
2. Agent may hold unique or valuable perspectives
3. Select diverse perspectives (e.g., supporters, opposers, neutral, experts, etc.)
4. Prioritize roles directly related to the event

Return JSON format:
{
    "selected_indices": [List of indices of selected Agents],
    "reasoning": "Brief explanation (max 2 short sentences, 200 characters total)"
}

Keep `reasoning` deliberately short — the truncation budget caps the payload."""

        user_prompt = f"""Interview Requirement:
{interview_requirement}

Simulation Background:
{simulation_requirement if simulation_requirement else "Not provided"}

Available Agent List ({len(agent_summaries)} total):
{json.dumps(agent_summaries, ensure_ascii=False, indent=2)}

Please select up to {max_agents} most suitable Agents for interview and explain your selection rationale."""

        try:
            # max_tokens 32768: bei 50-Agent-Profil-Listen produzieren Modelle
            # wie Gemini 3.1 Pro 500+ Zeichen "reasoning"; bei Default-4096
            # finish=length → JSON-Repair fischt 91 Zeichen raus → Caller
            # faellt auf Default [0,1,2,3,4]. Folge: jede Report-Section
            # interviewt dieselben 5 Agents (Bias). 32768 ist sicher fuer
            # Gemini 2.5+/Claude 4+/Ollama; gpt-4o (4096-Hardlimit) ist im
            # Stack bewusst nicht im Einsatz.
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=32768,
            )

            selected_indices = response.get("selected_indices", [])[:max_agents]
            reasoning = response.get("reasoning", "Automatically selected based on relevance")

            selected_agents = []
            valid_indices = []
            for idx in selected_indices:
                if 0 <= idx < len(profiles):
                    selected_agents.append(profiles[idx])
                    valid_indices.append(idx)

            return selected_agents, valid_indices, reasoning

        except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
            # Issue #978: Budgetabbruch (#764) ist kein Auswahlfehler — hart
            # durchreichen, sonst interviewt der Run nach einem harten Limit
            # klaglos mit einer Default-Auswahl weiter.
            from .run_budget import BudgetExceededError

            if isinstance(e, BudgetExceededError):
                raise
            logger.warning(f"LLM agent selection failed, using default selection: {e}")
            selected = profiles[:max_agents]
            indices = list(range(min(max_agents, len(profiles))))
            return selected, indices, "Using default selection strategy"

    def _generate_interview_questions(
        self,
        interview_requirement: str,
        simulation_requirement: str,
        selected_agents: List[Dict[str, Any]]
    ) -> List[str]:
        """Use LLM to generate interview questions"""

        agent_roles = [a.get("profession", "Unknown") for a in selected_agents]

        system_prompt = """You are a professional journalist/interviewer. Based on the interview requirements, generate 3-5 deep interview questions.

Question Requirements:
1. Open-ended questions that encourage detailed answers
2. Questions that may have different answers for different roles
3. Cover multiple dimensions: facts, viewpoints, feelings, etc.
4. Natural language, like real interviews
5. Keep each question under 50 characters, concise and clear
6. Ask directly, do not include background explanation or prefix

Return JSON format: {"questions": ["question1", "question2", ...]}"""

        user_prompt = f"""Interview Requirement: {interview_requirement}

Simulation Background: {simulation_requirement if simulation_requirement else "Not provided"}

Interview Subject Roles: {', '.join(agent_roles)}

Please generate 3-5 interview questions."""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.5,
                max_tokens=8192,
            )

            return response.get("questions", [f"What is your perspective on {interview_requirement}?"])

        except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
            # Issue #978: Budgetabbruch (#764) ist kein Generierungsfehler —
            # hart durchreichen, sonst interviewt der Run nach einem harten
            # Limit klaglos mit Default-Fragen weiter.
            from .run_budget import BudgetExceededError

            if isinstance(e, BudgetExceededError):
                raise
            logger.warning(f"Failed to generate interview questions: {e}")
            return [
                f"What is your perspective on {interview_requirement}?",
                "What impact does this have on you or the group you represent?",
                "How do you think this issue should be solved or improved?"
            ]

    def _generate_interview_summary(
        self,
        interviews: List[AgentInterview],
        interview_requirement: str
    ) -> str:
        """Generate interview summary"""

        if not interviews:
            return "No interviews completed"

        interview_texts = []
        for interview in interviews:
            interview_texts.append(f"[{interview.agent_name} ({interview.agent_role})]\n{interview.response[:500]}")

        system_prompt = """You are a professional news editor. Please generate an interview summary based on the responses from multiple interviewees.

Summary Requirements:
1. Extract main viewpoints from all parties
2. Point out consensus and disagreement among viewpoints
3. Highlight valuable quotes
4. Remain objective and neutral, do not favor any side
5. Keep it under 1000 words

Format Constraints (Must Follow):
- Use plain text paragraphs, separated by blank lines
- Do not use Markdown headings (e.g., #, ##, ###)
- Do not use dividers (e.g., ---, ***)
- Use appropriate quotes when citing interviewees
- Can use **bold** to mark keywords, but do not use other Markdown syntax"""

        user_prompt = f"""Interview Topic: {interview_requirement}

Interview Content:
{"".join(interview_texts)}

Please generate an interview summary."""

        try:
            summary = self.llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=800,
                # Kurzzusammenfassung mit bewusst engem Limit — der
                # Token-Boden gilt hier nicht.
                enforce_token_floor=False,
            )
            return summary

        except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
            # Issue #978: Budgetabbruch (#764) ist kein Generierungsfehler —
            # hart durchreichen, sonst interviewt der Run nach einem harten
            # Limit klaglos mit einem Default-Summary-Text weiter.
            from .run_budget import BudgetExceededError

            if isinstance(e, BudgetExceededError):
                raise
            logger.warning(f"Failed to generate interview summary: {e}")
            return f"Interviewed {len(interviews)} interviewees, including: " + ", ".join([i.agent_name for i in interviews])
