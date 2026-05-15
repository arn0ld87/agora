from __future__ import annotations

import json
from typing import Any, Callable, Optional

from ...config import Config
from ...contracts.report_contract import ReportOutlineModel, ReportOutlineSectionModel
from ...models.report import ReportOutline, ReportSection
from ...utils.logger import get_logger
from ..report_prompts import DEFAULT_REPORT_SECTIONS, format_required_sections
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

    sections = required_sections if required_sections is not None else DEFAULT_REPORT_SECTIONS
    system_prompt = PLAN_SYSTEM_PROMPT_TEMPLATE.replace("{language}", Config.REPORT_LANGUAGE)
    user_prompt = PLAN_USER_PROMPT_TEMPLATE.format(
        simulation_requirement=agent.simulation_requirement,
        total_nodes=context.get('graph_statistics', {}).get('total_nodes', 0),
        total_edges=context.get('graph_statistics', {}).get('total_edges', 0),
        entity_types=list(context.get('graph_statistics', {}).get('entity_types', {}).keys()),
        total_entities=context.get('total_entities', 0),
        related_facts_json=json.dumps(context.get('related_facts', [])[:10], ensure_ascii=False, indent=2),
        required_sections=format_required_sections(sections),
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
                title=(section_data.get("title") or "Section").strip() or "Section",
                description=raw_desc if raw_desc else "—",
            ))

        pydantic_outline = ReportOutlineModel(
            title=(response.get("title") or "Simulation Analysis Report").strip() or "Simulation Analysis Report",
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

        # M11.8a-Followup auf Gemini-MEDIUM (PR #335): Section-Cap (Min 2 / Max 5)
        # ist entfernt, aber ein leeres Outline-Array darf nicht durchgehen — ein
        # Report ohne Sections ist trivial invalid. Harter Vertrag (len ==
        # len(required_sections)) folgt erst in M11.8d (Strict-Schema-Forced-Output).
        if not result_sections:
            raise ValueError(
                "plan_outline() received empty sections from LLM; refusing to "
                "build an outline with zero entries (M11.8a)."
            )

        outline = ReportOutline(
            title=pydantic_outline.title,
            summary=pydantic_outline.summary,
            sections=result_sections,
        )

        if progress_callback:
            progress_callback("planning", 100, "Outline planning completed")

        logger.info(f"Outline planning completed: {len(result_sections)} sections")
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
            ],
        )


__all__ = ["plan_outline"]
