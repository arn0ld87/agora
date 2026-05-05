from __future__ import annotations

import json
from typing import Any, Callable, Optional

from ...config import Config
from ...models.report import ReportOutline, ReportSection
from ...utils.logger import get_logger
from .prompts import PLAN_SYSTEM_PROMPT_TEMPLATE, PLAN_USER_PROMPT_TEMPLATE

logger = get_logger('agora.report_agent')


def plan_outline(agent: Any, progress_callback: Optional[Callable] = None) -> ReportOutline:
    logger.info("Starting to plan report outline...")

    if progress_callback:
        progress_callback("planning", 0, "Analyzing simulation requirements...")

    context = agent.graph_tools.get_simulation_context(
        graph_id=agent.graph_id,
        simulation_requirement=agent.simulation_requirement,
    )

    if progress_callback:
        progress_callback("planning", 30, "Generating report outline...")

    system_prompt = PLAN_SYSTEM_PROMPT_TEMPLATE.replace("{language}", Config.REPORT_LANGUAGE)
    user_prompt = PLAN_USER_PROMPT_TEMPLATE.format(
        simulation_requirement=agent.simulation_requirement,
        total_nodes=context.get('graph_statistics', {}).get('total_nodes', 0),
        total_edges=context.get('graph_statistics', {}).get('total_edges', 0),
        entity_types=list(context.get('graph_statistics', {}).get('entity_types', {}).keys()),
        total_entities=context.get('total_entities', 0),
        related_facts_json=json.dumps(context.get('related_facts', [])[:10], ensure_ascii=False, indent=2),
    )

    try:
        response = agent.llm.chat_json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )

        if progress_callback:
            progress_callback("planning", 80, "Parsing outline structure...")

        sections = []
        for section_data in response.get("sections", []):
            title = (section_data.get("title", "") or "").strip()
            if title:
                sections.append(ReportSection(title=title, content=""))

        title = (response.get("title", "Simulation Analysis Report") or "").strip()
        summary = (response.get("summary", "") or "").strip()
        if not title or not summary or not (2 <= len(sections) <= 5):
            raise ValueError(
                f"invalid outline response: title={bool(title)} summary={bool(summary)} sections={len(sections)}"
            )

        outline = ReportOutline(
            title=title,
            summary=summary,
            sections=sections,
        )

        if progress_callback:
            progress_callback("planning", 100, "Outline planning completed")

        logger.info(f"Outline planning completed: {len(sections)} sections")
        return outline

    except Exception as e:
        logger.error(f"Outline planning failed: {str(e)}")
        return ReportOutline(
            title="Scenario Evaluation Report",
            summary="Emerging trends and risk analysis based on simulation observations",
            sections=[
                ReportSection(title="Evaluation Scenario and Core Findings"),
                ReportSection(title="Persona Reaction Analysis"),
                ReportSection(title="Trend Outlook and Risk Warning"),
            ],
        )


__all__ = ["plan_outline"]
