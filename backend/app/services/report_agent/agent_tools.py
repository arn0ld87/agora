from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ..graph.graph_dtos import provenance_at
from ..graph_tools import (
    InsightForgeResult,
    InterviewResult,
    PanoramaResult,
    SearchResult,
)
from .action_search import ActionSearchResult

#: Platzhalter, den GraphToolsService für stumme Interview-Plattformen einsetzt
#: — ein Interview, das nur daraus besteht, ist fehlgeschlagen, keine Evidence.
_INTERVIEW_NO_RESPONSE = "(No response from this platform)"
_INTERVIEW_STRUCTURE_RE = re.compile(r"\[(?:Twitter|Reddit) Platform Response\]")


def _record_action_search_hits(
    record_evidence_item: Any,
    result: ActionSearchResult,
    tool_name: str,
    section_index: int,
) -> Optional[Dict[int, str]]:
    """Registriert die Treffer der Beitragssuche als Belege ``agent_action``.

    Issue #1778 (Schritt 1.7): gleiche Form und Identität wie in der
    Stichprobe (``_collect_simulation_evidence_items``). Wie beim Interview
    (#1300) werden die IDs je Trefferindex zurückgegeben, damit
    ``execute_tool`` die Trefferliste damit anreichert — sonst ist ein Treffer
    nicht zitierbar.
    """
    from . import agent as _agent_mod

    evidence_ids: Dict[int, str] = {}
    for hit_index, action in enumerate(result.hits):
        item = _agent_mod.build_action_evidence_item(action)
        item["tool_name"] = tool_name
        if result.query:
            item["query"] = result.query
        item["agent_log_ref"] = {
            "section_index": section_index,
            "action": "tool_result",
            "tool_name": tool_name,
        }
        item.setdefault("source", "report_tool")
        evidence_id = record_evidence_item(item)
        if evidence_id:
            evidence_ids[hit_index] = evidence_id
    return evidence_ids or None


class ReportAgentToolsMixin:
    """Tool-Definitionen, Ausführung und Tool-Evidence-Erfassung für ReportAgent."""

    if TYPE_CHECKING:
        def __getattr__(self, name: str) -> Any: ...
        def __setattr__(self, name: str, value: Any) -> None: ...

    def _record_tool_evidence(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        structured_result: Any,
        rendered_result: str,
        section_index: int,
    ) -> Optional[Dict[int, str]]:
        from . import agent as _agent_mod

        if _agent_mod.is_search_tool(tool_name) and _agent_mod.is_empty_result(structured_result):
            _agent_mod.registry_for(self).record_empty(
                _agent_mod.dedup_key(tool_name, parameters)
            )

        def _graph_fact_item(
            fact: str,
            item_type: str,
            query: str,
            key_prefix: str,
            provenance: Optional[Dict[str, Any]] = None,
        ) -> Optional[Dict[str, Any]]:
            snippet = self._truncate(fact)
            if not snippet:
                _agent_mod.ledger_for(self).dropped(
                    {"snippet": fact, "type": item_type, "producer_key": key_prefix},
                    "empty_after_truncate",
                )
                return None
            item: Dict[str, Any] = {
                "type": item_type,
                "tool_name": tool_name,
                "query": query,
                "snippet": snippet,
                "raw": fact,
                "agent_log_ref": {
                    "section_index": section_index,
                    "action": "tool_result",
                    "tool_name": tool_name,
                },
                "producer_key": _agent_mod.build_producer_key(key_prefix, str(fact).strip()),
            }
            if _agent_mod.provenance_graph_origin(provenance) is not None:
                item["graph_origin"] = _agent_mod.provenance_graph_origin(provenance)
            else:
                anchor = _agent_mod.build_seed_document_anchor(provenance)
                if anchor:
                    item["type"] = "seed_document"
                    item["source_id_anchor"] = anchor
                    item["producer_key"] = _agent_mod.build_producer_key(
                        "seed-doc",
                        str(provenance["document_id"]).strip(),
                        str(provenance.get("chunk_id")),
                    )
            role = _agent_mod.document_role_of(provenance, getattr(self, "document_roles", None))
            if role:
                item["document_role"] = role
            return item

        if isinstance(structured_result, ActionSearchResult) and structured_result.hits:
            return _agent_mod._record_action_search_hits(
                self._record_evidence_item, structured_result, tool_name, section_index
            )

        items: List[Dict[str, Any]] = []
        interview_evidence_ids: Dict[int, str] = {}
        if isinstance(structured_result, InsightForgeResult):
            for position, fact in enumerate(structured_result.semantic_facts):
                item = _graph_fact_item(
                    fact,
                    "graph_fact",
                    structured_result.query,
                    "graph-fact",
                    provenance_at(structured_result.semantic_facts_provenance, position),
                )
                if item:
                    items.append(item)
            for entity in structured_result.entity_insights[:8]:
                item = {
                    "type": "entity_summary",
                    "tool_name": tool_name,
                    "query": structured_result.query,
                    "snippet": self._truncate(entity.get("summary") or entity.get("name")),
                    "raw": entity,
                    "agent_log_ref": {
                        "section_index": section_index,
                        "action": "tool_result",
                        "tool_name": tool_name,
                    },
                }
                if entity.get("uuid"):
                    item["producer_key"] = f"graph-node:{entity['uuid']}"
                if entity.get("graph_origin"):
                    item["graph_origin"] = entity["graph_origin"]
                items.append(item)
            for position, chain in enumerate(structured_result.relationship_chains[:8]):
                item = _graph_fact_item(
                    chain,
                    "relationship_chain",
                    structured_result.query,
                    "graph-chain",
                    provenance_at(structured_result.relationship_chains_provenance, position),
                )
                if item:
                    items.append(item)
        elif isinstance(structured_result, PanoramaResult):
            for position, fact in enumerate(structured_result.active_facts[:10]):
                item = _graph_fact_item(
                    fact,
                    "graph_fact",
                    structured_result.query,
                    "graph-fact",
                    provenance_at(structured_result.active_facts_provenance, position),
                )
                if item:
                    items.append(item)
            for position, fact in enumerate(structured_result.historical_facts[:6]):
                item = _graph_fact_item(
                    fact,
                    "graph_fact",
                    structured_result.query,
                    "graph-fact",
                    provenance_at(structured_result.historical_facts_provenance, position),
                )
                if item:
                    items.append(item)
        elif isinstance(structured_result, SearchResult):
            for position, fact in enumerate(structured_result.facts[:10]):
                item = _graph_fact_item(
                    fact,
                    "graph_fact",
                    structured_result.query,
                    "graph-fact",
                    provenance_at(structured_result.fact_provenance, position),
                )
                if item:
                    items.append(item)
        elif isinstance(structured_result, InterviewResult):
            topic = (structured_result.interview_topic or "").strip()
            for original_index, interview in enumerate(structured_result.interviews[:10]):
                response = (interview.response or "").strip()
                substance = _INTERVIEW_STRUCTURE_RE.sub("", response)
                substance = substance.replace(_INTERVIEW_NO_RESPONSE, "").strip()
                if not substance:
                    continue
                agent_name = (interview.agent_name or "").strip() or "unknown-agent"
                question = (interview.question or "").strip() or "no-question"
                role_family = (getattr(interview, "agent_role_family", None) or "").strip() or None
                stakeholder_group = _agent_mod.resolve_stakeholder_group(
                    interview.agent_role, role_family
                )
                quote_source = next(
                    (q.strip() for q in interview.key_quotes if q and q.strip()),
                    substance,
                )
                item: Dict[str, Any] = {
                    "type": "agent_interview",
                    "tool_name": tool_name,
                    "query": topic,
                    "snippet": self._truncate(response),
                    "raw": interview.to_dict(),
                    "quote": quote_source[:500],
                    "persona_stakeholder_group": stakeholder_group[:200],
                    "persona_role_family": role_family[:120] if role_family else None,
                    "topic_stance": getattr(interview, "topic_stance", None),
                    "voice_key": f"agent:{interview.agent_id}"
                    if getattr(interview, "agent_id", None) is not None
                    else None,
                    "agent_log_ref": {
                        "section_index": section_index,
                        "action": "tool_result",
                        "tool_name": tool_name,
                    },
                    "producer_key": _agent_mod.build_producer_key(
                        f"interview:s{section_index}",
                        topic or "no-topic",
                        agent_name,
                        question,
                        response,
                    ),
                }
                item.setdefault("source", "report_tool")
                evidence_id = self._record_evidence_item(item)
                if evidence_id:
                    interview_evidence_ids[original_index] = evidence_id
        elif isinstance(structured_result, dict) and "results" in structured_result:
            for result in (structured_result.get("results") or [])[:8]:
                item = {
                    "type": "web_search_result",
                    "tool_name": tool_name,
                    "query": structured_result.get("query") or parameters.get("query"),
                    "snippet": self._truncate(result.get("content") or result.get("title")),
                    "raw": result,
                    "agent_log_ref": {
                        "section_index": section_index,
                        "action": "tool_result",
                        "tool_name": tool_name,
                    },
                }
                result_url = result.get("url") or result.get("source_url")
                if result_url:
                    item["producer_key"] = f"web:{result_url}"
                items.append(item)
        elif isinstance(structured_result, dict) and "url" in structured_result:
            items.append(
                {
                    "type": "web_fetch",
                    "tool_name": tool_name,
                    "query": structured_result.get("url"),
                    "snippet": self._truncate(
                        structured_result.get("content") or structured_result.get("title")
                    ),
                    "raw": structured_result,
                    "agent_log_ref": {
                        "section_index": section_index,
                        "action": "tool_result",
                        "tool_name": tool_name,
                    },
                    "producer_key": f"web:{structured_result['url']}",
                }
            )

        if not items and rendered_result:
            items.append(
                {
                    "type": "model_generated_inference",
                    "source": "report_tool",
                    "tool_name": tool_name,
                    "query": parameters.get("query")
                    or parameters.get("url")
                    or parameters.get("interview_topic"),
                    "snippet": self._truncate(rendered_result),
                    "raw": rendered_result,
                    "agent_log_ref": {
                        "section_index": section_index,
                        "action": "tool_result",
                        "tool_name": tool_name,
                    },
                }
            )

        for item in items:
            item.setdefault("source", "report_tool")
            self._record_evidence_item(item)

        return interview_evidence_ids or None

    def _define_tools(self) -> Dict[str, Dict[str, Any]]:
        from . import agent as _agent_mod

        return _agent_mod.define_tools(self)

    def _execute_tool(
        self, tool_name: str, parameters: Dict[str, Any], report_context: str = ""
    ) -> str:
        from . import agent as _agent_mod

        return _agent_mod.execute_tool_call(
            self, tool_name, parameters, report_context=report_context
        )

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        from . import agent as _agent_mod

        return _agent_mod.parse_tool_calls(response)

    def _is_valid_tool_call(self, data: dict) -> bool:
        from . import agent as _agent_mod

        return _agent_mod.is_valid_tool_call(data)

    def _get_tools_description(self) -> str:
        from . import agent as _agent_mod

        return _agent_mod.describe_tools(self.tools)

    def _get_openai_tools_schema(self) -> List[Dict[str, Any]]:
        """Liefert die Tool-Definitionen im OpenAI function-calling Format."""
        from . import agent as _agent_mod

        return _agent_mod.get_openai_tools_schema(self)


__all__ = [
    "ReportAgentToolsMixin",
    "_INTERVIEW_NO_RESPONSE",
    "_INTERVIEW_STRUCTURE_RE",
    "_record_action_search_hits",
]
