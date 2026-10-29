# ruff: noqa: F401, E402, F811
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from pydantic import ValidationError

from ...config import Config
from ...contracts.report_contract import ReportOutlineModel, ReportOutlineSectionModel
from ...contracts.report_v3 import (
    DEFAULT_REPORT_MODE,
    RED_TEAM_FINDINGS_LIMIT,
    ModelAttribution,
    ReportMode,
    ReportV3,
)
from ...llm.tokens import PROMPT_HEADROOM_TOKENS
from ...models.report import Report, ReportStatus
from ...utils.logger import get_logger
from ...utils.provider_message import redacted_provider_message as _redacted_provider_message
from ..artifact_store import resolve_default_store
from ..evidence_migrations import migrate_v1_to_v2, normalize_persisted_evidence_map
from ..report_intent import ReportIntent, detect_report_intent
from ..run_budget import reraise_if_budget_exceeded
from ..sim.action_log_reader import action_log_health
from ..simulation_agent_identity import align_config_to_profiles, load_simulation_profiles
from .contract_constants import MIN_PERSONA_TABLE_ROWS
from .evidence import validate_quote_anchors
from .evidence_density import compute_evidence_density
from .manager import ReportManager
from .output_contract import (
    FinalContentRejected,
    apply_degradation_downgrade,
    apply_quote_validation_downgrade,
    apply_report_v3_validation_downgrade,
    is_fallback_content,
    resolve_report_status,
    sanitize_final_content,
)
from .planning import plan_outline as plan_outline_impl
from .postprocess_timing import PostprocessPhaseTracker
from .requirement_checker import (
    checklist_for_intent,
    collect_requirement_degradations,
    find_missing_requirements,
)
from .run_degradation import (
    apply_run_degradation_downgrade,
    assert_run_invariants,
    clear_fallback_outline_used,
    collect_run_degradations,
    events_for,
    mark_fallback_outline_used,
    mark_forced_final,
    mark_metadata_failure,
    mark_work_traces_removed,
    stance_analysis_unavailable,
)
from .schemas import EvidenceMapModel, _section_schema_for
from .search_dedup import (
    dedup_key,
    is_search_tool,
    query_of,
    registry_for,
    repeated_empty_search_message,
)
from .section_coverage import section_has_sufficient_evidence
from .section_kinds import coerce_section_kind
from .section_pipeline import (
    SectionContext,
    SectionResult,
    _section_expects_quotes,
    process_section,
)
from .simulation_snapshot import (
    capture_simulation_snapshot,
    load_simulation_llm_call_stats,
)
from .stance_analysis import (
    build_stance_analysis,
    contested_statement_of,
    has_contested_statement,
    load_stance_analysis,
    save_stance_analysis,
    voices_match_config,
)
from .text_verification import verify_prose
from .threshold_deviation import prior_threshold_lines, threshold_conflict_findings
from .tool_circuit_breaker import breaker_for
from .workflow_finalization import (
    METADATA_MAX_CONTENT_CHARS,
    METADATA_MAX_OUTPUT_TOKENS,
    _INTERVIEW_EVIDENCE_TYPE,
    _INVARIANT_FINDINGS,
    _RED_TEAM_ECHO_THRESHOLD,
    _RED_TEAM_EXCERPT_BUDGET,
    _RED_TEAM_MANDATORY_INTENTS,
    _RED_TEAM_MAX_TOKENS,
    _RED_TEAM_SYSTEM_PROMPT,
    _RED_TEAM_USER_TEMPLATE,
    _apply_requirement_check,
    _build_and_validate_report_v3,
    _build_partial_report,
    _build_red_team_excerpt,
    _count_interview_evidence,
    _deterministic_red_team_findings,
    _get_echo_index,
    _is_cancel_requested,
    _merge_findings,
    _merge_run_degradations,
    _persist_evidence_density,
    _persist_fallback_outline_marker,
    _persist_work_trace_markers,
    _prior_thresholds_prompt,
    _record_metadata_truncation_degradation,
    _red_team_required,
    _restore_work_trace_markers,
    _run_red_team_review,
    _sections_with_persisted_evidence,
    generate_section_metadata,
)
from .workflow_outline import (
    _compute_stance_analysis,
    _load_persona_candidate_count,
    _load_persona_count,
    _load_persona_fallback_stats,
    _load_persona_floor,
    _mark_incomplete_for_persona_floor,
    _reusable_persisted_outline,
    _stance_analysis_of,
    _validate_outline_structure,
    load_persona_count_for,
    load_persona_floor_for,
)
from .workflow_react import (
    SECTION_EMPTY_RESPONSE_BODY,
    SECTION_FALLBACK_BODY,
    SECTION_FALLBACK_ERROR_BODY,
    SECTION_FALLBACK_HINT_BAD_REQUEST,
    SECTION_FALLBACK_HINT_GENERIC,
    SECTION_FALLBACK_HINT_SKIPPED,
    SECTION_FALLBACK_TITLE,
    SECTION_UNUSABLE_OUTPUT_BODY,
    _POST_SEARCH_TOOL,
    _PROMPT_SPECIFIC_400_CODES,
    _PROMPT_SPECIFIC_400_PHRASES,
    _draft_content,
    _finalize_content,
    _forced_final_response,
    _is_persistent_provider_400,
    _persistent_error_note,
    _prefetch_into_prompt,
    _prefetch_simulation_posts,
    _request_coverage_retrieval,
    _run_post_search,
    _safe_generate_section_react,
    _section_error_fallback,
    _section_has_sufficient_evidence,
    generate_section_react,
)

logger = get_logger("agora.report_agent")


def generate_report(
    agent: Any,
    progress_callback: Optional[Callable[[str, int, str], None]] = None,
    report_id: Optional[str] = None,
    *,
    report_mode: ReportMode = DEFAULT_REPORT_MODE,
    cancel_run_id: Optional[str] = None,
) -> Report:
    import uuid

    if not report_id:
        report_id = f"report_{uuid.uuid4().hex[:12]}"
    start_time = datetime.now()

    report = Report(
        report_id=report_id,
        simulation_id=agent.simulation_id,
        graph_id=agent.graph_id,
        simulation_requirement=agent.simulation_requirement,
        status=ReportStatus.PENDING,
        created_at=datetime.now().isoformat(),
        simulation_snapshot=capture_simulation_snapshot(agent.simulation_id),
    )

    completed_section_titles = []

    try:
        ReportManager._ensure_report_folder(report_id)
        ReportManager.reset_review_state(report_id)
        legacy_evidence_map = migrate_v1_to_v2(
            ReportManager.get_evidence_map(report_id)
        )
        agent.evidence_map = normalize_persisted_evidence_map(legacy_evidence_map)
        if agent.evidence_map is None:
            agent._init_evidence_map(report_id)
            agent.evidence_map = EvidenceMapModel.model_validate(
                agent.evidence_map
            ).model_dump(mode="json")

        agent.stance_analysis = _compute_stance_analysis(agent, report_id)

        _restore_work_trace_markers(agent, report_id)

        agent.report_logger = agent.ReportLogger(report_id)
        agent.report_logger.log_start(
            simulation_id=agent.simulation_id,
            graph_id=agent.graph_id,
            simulation_requirement=agent.simulation_requirement,
        )
        agent.console_logger = agent.ReportConsoleLogger(report_id)

        existing_outline = ReportManager.get_report(report_id)

        ReportManager.update_progress(report_id, "pending", 0, "Initializing report...", completed_sections=[])
        ReportManager.save_report(report)

        report.status = ReportStatus.PLANNING
        ReportManager.update_progress(report_id, "planning", 5, "Start planning report outline...", completed_sections=[])
        agent.report_logger.log_planning_start()
        if progress_callback:
            progress_callback("planning", 0, "Start planning report outline...")

        outline = _reusable_persisted_outline(existing_outline, report_id)
        if outline is None:
            clear_fallback_outline_used(agent)
            outline = plan_outline_impl(
                agent,
                progress_callback=lambda stage, prog, msg: progress_callback(stage, prog // 5, msg) if progress_callback else None,
            )
            _validate_outline_structure(outline)
            agent.report_logger.log_planning_complete(outline.to_dict())
            ReportManager.save_outline(report_id, outline)
            _persist_fallback_outline_marker(agent, report_id)

        _validate_outline_structure(outline)
        report.outline = outline
        ReportManager.update_progress(report_id, "planning", 15, f"Outline planning completed, {len(outline.sections)} sections in total", completed_sections=[])
        ReportManager.save_report(report)

        if _is_cancel_requested(cancel_run_id):
            return _build_partial_report(
                report,
                report_id=report_id,
                completed_section_titles=completed_section_titles,
                outline=outline,
                agent=agent,
                progress_callback=progress_callback,
            )

        persona_count = _load_persona_count(agent)
        persona_floor = _load_persona_floor(agent)
        if persona_count < persona_floor:
            report = _mark_incomplete_for_persona_floor(
                report,
                report_id=report_id,
                persona_count=persona_count,
                floor=persona_floor,
                candidate_count=_load_persona_candidate_count(agent),
                progress_callback=progress_callback,
            )
            if agent.console_logger:
                agent.console_logger.close()
                agent.console_logger = None
            return report

        report.status = ReportStatus.GENERATING
        ReportManager.save_report(report)
        events_for(agent).persistent_provider_error = None
        total_sections = len(outline.sections)
        generated_sections = []
        failed_section_indices: List[int] = []
        quote_validation_failed_section_indices: List[int] = sorted(
            ReportManager.load_quote_validation_failed_sections(report_id)
        )
        existing_sections = {item["section_index"]: item["content"] for item in ReportManager.get_generated_sections(report_id)}
        for section_info in _sections_with_persisted_evidence(agent, report_id):
            title = outline.sections[section_info["section_index"] - 1].title if outline.sections and section_info["section_index"] <= len(outline.sections) else ""
            completed_section_titles.append(title)
            generated_sections.append(section_info["content"])

        section_ctx = SectionContext(
            report_id=report_id,
            outline=outline,
            total_sections=total_sections,
            generate_section=_safe_generate_section_react,
            generate_metadata=generate_section_metadata,
            report_mode=report_mode,
            previous_sections=generated_sections,
            completed_section_titles=completed_section_titles,
            persisted_section_contents=existing_sections,
            progress_callback=progress_callback,
            validate_quotes=validate_quote_anchors,
            verify_prose_fn=verify_prose,
            is_fallback=is_fallback_content,
            report_manager=ReportManager,
            phase_tracker_factory=PostprocessPhaseTracker,
        )

        for i, section in enumerate(outline.sections):
            if _is_cancel_requested(cancel_run_id):
                return _build_partial_report(
                    report,
                    report_id=report_id,
                    completed_section_titles=completed_section_titles,
                    outline=outline,
                    agent=agent,
                    progress_callback=progress_callback,
                    quote_validation_failed_section_indices=quote_validation_failed_section_indices,
                    failed_section_indices=failed_section_indices,
                )
            section_num = i + 1
            result: SectionResult = process_section(
                agent, section, section_ctx, section_index=section_num
            )
            if result.failed:
                failed_section_indices.append(section_num)
            if result.quote_validation_failed:
                if section_num not in quote_validation_failed_section_indices:
                    quote_validation_failed_section_indices.append(section_num)
                ReportManager.save_quote_validation_failed_sections(
                    report_id, quote_validation_failed_section_indices
                )
            if result.restored:
                continue
            generated_sections.append(result.markdown)
            completed_section_titles.append(result.title)
            _persist_work_trace_markers(agent, report_id)
            if agent.report_logger:
                agent.report_logger.log_section_full_complete(
                    section_title=result.title,
                    section_index=section_num,
                    full_content=result.markdown.strip(),
                )
            ReportManager.update_progress(
                report_id,
                "generating",
                section_ctx.base_progress_for(section_num) + int(70 / total_sections),
                f"Section {result.title} completed",
                current_section=None,
                completed_sections=completed_section_titles,
            )

        assembling_message = "Assembling the complete report..."
        if progress_callback:
            progress_callback("generating", 95, assembling_message)
        ReportManager.update_progress(report_id, "generating", 95, assembling_message, completed_sections=completed_section_titles)
        report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
        report.status = resolve_report_status(
            total_sections=total_sections,
            failed_section_indices=failed_section_indices,
            required_section_indices=list(range(1, total_sections + 1)),
        )
        evidence_map = agent.evidence_map if isinstance(agent.evidence_map, dict) else {}
        report.status = apply_degradation_downgrade(
            report.status,
            evidence_map.get("degradation_log") or [],
        )
        report.status = apply_quote_validation_downgrade(
            report.status,
            quote_validation_failed_section_indices,
        )
        persona_fallbacks, persona_total = _load_persona_fallback_stats(agent)
        sim_llm_total, sim_llm_failed = load_simulation_llm_call_stats(
            report.simulation_id
        )
        fresh_degradations = collect_run_degradations(
            simulation_snapshot=report.simulation_snapshot,
            simulation_llm_calls_total=sim_llm_total,
            simulation_llm_calls_failed=sim_llm_failed,
            persona_fallback_count=persona_fallbacks,
            persona_total=persona_total,
            interviews_requested=breaker_for(agent).request_count("interview_agents"),
            interviews_succeeded=_count_interview_evidence(agent),
            interview_disabled_reason=breaker_for(agent).reason_for("interview_agents"),
            failed_section_indices=failed_section_indices,
            fallback_outline_used=events_for(agent).fallback_outline_used,
            forced_final_section_indices=events_for(agent).forced_final_sections,
            work_trace_removed_section_indices=events_for(
                agent
            ).work_trace_removed_sections,
            metadata_failed_section_indices=events_for(agent).metadata_failed_sections,
            stance_analysis=_stance_analysis_of(agent),
        )
        report.run_degradations = _merge_run_degradations(report, fresh_degradations)
        report.status = apply_run_degradation_downgrade(
            report.status, report.run_degradations
        )
        if failed_section_indices:
            failed_note = (
                f"{total_sections - len(failed_section_indices)}/{total_sections} "
                f"Sections erfolgreich. Fehlgeschlagen: "
                f"{', '.join(str(i) for i in sorted(failed_section_indices))}."
            )
            failed_note += _persistent_error_note(
                events_for(agent).persistent_provider_error
            )
            logger.warning("report %s: %s", report_id, failed_note)
            report.error = failed_note if not getattr(report, "error", None) else report.error
        report.completed_at = datetime.now().isoformat()
        total_time_seconds = (datetime.now() - start_time).total_seconds()
        if agent.report_logger:
            agent.report_logger.log_report_complete(total_sections=total_sections, total_time_seconds=total_time_seconds)

        _build_and_validate_report_v3(
            report, agent, report_mode=report_mode, report_id=report_id
        )
        _apply_requirement_check(report, agent, report_id)
        ReportManager.save_report(report)
        _persist_evidence_density(agent, report_id)

        try:
            report_v3_raw = ReportManager.get_report_v3(report_id)
            if report_v3_raw:
                try:
                    report_v3_obj = ReportV3.model_validate(report_v3_raw)
                except ValidationError as val_exc:
                    error_count = len(val_exc.errors())
                    logger.error(
                        "generate_report: ReportV3.model_validate hat report=%s "
                        "abgelehnt — %d Schema-Verletzung(en), vermutlich aus "
                        "fehlgeschlagenen LLM-Calls. Errors=%s",
                        report_id,
                        error_count,
                        val_exc.errors()[:5],
                    )
                    if report and not getattr(report, "error", None):
                        report.error = (
                            f"Report enthält {error_count} unvollständige Section(s) — "
                            "LLM-Calls sind fehlgeschlagen. Server-Logs zeigen die "
                            "betroffenen Felder. Mit gültigem LLM-Profil neu starten."
                        )
                    previous_status = report.status
                    report.status = apply_report_v3_validation_downgrade(
                        report.status, val_exc.errors()
                    )
                    if report.status != previous_status:
                        ReportManager.save_report(report)
                    report_v3_obj = None
                if report_v3_obj is not None:
                    echo_index = _get_echo_index(agent)
                    intent = detect_report_intent(
                        getattr(agent, "simulation_requirement", "") or ""
                    )
                    report_v3_obj = _run_red_team_review(
                        agent,
                        report_v3_obj,
                        echo_index,
                        intent=intent,
                        deterministic_findings=_deterministic_red_team_findings(
                            agent, report
                        ),
                    )
                    ReportManager.save_report_v3(report_v3_obj)
                    logger.info(
                        "generate_report: red_team_review abgeschlossen, "
                        "findings=%d, intent=%s, echo_index=%.3f",
                        len(report_v3_obj.red_team_findings),
                        intent.value,
                        echo_index,
                    )
        except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
            from ..run_budget import BudgetExceededError

            if isinstance(exc, BudgetExceededError):
                raise
            logger.warning("generate_report: red_team_review fehlgeschlagen: %r", exc)

        if report.status == ReportStatus.INCOMPLETE:
            terminal_stage = "incomplete"
            terminal_message = report.error or "Report generation incomplete"
        else:
            terminal_stage = "completed"
            terminal_message = "Report generation completed"
        ReportManager.update_progress(report_id, terminal_stage, 100, terminal_message, completed_sections=completed_section_titles)
        if progress_callback:
            progress_callback(terminal_stage, 100, terminal_message)
        if agent.console_logger:
            agent.console_logger.close()
            agent.console_logger = None
        return report

    except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
        from ..run_budget import BudgetExceededError

        if isinstance(e, BudgetExceededError):
            raise
        logger.error("Report generation failed: %s", e)
        report.status = ReportStatus.FAILED
        report.error = str(e)
        if agent.report_logger:
            agent.report_logger.log_error(str(e), "failed")
        try:
            ReportManager.save_report(report)
            ReportManager.update_progress(report_id, "failed", -1, f"Report generation failed: {e}", completed_sections=completed_section_titles)
        except Exception as exc:  # noqa: BLE001 — exc used in report status; error recorded
            logger.debug("workflow: save_report/update_progress failed in error handler, ignoring: %s", exc)
        if agent.console_logger:
            agent.console_logger.close()
            agent.console_logger = None
        return report


def chat(agent: Any, message: str, chat_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
    logger.info("Report agent chat: %s...", message[:50])
    chat_history = chat_history or []
    report_content = ""
    try:
        report = ReportManager.get_report_by_simulation(agent.simulation_id)
        if report and report.markdown_content:
            report_content = report.markdown_content[:15000]
            if len(report.markdown_content) > 15000:
                report_content += "\n\n... [reportcontenthasTruncate] ..."
    except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning("Could not read the report content: %s", e)

    system_prompt = agent.CHAT_SYSTEM_PROMPT_TEMPLATE.format(
        simulation_requirement=agent.simulation_requirement,
        report_content=report_content if report_content else "(nonereport)",
        tools_description=agent._get_tools_description(),
        language=Config.REPORT_LANGUAGE,
    )

    messages = [{"role": "system", "content": system_prompt}]
    for h in chat_history[-10:]:
        messages.append(h)
    messages.append({"role": "user", "content": message})

    tool_calls_made = []
    max_iterations = 2
    _raw_chat_toolcall_mode = (Config.REPORT_TOOLCALL_MODE or "native").strip().lower()
    _chat_toolcall_mode = (
        _raw_chat_toolcall_mode
        if _raw_chat_toolcall_mode in ("native", "xml")
        else "native"
    )

    for _ in range(max_iterations):
        if _chat_toolcall_mode == "native":
            chat_result = agent.llm.chat_with_tools(
                messages=messages,
                tools=agent._get_openai_tools_schema(),
                tool_choice="auto",
                temperature=0.5,
                max_tokens=4096,
                context="report",
            )
            response = chat_result["content"]
            native_calls = chat_result["tool_calls"]
            tool_calls = (
                [{"name": tc["name"], "parameters": tc["arguments"]} for tc in native_calls]
                if native_calls
                else agent._parse_tool_calls(response)
            )
        else:
            response = agent.llm.chat(messages=messages, temperature=0.5)
            tool_calls = []

        if response is None:
            return {
                "response": "",
                "tool_calls": tool_calls_made,
                "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made],
            }

        if _chat_toolcall_mode == "xml":
            tool_calls = agent._parse_tool_calls(response)

        if not tool_calls:
            clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', response, flags=re.DOTALL)
            clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
            return {
                "response": clean_response.strip(),
                "tool_calls": tool_calls_made,
                "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made],
            }
        tool_results = []
        for call in tool_calls[:1]:
            if len(tool_calls_made) >= agent.MAX_TOOL_CALLS_PER_CHAT:
                break
            result = agent._execute_tool(call["name"], call.get("parameters", {}))
            tool_results.append({"tool": call["name"], "result": result[:1500]})
            tool_calls_made.append(call)
        messages.append({"role": "assistant", "content": response})
        observation = "\n".join([f"[{r['tool']}result]\n{r['result']}" for r in tool_results])
        messages.append({"role": "user", "content": observation + agent.CHAT_OBSERVATION_SUFFIX})

    if _chat_toolcall_mode == "native":
        final_result = agent.llm.chat_with_tools(
            messages=messages,
            tools=agent._get_openai_tools_schema(),
            tool_choice="none",
            temperature=0.5,
            max_tokens=4096,
            context="report",
        )
        final_response = final_result["content"]
    else:
        final_response = agent.llm.chat(messages=messages, temperature=0.5)
    if final_response is None:
        final_response = ""
    clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL)
    clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
    return {
        "response": clean_response.strip(),
        "tool_calls": tool_calls_made,
        "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made],
    }


__all__ = [
    "_section_expects_quotes",
    "chat",
    "generate_report",
    "generate_section_metadata",
    "generate_section_react",
]
