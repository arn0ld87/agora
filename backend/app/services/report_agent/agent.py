from contextlib import nullcontext
from typing import Any, Callable, Dict, List, Optional

from pydantic import ValidationError

from ...contracts.report_contract import counts_for_confidence
from ...models.report import (
    EvidenceItem,
    Report,
    ReportClaim,
    ReportOutline,
    ReportSection,
)
from ...utils.llm_client import LLMClient
from ...utils.logger import get_logger
from ..claim_atomizer import split_claim_chunks
from ..claim_type_classifier import classify_claim_type
from ..confidence_calculator import apply_claim_type_floor, compute_confidence
from ..evidence_binder import bind_evidence_to_claim, detect_contradiction_penalty
from ..evidence_entailment import SCENARIO_ROLE_REASON_PREFIX, EntailmentJudge
from ..evidence_identity import build_producer_key
from ..graph.graph_dtos import provenance_at
from ..graph_tools import (
    GraphToolsService,
    InsightForgeResult,
    InterviewResult,
    PanoramaResult,
    SearchResult,
)
from ..llm_entailment_judge import build_llm_judge
from ..llm_routing_seed import workspace_credential_id_for_run
from ..persona_role import resolve_stakeholder_group
from ..report_logger import ReportConsoleLogger, ReportLogger
from ..run_budget import reraise_if_budget_exceeded
from ..tool_validation import VALID_TOOL_NAMES  # noqa: F401  # re-exported for backwards-compat
from ..web_tools import WebToolsService
from .action_search import ActionSearchResult, build_action_evidence_item
from .agent_claims import (
    FORBIDDEN_EVIDENCE_TYPES,
    ReportAgentClaimsMixin,
    _count_scenario_bindings,
    _counts_for_claim,
    _GAP_SUGGESTED_FIX,
    _GAP_SUGGESTED_FIX_DEFAULT,
    _is_non_factual_claim,
    _NON_FACTUAL_CLAIM_TYPES,
    _typed_confidence,
)
from .agent_hypotheses import ReportAgentHypothesesMixin
from .agent_section_saving import ReportAgentSectionSavingMixin
from .agent_evidence import (
    ReportAgentEvidenceMixin,
    _binding_strength,
    _ENTAILMENT_RANK,
    _HARD_ROLE_CONFLICTS,
    _remap_claim_bindings,
)
from .agent_tools import (
    ReportAgentToolsMixin,
    _INTERVIEW_NO_RESPONSE,
    _INTERVIEW_STRUCTURE_RE,
    _record_action_search_hits,
)
from .data_gap import ClaimGapKind, classify_claim_gap
from .evidence import (
    build_seed_document_anchor,
    degrade_sections_for_violations,
    document_role_of,
    downgrade_medium_without_agent_grounded,
    init_evidence_map,
    normalize_claims_for_contract,
    normalize_sections_for_contract,
    provenance_graph_origin,
    record_evidence_item,
    register_evidence_record,
    resolve_embedder,
)
from .evidence_candidates import RESERVED_CANDIDATE_SLOTS, EvidenceCandidatePool
from .evidence_ledger import ledger_for
from .manager import ReportManager
from .planning import plan_outline as plan_outline_impl
from .postprocess_timing import PostprocessPhaseTracker
from .prompts import (
    CHAT_OBSERVATION_SUFFIX,
    CHAT_SYSTEM_PROMPT_TEMPLATE,
    REACT_FORCE_FINAL_MSG,
    REACT_INSUFFICIENT_TOOLS_MSG,
    REACT_INSUFFICIENT_TOOLS_MSG_ALT,
    REACT_OBSERVATION_TEMPLATE,
    REACT_PREFETCH_EMPTY_NOTE,
    REACT_PREFETCHED_POSTS_TEMPLATE,
    REACT_TOOL_LIMIT_MSG,
    REACT_UNUSED_TOOLS_HINT,
    SECTION_SYSTEM_PROMPT_TEMPLATE,
    SECTION_USER_PROMPT_TEMPLATE,
)
from .schemas import CURRENT_SCHEMA_VERSION, EvidenceMapModel, normalize_persisted_evidence_map
from .search_dedup import (
    EmptySearchRegistry,
    dedup_key,
    is_empty_result,
    is_search_tool,
    registry_for,
)
from .section_pipeline import SectionEvidenceOutcome
from .sections import (
    atomize_claim_chunk,
    attach_provenance,
    build_source_id_anchor,
    is_atomic_claim,
    is_claim_candidate,
    is_discourse_sentence,
    sample_actions_timeseries,
    section_dedup_check,
    truncate_text,
)
from .takeaway_confidence import cap_section_key_takeaways
from .text_verification import prose_gate_decisions
from .tools import (
    define_tools,
    describe_tools,
    execute_tool_call,
    get_openai_tools_schema,
    is_valid_tool_call,
    parse_tool_calls,
)
from .workflow import (
    chat as chat_impl,
    generate_report as generate_report_impl,
    generate_section_react as generate_section_react_impl,
)

logger = get_logger("agora.report_agent")


class ReportAgent(
    ReportAgentToolsMixin,
    ReportAgentEvidenceMixin,
    ReportAgentClaimsMixin,
    ReportAgentSectionSavingMixin,
):
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
    REACT_PREFETCHED_POSTS_TEMPLATE = REACT_PREFETCHED_POSTS_TEMPLATE
    REACT_PREFETCH_EMPTY_NOTE = REACT_PREFETCH_EMPTY_NOTE
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
        document_roles: Optional[Dict[str, str]] = None,
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
            document_roles: ``document_id`` → Dokument-Rolle (Issue #1240),
                siehe ``services.document_roles.load_document_roles``
        """
        self.graph_id = graph_id
        self.document_roles: Dict[str, str] = dict(document_roles or {})
        self.simulation_id = simulation_id
        self.simulation_requirement = simulation_requirement

        if llm_client is not None:
            self.llm = llm_client
        else:
            self.llm = LLMClient(model=model_name) if model_name else LLMClient()

        # Optional live-web tools (Tavily). Disabled silently when no API key
        # — and hard-disabled for a workspace-scoped (JWT/BYOK) run, whose
        # principal never brought a Tavily key of their own: the operator's
        # TAVILY_API_KEY must not be usable through a visitor's report (#1688).
        is_workspace_scoped_run = workspace_credential_id_for_run(None) is not None
        self.web_tools = (
            WebToolsService(enabled=False) if is_workspace_scoped_run else WebToolsService()
        )
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
        self._active_section_unresolved_evidence: List[Dict[str, Any]] = []
        self._current_section_index: Optional[int] = None

        logger.info(
            f"ReportAgent initialization complete: graph_id={graph_id}, simulation_id={simulation_id}"
        )

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
        section_index: int = 0,
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
        cancel_run_id: Optional[str] = None,
    ) -> Report:
        return generate_report_impl(  # type: ignore[arg-type]
            self,
            progress_callback=progress_callback,
            report_id=report_id,
            report_mode=report_mode,
            cancel_run_id=cancel_run_id,
        )

    def chat(self, message: str, chat_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        return chat_impl(self, message=message, chat_history=chat_history)

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
    def _is_discourse_sentence(text: str) -> bool:
        return is_discourse_sentence(text)

    def _section_dedup_check(
        self, new_summary: str, existing: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        return section_dedup_check(
            new_summary,
            existing,
            get_embedder=self._try_get_embedder,
            logger=logger,
        )


__all__ = [
    "ActionSearchResult",
    "CHAT_OBSERVATION_SUFFIX",
    "CHAT_SYSTEM_PROMPT_TEMPLATE",
    "CURRENT_SCHEMA_VERSION",
    "ClaimGapKind",
    "EmptySearchRegistry",
    "EntailmentJudge",
    "EvidenceCandidatePool",
    "EvidenceItem",
    "EvidenceMapModel",
    "FORBIDDEN_EVIDENCE_TYPES",
    "GraphToolsService",
    "InsightForgeResult",
    "InterviewResult",
    "LLMClient",
    "PanoramaResult",
    "PostprocessPhaseTracker",
    "REACT_FORCE_FINAL_MSG",
    "REACT_INSUFFICIENT_TOOLS_MSG",
    "REACT_INSUFFICIENT_TOOLS_MSG_ALT",
    "REACT_OBSERVATION_TEMPLATE",
    "REACT_PREFETCHED_POSTS_TEMPLATE",
    "REACT_PREFETCH_EMPTY_NOTE",
    "REACT_TOOL_LIMIT_MSG",
    "REACT_UNUSED_TOOLS_HINT",
    "RESERVED_CANDIDATE_SLOTS",
    "Report",
    "ReportAgent",
    "ReportAgentClaimsMixin",
    "ReportAgentEvidenceMixin",
    "ReportAgentHypothesesMixin",
    "ReportAgentSectionSavingMixin",
    "ReportAgentToolsMixin",
    "ReportClaim",
    "ReportConsoleLogger",
    "ReportLogger",
    "ReportManager",
    "ReportOutline",
    "ReportSection",
    "SCENARIO_ROLE_REASON_PREFIX",
    "SECTION_SYSTEM_PROMPT_TEMPLATE",
    "SECTION_USER_PROMPT_TEMPLATE",
    "SearchResult",
    "SectionEvidenceOutcome",
    "VALID_TOOL_NAMES",
    "ValidationError",
    "WebToolsService",
    "_ENTAILMENT_RANK",
    "_GAP_SUGGESTED_FIX",
    "_GAP_SUGGESTED_FIX_DEFAULT",
    "_HARD_ROLE_CONFLICTS",
    "_INTERVIEW_NO_RESPONSE",
    "_INTERVIEW_STRUCTURE_RE",
    "_NON_FACTUAL_CLAIM_TYPES",
    "_binding_strength",
    "_count_scenario_bindings",
    "_counts_for_claim",
    "_is_non_factual_claim",
    "_record_action_search_hits",
    "_remap_claim_bindings",
    "_typed_confidence",
    "apply_claim_type_floor",
    "atomize_claim_chunk",
    "attach_provenance",
    "bind_evidence_to_claim",
    "build_action_evidence_item",
    "build_llm_judge",
    "build_producer_key",
    "build_seed_document_anchor",
    "build_source_id_anchor",
    "cap_section_key_takeaways",
    "chat_impl",
    "classify_claim_gap",
    "classify_claim_type",
    "compute_confidence",
    "counts_for_confidence",
    "dedup_key",
    "define_tools",
    "degrade_sections_for_violations",
    "describe_tools",
    "detect_contradiction_penalty",
    "document_role_of",
    "downgrade_medium_without_agent_grounded",
    "execute_tool_call",
    "generate_report_impl",
    "generate_section_react_impl",
    "get_logger",
    "get_openai_tools_schema",
    "init_evidence_map",
    "is_atomic_claim",
    "is_claim_candidate",
    "is_discourse_sentence",
    "is_empty_result",
    "is_search_tool",
    "is_valid_tool_call",
    "ledger_for",
    "logger",
    "normalize_claims_for_contract",
    "normalize_persisted_evidence_map",
    "normalize_sections_for_contract",
    "nullcontext",
    "parse_tool_calls",
    "plan_outline_impl",
    "prose_gate_decisions",
    "provenance_at",
    "provenance_graph_origin",
    "record_evidence_item",
    "register_evidence_record",
    "registry_for",
    "reraise_if_budget_exceeded",
    "resolve_embedder",
    "resolve_stakeholder_group",
    "sample_actions_timeseries",
    "section_dedup_check",
    "split_claim_chunks",
    "truncate_text",
    "workspace_credential_id_for_run",
]
