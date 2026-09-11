"""Focused interview helper implementations for :mod:`app.services.graph_tools`.

The public compatibility surface stays on ``GraphToolsService``.  This module
contains the file-loading and LLM-backed helper implementations so the service
facade can remain small without changing historical call sites or monkeypatch
hooks.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ...utils.logger import get_logger
from ..interview_panel import InterviewPanelTracker
from .graph_dtos import AgentInterview

logger = get_logger("agora.graph_tools")


def clean_tool_call_response(response: str) -> str:
    """Clean JSON tool-call wrappers in agent responses."""
    if not response or not response.strip().startswith("{"):
        return response
    text = response.strip()
    if "tool_name" not in text[:80]:
        return response

    import re as _re

    try:
        data = json.loads(text)
        if isinstance(data, dict) and "arguments" in data:
            for key in ("content", "text", "body", "message", "reply"):
                if key in data["arguments"]:
                    return str(data["arguments"][key])
    except (json.JSONDecodeError, KeyError, TypeError):
        match = _re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        if match:
            return match.group(1).replace("\\n", "\n").replace('\\"', '"')
    return response


def load_agent_profiles(
    simulation_id: str,
    *,
    service_dir: str,
) -> List[Dict[str, Any]]:
    """Load persisted Reddit or Twitter agent profiles for a simulation."""
    import csv
    import os

    sim_dir = os.path.join(
        service_dir,
        f"../../uploads/simulations/{simulation_id}",
    )

    profiles: List[Dict[str, Any]] = []

    reddit_profile_path = os.path.join(sim_dir, "reddit_profiles.json")
    if os.path.exists(reddit_profile_path):
        try:
            with open(reddit_profile_path, "r", encoding="utf-8") as file_handle:
                profiles = json.load(file_handle)
            logger.info(
                "Loaded %s profiles from reddit_profiles.json",
                len(profiles),
            )
            return profiles
        except Exception as exc:  # noqa: BLE001 — logged, fallback to CSV intended
            logger.warning("Failed to read reddit_profiles.json: %s", exc)

    twitter_profile_path = os.path.join(sim_dir, "twitter_profiles.csv")
    if os.path.exists(twitter_profile_path):
        try:
            with open(twitter_profile_path, "r", encoding="utf-8") as file_handle:
                reader = csv.DictReader(file_handle)
                for row in reader:
                    profiles.append(
                        {
                            "realname": row.get("name", ""),
                            "username": row.get("username", ""),
                            "bio": row.get("description", ""),
                            "persona": row.get("user_char", ""),
                            "profession": "Unknown",
                        }
                    )
            logger.info(
                "Loaded %s profiles from twitter_profiles.csv",
                len(profiles),
            )
            return profiles
        except Exception as exc:  # noqa: BLE001 — logged, empty fallback intended
            logger.warning("Failed to read twitter_profiles.csv: %s", exc)

    return profiles


def select_agents_for_interview(
    profiles: List[Dict[str, Any]],
    interview_requirement: str,
    simulation_requirement: str,
    max_agents: int,
    llm: Any,
    panel_tracker: Optional[InterviewPanelTracker] = None,
) -> tuple:
    """Use the configured LLM to select agents for an interview panel."""
    agent_summaries = []
    for index, profile in enumerate(profiles):
        summary = {
            "index": index,
            "name": profile.get("realname", profile.get("username", f"Agent_{index}")),
            "profession": profile.get("profession", "Unknown"),
            "bio": profile.get("bio", "")[:200],
            "interested_topics": profile.get("interested_topics", []),
        }
        if panel_tracker is not None:
            summary["times_interviewed"] = panel_tracker.usage(
                panel_tracker.persona_key(profile)
            )
        agent_summaries.append(summary)

    rotation_rule = (
        "\n5. Diversify across report sections: agents with "
        '"times_interviewed": 0 have NOT yet been interviewed in this '
        "report run and must be strongly preferred. Reuse an already "
        "interviewed agent only for a clearly different aspect."
        if panel_tracker is not None
        else ""
    )

    system_prompt = (
        """You are a professional interview planning expert. Your task is to select the most suitable Agents for interview from the simulated Agent list based on the interview requirements.

Selection Criteria:
1. Agent's identity/profession is relevant to the interview topic
2. Agent may hold unique or valuable perspectives
3. Select diverse perspectives (e.g., supporters, opposers, neutral, experts, etc.)
4. Prioritize roles directly related to the event"""
        + rotation_rule
        + """

Return JSON format:
{
    "selected_indices": [List of indices of selected Agents],
    "reasoning": "Brief explanation (max 2 short sentences, 200 characters total)"
}

Keep `reasoning` deliberately short — the truncation budget caps the payload."""
    )

    user_prompt = f"""Interview Requirement:
{interview_requirement}

Simulation Background:
{simulation_requirement if simulation_requirement else "Not provided"}

Available Agent List ({len(agent_summaries)} total):
{json.dumps(agent_summaries, ensure_ascii=False, indent=2)}

Please select up to {max_agents} most suitable Agents for interview and explain your selection rationale."""

    try:
        response = llm.chat_json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=32768,
        )

        selected_indices = response.get("selected_indices", [])[:max_agents]
        reasoning = response.get(
            "reasoning",
            "Automatically selected based on relevance",
        )

        selected_agents = []
        valid_indices = []
        for index in selected_indices:
            if 0 <= index < len(profiles):
                selected_agents.append(profiles[index])
                valid_indices.append(index)

        return selected_agents, valid_indices, reasoning

    except Exception as exc:  # noqa: BLE001 — budget errors re-raised, fallback intentional
        from ..run_budget import BudgetExceededError

        if isinstance(exc, BudgetExceededError):
            raise
        logger.warning(
            "LLM agent selection failed, using default selection: %s",
            exc,
        )
        selected = profiles[:max_agents]
        indices = list(range(min(max_agents, len(profiles))))
        return selected, indices, "Using default selection strategy"


def generate_interview_questions(
    interview_requirement: str,
    simulation_requirement: str,
    selected_agents: List[Dict[str, Any]],
    llm: Any,
) -> List[str]:
    """Use the configured LLM to generate interview questions."""
    agent_roles = [agent.get("profession", "Unknown") for agent in selected_agents]

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

Interview Subject Roles: {", ".join(agent_roles)}

Please generate 3-5 interview questions."""

    try:
        response = llm.chat_json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.5,
            max_tokens=8192,
        )
        return response.get(
            "questions",
            [f"What is your perspective on {interview_requirement}?"],
        )

    except Exception as exc:  # noqa: BLE001 — budget errors re-raised, fallback intentional
        from ..run_budget import BudgetExceededError

        if isinstance(exc, BudgetExceededError):
            raise
        logger.warning("Failed to generate interview questions: %s", exc)
        return [
            f"What is your perspective on {interview_requirement}?",
            "What impact does this have on you or the group you represent?",
            "How do you think this issue should be solved or improved?",
        ]


def generate_interview_summary(
    interviews: List[AgentInterview],
    interview_requirement: str,
    llm: Any,
) -> str:
    """Generate a concise synthesis of completed interviews."""
    if not interviews:
        return "No interviews completed"

    interview_texts = []
    for interview in interviews:
        interview_texts.append(
            f"[{interview.agent_name} ({interview.agent_role})]\n"
            f"{interview.response[:500]}"
        )

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
        return llm.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=800,
            enforce_token_floor=False,
        )

    except Exception as exc:  # noqa: BLE001 — budget errors re-raised, fallback intentional
        from ..run_budget import BudgetExceededError

        if isinstance(exc, BudgetExceededError):
            raise
        logger.warning("Failed to generate interview summary: %s", exc)
        return f"Interviewed {len(interviews)} interviewees, including: " + ", ".join(
            interview.agent_name for interview in interviews
        )
