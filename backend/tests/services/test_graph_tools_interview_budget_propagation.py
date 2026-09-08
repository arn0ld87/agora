"""Regressionstest Issue #1478 (Codex P1) — Budget-Abbruch erreicht den Run.

Vor dem Fix fing ``GraphToolsService.interview_agents`` (``graph_tools.py``)
jede Exception aus ``SimulationRunner.interview_agents_batch`` — inklusive
``BudgetExceededError`` — mit einem breiten ``except Exception``-Block ab und
verwandelte sie in eine weiche ``result.summary``. Ein erschoepftes
Hard-Budget ist aber kein Interview-Fehler mit Fallback, sondern das Ende des
Laufs: ``report_generation.py`` sieht die Exception nie und markiert den Run
nie als ``stopped``/``termination_reason=budget_*``.

Analog zum bereits gehaerteten ``_select_agents_for_interview``-Pfad
(Issue #978) muss ``BudgetExceededError`` auch hier hart durchgereicht
werden.
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from app.services.graph_tools import GraphToolsService
from app.services.run_budget import BudgetExceededError
from app.services.simulation_runner import SimulationRunner


def _make_service(profiles: List[Dict[str, Any]]) -> GraphToolsService:
    svc = GraphToolsService.__new__(GraphToolsService)
    svc._llm_client = MagicMock()
    svc.panel_tracker = None
    svc._load_agent_profiles = MagicMock(return_value=profiles)
    svc._select_agents_for_interview = MagicMock(
        return_value=(profiles, list(range(len(profiles))), "reasoning")
    )
    svc._apply_panel_rotation = MagicMock(
        side_effect=lambda **kwargs: (
            kwargs["selected_indices"],
            kwargs["selected_agents"],
            kwargs["selection_reasoning"],
        )
    )
    return svc


class TestInterviewAgentsBudgetPropagation:
    def test_budget_exceeded_error_propagates_instead_of_soft_summary(self) -> None:
        profiles = [{"user_id": 0, "profession": "Tester", "realname": "T"}]
        svc = _make_service(profiles)

        with patch.object(
            SimulationRunner, "interviews_possible", return_value=True
        ), patch.object(
            SimulationRunner,
            "interview_agents_batch",
            side_effect=BudgetExceededError("calls", 11, 10),
        ):
            with pytest.raises(BudgetExceededError):
                svc.interview_agents(
                    simulation_id="sim_budget_xyz",
                    interview_requirement="Wie bewerten Sie X?",
                    simulation_requirement="Kontext",
                    max_agents=1,
                    custom_questions=["Q1?"],
                )
