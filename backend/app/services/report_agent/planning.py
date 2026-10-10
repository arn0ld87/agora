from __future__ import annotations

import json
from typing import Any, Callable, Optional

from ...config import Config
from ...contracts.report_contract import ReportOutlineModel, ReportOutlineSectionModel
from ...models.report import ReportOutline, ReportSection
from ...utils.logger import get_logger
from ..report_prompts import format_required_sections
from .prompts import PLAN_SYSTEM_PROMPT_TEMPLATE, PLAN_USER_PROMPT_TEMPLATE
from .schemas import PlanResponse

logger = get_logger('agora.report_agent')


def plan_outline(
    agent: Any,
    progress_callback: Optional[Callable] = None,
    required_sections: Optional[list[tuple[str, str]]] = None,
) -> ReportOutline:
    logger.info("Starting to plan report outline...")

    if progress_callback:
        progress_callback("planning", 0, "Analyzing simulation requirements...")

    context = agent.graph_tools.get_simulation_context(
        graph_id=agent.graph_id,
        simulation_requirement=agent.simulation_requirement,
    )

    if progress_callback:
        progress_callback("planning", 30, "Generating report outline...")

    section_instructions = (
        "Explicit required_sections (exact titles and order):\n"
        + format_required_sections(required_sections)
        if required_sections is not None
        else "No explicit required_sections. Choose the sections from the question and available data."
    )
    system_prompt = PLAN_SYSTEM_PROMPT_TEMPLATE.replace("{language}", Config.REPORT_LANGUAGE)
    user_prompt = PLAN_USER_PROMPT_TEMPLATE.format(
        simulation_requirement=agent.simulation_requirement,
        total_nodes=context.get('graph_statistics', {}).get('total_nodes', 0),
        total_edges=context.get('graph_statistics', {}).get('total_edges', 0),
        entity_types=list(context.get('graph_statistics', {}).get('entity_types', {}).keys()),
        total_entities=context.get('total_entities', 0),
        related_facts_json=json.dumps(context.get('related_facts', [])[:10], ensure_ascii=False, indent=2),
        required_sections=section_instructions,
    )

    try:
        # M11.8d / Smoke-02: strict json_schema mode — PlanResponse DTO erzwingt Struktur.
        # max_tokens=16384 verhindert Token-Cap-Truncation bei Ollama-Fallback-Modellen.
        # force_no_thinking=True deaktiviert Ollama-Thinking-Mode, damit der Token-Cap
        # nicht durch Thought-Tokens belegt wird und kein leeres JSON entsteht.
        # Bei nicht-strict-fähigen Providern macht llm_client.py automatisch
        # Fallback auf json_object (kein Inline-Schema-String nötig).
        _messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            response = agent.llm.chat_json(
                messages=_messages,
                temperature=0.2,
                max_tokens=16384,
                schema=PlanResponse,
                schema_name="report_plan",
                force_no_thinking=True,
            )
        except ValueError as _first_err:
            _msg = str(_first_err)
            if "len=0" in _msg or "Invalid JSON format from LLM" in _msg:
                logger.warning(
                    "plan_outline: first chat_json attempt failed with empty/invalid "
                    "response (%s) — retrying once with max_tokens=24576, temperature=0.1",
                    _msg[:120],
                )
                response = agent.llm.chat_json(
                    messages=_messages,
                    temperature=0.1,
                    max_tokens=24576,
                    schema=PlanResponse,
                    schema_name="report_plan",
                    force_no_thinking=True,
                )
            else:
                raise

        if progress_callback:
            progress_callback("planning", 80, "Parsing outline structure...")

        # Parse outline — validate via Pydantic contract first, then
        # convert to ReportSection for downstream processing with content.
        # chat_json already validated response against PlanResponse; safe to use .get().
        pydantic_sections = []
        for section_data in response.get("sections", []):
            raw_desc = (section_data.get("description") or "").strip()
            pydantic_sections.append(ReportOutlineSectionModel(
                title=section_data.get("title") or "",
                description=raw_desc if raw_desc else "—",
            ))

        pydantic_outline = ReportOutlineModel(
            title=response.get("title") or "",
            summary=(response.get("summary") or "").strip() or "—",
            sections=pydantic_sections,
        )

        result_sections = [
            ReportSection(
                title=s.title,
                description=s.description,
            )
            for s in pydantic_outline.sections
        ]

        if required_sections is not None:
            expected_titles = [title.strip() for title, _ in required_sections]
            if [section.title for section in pydantic_outline.sections] != expected_titles:
                raise ValueError("Report outline does not match explicit required_sections titles and order")

        outline = ReportOutline(
            title=pydantic_outline.title,
            summary=pydantic_outline.summary,
            sections=result_sections,
        )

        if progress_callback:
            progress_callback("planning", 100, "Outline planning completed")

        logger.info(f"Outline planning completed: {len(result_sections)} sections")
        return outline

    except Exception as e:  # noqa: BLE001 — logged and propagated to the workflow FAILED handler
        logger.error("Outline planning failed: %s", e)
        raise



__all__ = ["plan_outline"]
