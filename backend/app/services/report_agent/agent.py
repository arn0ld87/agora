import re
from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional

from ...utils.llm_client import LLMClient
from ..confidence_calculator import compute_confidence
from ..evidence_binder import bind_evidence_to_claim, detect_contradiction_penalty
from .evidence import (
    init_evidence_map,
    normalize_claims_for_contract,
    normalize_sections_for_contract,
    record_evidence_item,
    resolve_embedder,
)
from .manager import ReportManager
from .planning import plan_outline as plan_outline_impl
from .schemas import CURRENT_SCHEMA_VERSION, EvidenceMapModel
from .sections import (
    attach_provenance,
    atomize_claim_chunk,
    build_source_id_anchor,
    is_atomic_claim,
    is_claim_candidate,
    sample_actions_timeseries,
    section_dedup_check,
    truncate_text,
)
from ..web_tools import WebToolsService
from ...utils.logger import get_logger
from ...models.report import (
    EvidenceItem,
    Report,
    ReportClaim,
    ReportOutline,
    ReportSection,
)
from ..report_logger import ReportLogger, ReportConsoleLogger
from ..tool_validation import VALID_TOOL_NAMES  # noqa: F401  # re-exported for backwards-compat
from .tools import (
    describe_tools,
    define_tools,
    execute_tool_call,
    get_openai_tools_schema,
    is_valid_tool_call,
    parse_tool_calls,
)
from .workflow import chat as chat_impl, generate_report as generate_report_impl, generate_section_react as generate_section_react_impl
from .prompts import (
    CHAT_OBSERVATION_SUFFIX,
    CHAT_SYSTEM_PROMPT_TEMPLATE,
    REACT_FORCE_FINAL_MSG,
    REACT_INSUFFICIENT_TOOLS_MSG,
    REACT_INSUFFICIENT_TOOLS_MSG_ALT,
    REACT_OBSERVATION_TEMPLATE,
    REACT_TOOL_LIMIT_MSG,
    REACT_UNUSED_TOOLS_HINT,
    SECTION_SYSTEM_PROMPT_TEMPLATE,
    SECTION_USER_PROMPT_TEMPLATE,
)
from ..graph_tools import (
    GraphToolsService,
    SearchResult,
    InsightForgeResult,
    PanoramaResult,
    InterviewResult
)

logger = get_logger('agora.report_agent')

# S5: diese Item-Typen sind Modell-Output, keine Evidence. Sie dürfen
# nicht im `evidence`-Array eines Claims stehen, sondern im separaten
# `audit_trail`-Feld.
FORBIDDEN_EVIDENCE_TYPES = frozenset({
    "model_generated_inference",
    "section_synthesis",
})


class ReportAgent:
    """Simulation report generation agent."""
    
    # Maximum tool call count (per section)
    MAX_TOOL_CALLS_PER_SECTION = 5

    # Maximum reflection rounds
    MAX_REFLECTION_ROUNDS = 3

    # Maximum tool call count in conversation
    MAX_TOOL_CALLS_PER_CHAT = 2

    ReportLogger = ReportLogger
    ReportConsoleLogger = ReportConsoleLogger

    SECTION_SYSTEM_PROMPT_TEMPLATE = SECTION_SYSTEM_PROMPT_TEMPLATE
    SECTION_USER_PROMPT_TEMPLATE = SECTION_USER_PROMPT_TEMPLATE
    REACT_OBSERVATION_TEMPLATE = REACT_OBSERVATION_TEMPLATE
    REACT_INSUFFICIENT_TOOLS_MSG = REACT_INSUFFICIENT_TOOLS_MSG
    REACT_INSUFFICIENT_TOOLS_MSG_ALT = REACT_INSUFFICIENT_TOOLS_MSG_ALT
    REACT_TOOL_LIMIT_MSG = REACT_TOOL_LIMIT_MSG
    REACT_UNUSED_TOOLS_HINT = REACT_UNUSED_TOOLS_HINT
    REACT_FORCE_FINAL_MSG = REACT_FORCE_FINAL_MSG
    CHAT_SYSTEM_PROMPT_TEMPLATE = CHAT_SYSTEM_PROMPT_TEMPLATE
    CHAT_OBSERVATION_SUFFIX = CHAT_OBSERVATION_SUFFIX
    
    def __init__(
        self,
        graph_id: str,
        simulation_id: str,
        simulation_requirement: str,
        llm_client: Optional[LLMClient] = None,
        graph_tools: Optional[GraphToolsService] = None,
        model_name: Optional[str] = None,
    ):
        """
        Initialize Report Agent

        Args:
            graph_id: Graph ID
            simulation_id: Simulation ID
            simulation_requirement: Simulation requirement description
            llm_client: LLM client (optional — overrides model_name if given)
            graph_tools: Graph tools service (optional, requires external GraphStorage injection)
            model_name: per-report model override (e.g. "deepseek-v3.2:cloud")
        """
        self.graph_id = graph_id
        self.simulation_id = simulation_id
        self.simulation_requirement = simulation_requirement

        if llm_client is not None:
            self.llm = llm_client
        else:
            self.llm = LLMClient(model=model_name) if model_name else LLMClient()

        # Optional live-web tools (Tavily). Disabled silently when no API key.
        self.web_tools = WebToolsService()
        if graph_tools is None:
            raise ValueError(
                "graph_tools (GraphToolsService) is required. "
                "Create it via GraphToolsService(storage=...) and pass it in."
            )
        self.graph_tools = graph_tools
        
        # Tool definitions
        self.tools = self._define_tools()

        # Logger (initialized in generate_report)
        self.report_logger: Optional[ReportLogger] = None
        # Console logger (initialized in generate_report)
        self.console_logger: Optional[ReportConsoleLogger] = None
        self.evidence_map: Optional[Dict[str, Any]] = None
        self._active_section_evidence: List[Dict[str, Any]] = []
        self._current_section_index: Optional[int] = None

        logger.info(f"ReportAgent initialization complete: graph_id={graph_id}, simulation_id={simulation_id}")

    def _init_evidence_map(self, report_id: str) -> None:
        self.evidence_map = init_evidence_map(
            report_id=report_id,
            simulation_id=self.simulation_id,
            global_evidence=self._collect_simulation_evidence_items(),
        )

    def _truncate(self, text: str, limit: int = 300) -> str:
        return truncate_text(text, limit)

    def _record_evidence_item(self, item: Dict[str, Any]) -> None:
        self._active_section_evidence = record_evidence_item(
            self._active_section_evidence,
            item,
        )

    def _try_get_embedder(self) -> Optional[Callable[[str], List[float]]]:
        cached = getattr(self, "_embed_cache", "missing")
        embed_fn = resolve_embedder(cached=cached, logger=logger)
        self._embed_cache = embed_fn
        return embed_fn

    @staticmethod
    def _sample_actions_timeseries(
        actions: List[Dict[str, Any]], k: int = 8
    ) -> List[Dict[str, Any]]:
        return sample_actions_timeseries(actions, k)

    def _collect_simulation_evidence_items(self) -> List[Dict[str, Any]]:
        """Collect reusable evidence from existing metrics and simulation actions."""
        try:
            from ..network_analytics import NetworkAnalyticsService
            from ..simulation_runner import SimulationRunner

            actions = SimulationRunner.get_all_actions(self.simulation_id)
            action_dicts = [action.to_dict() for action in actions]
            if not action_dicts:
                return []

            metrics = NetworkAnalyticsService().compute_metrics(
                action_dicts,
                simulation_id=self.simulation_id,
            ).to_dict()
            items: List[Dict[str, Any]] = []
            # S2b: Wenn der Snapshot keinen "ok"-Status hat (z. B. Broadcast-
            # only-Run ohne pairwise Interactions), keine 0er Pseudo-Metriken
            # als Evidence ausweisen. Stattdessen ein einzelnes Status-Item
            # mit klarer Aussage anhängen, damit der Audit-Trail nicht ganz
            # leer ist.
            if metrics.get("status") != "ok":
                items.append(EvidenceItem(
                    type="graph_metric_status",
                    source="simulation_metrics",
                    value=f"status={metrics.get('status')}",
                    snippet=(
                        f"Polarization-Metriken nicht verfügbar "
                        f"(Status: {metrics.get('status')})"
                    ),
                    raw={"metrics": metrics},
                ).to_dict())
            else:
                metric_fields = (
                    "echo_chamber_index",
                    "cluster_count",
                    "total_interactions",
                    "bridge_agents",
                )
                for field in metric_fields:
                    value = metrics.get(field)
                    if value in (None, [], ""):
                        continue
                    items.append(EvidenceItem(
                        type="graph_metric",
                        source="simulation_metrics",
                        value=f"{field}={value}",
                        snippet=f"{field}: {value}",
                        raw={"metric": field, "value": value, "metrics": metrics},
                    ).to_dict())

            sampled_actions = self._sample_actions_timeseries(action_dicts, k=8)
            for action in sampled_actions:
                action_type = action.get("action_type") or "action"
                agent = action.get("agent_name") or f"Agent {action.get('agent_id')}"
                platform = action.get("platform") or "unknown"
                round_num = action.get("round_num")
                items.append(EvidenceItem(
                    type="agent_action",
                    source="simulation_actions",
                    value=action_type,
                    snippet=f"{agent} {action_type} on {platform} in round {round_num}",
                    raw=action,
                ).to_dict())
            return items
        except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
            logger.warning(f"Failed to collect simulation evidence: {exc}")
            return []

    def _record_tool_evidence(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        structured_result: Any,
        rendered_result: str,
        section_index: int,
    ) -> None:
        items: List[Dict[str, Any]] = []
        if isinstance(structured_result, InsightForgeResult):
            for fact in structured_result.semantic_facts[:10]:
                items.append({
                    "type": "graph_fact",
                    "tool_name": tool_name,
                    "query": structured_result.query,
                    "snippet": self._truncate(fact),
                    "raw": fact,
                    "agent_log_ref": {"section_index": section_index, "action": "tool_result", "tool_name": tool_name},
                })
            for entity in structured_result.entity_insights[:8]:
                items.append({
                    "type": "entity_summary",
                    "tool_name": tool_name,
                    "query": structured_result.query,
                    "snippet": self._truncate(entity.get("summary") or entity.get("name")),
                    "raw": entity,
                    "agent_log_ref": {"section_index": section_index, "action": "tool_result", "tool_name": tool_name},
                })
            for chain in structured_result.relationship_chains[:8]:
                items.append({
                    "type": "relationship_chain",
                    "tool_name": tool_name,
                    "query": structured_result.query,
                    "snippet": self._truncate(chain),
                    "raw": chain,
                    "agent_log_ref": {"section_index": section_index, "action": "tool_result", "tool_name": tool_name},
                })
        elif isinstance(structured_result, PanoramaResult):
            for fact in structured_result.active_facts[:10]:
                items.append({
                    "type": "graph_fact",
                    "tool_name": tool_name,
                    "query": structured_result.query,
                    "snippet": self._truncate(fact),
                    "raw": fact,
                    "agent_log_ref": {"section_index": section_index, "action": "tool_result", "tool_name": tool_name},
                })
            for fact in structured_result.historical_facts[:6]:
                items.append({
                    "type": "graph_fact",
                    "tool_name": tool_name,
                    "query": structured_result.query,
                    "snippet": self._truncate(fact),
                    "raw": fact,
                    "agent_log_ref": {"section_index": section_index, "action": "tool_result", "tool_name": tool_name},
                })
        elif isinstance(structured_result, SearchResult):
            for fact in structured_result.facts[:10]:
                items.append({
                    "type": "graph_fact",
                    "tool_name": tool_name,
                    "query": structured_result.query,
                    "snippet": self._truncate(fact),
                    "raw": fact,
                    "agent_log_ref": {"section_index": section_index, "action": "tool_result", "tool_name": tool_name},
                })
        elif isinstance(structured_result, InterviewResult):
            for interview in structured_result.interviews[:6]:
                items.append({
                    "type": "agent_interview",
                    "tool_name": tool_name,
                    "query": structured_result.interview_topic,
                    "snippet": self._truncate(interview.response),
                    "raw": interview.to_dict(),
                    "agent_log_ref": {"section_index": section_index, "action": "tool_result", "tool_name": tool_name},
                })
        elif isinstance(structured_result, dict) and "results" in structured_result:
            for result in (structured_result.get("results") or [])[:8]:
                items.append({
                    "type": "web_search_result",
                    "tool_name": tool_name,
                    "query": structured_result.get("query") or parameters.get("query"),
                    "snippet": self._truncate(result.get("content") or result.get("title")),
                    "raw": result,
                    "agent_log_ref": {"section_index": section_index, "action": "tool_result", "tool_name": tool_name},
                })
        elif isinstance(structured_result, dict) and "url" in structured_result:
            items.append({
                "type": "web_fetch",
                "tool_name": tool_name,
                "query": structured_result.get("url"),
                "snippet": self._truncate(structured_result.get("content") or structured_result.get("title")),
                "raw": structured_result,
                "agent_log_ref": {"section_index": section_index, "action": "tool_result", "tool_name": tool_name},
            })

        if not items and rendered_result:
            items.append({
                "type": "model_generated_inference",
                "source": "report_tool",
                "tool_name": tool_name,
                "query": parameters.get("query") or parameters.get("url") or parameters.get("interview_topic"),
                "snippet": self._truncate(rendered_result),
                "raw": rendered_result,
                "agent_log_ref": {"section_index": section_index, "action": "tool_result", "tool_name": tool_name},
            })

        for item in items:
            item.setdefault("source", "report_tool")
            self._record_evidence_item(item)

    @staticmethod
    def _atomize_claim_chunk(chunk: str) -> List[str]:
        return atomize_claim_chunk(chunk)

    @staticmethod
    def _is_atomic_claim(text: str) -> bool:
        return is_atomic_claim(text)

    @staticmethod
    def _is_claim_candidate(text: str) -> bool:
        return is_claim_candidate(text)

    @staticmethod
    def _build_source_id_anchor(item: Dict[str, Any]) -> Optional[str]:
        return build_source_id_anchor(item)

    @staticmethod
    def _attach_provenance(item: Dict[str, Any]) -> Dict[str, Any]:
        return attach_provenance(item)

    def _build_claims_for_section(self, content: str) -> List[Dict[str, Any]]:
        raw_chunks = [part.strip() for part in re.split(r"\n\s*\n", (content or "").strip()) if part.strip()]
        # S3a: Strukturmarkup (Header, Bold-Section-Titel) verwerfen.
        chunks = [c for c in raw_chunks if self._is_claim_candidate(c)]
        # S3b: Mehrsatz-Chunks in atomare Aussagen splitten und Übergangs-
        # sätze ohne prüfbare Substanz verwerfen. Fallback: wenn nichts den
        # Atom-Filter passiert, behält der Chunk einen Eintrag (sonst gehen
        # legitime Single-Sentence-Sections verloren).
        atomic_chunks: List[str] = []
        for chunk in chunks:
            atoms = [a for a in self._atomize_claim_chunk(chunk) if self._is_atomic_claim(a)]
            atomic_chunks.extend(atoms or [chunk])
        chunks = atomic_chunks
        claims = []
        global_items = deepcopy((self.evidence_map or {}).get("global_evidence", [])[:6])
        # S4b: claim-spezifisches Binding wenn ein Embedder verfügbar ist.
        # S5: model_generated_inference und section_synthesis sind keine
        # Evidence — sie sind Modell-Output. Sie wandern in das separate
        # `audit_trail`-Feld der Claim-Dataclass, nicht ins `evidence`-Array.
        embedder = self._try_get_embedder()
        for index, chunk in enumerate(chunks, 1):
            direct_items = [
                deepcopy(item) for item in self._active_section_evidence[:10]
                if item.get("type") not in FORBIDDEN_EVIDENCE_TYPES
            ]
            audit_trail = [
                EvidenceItem(
                    type="model_generated_inference",
                    source="section_synthesis",
                    tool_name="section_synthesis",
                    snippet=self._truncate(chunk),
                    raw={"content": chunk},
                ).to_dict()
            ]

            bound: List[Dict[str, Any]] = []
            embedder_ok = False
            if embedder is not None:
                try:
                    bound = bind_evidence_to_claim(
                        chunk,
                        direct_items + global_items,
                        embedder,
                        threshold=0.55,
                        top_k=5,
                    )
                    embedder_ok = True
                except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
                    logger.warning(
                        f"EvidenceBinder failed, falling back to generic pool: {exc!r}"
                    )
                    self._embed_cache = None
                    embedder = None
            if embedder_ok:
                evidence_items = bound
                direct_count = len(bound)
            else:
                evidence_items = direct_items
                direct_count = len(direct_items)

            # Layer 3 (Task 12): Provenance-Anker an jedes Evidence-Item heften.
            evidence_items = [self._attach_provenance(it) for it in evidence_items]

            # S6: formelbasierte Confidence statt linear-in-N. Berechnet
            # aus relevance (mean match_score), source_quality (Typ-
            # Gewichtung), specificity (top match_score), consistency
            # (Anzahl unique Quellen). Verified-Label nur bei Top-
            # Match-Score >= 0.85.
            penalty = detect_contradiction_penalty(evidence_items)
            confidence_score, confidence_label = compute_confidence(
                evidence_items,
                contradiction_penalty=penalty,
            )
            if penalty > 0.0:
                audit_trail.append({
                    "type": "contradiction_penalty_applied",
                    "value": penalty,
                    "source": "evidence_binder.detect_contradiction_penalty",
                })
            # Anti-Dekorations-Guard: kein Evidence → ehrliches speculative-Label
            # und Audit-Eintrag statt dekorativem global_items-Fallback.
            if not evidence_items:
                confidence_score, confidence_label = 0.15, "speculative"
                audit_trail.append({
                    "type": "model_generated_inference",
                    "source": "validator",
                    "tool_name": "evidence_validator",
                    "snippet": "no_direct_evidence_bound",
                    "raw": {"reason": "no_direct_evidence_bound"},
                })
            # Hinweis fürs Test-Backwards-Compat: support_count wird nicht
            # mehr genutzt, bleibt aber lokal für ggf. Logging.
            support_count = direct_count + len(global_items)  # noqa: F841
            claim_dict = ReportClaim(
                claim_id=f"claim_{index:02d}",
                claim_text=chunk,
                evidence=evidence_items,
                confidence_score=confidence_score,
                confidence_label=confidence_label,
                notes="Section-chunk level evidence mapping (schema_version 2).",
            ).to_dict()
            claim_dict["audit_trail"] = audit_trail
            claims.append(claim_dict)
        if not claims:
            claims.append(ReportClaim(
                claim_id="claim_01",
                claim_text="No claim candidate extracted from this section.",
                evidence=[],
                confidence_score=0.0,
                confidence_label="speculative",
                notes="No section content captured.",
            ).to_dict())
        return claims

    @staticmethod
    def _suggested_evidence_from_claim_audit(claim: Dict[str, Any]) -> List[str]:
        suggestions: List[str] = []
        for entry in claim.get("audit_trail") or []:
            if not isinstance(entry, dict):
                continue
            reason = entry.get("snippet") or entry.get("source") or entry.get("type")
            if reason == "no_direct_evidence_bound":
                suggestions.append("Direkte Evidence per Graph- oder Agent-Tool nachreichen.")
            elif reason:
                suggestions.append(str(reason)[:200])
        return suggestions[:5] or ["Direkte Evidence per Graph- oder Agent-Tool nachreichen."]

    def _finalize_section_claims(
        self,
        claims: List[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        finalized_claims: List[Dict[str, Any]] = []
        hypotheses: List[Dict[str, Any]] = []
        data_gaps: List[Dict[str, Any]] = []

        from app.contracts.report_v3 import CLAIM_MIN_EVIDENCE_FOR_CLAIM  # noqa: PLC0415

        for claim in normalize_claims_for_contract(claims):
            evidence = claim.get("evidence") or []
            score = float(claim.get("confidence_score") or 0.0)
            label = str(claim.get("confidence_label") or "").lower()

            # Reviewer-Floor (report_4fe2dacd80ba, Sub-Slice S1):
            # Claim braucht ≥2 unabhängige Evidence-Items, sonst Routing zur Hypothesis.
            # evidence_count==0 fällt durch zum Bestands-Low-Confidence-Branch (mit data_gap).
            evidence_count = len(evidence) or len(claim.get("evidence_refs") or [])
            if 0 < evidence_count < CLAIM_MIN_EVIDENCE_FOR_CLAIM:
                index = len(hypotheses) + 1
                claim_text = (
                    str(claim.get("claim_text") or claim.get("claim") or "").strip()
                    or "No evidence-bound claim text available."
                )
                claim_text = self._truncate(claim_text, 1000)
                hypotheses.append({
                    "hypothesis_id": f"hypothesis_{index:02d}",
                    "hypothesis_text": claim_text,
                    "rationale": (
                        f"Reviewer-Floor: nur {evidence_count} von "
                        f"{CLAIM_MIN_EVIDENCE_FOR_CLAIM} geforderten Evidence-Items "
                        "— als Hypothese geführt."
                    ),
                    "suggested_evidence": [],
                })
                continue

            if not evidence and score < 0.4:
                # Low-confidence ohne Evidence → hypothesis + data_gap
                index = len(hypotheses) + 1
                claim_text = (
                    str(claim.get("claim_text") or claim.get("claim") or "").strip()
                    or "No evidence-bound claim text available."
                )
                claim_text = self._truncate(claim_text, 1000)
                suggestions = self._suggested_evidence_from_claim_audit(claim)
                hypotheses.append({
                    "hypothesis_id": f"hypothesis_{index:02d}",
                    "hypothesis_text": claim_text,
                    "rationale": (
                        "Keine direkte Evidence gebunden; deshalb nicht als "
                        "validierter Claim persistiert."
                    ),
                    "suggested_evidence": suggestions,
                })
                data_gaps.append({
                    "gap_id": f"gap_{index:02d}",
                    "claim_text": claim_text,
                    "gap_reason": "no_evidence_bound",
                    "suggested_fix": suggestions[0],
                })
                continue
            if not evidence and label in ("medium", "high", "verified"):
                # P2.1: medium/high/verified ohne Evidence darf nicht in claims[]
                # (würde ReportClaimModel-Validator verletzen). Stattdessen data_gap.
                index = len(data_gaps) + 1
                claim_text = (
                    str(claim.get("claim_text") or claim.get("claim") or "").strip()
                    or "No evidence-bound claim text available."
                )
                claim_text = self._truncate(claim_text, 1000)
                suggestions = self._suggested_evidence_from_claim_audit(claim)
                data_gaps.append({
                    "gap_id": f"gap_{index:02d}",
                    "claim_text": claim_text,
                    "gap_reason": "no_evidence_bound",
                    "suggested_fix": suggestions[0] if suggestions else None,
                })
                continue
            finalized_claims.append(claim)

        return finalized_claims, hypotheses, data_gaps

    def _section_dedup_check(
        self, new_summary: str, existing: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        return section_dedup_check(
            new_summary,
            existing,
            get_embedder=self._try_get_embedder,
            logger=logger,
        )

    def _save_evidence_section(self, report_id: str, section_index: int, section_title: str, content: str) -> None:
        if self.evidence_map is None:
            self._init_evidence_map(report_id)
        self.evidence_map.setdefault("schema_version", CURRENT_SCHEMA_VERSION)
        self.evidence_map.setdefault("global_evidence", self._collect_simulation_evidence_items())
        # schema_version gehört nur auf Map-Ebene, nicht auf Section-Ebene
        # (ReportSectionModel hat das Feld nicht).
        claims, raw_hypotheses, data_gaps = self._finalize_section_claims(
            self._build_claims_for_section(content)
        )
        # Slice 3 (Issue #495): Dedup + Cap per Section.
        from .hypothesis_cap import dedup_and_cap_hypotheses  # noqa: PLC0415
        hypotheses_visible, hypotheses_appendix = dedup_and_cap_hypotheses(raw_hypotheses)
        section_entry = {
            "section_index": section_index,
            "section_title": section_title,
            "section_summary": self._truncate(content, 400),
            "claims": claims,
            "hypotheses": hypotheses_visible,
            "hypotheses_appendix": hypotheses_appendix,
            "data_gaps": data_gaps,
        }
        # schema_version auf Section-Ebene entfernen — Überbleibsel von
        # migrate_v1_to_v2 oder alten Persistierungen; ReportSectionModel
        # erlaubt das Feld nicht (extra="forbid").
        existing_sections = normalize_sections_for_contract([
            s for s in self.evidence_map["sections"]
            if s.get("section_index") != section_index
        ])
        # Reader Honesty: Section-Dedup — Duplikat-Marker im audit_trail ablegen,
        # Section selbst nicht droppen (Frontend entscheidet).
        dedup_marker = self._section_dedup_check(
            new_summary=section_title or content[:200],
            existing=existing_sections,
        )
        if dedup_marker is not None:
            claims = section_entry.get("claims") or []
            if claims:
                claims[0].setdefault("audit_trail", []).append(dedup_marker)
        existing_sections.append(section_entry)
        existing_sections.sort(key=lambda item: item.get("section_index", 0))
        # Layer-0 Boundary: vor dem Persistieren auto-downgrade'n und gegen
        # EvidenceMapModel validieren. ``normalize_sections_for_contract``
        # senkt confidence_label='high'/'verified' auf 'medium', wenn die
        # ADR-0002-Cross-Stakeholder-Anforderung nicht erfüllt ist
        # (Smoke-Live 2026-05-15). Der Validator bleibt strikt.
        self.evidence_map["sections"] = normalize_sections_for_contract(
            existing_sections, logger=logger,
        )
        validated = EvidenceMapModel.model_validate(self.evidence_map).model_dump(mode="json")
        self.evidence_map = validated
        ReportManager.save_evidence_map(report_id, validated)
    
    def _define_tools(self) -> Dict[str, Dict[str, Any]]:
        return define_tools(self)

    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        return execute_tool_call(self, tool_name, parameters, report_context=report_context)

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        return parse_tool_calls(response)

    def _is_valid_tool_call(self, data: dict) -> bool:
        return is_valid_tool_call(data)

    def _get_tools_description(self) -> str:
        return describe_tools(self.tools)

    def _get_openai_tools_schema(self) -> List[Dict[str, Any]]:
        """Liefert die Tool-Definitionen im OpenAI function-calling Format."""
        return get_openai_tools_schema(self)

    def plan_outline(
        self,
        progress_callback: Optional[Callable] = None,
        required_sections: Optional[list[tuple[str, str]]] = None,
    ) -> ReportOutline:
        return plan_outline_impl(
            self,
            progress_callback=progress_callback,
            required_sections=required_sections,
        )

    def _generate_section_react(
        self,
        section: ReportSection,
        outline: ReportOutline,
        previous_sections: List[str],
        progress_callback: Optional[Callable] = None,
        section_index: int = 0
    ) -> str:
        return generate_section_react_impl(
            self,
            section=section,
            outline=outline,
            previous_sections=previous_sections,
            progress_callback=progress_callback,
            section_index=section_index,
        )

    def generate_report(
        self,
        progress_callback: Optional[Callable[[str, int, str], None]] = None,
        report_id: Optional[str] = None,
        *,
        report_mode: str = "balanced",
    ) -> Report:
        return generate_report_impl(self, progress_callback=progress_callback, report_id=report_id, report_mode=report_mode)  # type: ignore[arg-type]

    def chat(
        self,
        message: str,
        chat_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        return chat_impl(self, message=message, chat_history=chat_history)
