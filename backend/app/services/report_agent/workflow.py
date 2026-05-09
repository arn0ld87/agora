from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from ...config import Config
from ...models.report import Report, ReportStatus
from ...utils.logger import get_logger
from .manager import ReportManager
from .planning import plan_outline as plan_outline_impl
from .schemas import (
    CURRENT_SCHEMA_VERSION,
    EvidenceMapModel,
    _section_schema_for,
    migrate_v1_to_v2,
)

logger = get_logger('agora.report_agent')


def generate_section_react(
    agent: Any,
    section,
    outline,
    previous_sections: List[str],
    progress_callback: Optional[Callable] = None,
    section_index: int = 0,
) -> str:
    logger.info(f"ReACT generating section: {section.title}")
    agent._current_section_index = section_index
    agent._active_section_evidence = []

    if agent.report_logger:
        agent.report_logger.log_section_start(section.title, section_index)

    system_prompt = agent.SECTION_SYSTEM_PROMPT_TEMPLATE.format(
        report_title=outline.title,
        report_summary=outline.summary,
        simulation_requirement=agent.simulation_requirement,
        section_title=section.title,
        tools_description=agent._get_tools_description(),
        language=Config.REPORT_LANGUAGE,
    )

    if previous_sections:
        previous_parts = []
        for sec in previous_sections:
            truncated = sec[:4000] + "..." if len(sec) > 4000 else sec
            previous_parts.append(truncated)
        previous_content = "\n\n---\n\n".join(previous_parts)
    else:
        previous_content = "(This is the first section)"

    user_prompt = agent.SECTION_USER_PROMPT_TEMPLATE.format(
        previous_content=previous_content,
        section_title=section.title,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    tool_calls_count = 0
    max_iterations = 5
    min_tool_calls = 3
    conflict_retries = 0
    used_tools = set()
    all_tools = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}
    report_context = f"Section Title: {section.title}\nSimulation Requirement: {agent.simulation_requirement}"

    for iteration in range(max_iterations):
        if progress_callback:
            progress_callback(
                "generating",
                int((iteration / max_iterations) * 100),
                f"Deep retrieval and writing in progress ({tool_calls_count}/{agent.MAX_TOOL_CALLS_PER_SECTION})",
            )

        response = agent.llm.chat(messages=messages, temperature=0.5, max_tokens=4096)
        if response is None:
            logger.warning(f"Section {section.title} round {iteration + 1} iteration: LLM returned None")
            if iteration < max_iterations - 1:
                messages.append({"role": "assistant", "content": "(Response empty)"})
                messages.append({"role": "user", "content": "Please continue generating content."})
                continue
            break

        logger.debug(f"LLM response: {response[:200]}...")
        tool_calls = agent._parse_tool_calls(response)
        has_tool_calls = bool(tool_calls)
        has_final_answer = "Final Answer:" in response

        if has_tool_calls and has_final_answer:
            conflict_retries += 1
            logger.warning(
                f"Section {section.title} round {iteration+1} : "
                f"LLM simultaneously output tool calls and Final Answer (round {conflict_retries} conflicts)"
            )
            if conflict_retries <= 2:
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
            logger.warning(
                f"Section {section.title}: consecutive {conflict_retries} conflicts，downgraded to truncate and execute first tool call"
            )
            first_tool_end = response.find('</tool_call>')
            if first_tool_end != -1:
                response = response[:first_tool_end + len('</tool_call>')]
                tool_calls = agent._parse_tool_calls(response)
                has_tool_calls = bool(tool_calls)
            has_final_answer = False
            conflict_retries = 0

        if agent.report_logger:
            agent.report_logger.log_llm_response(
                section_title=section.title,
                section_index=section_index,
                response=response,
                iteration=iteration + 1,
                has_tool_calls=has_tool_calls,
                has_final_answer=has_final_answer,
            )

        if has_final_answer:
            if tool_calls_count < min_tool_calls:
                messages.append({"role": "assistant", "content": response})
                unused_tools = all_tools - used_tools
                unused_hint = f"(These tools have not been used, recommend using them: {', '.join(unused_tools)}）" if unused_tools else ""
                messages.append({
                    "role": "user",
                    "content": agent.REACT_INSUFFICIENT_TOOLS_MSG.format(
                        tool_calls_count=tool_calls_count,
                        min_tool_calls=min_tool_calls,
                        unused_hint=unused_hint,
                    ),
                })
                continue

            final_answer = response.split("Final Answer:")[-1].strip()
            logger.info(f"Section {section.title} generation completed (tool calls: {tool_calls_count}times)")
            if agent.report_logger:
                agent.report_logger.log_section_content(
                    section_title=section.title,
                    section_index=section_index,
                    content=final_answer,
                    tool_calls_count=tool_calls_count,
                )
            agent._current_section_index = None
            return final_answer

        if has_tool_calls:
            if tool_calls_count >= agent.MAX_TOOL_CALLS_PER_SECTION:
                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": agent.REACT_TOOL_LIMIT_MSG.format(
                        tool_calls_count=tool_calls_count,
                        max_tool_calls=agent.MAX_TOOL_CALLS_PER_SECTION,
                    ),
                })
                continue

            call = tool_calls[0]
            if agent.report_logger:
                agent.report_logger.log_tool_call(
                    section_title=section.title,
                    section_index=section_index,
                    tool_name=call["name"],
                    parameters=call.get("parameters", {}),
                    iteration=iteration + 1,
                )
            result = agent._execute_tool(call["name"], call.get("parameters", {}), report_context=report_context)
            if agent.report_logger:
                agent.report_logger.log_tool_result(
                    section_title=section.title,
                    section_index=section_index,
                    tool_name=call["name"],
                    result=result,
                    iteration=iteration + 1,
                )
            tool_calls_count += 1
            used_tools.add(call['name'])
            unused_tools = all_tools - used_tools
            unused_hint = ""
            if unused_tools and tool_calls_count < agent.MAX_TOOL_CALLS_PER_SECTION:
                unused_hint = agent.REACT_UNUSED_TOOLS_HINT.format(unused_list="、".join(unused_tools))
            messages.append({"role": "assistant", "content": response})
            messages.append({
                "role": "user",
                "content": agent.REACT_OBSERVATION_TEMPLATE.format(
                    tool_name=call["name"],
                    result=result,
                    tool_calls_count=tool_calls_count,
                    max_tool_calls=agent.MAX_TOOL_CALLS_PER_SECTION,
                    used_tools_str=", ".join(used_tools),
                    unused_hint=unused_hint,
                ),
            })
            continue

        messages.append({"role": "assistant", "content": response})
        if tool_calls_count < min_tool_calls:
            unused_tools = all_tools - used_tools
            unused_hint = f"(These tools have not been used, recommend using them: {', '.join(unused_tools)}）" if unused_tools else ""
            messages.append({
                "role": "user",
                "content": agent.REACT_INSUFFICIENT_TOOLS_MSG_ALT.format(
                    tool_calls_count=tool_calls_count,
                    min_tool_calls=min_tool_calls,
                    unused_hint=unused_hint,
                ),
            })
            continue

        final_answer = response.strip()
        logger.info(f"Section {section.title} did not detectto 'Final Answer:' prefix, directlyadoptLLM outputas finalcontent（Tool call: {tool_calls_count}times)")
        if agent.report_logger:
            agent.report_logger.log_section_content(
                section_title=section.title,
                section_index=section_index,
                content=final_answer,
                tool_calls_count=tool_calls_count,
            )
        agent._current_section_index = None
        return final_answer

    logger.warning(f"Section {section.title} reachedmaximumiterationscount，Forcegenerate")
    messages.append({"role": "user", "content": agent.REACT_FORCE_FINAL_MSG})
    response = agent.llm.chat(messages=messages, temperature=0.5, max_tokens=4096)
    if response is None:
        final_answer = "(ThisSectiongeneratefailed: LLM returnedemptyresponse, pleaselaterretry)"
    elif "Final Answer:" in response:
        final_answer = response.split("Final Answer:")[-1].strip()
    else:
        final_answer = response
    if agent.report_logger:
        agent.report_logger.log_section_content(
            section_title=section.title,
            section_index=section_index,
            content=final_answer,
            tool_calls_count=tool_calls_count,
        )
    agent._current_section_index = None
    return final_answer


def generate_section_metadata(
    agent: Any,
    section_title: str,
    section_content: str,
    section_index: int,
) -> Dict[str, Any]:
    """Extrahiert strukturierte Metadaten aus einem fertig generierten Abschnitt.

    Wählt via :func:`_section_schema_for` das passende ReportV3-DTO aus
    und übergibt es als ``schema=`` an :meth:`LLMClient.chat_json`.
    Bei nicht-strict-fähigen Providern greift llm_client.py automatisch
    auf json_object zurück — kein manueller Fallback nötig.

    Args:
        agent: Report-Agent-Instanz mit ``llm``-Attribut.
        section_title: Titel des Abschnitts (steuert DTO-Auswahl).
        section_content: Markdown-Text des generierten Abschnitts.
        section_index: 1-basierter Abschnittsindex (für Logging).

    Returns:
        Validiertes dict aus dem gewählten DTO (via model_dump).
        Bei Fehler leeres dict — die Hauptgenerierung ist nicht blockiert.
    """
    schema_cls = _section_schema_for(section_title)
    schema_name = f"section_metadata_{schema_cls.__name__.lower()}"

    system_msg = (
        "Du bist ein Analyse-Assistent. Extrahiere strukturierte Metadaten "
        f"aus dem folgenden Report-Abschnitt. Halte dich streng an das "
        f"vorgegebene JSON-Schema ({schema_cls.__name__}). "
        "Verwende nur Informationen, die explizit im Text stehen. "
        "Erfinde keine Daten."
    )
    user_msg = (
        f"## Abschnittstitel\n{section_title}\n\n"
        f"## Inhalt\n{section_content[:6000]}"
    )

    try:
        result = agent.llm.chat_json(
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            schema=schema_cls,
            schema_name=schema_name,
            context="report",
        )
        logger.info(
            "generate_section_metadata: section=%d title=%r schema=%s",
            section_index,
            section_title,
            schema_cls.__name__,
        )
        return result
    except Exception as exc:
        logger.warning(
            "generate_section_metadata: section=%d schema=%s extraction failed: %r",
            section_index,
            schema_cls.__name__,
            exc,
        )
        return {}


def generate_report(agent: Any, progress_callback: Optional[Callable[[str, int, str], None]] = None, report_id: Optional[str] = None) -> Report:
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
    )

    completed_section_titles = []

    try:
        ReportManager._ensure_report_folder(report_id)
        agent.evidence_map = migrate_v1_to_v2(ReportManager.get_evidence_map(report_id)) or (
            EvidenceMapModel.model_validate({
                "schema_version": CURRENT_SCHEMA_VERSION,
                "report_id": report_id,
                "simulation_id": agent.simulation_id,
                "global_evidence": agent._collect_simulation_evidence_items(),
                "sections": [],
            }).model_dump(mode="json")
        )

        agent.report_logger = agent.ReportLogger(report_id)
        agent.report_logger.log_start(
            simulation_id=agent.simulation_id,
            graph_id=agent.graph_id,
            simulation_requirement=agent.simulation_requirement,
        )
        agent.console_logger = agent.ReportConsoleLogger(report_id)

        ReportManager.update_progress(report_id, "pending", 0, "Initializereport...", completed_sections=[])
        ReportManager.save_report(report)

        report.status = ReportStatus.PLANNING
        ReportManager.update_progress(report_id, "planning", 5, "Start planning report outline...", completed_sections=[])
        agent.report_logger.log_planning_start()
        if progress_callback:
            progress_callback("planning", 0, "Start planning report outline...")

        existing_outline = ReportManager.get_report(report_id)
        if existing_outline and existing_outline.outline:
            outline = existing_outline.outline
        else:
            outline = plan_outline_impl(
                agent,
                progress_callback=lambda stage, prog, msg: progress_callback(stage, prog // 5, msg) if progress_callback else None,
            )
            agent.report_logger.log_planning_complete(outline.to_dict())
            ReportManager.save_outline(report_id, outline)

        report.outline = outline
        ReportManager.update_progress(report_id, "planning", 15, f"Outline planning completed, total{len(outline.sections)}sections", completed_sections=[])
        ReportManager.save_report(report)

        report.status = ReportStatus.GENERATING
        total_sections = len(outline.sections)
        generated_sections = []
        existing_sections = {item["section_index"]: item["content"] for item in ReportManager.get_generated_sections(report_id)}
        for section_info in ReportManager.get_generated_sections(report_id):
            title = outline.sections[section_info["section_index"] - 1].title if outline.sections and section_info["section_index"] <= len(outline.sections) else ""
            completed_section_titles.append(title)
            generated_sections.append(section_info["content"])

        for i, section in enumerate(outline.sections):
            section_num = i + 1
            base_progress = 20 + int((i / total_sections) * 70)
            if section_num in existing_sections:
                section.content = ReportManager._clean_section_content(existing_sections[section_num], section.title)
                persisted_sections = (agent.evidence_map or {}).get("sections") or []
                has_persisted_evidence = any(s.get("section_index") == section_num for s in persisted_sections)
                if not has_persisted_evidence:
                    logger.warning(
                        "Section %s already exists on disk without persisted evidence; preserving markdown and leaving evidence unchanged",
                        section_num,
                    )
                continue
            ReportManager.update_progress(report_id, "generating", base_progress, f"generatinggenerateSection: {section.title} ({section_num}/{total_sections})", current_section=section.title, completed_sections=completed_section_titles)
            if progress_callback:
                progress_callback("generating", base_progress, f"generatinggenerateSection: {section.title} ({section_num}/{total_sections})")
            section_content = generate_section_react(
                agent,
                section=section,
                outline=outline,
                previous_sections=generated_sections,
                progress_callback=lambda stage, prog, msg: progress_callback(stage, base_progress + int(prog * 0.7 / total_sections), msg) if progress_callback else None,
                section_index=section_num,
            )
            # M11.8d: Strukturierte Metadaten-Extraktion via strict-schema chat_json.
            # Fehler blockieren nicht die Hauptgenerierung (generate_section_metadata
            # gibt bei Exception {} zurück). Metadaten werden im Report-Logger
            # für Provenance-Tracking gespeichert.
            section_meta = generate_section_metadata(
                agent,
                section_title=section.title,
                section_content=section_content,
                section_index=section_num,
            )
            if section_meta and agent.report_logger and hasattr(agent.report_logger, "log_section_metadata"):
                agent.report_logger.log_section_metadata(
                    section_title=section.title,
                    section_index=section_num,
                    metadata=section_meta,
                )
            section.content = section_content
            generated_sections.append(f"## {section.title}\n\n{section_content}")
            ReportManager.save_section(report_id, section_num, section)
            agent._save_evidence_section(report_id, section_num, section.title, section_content)
            completed_section_titles.append(section.title)
            if agent.report_logger:
                agent.report_logger.log_section_full_complete(
                    section_title=section.title,
                    section_index=section_num,
                    full_content=f"## {section.title}\n\n{section_content}".strip(),
                )
            ReportManager.update_progress(report_id, "generating", base_progress + int(70 / total_sections), f"Section {section.title} completed", current_section=None, completed_sections=completed_section_titles)

        if progress_callback:
            progress_callback("generating", 95, "generatingassemblecompletereport...")
        ReportManager.update_progress(report_id, "generating", 95, "generatingassemblecompletereport...", completed_sections=completed_section_titles)
        report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
        report.status = ReportStatus.COMPLETED
        report.completed_at = datetime.now().isoformat()
        total_time_seconds = (datetime.now() - start_time).total_seconds()
        if agent.report_logger:
            agent.report_logger.log_report_complete(total_sections=total_sections, total_time_seconds=total_time_seconds)
        ReportManager.save_report(report)
        ReportManager.update_progress(report_id, "completed", 100, "reportgeneratecomplete", completed_sections=completed_section_titles)
        if progress_callback:
            progress_callback("completed", 100, "reportgeneratecomplete")
        if agent.console_logger:
            agent.console_logger.close()
            agent.console_logger = None
        return report

    except Exception as e:
        logger.error(f"reportgeneratefailed: {str(e)}")
        report.status = ReportStatus.FAILED
        report.error = str(e)
        if agent.report_logger:
            agent.report_logger.log_error(str(e), "failed")
        try:
            ReportManager.save_report(report)
            ReportManager.update_progress(report_id, "failed", -1, f"reportgeneratefailed: {str(e)}", completed_sections=completed_section_titles)
        except Exception:
            pass
        if agent.console_logger:
            agent.console_logger.close()
            agent.console_logger = None
        return report


def chat(agent: Any, message: str, chat_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
    logger.info(f"Report Agentchat: {message[:50]}...")
    chat_history = chat_history or []
    report_content = ""
    try:
        report = ReportManager.get_report_by_simulation(agent.simulation_id)
        if report and report.markdown_content:
            report_content = report.markdown_content[:15000]
            if len(report.markdown_content) > 15000:
                report_content += "\n\n... [reportcontenthasTruncate] ..."
    except Exception as e:
        logger.warning(f"getreportcontentfailed: {e}")

    system_prompt = agent.CHAT_SYSTEM_PROMPT_TEMPLATE.format(
        simulation_requirement=agent.simulation_requirement,
        report_content=report_content if report_content else "（nonereport）",
        tools_description=agent._get_tools_description(),
        language=Config.REPORT_LANGUAGE,
    )

    messages = [{"role": "system", "content": system_prompt}]
    for h in chat_history[-10:]:
        messages.append(h)
    messages.append({"role": "user", "content": message})

    tool_calls_made = []
    max_iterations = 2
    for _ in range(max_iterations):
        response = agent.llm.chat(messages=messages, temperature=0.5)
        if response is None:
            return {
                "response": "",
                "tool_calls": tool_calls_made,
                "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made],
            }
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
    "chat",
    "generate_report",
    "generate_section_metadata",
    "generate_section_react",
]
