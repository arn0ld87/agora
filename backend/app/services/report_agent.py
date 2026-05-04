"""
Report Agent Service
Generate simulated reports using ReACT pattern (via GraphStorage / Neo4j)

Features:
1. Generate reports based on simulation requirements and graph information
2. First plan the outline structure, then generate section by section
3. Each section uses ReACT multi-round thinking and reflection pattern
4. Support conversations with users, autonomously call retrieval tools during conversations
"""

import os
import json
import re
import tempfile
from copy import deepcopy
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime

from ..config import Config
from ..utils.llm_client import LLMClient
from .confidence_calculator import compute_confidence
from .evidence_binder import bind_evidence_to_claim, detect_contradiction_penalty
from .evidence_migrations import CURRENT_SCHEMA_VERSION, migrate_v1_to_v2
from ..contracts import EvidenceMapModel
from ..contracts.report_contract import ReportOutlineModel, ReportOutlineSectionModel
from .web_tools import WebToolsService
from ..utils.logger import get_logger
from ..models.report import (
    EvidenceItem,
    Report,
    ReportClaim,
    ReportOutline,
    ReportSection,
    ReportStatus,
)
from .report_logger import ReportLogger, ReportConsoleLogger
from .tool_schema import (
    TOOL_DESC_INSIGHT_FORGE,
    TOOL_DESC_PANORAMA_SEARCH,
    TOOL_DESC_QUICK_SEARCH,
    TOOL_DESC_INTERVIEW_AGENTS,
)
from .tool_validation import (
    VALID_TOOL_NAMES,  # noqa: F401  # re-exported for backwards-compat
    is_valid_tool_call,
    parse_tool_calls,
)
from .tool_execution import execute_tool
from .report_prompts import (
    PLAN_SYSTEM_PROMPT_TEMPLATE,
    PLAN_USER_PROMPT_TEMPLATE,
    SECTION_SYSTEM_PROMPT_TEMPLATE,
    SECTION_USER_PROMPT_TEMPLATE,
    REACT_OBSERVATION_TEMPLATE,
    REACT_INSUFFICIENT_TOOLS_MSG,
    REACT_INSUFFICIENT_TOOLS_MSG_ALT,
    REACT_TOOL_LIMIT_MSG,
    REACT_UNUSED_TOOLS_HINT,
    REACT_FORCE_FINAL_MSG,
    CHAT_SYSTEM_PROMPT_TEMPLATE,
    CHAT_OBSERVATION_SUFFIX,
)
from .graph_tools import (
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


# ReportLogger and ReportConsoleLogger live in services/report_logger.py
# (Issue #46) and are re-exported above so existing call sites in this
# module keep working unchanged.

# Models live in ``app/models/report.py`` (Issue #45) and are re-exported above
# so existing callers (``api/report.py``, ``api/runs.py``, tests) keep working
# unchanged.


# ═══════════════════════════════════════════════════════════════
# Prompt Template Constants
# ═══════════════════════════════════════════════════════════════

# ── Tool Descriptions ──
# TOOL_DESC_* leben in services/tool_schema.py (Issue #47) und werden oben
# re-exportiert, damit das Tool-Registry-Dict in `_define_tools` und
# externe Aufrufstellen unverändert bleiben.

# Prompt-Templates leben in services/report_prompts.py (Issue #48) und
# werden oben re-exportiert, damit alle bestehenden Aufrufstellen
# (plan_outline, _generate_section, _run_react_loop, chat_with_report)
# unverändert bleiben.


# ═══════════════════════════════════════════════════════════════
# ReportAgent Main Class
# ═══════════════════════════════════════════════════════════════


class ReportAgent:
    """
    Report Agent - Simulation Report Generation Agent

    Uses ReACT (Reasoning + Acting) pattern:
    1. Planning Phase: Analyze simulation requirements, plan report outline structure
    2. Generation Phase: Generate content section by section, each section can call tools multiple times to get information
    3. Reflection Phase: Check content completeness and accuracy
    """
    
    # Maximum tool call count (per section)
    MAX_TOOL_CALLS_PER_SECTION = 5

    # Maximum reflection rounds
    MAX_REFLECTION_ROUNDS = 3

    # Maximum tool call count in conversation
    MAX_TOOL_CALLS_PER_CHAT = 2
    
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
        # S4b: schema_version 2 markiert claim-spezifisches Evidence-Binding.
        # v1-Reports bleiben lesbar, neue Reports tragen den v2-Tag und
        # zusätzliche Felder (`match_score`, `supports_claim`).
        # Layer-0 Boundary: EvidenceMapModel validiert das Dict beim Anlegen.
        payload = {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "report_id": report_id,
            "simulation_id": self.simulation_id,
            "global_evidence": self._collect_simulation_evidence_items(),
            "sections": [],
        }
        self.evidence_map = EvidenceMapModel.model_validate(payload).model_dump(mode="json")

    def _truncate(self, text: str, limit: int = 300) -> str:
        if not text:
            return ""
        text = str(text).strip()
        return text if len(text) <= limit else text[:limit] + "..."

    def _record_evidence_item(self, item: Dict[str, Any]) -> None:
        if not self._active_section_evidence:
            self._active_section_evidence = []
        self._active_section_evidence.append(item)

    def _try_get_embedder(self) -> Optional[Callable[[str], List[float]]]:
        """S4b: liefert eine `embed(text) -> Vector`-Callable oder None.

        Lazy-import von ``EmbeddingService`` damit Tests, die den
        ReportAgent ohne lebenden Storage instanziieren, nicht durch
        Ollama-Init scheitern. Cache: einmal pro Agent-Instanz.
        """
        cached = getattr(self, "_embed_cache", "missing")
        if cached != "missing":
            return cached
        try:
            from ..storage.embedding_service import EmbeddingService

            service = EmbeddingService()
            embed_fn = service.embed
        except Exception as exc:  # pragma: no cover - environment dependent
            logger.debug(f"EvidenceBinder: kein Embedder verfügbar ({exc!r})")
            embed_fn = None
        self._embed_cache = embed_fn
        return embed_fn

    @staticmethod
    def _sample_actions_timeseries(
        actions: List[Dict[str, Any]], k: int = 8
    ) -> List[Dict[str, Any]]:
        """Stratified Sampling ueber round_num (oder created_at als Fallback).

        - len(actions) <= k: alle behalten, KEIN Sampling-Marker im raw.
        - len(actions) > k: k gleichgrosse Bins ueber den Sortier-Schluessel,
          aus jedem Bin das chronologisch erste Item. Falls round_num fehlt,
          fallback auf Index-Reihenfolge (also stratified ueber Position).

        Reader Honesty: Burst-Verzerrung verhindern, ohne Posts zu droppen
        die einen einzelnen Bin dominieren.
        """
        if not actions:
            return []
        if len(actions) <= k:
            return list(actions)

        def sort_key(a: Dict[str, Any]) -> Any:
            r = a.get("round_num")
            if r is not None:
                return (0, r, str(a.get("action_id") or a.get("id") or ""))
            ts = a.get("created_at") or a.get("timestamp")
            if ts is not None:
                return (1, str(ts), "")
            return (2, 0, "")

        sorted_actions = sorted(actions, key=sort_key)
        n = len(sorted_actions)
        sampled: List[Dict[str, Any]] = []
        for bin_idx in range(k):
            start = (bin_idx * n) // k
            end = ((bin_idx + 1) * n) // k
            if start >= end:
                continue
            picked = sorted_actions[start]
            picked = dict(picked)  # shallow copy, ohne Original zu mutieren
            raw_marker = picked.setdefault("_sampling", {})
            raw_marker["bin"] = bin_idx
            raw_marker["bin_total"] = k
            raw_marker["sampled_from_total"] = n
            sampled.append(picked)
        return sampled

    def _collect_simulation_evidence_items(self) -> List[Dict[str, Any]]:
        """Collect reusable evidence from existing metrics and simulation actions."""
        try:
            from .network_analytics import NetworkAnalyticsService
            from .simulation_runner import SimulationRunner

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
        except Exception as exc:
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
        """S3b: Section-Chunk in Einzelsätze splitten.

        Reviewer hatte gefordert: ein Claim = eine prüfbare Aussage.
        Mehrsatz-Chunks werden in atomare Sätze zerlegt; Trennung über
        Satzendzeichen + Großbuchstaben-Folgewort. Reicht für DACH-
        Reports ohne neue NLP-Dependency.
        """
        cleaned = (chunk or "").strip()
        if not cleaned:
            return []
        # Lookbehind verlangt einen *Buchstaben* vor dem Satzende-Zeichen,
        # damit Datums-/Zahlen-Punkte ("am 22. Mai") und einzelne
        # Initialen-Punkte nicht fälschlich als Satzgrenze gewertet werden.
        parts = re.split(r"(?<=[a-zäöüß][.!?])\s+(?=[A-ZÄÖÜ])", cleaned)
        return [p.strip() for p in parts if p.strip()]

    # S3b-Verbliste — finite Verben, die typische Aussagen einleiten.
    # Bewusst klein gehalten; größere NER-Listen würden falsch-negative
    # Filter erzeugen, der Filter soll nur grobe Übergangssätze killen.
    _CLAIM_VERB_HINTS = (
        " ist ", " sind ", " war ", " waren ", " wird ", " werden ",
        " soll ", " sollen ", " kann ", " können ", " muss ", " müssen ",
        " hat ", " haben ", " erklärt", " fordert", " kritisiert",
        " betont", " sagt", " warnt", " beschloss", " plant",
        " antwortete", " unterstützt",
    )

    @staticmethod
    def _is_atomic_claim(text: str) -> bool:
        """S3b: Atom-Satz-Filter — verlangt minimale Aussage-Substanz."""
        s = (text or "").strip()
        if len(s.split()) < 5:
            return False
        if s.endswith((".", "!", "?")):
            return True
        return any(hint in s.lower() for hint in ReportAgent._CLAIM_VERB_HINTS)

    @staticmethod
    def _is_claim_candidate(text: str) -> bool:
        """S3a: filtert Markdown-Header, Bold-Section-Titel, leere Stellen.

        Externer Review hatte beanstandet, dass Überschriften wie
        ``**Der Beschluss und seine Architekten**`` als prüfbare Claims
        in der Evidence-Map landen. Eine Überschrift ist kein Claim,
        sondern Strukturmarkup. Dieser Filter wirft sie raus, bevor
        Evidence gebunden wird.
        """
        stripped = (text or "").strip()
        if not stripped:
            return False
        if stripped.startswith("#"):
            return False
        # Reine Bold-Zeile als Section-Title (kürzer als 8 Wörter).
        if (
            stripped.startswith("**")
            and stripped.endswith("**")
            and stripped.count("**") == 2
            and len(stripped.split()) < 8
        ):
            return False
        # Single-bullet bold-only-Heading (`- **Was passiert ist**`).
        if re.fullmatch(r"[-*]\s*\*\*[^*]+\*\*\s*", stripped):
            return False
        return True

    @staticmethod
    def _build_source_id_anchor(item: Dict[str, Any]) -> Optional[str]:
        """Leite einen stabilen Anker fuer das Frontend ab.
        Reihenfolge: agent_log_ref > raw['url'] > None.
        """
        ref = item.get("agent_log_ref") or {}
        if isinstance(ref, dict):
            log_id = ref.get("agent_log_id") or ref.get("log_id")
            entry = ref.get("entry_id") or ref.get("post_id")
            if log_id and entry:
                return f"agent-log-{log_id}#entry-{entry}"
            if log_id:
                return f"agent-log-{log_id}"
        raw = item.get("raw") or {}
        if isinstance(raw, dict):
            url = raw.get("url") or raw.get("source_url")
            text = raw.get("text") or raw.get("content") or item.get("snippet") or ""
            if url:
                # Word-prefix fuer text-fragment, max 60 chars, urlsafe genug
                if text:
                    fragment = text.strip().split("\n", 1)[0][:60]
                    return f"web:{url}#:~:text={fragment}"
                return f"web:{url}"
        return None

    @staticmethod
    def _attach_provenance(item: Dict[str, Any]) -> Dict[str, Any]:
        """Idempotenter Mutator: setzt quote + source_id_anchor wenn ableitbar.
        Existierende Werte werden NICHT ueberschrieben.
        """
        if not isinstance(item, dict):
            return item
        # quote: bevorzugt raw['text'] / raw['content'], sonst snippet selbst
        if not item.get("quote"):
            raw = item.get("raw") or {}
            candidate = None
            if isinstance(raw, dict):
                candidate = raw.get("text") or raw.get("content")
            candidate = candidate or item.get("snippet")
            if candidate:
                quote = str(candidate).strip()
                if quote:
                    item["quote"] = quote[:500]
        # source_id_anchor
        if not item.get("source_id_anchor"):
            anchor = ReportAgent._build_source_id_anchor(item)
            if anchor:
                item["source_id_anchor"] = anchor[:200]
        return item

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
                except Exception as exc:
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
            # Anti-Dekorations-Guard: kein Evidence → ehrliches low-Label
            # und Audit-Eintrag statt dekorativem global_items-Fallback.
            if not evidence_items:
                confidence_score, confidence_label = 0.15, "low"
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
                claim_text="",
                evidence=[],
                confidence_score=0.0,
                confidence_label="low",
                notes="No section content captured.",
            ).to_dict())
        return claims

    def _section_dedup_check(
        self, new_summary: str, existing: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Prueft ob new_summary fast identisch zu einer bestehenden Section ist.

        Returns ein Audit-Trail-dict (Marker), wenn Match. Sonst None.
        Reihenfolge:
        1. Embedder verfuegbar -> cosine-Similarity, threshold 0.92
        2. Sonst Jaccard auf normalisierten Tokens, threshold 0.85
        Defensiv: leere/None summary -> None, leere existing -> None,
        Embedder-Crash -> Jaccard-Fallback.
        """
        if not new_summary or not existing:
            return None
        new_norm = (new_summary or "").strip()
        if not new_norm:
            return None
        embedder = self._try_get_embedder()
        if embedder is not None:
            try:
                from .evidence_binder import _cosine
                new_vec = embedder(new_norm)
                for sec in existing:
                    other = (sec.get("section_summary") or "").strip()
                    if not other:
                        continue
                    other_vec = embedder(other)
                    sim = float(_cosine(new_vec, other_vec))
                    if sim >= 0.92:
                        return {
                            "type": "model_generated_inference",
                            "source": "section_dedup",
                            "tool_name": "section_dedup_check",
                            "snippet": f"duplicate_of_section_{sec.get('section_index')}",
                            "raw": {
                                "similarity": round(sim, 4),
                                "method": "cosine",
                                "matched_section_index": sec.get("section_index"),
                            },
                        }
            except Exception as exc:
                logger.warning(f"Section-Dedup cosine fail, jaccard fallback: {exc!r}")

        # Jaccard-Fallback
        def tokens(s: str) -> set:
            return {t for t in re.split(r"\W+", (s or "").lower()) if len(t) > 2}

        new_tok = tokens(new_norm)
        if not new_tok:
            return None
        for sec in existing:
            other_tok = tokens(sec.get("section_summary") or "")
            if not other_tok:
                continue
            inter = len(new_tok & other_tok)
            union = len(new_tok | other_tok)
            if union == 0:
                continue
            jac = inter / union
            if jac >= 0.85:
                return {
                    "type": "model_generated_inference",
                    "source": "section_dedup",
                    "tool_name": "section_dedup_check",
                    "snippet": f"duplicate_of_section_{sec.get('section_index')}",
                    "raw": {
                        "similarity": round(jac, 4),
                        "method": "jaccard",
                        "matched_section_index": sec.get("section_index"),
                    },
                }
        return None

    def _save_evidence_section(self, report_id: str, section_index: int, section_title: str, content: str) -> None:
        if self.evidence_map is None:
            self._init_evidence_map(report_id)
        self.evidence_map.setdefault("schema_version", CURRENT_SCHEMA_VERSION)
        self.evidence_map.setdefault("global_evidence", self._collect_simulation_evidence_items())
        # schema_version gehört nur auf Map-Ebene, nicht auf Section-Ebene
        # (ReportSectionModel hat das Feld nicht).
        section_entry = {
            "section_index": section_index,
            "section_title": section_title,
            "section_summary": self._truncate(content, 400),
            "claims": self._build_claims_for_section(content),
        }
        # schema_version auf Section-Ebene entfernen — Überbleibsel von
        # migrate_v1_to_v2 oder alten Persistierungen; ReportSectionModel
        # erlaubt das Feld nicht (extra="forbid").
        existing_sections = [
            {k: v for k, v in s.items() if k != "schema_version"}
            for s in self.evidence_map["sections"]
            if s.get("section_index") != section_index
        ]
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
        self.evidence_map["sections"] = existing_sections
        # Layer-0 Boundary: vor dem Persistieren gegen EvidenceMapModel validieren.
        validated = EvidenceMapModel.model_validate(self.evidence_map).model_dump(mode="json")
        self.evidence_map = validated
        ReportManager.save_evidence_map(report_id, validated)
    
    def _define_tools(self) -> Dict[str, Dict[str, Any]]:
        """Define available tools"""
        tools: Dict[str, Dict[str, Any]] = {
            "insight_forge": {
                "name": "insight_forge",
                "description": TOOL_DESC_INSIGHT_FORGE,
                "parameters": {
                    "query": "The question or topic you want to deeply analyze",
                    "report_context": "Context of current report section (optional, helps generate more accurate sub-questions)"
                }
            },
            "panorama_search": {
                "name": "panorama_search",
                "description": TOOL_DESC_PANORAMA_SEARCH,
                "parameters": {
                    "query": "Search query, used for relevance sorting",
                    "include_expired": "Whether to include expired/historical content (default True)"
                }
            },
            "quick_search": {
                "name": "quick_search",
                "description": TOOL_DESC_QUICK_SEARCH,
                "parameters": {
                    "query": "Search query string",
                    "limit": "Number of results to return (optional, default 10)"
                }
            },
            "interview_agents": {
                "name": "interview_agents",
                "description": TOOL_DESC_INTERVIEW_AGENTS,
                "parameters": {
                    "interview_topic": "Interview topic or requirement description (e.g. 'understand students' views on the dorm formaldehyde incident')",
                    "max_agents": "Maximum number of agents to interview (optional, default 5, max 10)"
                }
            }
        }

        # Live-web tools (only exposed when Tavily key is configured).
        if self.web_tools.is_available():
            tools["web_search"] = {
                "name": "web_search",
                "description": (
                    "Live web search via Tavily. Use for CURRENT, POST-SIMULATION facts "
                    "(news, recent developments, statistics, official sources) that are NOT in the knowledge graph. "
                    "Prefer this over guessing whenever the topic is time-sensitive or external."
                ),
                "parameters": {
                    "query": "Search query in natural language (German or English)",
                    "max_results": "Number of results (optional, default 5, max 10)"
                }
            }
            tools["fetch_url"] = {
                "name": "fetch_url",
                "description": (
                    "Fetch the main text of a specific URL found via web_search (or one you already know). "
                    "Returns cleaned article content. Use when a search snippet is insufficient."
                ),
                "parameters": {
                    "url": "Absolute URL starting with http(s)://"
                }
            }
        return tools
    
    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        """Dispatch a tool call (delegates to tool_execution.execute_tool)."""
        return execute_tool(
            tool_name=tool_name,
            parameters=parameters,
            report_context=report_context,
            graph_tools=self.graph_tools,
            web_tools=self.web_tools,
            graph_id=self.graph_id,
            simulation_id=self.simulation_id,
            simulation_requirement=self.simulation_requirement,
            record_evidence=self._record_tool_evidence,
            section_index=self._current_section_index or 0,
        )


    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """Parse tool calls from an LLM response (delegates to tool_validation)."""
        return parse_tool_calls(response)

    def _is_valid_tool_call(self, data: dict) -> bool:
        """Validate the parsed JSON as a tool call (delegates to tool_validation)."""
        return is_valid_tool_call(data)


    def _get_tools_description(self) -> str:
        """Generate tool description text"""
        desc_parts = ["Available Tools:"]
        for name, tool in self.tools.items():
            params_desc = ", ".join([f"{k}: {v}" for k, v in tool["parameters"].items()])
            desc_parts.append(f"- {name}: {tool['description']}")
            if params_desc:
                desc_parts.append(f"  Parameters: {params_desc}")
        return "\n".join(desc_parts)
    
    def plan_outline(
        self,
        progress_callback: Optional[Callable] = None
    ) -> ReportOutline:
        """
        Plan report outline

        Use LLM to analyze simulation requirements and plan the report structure

        Args:
            progress_callback: Progress callback function

        Returns:
            ReportOutline: Report outline
        """
        logger.info("Starting to plan report outline...")

        if progress_callback:
            progress_callback("planning", 0, "Analyzing simulation requirements...")

        # First get simulation context
        context = self.graph_tools.get_simulation_context(
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement
        )

        if progress_callback:
            progress_callback("planning", 30, "Generating report outline...")
        
        system_prompt = PLAN_SYSTEM_PROMPT_TEMPLATE.replace("{language}", Config.REPORT_LANGUAGE)
        user_prompt = PLAN_USER_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            total_nodes=context.get('graph_statistics', {}).get('total_nodes', 0),
            total_edges=context.get('graph_statistics', {}).get('total_edges', 0),
            entity_types=list(context.get('graph_statistics', {}).get('entity_types', {}).keys()),
            total_entities=context.get('total_entities', 0),
            related_facts_json=json.dumps(context.get('related_facts', [])[:10], ensure_ascii=False, indent=2),
        )

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            if progress_callback:
                progress_callback("planning", 80, "Parsing outline structure...")

            # Parse outline — validate via Pydantic contract first, then
            # convert to ReportOutline for downstream processing with content.
            pydantic_sections = []
            for section_data in response.get("sections", []):
                raw_desc = (section_data.get("description") or "").strip()
                pydantic_sections.append(ReportOutlineSectionModel(
                    title=(section_data.get("title") or "Section").strip() or "Section",
                    description=raw_desc if raw_desc else "—",
                ))

            pydantic_outline = ReportOutlineModel(
                title=(response.get("title") or "Simulation Analysis Report").strip() or "Simulation Analysis Report",
                summary=(response.get("summary") or "").strip() or "—",
                sections=pydantic_sections,
            )

            sections = [
                ReportSection(
                    title=s.title,
                    description=s.description,
                )
                for s in pydantic_outline.sections
            ]
            outline = ReportOutline(
                title=pydantic_outline.title,
                summary=pydantic_outline.summary,
                sections=sections,
            )

            if progress_callback:
                progress_callback("planning", 100, "Outline planning completed")

            logger.info(f"Outline planning completed: {len(sections)} sections")
            return outline

        except Exception as e:
            logger.error(f"Outline planning failed: {str(e)}")
            # Return default outline (3 sections as fallback) — all descriptions filled.
            return ReportOutline(
                title="Scenario Evaluation Report",
                summary="Emerging trends and risk analysis based on simulation observations",
                sections=[
                    ReportSection(
                        title="Evaluation Scenario and Core Findings",
                        description="Overview of the simulated scenario and main findings",
                    ),
                    ReportSection(
                        title="Persona Reaction Analysis",
                        description="Analysis of how simulated personas reacted to key events",
                    ),
                    ReportSection(
                        title="Trend Outlook and Risk Warning",
                        description="Identified trends and potential risk signals from the simulation",
                    ),
                ]
            )
    
    def _generate_section_react(
        self, 
        section: ReportSection,
        outline: ReportOutline,
        previous_sections: List[str],
        progress_callback: Optional[Callable] = None,
        section_index: int = 0
    ) -> str:
        """
        Generate individual section content using ReACT pattern

        ReACT loop:
        1. Thought - Analyze what information is needed
        2. Action - Call tool to get information
        3. Observation - Analyze tool return results
        4. Repeat until information is sufficient or maximum iterations reached
        5. Final Answer - Generate section content

        Args:
            section: Section to generate
            outline: Complete outline
            previous_sections: Content of previous sections (for maintaining coherence)
            progress_callback: Progress callback
            section_index: Section index (for logging)

        Returns:
            Section content (Markdown format)
        """
        logger.info(f"ReACT generating section: {section.title}")
        self._current_section_index = section_index
        self._active_section_evidence = []
        
        # Log section start
        if self.report_logger:
            self.report_logger.log_section_start(section.title, section_index)
        
        system_prompt = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            report_title=outline.title,
            report_summary=outline.summary,
            simulation_requirement=self.simulation_requirement,
            section_title=section.title,
            tools_description=self._get_tools_description(),
            language=Config.REPORT_LANGUAGE,
        )

        # Build user prompt - pass maximum 4000 characters for each completed section
        if previous_sections:
            previous_parts = []
            for sec in previous_sections:
                # Maximum 4000 characters per section
                truncated = sec[:4000] + "..." if len(sec) > 4000 else sec
                previous_parts.append(truncated)
            previous_content = "\n\n---\n\n".join(previous_parts)
        else:
            previous_content = "(This is the first section)"
        
        user_prompt = SECTION_USER_PROMPT_TEMPLATE.format(
            previous_content=previous_content,
            section_title=section.title,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # ReACT loop
        tool_calls_count = 0
        max_iterations = 5  # Maximum iterations
        min_tool_calls = 3  # Minimum tool calls
        conflict_retries = 0  # Consecutive conflicts where tool calls and Final Answer appear simultaneously
        used_tools = set()  # Record tool names already called
        all_tools = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}

        # Report context for InsightForge sub-question generation
        report_context = f"Section Title: {section.title}\nSimulation Requirement: {self.simulation_requirement}"
        
        for iteration in range(max_iterations):
            if progress_callback:
                progress_callback(
                    "generating", 
                    int((iteration / max_iterations) * 100),
                    f"Deep retrieval and writing in progress ({tool_calls_count}/{self.MAX_TOOL_CALLS_PER_SECTION})"
                )
            
            # Call LLM
            response = self.llm.chat(
                messages=messages,
                temperature=0.5,
                max_tokens=4096
            )

            # Check if LLM return is None (API exception or empty content)
            if response is None:
                logger.warning(f"Section {section.title} round {iteration + 1} iteration: LLM returned None")
                # If there are more iterations, add message and retry
                if iteration < max_iterations - 1:
                    messages.append({"role": "assistant", "content": "(Response empty)"})
                    messages.append({"role": "user", "content": "Please continue generating content."})
                    continue
                # Last iteration also returned None, exit loop and enter forced conclusion
                break

            logger.debug(f"LLM response: {response[:200]}...")

            # Parse once, reuse result
            tool_calls = self._parse_tool_calls(response)
            has_tool_calls = bool(tool_calls)
            has_final_answer = "Final Answer:" in response

            # ── Conflict handling: LLM simultaneously output tool calls and Final Answer ──
            if has_tool_calls and has_final_answer:
                conflict_retries += 1
                logger.warning(
                    f"Section {section.title} round {iteration+1} : "
                    f"LLM simultaneously output tool calls and Final Answer (round {conflict_retries} conflicts)"
                )

                if conflict_retries <= 2:
                    # First two times: discard this response and request LLM to reply again
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": (
                            "[Format Error] You cannot include both tool calls and Final Answer in one reply.\n"
                            "Each reply can only do one of the following:\n"
                            "- Call a tool (output a <tool_call> block, don't write Final Answer)\n"
                            "- Output final content (starting with 'Final Answer:', don't include <tool_call>)\n"
                            "Please reply again and only do one of these."
                        ),
                    })
                    continue
                else:
                    # Third time: downgrade, truncate to first tool call, force execution
                    logger.warning(
                        f"Section {section.title}: consecutive {conflict_retries} conflicts，"
                        "downgraded to truncate and execute first tool call"
                    )
                    first_tool_end = response.find('</tool_call>')
                    if first_tool_end != -1:
                        response = response[:first_tool_end + len('</tool_call>')]
                        tool_calls = self._parse_tool_calls(response)
                        has_tool_calls = bool(tool_calls)
                    has_final_answer = False
                    conflict_retries = 0

            # Log LLM response
            if self.report_logger:
                self.report_logger.log_llm_response(
                    section_title=section.title,
                    section_index=section_index,
                    response=response,
                    iteration=iteration + 1,
                    has_tool_calls=has_tool_calls,
                    has_final_answer=has_final_answer
                )

            # ── Case 1: LLM output Final Answer ──
            if has_final_answer:
                # Insufficient tool calls, reject and request to continue calling tools
                if tool_calls_count < min_tool_calls:
                    messages.append({"role": "assistant", "content": response})
                    unused_tools = all_tools - used_tools
                    unused_hint = f"(These tools have not been used, recommend using them: {', '.join(unused_tools)}）" if unused_tools else ""
                    messages.append({
                        "role": "user",
                        "content": REACT_INSUFFICIENT_TOOLS_MSG.format(
                            tool_calls_count=tool_calls_count,
                            min_tool_calls=min_tool_calls,
                            unused_hint=unused_hint,
                        ),
                    })
                    continue

                # Normal completion
                final_answer = response.split("Final Answer:")[-1].strip()
                logger.info(f"Section {section.title} generation completed (tool calls: {tool_calls_count}times)")

                if self.report_logger:
                    self.report_logger.log_section_content(
                        section_title=section.title,
                        section_index=section_index,
                        content=final_answer,
                        tool_calls_count=tool_calls_count
                    )
                self._current_section_index = None
                return final_answer

            # ── Case 2: LLM attempts to call tools ──
            if has_tool_calls:
                # Tool quota exhausted → inform clearly, request output Final Answer
                if tool_calls_count >= self.MAX_TOOL_CALLS_PER_SECTION:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": REACT_TOOL_LIMIT_MSG.format(
                            tool_calls_count=tool_calls_count,
                            max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        ),
                    })
                    continue

                # Only execute the first tool call
                call = tool_calls[0]
                if len(tool_calls) > 1:
                    logger.info(f"LLM attempted to call {len(tool_calls)} tools, only execute the first: {call['name']}")

                if self.report_logger:
                    self.report_logger.log_tool_call(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        parameters=call.get("parameters", {}),
                        iteration=iteration + 1
                    )

                result = self._execute_tool(
                    call["name"],
                    call.get("parameters", {}),
                    report_context=report_context
                )

                if self.report_logger:
                    self.report_logger.log_tool_result(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        result=result,
                        iteration=iteration + 1
                    )

                tool_calls_count += 1
                used_tools.add(call['name'])

                # Build unused tools hint
                unused_tools = all_tools - used_tools
                unused_hint = ""
                if unused_tools and tool_calls_count < self.MAX_TOOL_CALLS_PER_SECTION:
                    unused_hint = REACT_UNUSED_TOOLS_HINT.format(unused_list="、".join(unused_tools))

                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": REACT_OBSERVATION_TEMPLATE.format(
                        tool_name=call["name"],
                        result=result,
                        tool_calls_count=tool_calls_count,
                        max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        used_tools_str=", ".join(used_tools),
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # ── Case 3: NeitherTool call，nor Final Answer ──
            messages.append({"role": "assistant", "content": response})

            if tool_calls_count < min_tool_calls:
                # Tool callcount insufficient，recommend unused tools
                unused_tools = all_tools - used_tools
                unused_hint = f"(These tools have not been used, recommend using them: {', '.join(unused_tools)}）" if unused_tools else ""

                messages.append({
                    "role": "user",
                    "content": REACT_INSUFFICIENT_TOOLS_MSG_ALT.format(
                        tool_calls_count=tool_calls_count,
                        min_tool_calls=min_tool_calls,
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # Directly adopt this content as final answer, no more waiting
            # directlyconvertthis contentas finalanswer, no more waiting
            logger.info(f"Section {section.title} did not detectto 'Final Answer:' prefix, directlyadoptLLM outputas finalcontent（Tool call: {tool_calls_count}times)")
            final_answer = response.strip()

            if self.report_logger:
                self.report_logger.log_section_content(
                    section_title=section.title,
                    section_index=section_index,
                    content=final_answer,
                    tool_calls_count=tool_calls_count
                )
            self._current_section_index = None
            return final_answer
        
        # Reachedmaximum iterations, forcegeneratecontent
        logger.warning(f"Section {section.title} reachedmaximumiterationscount，Forcegenerate")
        messages.append({"role": "user", "content": REACT_FORCE_FINAL_MSG})
        
        response = self.llm.chat(
            messages=messages,
            temperature=0.5,
            max_tokens=4096
        )

        # Check forceconclusion when LLM return is None
        if response is None:
            final_answer = "(ThisSectiongeneratefailed: LLM returnedemptyresponse, pleaselaterretry)"
        elif "Final Answer:" in response:
            final_answer = response.split("Final Answer:")[-1].strip()
        else:
            final_answer = response
        
        # Log sectioncontentgeneratecompletion log
        if self.report_logger:
            self.report_logger.log_section_content(
                section_title=section.title,
                section_index=section_index,
                content=final_answer,
                tool_calls_count=tool_calls_count
            )
        self._current_section_index = None
        
        return final_answer
    
    def generate_report(
        self, 
        progress_callback: Optional[Callable[[str, int, str], None]] = None,
        report_id: Optional[str] = None
    ) -> Report:
        """
        Generate complete report (realtime output per section)
        
        File structure:
        File structure:
        reports/{report_id}/
            outline.json    - Report outline
            progress.json   - Generation progress
            section_01.md   - Section 1
            section_02.md   - Section 2
            section_02.md   - Section 2
            ...
            full_report.md  - Complete report
        
        Args:
            report_id: Report ID (optional, auto-generate if not provided)
            report_id: Report ID (optional, auto-generate if not provided)
            
        Returns:
            Report: Complete report
        """
        import uuid
        
        # If not provided report_id，then autogenerate
        if not report_id:
            report_id = f"report_{uuid.uuid4().hex[:12]}"
        start_time = datetime.now()
        
        report = Report(
            report_id=report_id,
            simulation_id=self.simulation_id,
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement,
            status=ReportStatus.PENDING,
            created_at=datetime.now().isoformat()
        )
        
        # CompletedSection Titlelist（for progress tracking）
        completed_section_titles = []
        
        try:
            # Initialize: Create report folder and save initial state
            ReportManager._ensure_report_folder(report_id)
            # Layer-0 Boundary: Fallback-Init via EvidenceMapModel validieren.
            # migrate_v1_to_v2 liefert bei v1-Daten bereits ein v2-Dict;
            # das wird in der nächsten _save_evidence_section erneut validiert.
            self.evidence_map = migrate_v1_to_v2(ReportManager.get_evidence_map(report_id)) or (
                EvidenceMapModel.model_validate({
                    "schema_version": CURRENT_SCHEMA_VERSION,
                    "report_id": report_id,
                    "simulation_id": self.simulation_id,
                    "global_evidence": self._collect_simulation_evidence_items(),
                    "sections": [],
                }).model_dump(mode="json")
            )
            
            # Initialize logslogger（structured logs agent_log.jsonl）
            self.report_logger = ReportLogger(report_id)
            self.report_logger.log_start(
                simulation_id=self.simulation_id,
                graph_id=self.graph_id,
                simulation_requirement=self.simulation_requirement
            )
            
            # Initialize console logslogger（console_log.txt）
            self.console_logger = ReportConsoleLogger(report_id)
            
            ReportManager.update_progress(
                report_id, "pending", 0, "Initializereport...",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            # phase1: planoutline
            report.status = ReportStatus.PLANNING
            ReportManager.update_progress(
                report_id, "planning", 5, "Start planning report outline...",
                completed_sections=[]
            )
            
            # Log outline planning start
            self.report_logger.log_planning_start()
            
            if progress_callback:
                progress_callback("planning", 0, "Start planning report outline...")

            existing_outline = ReportManager.get_report(report_id)
            if existing_outline and existing_outline.outline:
                outline = existing_outline.outline
            else:
                outline = self.plan_outline(
                    progress_callback=lambda stage, prog, msg:
                        progress_callback(stage, prog // 5, msg) if progress_callback else None
                )
                # recordplancompletion log
                self.report_logger.log_planning_complete(outline.to_dict())
                # saveoutlinetofile
                ReportManager.save_outline(report_id, outline)

            report.outline = outline
            ReportManager.update_progress(
                report_id, "planning", 15, f"Outline planning completed, total{len(outline.sections)}sections",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            logger.info(f"outlinesavedtofile: {report_id}/outline.json")
            
            # Phase 2: Sequentially generate sectionsgeneration (per sectionsave）
            report.status = ReportStatus.GENERATING
            
            total_sections = len(outline.sections)
            generated_sections = []  # savecontentfor context
            existing_sections = {
                item["section_index"]: item["content"]
                for item in ReportManager.get_generated_sections(report_id)
            }
            for section_info in ReportManager.get_generated_sections(report_id):
                title = outline.sections[section_info["section_index"] - 1].title if outline.sections and section_info["section_index"] <= len(outline.sections) else ""
                completed_section_titles.append(title)
                generated_sections.append(section_info["content"])
            
            for i, section in enumerate(outline.sections):
                section_num = i + 1
                base_progress = 20 + int((i / total_sections) * 70)
                if section_num in existing_sections:
                    section.content = ReportManager._clean_section_content(existing_sections[section_num], section.title)
                    continue
                
                # Update progress
                ReportManager.update_progress(
                    report_id, "generating", base_progress,
                    f"generatinggenerateSection: {section.title} ({section_num}/{total_sections})",
                    current_section=section.title,
                    completed_sections=completed_section_titles
                )
                
                if progress_callback:
                    progress_callback(
                        "generating", 
                        base_progress, 
                        f"generatinggenerateSection: {section.title} ({section_num}/{total_sections})"
                    )
                
                # Generate main sectioncontent
                section_content = self._generate_section_react(
                    section=section,
                    outline=outline,
                    previous_sections=generated_sections,
                    progress_callback=lambda stage, prog, msg:
                        progress_callback(
                            stage, 
                            base_progress + int(prog * 0.7 / total_sections),
                            msg
                        ) if progress_callback else None,
                    section_index=section_num
                )
                
                section.content = section_content
                generated_sections.append(f"## {section.title}\n\n{section_content}")

                # saveSection
                ReportManager.save_section(report_id, section_num, section)
                self._save_evidence_section(report_id, section_num, section.title, section_content)
                completed_section_titles.append(section.title)

                # Log sectioncompletion log
                full_section_content = f"## {section.title}\n\n{section_content}"

                if self.report_logger:
                    self.report_logger.log_section_full_complete(
                        section_title=section.title,
                        section_index=section_num,
                        full_content=full_section_content.strip()
                    )

                logger.info(f"Sectionsaved: {report_id}/section_{section_num:02d}.md")
                
                # Update progress
                ReportManager.update_progress(
                    report_id, "generating", 
                    base_progress + int(70 / total_sections),
                    f"Section {section.title} completed",
                    current_section=None,
                    completed_sections=completed_section_titles
                )
            
            # phase3: assembleComplete report
            if progress_callback:
                progress_callback("generating", 95, "generatingassemblecompletereport...")
            
            ReportManager.update_progress(
                report_id, "generating", 95, "generatingassemblecompletereport...",
                completed_sections=completed_section_titles
            )
            
            # Using ReportManagerassembleComplete report
            report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
            report.status = ReportStatus.COMPLETED
            report.completed_at = datetime.now().isoformat()
            
            # Calculate total elapsed time
            total_time_seconds = (datetime.now() - start_time).total_seconds()
            
            # recordReportcompletion log
            if self.report_logger:
                self.report_logger.log_report_complete(
                    total_sections=total_sections,
                    total_time_seconds=total_time_seconds
                )
            
            # savefinalReport
            ReportManager.save_report(report)
            ReportManager.update_progress(
                report_id, "completed", 100, "reportgeneratecomplete",
                completed_sections=completed_section_titles
            )
            
            if progress_callback:
                progress_callback("completed", 100, "reportgeneratecomplete")
            
            logger.info(f"reportgeneratecomplete: {report_id}")
            
            # Closeconsoleloglogger
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
            
        except Exception as e:
            logger.error(f"reportgeneratefailed: {str(e)}")
            report.status = ReportStatus.FAILED
            report.error = str(e)
            
            # recorderrorlog
            if self.report_logger:
                self.report_logger.log_error(str(e), "failed")
            
            # savefailedstatus
            try:
                ReportManager.save_report(report)
                ReportManager.update_progress(
                    report_id, "failed", -1, f"reportgeneratefailed: {str(e)}",
                    completed_sections=completed_section_titles
                )
            except Exception:
                pass  # ignoresavefailederror
            
            # Closeconsoleloglogger
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
    
    def chat(
        self, 
        message: str,
        chat_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        andReport Agentchat
        
        inchatinAgentcan autonomouslycallretrievaltoolto answer questions
        
        Args:
            message: user message
            chat_history: chathistory
            
        Returns:
            {
                "response": "Agentresponse",
                "tool_calls": [calltoollist],
                "sources": [informationsource]
            }
        """
        logger.info(f"Report Agentchat: {message[:50]}...")
        
        chat_history = chat_history or []
        
        # GetalreadygenerateReportcontent
        report_content = ""
        try:
            report = ReportManager.get_report_by_simulation(self.simulation_id)
            if report and report.markdown_content:
                # limitReportlength，avoid overly long context
                report_content = report.markdown_content[:15000]
                if len(report.markdown_content) > 15000:
                    report_content += "\n\n... [reportcontenthasTruncate] ..."
        except Exception as e:
            logger.warning(f"getreportcontentfailed: {e}")
        
        system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            report_content=report_content if report_content else "（nonereport）",
            tools_description=self._get_tools_description(),
            language=Config.REPORT_LANGUAGE,
        )

        # Buildmessage
        messages = [{"role": "system", "content": system_prompt}]
        
        # add historychat
        for h in chat_history[-10:]:  # limithistorylength
            messages.append(h)
        
        # add user message
        messages.append({
            "role": "user", 
            "content": message
        })
        
        # ReACT loop（simplified version）
        tool_calls_made = []
        max_iterations = 2  # reduce iterations
        
        for iteration in range(max_iterations):
            response = self.llm.chat(
                messages=messages,
                temperature=0.5
            )
            
            # parseTool call
            tool_calls = self._parse_tool_calls(response)
            
            if not tool_calls:
                # noTool call，directlyReturnresponse
                clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', response, flags=re.DOTALL)
                clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
                
                return {
                    "response": clean_response.strip(),
                    "tool_calls": tool_calls_made,
                    "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
                }
            
            # Execute toolcall（limitcount）
            tool_results = []
            for call in tool_calls[:1]:  # at mostExecute1 time tool call
                if len(tool_calls_made) >= self.MAX_TOOL_CALLS_PER_CHAT:
                    break
                result = self._execute_tool(call["name"], call.get("parameters", {}))
                tool_results.append({
                    "tool": call["name"],
                    "result": result[:1500]  # limitresultlength
                })
                tool_calls_made.append(call)
            
            # convertresultadd to message
            messages.append({"role": "assistant", "content": response})
            observation = "\n".join([f"[{r['tool']}result]\n{r['result']}" for r in tool_results])
            messages.append({
                "role": "user",
                "content": observation + CHAT_OBSERVATION_SUFFIX
            })
        
        # Reachedmaximum iteration，Getfinalresponse
        final_response = self.llm.chat(
            messages=messages,
            temperature=0.5
        )
        
        # cleanresponse
        clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL)
        clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
        
        return {
            "response": clean_response.strip(),
            "tool_calls": tool_calls_made,
            "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
        }


class ReportManager:
    """
    ReportManagemanager
    
    responsible forReportpersistence storage and retrieval
    
    filestructure（perSectionoutput）：
    reports/
      {report_id}/
        meta.json          - Reportmetainformationand status
        outline.json       - Reportoutline
        progress.json      - generateProgress
        section_01.md      - Section 1
        section_02.md      - Section 2
        ...
        full_report.md     - Complete report
    """
    
    # Reportstorage directory
    REPORTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'reports')
    
    @classmethod
    def _ensure_reports_dir(cls):
        """ensurereportroot directory exists"""
        os.makedirs(cls.REPORTS_DIR, exist_ok=True)
    
    @classmethod
    def _get_report_folder(cls, report_id: str) -> str:
        """getreportfolderpath"""
        return os.path.join(cls.REPORTS_DIR, report_id)
    
    @classmethod
    def _ensure_report_folder(cls, report_id: str) -> str:
        """ensurereportfolderexists andreturnedpath"""
        folder = cls._get_report_folder(report_id)
        os.makedirs(folder, exist_ok=True)
        return folder
    
    @classmethod
    def _get_report_path(cls, report_id: str) -> str:
        """getreportmetainformationfile path"""
        return os.path.join(cls._get_report_folder(report_id), "meta.json")
    
    @classmethod
    def _get_report_markdown_path(cls, report_id: str) -> str:
        """getcompletereportMarkdownfile path"""
        return os.path.join(cls._get_report_folder(report_id), "full_report.md")
    
    @classmethod
    def _get_outline_path(cls, report_id: str) -> str:
        """getoutlinefile path"""
        return os.path.join(cls._get_report_folder(report_id), "outline.json")
    
    @classmethod
    def _get_progress_path(cls, report_id: str) -> str:
        """getprogressfile path"""
        return os.path.join(cls._get_report_folder(report_id), "progress.json")
    
    @classmethod
    def _get_section_path(cls, report_id: str, section_index: int) -> str:
        """getSectionMarkdownfile path"""
        return os.path.join(cls._get_report_folder(report_id), f"section_{section_index:02d}.md")
    
    @classmethod
    def _get_agent_log_path(cls, report_id: str) -> str:
        """get Agent logsfile path"""
        return os.path.join(cls._get_report_folder(report_id), "agent_log.jsonl")
    
    @classmethod
    def _get_console_log_path(cls, report_id: str) -> str:
        """getconsolelogsfile path"""
        return os.path.join(cls._get_report_folder(report_id), "console_log.txt")

    @classmethod
    def _get_evidence_map_path(cls, report_id: str) -> str:
        """Get evidence map path"""
        return os.path.join(cls._get_report_folder(report_id), "evidence_map.json")

    @classmethod
    def _write_json_atomic(cls, path: str, payload: Dict[str, Any]) -> None:
        """Write JSON atomically so polling never sees a half-written file."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix='.tmp-report-', suffix='.json', dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    @classmethod
    def _read_json_safe(cls, path: str) -> Optional[Dict[str, Any]]:
        """Read JSON defensively; return None for empty/truncated files during polling."""
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"Skipping unreadable report JSON {path}: {exc}")
            return None
    
    @classmethod
    def get_console_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Getconsolelogcontent
        
        This isReportgenerateduring processconsoleoutputlog（INFO、WARNINGetc），
        and agent_log.jsonl structured logsdifferent。
        
        Args:
            report_id: ReportID
            from_line: from which rowrowStartRead（for incrementalGet，0 means from the beginningStart）
            
        Returns:
            {
                "logs": [logrowlist],
                "total_lines": totalrownumber,
                "from_line": startrownumber,
                "has_more": whether there are morelog
            }
        """
        log_path = cls._get_console_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    # keeporiginallogrow，remove trailingrowcharacter
                    logs.append(line.rstrip('\n\r'))
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # alreadyReadto the end
        }
    
    @classmethod
    def get_console_log_stream(cls, report_id: str) -> List[str]:
        """
        GetCompleteconsolelog（one-timeGetall）
        
        Args:
            report_id: ReportID
            
        Returns:
            logrowlist
        """
        result = cls.get_console_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def get_agent_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Get Agent logcontent
        
        Args:
            report_id: ReportID
            from_line: from which rowrowStartRead（for incrementalGet，0 means from the beginningStart）
            
        Returns:
            {
                "logs": [logentrylist],
                "total_lines": totalrownumber,
                "from_line": startrownumber,
                "has_more": whether there are morelog
            }
        """
        log_path = cls._get_agent_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    try:
                        log_entry = json.loads(line.strip())
                        logs.append(log_entry)
                    except json.JSONDecodeError:
                        # skip parsingfailedrow
                        continue
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # alreadyReadto the end
        }
    
    @classmethod
    def get_agent_log_stream(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        GetComplete Agent log（for one-timeGetall）
        
        Args:
            report_id: ReportID
            
        Returns:
            logentrylist
        """
        result = cls.get_agent_log(report_id, from_line=0)
        return result["logs"]

    @classmethod
    def save_evidence_map(cls, report_id: str, evidence_map: Dict[str, Any]) -> None:
        cls._ensure_report_folder(report_id)
        cls._write_json_atomic(cls._get_evidence_map_path(report_id), evidence_map)

    @classmethod
    def get_evidence_map(cls, report_id: str) -> Optional[Dict[str, Any]]:
        return cls._read_json_safe(cls._get_evidence_map_path(report_id))
    
    @classmethod
    def save_outline(cls, report_id: str, outline: ReportOutline) -> None:
        """
        saveReportoutline
        
        in planningphasecompleteimmediately aftercall
        """
        cls._ensure_report_folder(report_id)
        
        cls._write_json_atomic(cls._get_outline_path(report_id), outline.to_dict())
        
        logger.info(f"outlinesaved: {report_id}")
    
    @classmethod
    def save_section(
        cls,
        report_id: str,
        section_index: int,
        section: ReportSection
    ) -> str:
        """
        savesinglesections

        inEach sectiongeneration completed afterimmediatelycall，implementperSectionoutput

        Args:
            report_id: ReportID
            section_index: Sectionindex（from1Start）
            section: Sectionobject

        Returns:
            savefile path
        """
        cls._ensure_report_folder(report_id)

        # BuildSectionMarkdowncontent - clean possibleduplicatetitle
        cleaned_content = cls._clean_section_content(section.content, section.title)
        md_content = f"## {section.title}\n\n"
        if cleaned_content:
            md_content += f"{cleaned_content}\n\n"

        # savefile
        file_suffix = f"section_{section_index:02d}.md"
        file_path = os.path.join(cls._get_report_folder(report_id), file_suffix)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        logger.info(f"Sectionsaved: {report_id}/{file_suffix}")
        return file_path
    
    @classmethod
    def _clean_section_content(cls, content: str, section_title: str) -> str:
        """
        cleanSectioncontent
        
        1. removecontentbeginningandSection TitleduplicateMarkdowntitlerow
        2. convertall ### and below levelstitleconvert toboldtext
        
        Args:
            content: originalcontent
            section_title: Section Title
            
        Returns:
            after cleaningcontent
        """
        import re
        
        if not content:
            return content
        
        content = content.strip()
        lines = content.split('\n')
        cleaned_lines = []
        skip_next_empty = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Checkwhether isMarkdowntitlerow
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                title_text = heading_match.group(2).strip()
                
                # Checkwhether isandSection Titleduplicatetitle（skip first5rowwithinduplicate）
                if i < 5:
                    if title_text == section_title or title_text.replace(' ', '') == section_title.replace(' ', ''):
                        skip_next_empty = True
                        continue
                
                # convertallleveltitle（#, ##, ###, ####etc）convert tobold
                # becauseSection Titleadded by system，contentshould not have anytitle
                cleaned_lines.append(f"**{title_text}**")
                cleaned_lines.append("")  # addempty line
                continue
            
            # if previousrowwas skippedtitle，and currentrowempty，also skip
            if skip_next_empty and stripped == '':
                skip_next_empty = False
                continue
            
            skip_next_empty = False
            cleaned_lines.append(line)
        
        # removebeginningempty line
        while cleaned_lines and cleaned_lines[0].strip() == '':
            cleaned_lines.pop(0)
        
        # removebeginningseparatorline
        while cleaned_lines and cleaned_lines[0].strip() in ['---', '***', '___']:
            cleaned_lines.pop(0)
            # meanwhileremoveseparatorline afterempty line
            while cleaned_lines and cleaned_lines[0].strip() == '':
                cleaned_lines.pop(0)
        
        return '\n'.join(cleaned_lines)
    
    @classmethod
    def update_progress(
        cls, 
        report_id: str, 
        status: str, 
        progress: int, 
        message: str,
        current_section: str = None,
        completed_sections: List[str] = None
    ) -> None:
        """
        UpdateReportgenerateProgress
        
        frontend can getReadprogress.jsonGetrealtimeProgress
        """
        cls._ensure_report_folder(report_id)
        
        progress_data = {
            "status": status,
            "progress": progress,
            "message": message,
            "current_section": current_section,
            "completed_sections": completed_sections or [],
            "updated_at": datetime.now().isoformat()
        }
        
        cls._write_json_atomic(cls._get_progress_path(report_id), progress_data)
    
    @classmethod
    def get_progress(cls, report_id: str) -> Optional[Dict[str, Any]]:
        """getreportgenerateprogress"""
        return cls._read_json_safe(cls._get_progress_path(report_id))
    
    @classmethod
    def get_generated_sections(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        GetalreadygenerateSectionlist
        
        ReturnallalreadysaveSectionfileinformation
        """
        folder = cls._get_report_folder(report_id)
        
        if not os.path.exists(folder):
            return []
        
        sections = []
        for filename in sorted(os.listdir(folder)):
            if filename.startswith('section_') and filename.endswith('.md'):
                file_path = os.path.join(folder, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # fromfilename parsingSectionindex
                parts = filename.replace('.md', '').split('_')
                section_index = int(parts[1])

                sections.append({
                    "filename": filename,
                    "section_index": section_index,
                    "content": content
                })

        return sections
    
    @classmethod
    def assemble_full_report(cls, report_id: str, outline: ReportOutline) -> str:
        """
        assembleComplete report
        
        fromsaveSectionfileassembleComplete report，and processrowtitleclean
        """
        # BuildReportheader
        md_content = f"# {outline.title}\n\n"
        md_content += f"> {outline.summary}\n\n"
        md_content += "---\n\n"
        
        # sequentiallyReadallSectionfile
        sections = cls.get_generated_sections(report_id)
        for section_info in sections:
            md_content += section_info["content"]
        
        # post-processing：clean entireReporttitlequestion
        md_content = cls._post_process_report(md_content, outline)
        
        # saveComplete report
        full_path = cls._get_report_markdown_path(report_id)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(f"completereporthasassemble: {report_id}")
        return md_content
    
    @classmethod
    def _post_process_report(cls, content: str, outline: ReportOutline) -> str:
        """
        post-processingReportcontent
        
        1. removeduplicatetitle
        2. keepReportmain title(#)andSection Title(##)，removeother levelstitle(###, ####etc)
        3. clean redundantempty lineandseparatorline
        
        Args:
            content: originalReportcontent
            outline: Reportoutline
            
        Returns:
            after processingcontent
        """
        import re
        
        lines = content.split('\n')
        processed_lines = []
        prev_was_heading = False
        
        # collectoutlineinallSection Title
        section_titles = set()
        for section in outline.sections:
            section_titles.add(section.title)
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Checkwhether istitlerow
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                
                # Checkwhether isduplicatetitle（inconsecutive5rowappear the same withincontenttitle）
                is_duplicate = False
                for j in range(max(0, len(processed_lines) - 5), len(processed_lines)):
                    prev_line = processed_lines[j].strip()
                    prev_match = re.match(r'^(#{1,6})\s+(.+)$', prev_line)
                    if prev_match:
                        prev_title = prev_match.group(2).strip()
                        if prev_title == title:
                            is_duplicate = True
                            break
                
                if is_duplicate:
                    # skipduplicatetitleand subsequentempty line
                    i += 1
                    while i < len(lines) and lines[i].strip() == '':
                        i += 1
                    continue
                
                # titlelevel handling：
                # - # (level=1) onlykeepReportmain title
                # - ## (level=2) keepSection Title
                # - ### and below (level>=3) convert toboldtext
                
                if level == 1:
                    if title == outline.title:
                        # keepReportmain title
                        processed_lines.append(line)
                        prev_was_heading = True
                    elif title in section_titles:
                        # Section Titleerrorusing#，corrected to##
                        processed_lines.append(f"## {title}")
                        prev_was_heading = True
                    else:
                        # other first-leveltitleconvert tobold
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                elif level == 2:
                    if title in section_titles or title == outline.title:
                        # keepSection Title
                        processed_lines.append(line)
                        prev_was_heading = True
                    else:
                        # nonSectionsecond-leveltitleconvert tobold
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                else:
                    # ### and below levelstitleconvert toboldtext
                    processed_lines.append(f"**{title}**")
                    processed_lines.append("")
                    prev_was_heading = False
                
                i += 1
                continue
            
            elif stripped == '---' and prev_was_heading:
                # skiptitlefollowed immediately byseparatorline
                i += 1
                continue
            
            elif stripped == '' and prev_was_heading:
                # titleafter onlykeeponeempty line
                if processed_lines and processed_lines[-1].strip() != '':
                    processed_lines.append(line)
                prev_was_heading = False
            
            else:
                processed_lines.append(line)
                prev_was_heading = False
            
            i += 1
        
        # cleanconsecutivemultipleempty line（keepat most2)
        result_lines = []
        empty_count = 0
        for line in processed_lines:
            if line.strip() == '':
                empty_count += 1
                if empty_count <= 2:
                    result_lines.append(line)
            else:
                empty_count = 0
                result_lines.append(line)
        
        return '\n'.join(result_lines)
    
    @classmethod
    def save_report(cls, report: Report) -> None:
        """SavereportmetainformationandcompleteReport"""
        cls._ensure_report_folder(report.report_id)

        evidence_map = cls.get_evidence_map(report.report_id)
        report.has_evidence = bool(evidence_map and evidence_map.get("sections"))
        report.evidence_sections = len((evidence_map or {}).get("sections", []))
        
        # savemetainformationJSON
        cls._write_json_atomic(cls._get_report_path(report.report_id), report.to_dict())
        
        # saveoutline
        if report.outline:
            cls.save_outline(report.report_id, report.outline)
        
        # saveCompleteMarkdownReport
        if report.markdown_content:
            with open(cls._get_report_markdown_path(report.report_id), 'w', encoding='utf-8') as f:
                f.write(report.markdown_content)
        
        logger.info(f"reportsaved: {report.report_id}")
    
    @classmethod
    def get_report(cls, report_id: str) -> Optional[Report]:
        """getreport"""
        path = cls._get_report_path(report_id)
        
        if not os.path.exists(path):
            # backward compatibleformat：Checkdirectlystored inreportsunder directoryfile
            old_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
            if os.path.exists(old_path):
                path = old_path
            else:
                return None
        
        data = cls._read_json_safe(path)
        if not data:
            return None
        
        # rebuildReportobject
        outline = None
        if data.get('outline'):
            outline_data = data['outline']
            sections = []
            for s in outline_data.get('sections', []):
                # Prefer stored description; fall back to content for legacy
                # entries that predate the description field.
                stored_desc = s.get('description') or s.get('content') or ""
                sections.append(ReportSection(
                    title=s['title'],
                    content=s.get('content', ''),
                    description=stored_desc if stored_desc.strip() else "—",
                ))
            outline = ReportOutline(
                title=outline_data['title'],
                summary=outline_data['summary'],
                sections=sections
            )
        
        # ifmarkdown_contentempty，attempt tofromfull_report.mdRead
        markdown_content = data.get('markdown_content', '')
        if not markdown_content:
            full_report_path = cls._get_report_markdown_path(report_id)
            if os.path.exists(full_report_path):
                with open(full_report_path, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
        evidence_map = cls.get_evidence_map(report_id)
        
        return Report(
            report_id=data['report_id'],
            simulation_id=data['simulation_id'],
            graph_id=data['graph_id'],
            simulation_requirement=data['simulation_requirement'],
            status=ReportStatus(data['status']),
            outline=outline,
            markdown_content=markdown_content,
            created_at=data.get('created_at', ''),
            completed_at=data.get('completed_at', ''),
            error=data.get('error'),
            has_evidence=bool(data.get('has_evidence') or (evidence_map and evidence_map.get("sections"))),
            evidence_sections=int(
                data.get('evidence_sections', 0) or len((evidence_map or {}).get("sections", []))
            ),
        )
    
    @classmethod
    def get_report_by_simulation(cls, simulation_id: str) -> Optional[Report]:
        """based onsimulationIDgetreport"""
        cls._ensure_reports_dir()
        
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # newformat：filefolder
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report and report.simulation_id == simulation_id:
                    return report
            # backward compatibleformat：JSONfile
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report and report.simulation_id == simulation_id:
                    return report
        
        return None
    
    @classmethod
    def list_reports(cls, simulation_id: Optional[str] = None, limit: int = 50) -> List[Report]:
        """columnappearreport"""
        cls._ensure_reports_dir()
        
        reports = []
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # newformat：filefolder
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
            # backward compatibleformat：JSONfile
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
        
        # sorted by creation time descending
        reports.sort(key=lambda r: r.created_at, reverse=True)
        
        return reports[:limit]
    
    @classmethod
    def delete_report(cls, report_id: str) -> bool:
        """Deletereport（entirefolder）"""
        import shutil
        
        folder_path = cls._get_report_folder(report_id)
        
        # newformat：Deleteentirefilefolder
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            logger.info(f"reportfolderhasDelete: {report_id}")
            return True
        
        # backward compatibleformat：Deleteseparatefile
        deleted = False
        old_json_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
        old_md_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.md")
        
        if os.path.exists(old_json_path):
            os.remove(old_json_path)
            deleted = True
        if os.path.exists(old_md_path):
            os.remove(old_md_path)
            deleted = True
        
        return deleted
