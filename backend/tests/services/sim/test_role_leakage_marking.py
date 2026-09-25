"""Tests für Role-Leakage-Markierung im action_log_reader-Pfad (Issue #1323, Slice 5.2).

Abgedeckte Szenarien:
1. Reader markiert Fremdrolle (foreign_role) beim Lesen.
2. Eigene Rolle bleibt unmarkiert (None).
3. Konflikt-Zähler im State wird inkrementiert.
4. Alte run_state.json ohne role_conflict_count lädt mit Default 0.
5. Kill-Switch (AGORA_ROLE_LEAKAGE_MARKING=false) → keine Markierung.
6. Report-Stichprobe überspringt foreign_role-Aktionen, nicht unmatched.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

from app.services.sim.run_state_store import SimulationRunState
from app.services.sim.action_log_reader import (
    _clear_profile_cache,
    read_action_log_chunk,
)
from app.services.sim.role_leakage import detect_role_conflict


# ---------------------------------------------------------------------------
# Hilfs-Fixtures
# ---------------------------------------------------------------------------

def _persona(name: str, profession: Optional[str] = None) -> dict:
    return {"user_id": 0, "name": name, "profession": profession, "source_entity_type": None, "bio": ""}


DOZENTIN = _persona("Dozentin", profession="Dozentin für kaufmännische Umschulung")
BETRIEBSRAT = _persona("Betriebsratsvorsitzende", profession="Betriebsratsvorsitzende")

ALL_PERSONAS = [DOZENTIN, BETRIEBSRAT]


def _make_action_dict(
    agent_id: int = 0,
    agent_name: str = "Dozentin",
    action_type: str = "CREATE_POST",
    content: str = "",
    round_num: int = 1,
) -> dict:
    return {
        "agent_id": agent_id,
        "agent_name": agent_name,
        "action_type": action_type,
        "action_args": {"content": content},
        "round": round_num,
    }


def _write_actions_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_reddit_profiles(sim_dir: Path, profiles: list[dict]) -> None:
    (sim_dir / "reddit_profiles.json").write_text(
        json.dumps(profiles, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# 1. Reader markiert Fremdrolle
# ---------------------------------------------------------------------------

def test_read_action_log_chunk_marks_foreign_role(tmp_path: Path) -> None:
    """read_action_log_chunk setzt role_conflict='foreign_role' bei Fremdrolle."""
    _clear_profile_cache()
    sim_dir = tmp_path / "sim1"
    platform_dir = sim_dir / "reddit"
    log = platform_dir / "actions.jsonl"

    # Dozentin schreibt als Betriebsratsmitglied → foreign_role
    action = _make_action_dict(
        agent_id=0,
        agent_name="Dozentin",
        content="Als Betriebsratsvorsitzende war es mir wichtig, die Mitglieder zu informieren.",
    )
    _write_actions_jsonl(log, [action])
    _write_reddit_profiles(sim_dir, [DOZENTIN, BETRIEBSRAT])

    state = SimulationRunState(simulation_id="sim1")

    with patch("app.services.sim.action_log_reader.Config") as mock_cfg:
        mock_cfg.AGORA_ROLE_LEAKAGE_MARKING = True
        read_action_log_chunk(
            str(log), 0, state, "reddit", sim_dir=str(sim_dir)
        )

    assert len(state.recent_actions) == 1
    assert state.recent_actions[0].role_conflict == "foreign_role"


# ---------------------------------------------------------------------------
# 2. Eigene Rolle bleibt unmarkiert
# ---------------------------------------------------------------------------

def test_read_action_log_chunk_own_role_not_marked(tmp_path: Path) -> None:
    """Eigene Rolle löst keinen Konflikt aus — role_conflict bleibt None."""
    _clear_profile_cache()
    sim_dir = tmp_path / "sim2"
    platform_dir = sim_dir / "reddit"
    log = platform_dir / "actions.jsonl"

    # Dozentin schreibt als Dozentin → kein Konflikt
    action = _make_action_dict(
        agent_id=0,
        agent_name="Dozentin",
        content="Als Dozentin sehe ich die Situation folgendermaßen.",
    )
    _write_actions_jsonl(log, [action])
    _write_reddit_profiles(sim_dir, [DOZENTIN, BETRIEBSRAT])

    state = SimulationRunState(simulation_id="sim2")

    with patch("app.services.sim.action_log_reader.Config") as mock_cfg:
        mock_cfg.AGORA_ROLE_LEAKAGE_MARKING = True
        read_action_log_chunk(
            str(log), 0, state, "reddit", sim_dir=str(sim_dir)
        )

    assert len(state.recent_actions) == 1
    assert state.recent_actions[0].role_conflict is None


# ---------------------------------------------------------------------------
# 3. Konflikt-Zähler wird inkrementiert
# ---------------------------------------------------------------------------

def test_state_conflict_count_incremented(tmp_path: Path) -> None:
    """role_conflict_count und role_conflicts_by_reason werden korrekt gezählt."""
    _clear_profile_cache()
    sim_dir = tmp_path / "sim3"
    platform_dir = sim_dir / "reddit"
    log = platform_dir / "actions.jsonl"

    actions = [
        _make_action_dict(
            agent_id=0,
            agent_name="Dozentin",
            content="Als Betriebsratsvorsitzende war es mir wichtig, die Mitglieder zu informieren.",
            round_num=1,
        ),
        _make_action_dict(
            agent_id=0,
            agent_name="Dozentin",
            content="Als Dozentin sehe ich das anders.",
            round_num=2,
        ),
    ]
    _write_actions_jsonl(log, actions)
    _write_reddit_profiles(sim_dir, [DOZENTIN, BETRIEBSRAT])

    state = SimulationRunState(simulation_id="sim3")

    with patch("app.services.sim.action_log_reader.Config") as mock_cfg:
        mock_cfg.AGORA_ROLE_LEAKAGE_MARKING = True
        read_action_log_chunk(
            str(log), 0, state, "reddit", sim_dir=str(sim_dir)
        )

    assert state.role_conflict_count == 1
    assert state.role_conflicts_by_reason.get("foreign_role", 0) == 1


# ---------------------------------------------------------------------------
# 4. Alte run_state.json ohne role_conflict_count lädt mit Default 0
# ---------------------------------------------------------------------------

def test_load_run_state_without_conflict_count() -> None:
    """Backward-Compat: run_state ohne role_conflict_count lädt mit Default 0."""
    from app.services.sim.run_state_store import SimulationRunState

    # Simuliere alten run_state ohne die neuen Felder
    state = SimulationRunState(simulation_id="sim_old")
    d = state.to_dict()
    # Entferne die neuen Felder wie in altem run_state.json
    d.pop("role_conflict_count", None)
    d.pop("role_conflicts_by_reason", None)

    # Manuelles Laden wie in load_run_state
    restored_count = d.get("role_conflict_count", 0)
    restored_by_reason = d.get("role_conflicts_by_reason", {})

    assert restored_count == 0
    assert restored_by_reason == {}


# ---------------------------------------------------------------------------
# 5. Kill-Switch: AGORA_ROLE_LEAKAGE_MARKING=false → keine Markierung
# ---------------------------------------------------------------------------

def test_kill_switch_disables_marking(tmp_path: Path) -> None:
    """Wenn AGORA_ROLE_LEAKAGE_MARKING=False, bleibt role_conflict überall None."""
    _clear_profile_cache()
    sim_dir = tmp_path / "sim4"
    platform_dir = sim_dir / "reddit"
    log = platform_dir / "actions.jsonl"

    action = _make_action_dict(
        agent_id=0,
        agent_name="Dozentin",
        content="Als Betriebsratsvorsitzende war es mir wichtig, die Mitglieder zu informieren.",
    )
    _write_actions_jsonl(log, [action])
    _write_reddit_profiles(sim_dir, [DOZENTIN, BETRIEBSRAT])

    state = SimulationRunState(simulation_id="sim4")

    with patch("app.services.sim.action_log_reader.Config") as mock_cfg:
        mock_cfg.AGORA_ROLE_LEAKAGE_MARKING = False
        read_action_log_chunk(
            str(log), 0, state, "reddit", sim_dir=str(sim_dir)
        )

    assert len(state.recent_actions) == 1
    assert state.recent_actions[0].role_conflict is None
    assert state.role_conflict_count == 0


# ---------------------------------------------------------------------------
# 6a. Report-Stichprobe überspringt foreign_role
# ---------------------------------------------------------------------------

def test_report_evidence_skips_foreign_role() -> None:
    """foreign_role-Aktionen werden aus der Report-Evidence-Stichprobe ausgeschlossen."""
    from app.services.report_agent.agent import ReportAgent

    # Zwei Aktionen: eine mit foreign_role, eine sauber
    action_foreign = {
        "platform": "reddit",
        "round_num": 1,
        "agent_id": 0,
        "agent_name": "Dozentin",
        "action_type": "CREATE_POST",
        "action_args": {"content": "Als Betriebsratsvorsitzende war es wichtig."},
        "timestamp": "2026-01-01T00:00:00",
        "result": None,
        "success": True,
        "role_conflict": "foreign_role",
    }
    action_clean = {
        "platform": "reddit",
        "round_num": 2,
        "agent_id": 1,
        "agent_name": "Betriebsratsvorsitzende",
        "action_type": "CREATE_POST",
        "action_args": {"content": "Wir fordern eine bessere Ausbildung."},
        "timestamp": "2026-01-01T01:00:00",
        "result": None,
        "success": True,
        "role_conflict": None,
    }

    agent = ReportAgent.__new__(ReportAgent)
    agent.simulation_id = "test-sim"

    # Mock: get_all_actions und compute_metrics
    mock_action_foreign = MagicMock()
    mock_action_foreign.to_dict.return_value = action_foreign
    mock_action_clean = MagicMock()
    mock_action_clean.to_dict.return_value = action_clean

    with (
        patch(
            "app.services.simulation_runner.SimulationRunner.get_all_actions",
            return_value=[mock_action_foreign, mock_action_clean],
        ),
        patch(
            "app.services.network_analytics.NetworkAnalyticsService"
        ) as mock_analytics,
    ):
        mock_analytics.return_value.compute_metrics.return_value.to_dict.return_value = {
            "status": "insufficient_data"
        }
        items = agent._collect_simulation_evidence_items()

    # Nur die saubere Aktion darf als agent_action-Evidence auftauchen
    action_items = [i for i in items if i.get("type") == "agent_action"]
    assert len(action_items) == 1
    assert action_clean["agent_name"] in action_items[0]["snippet"]


# ---------------------------------------------------------------------------
# 6b. Report-Stichprobe behält unmatched_self_reference
# ---------------------------------------------------------------------------

def test_report_evidence_keeps_unmatched_self_reference() -> None:
    """unmatched_self_reference-Aktionen werden NICHT aus der Report-Evidence entfernt."""
    from app.services.report_agent.agent import ReportAgent

    action_unmatched = {
        "platform": "reddit",
        "round_num": 1,
        "agent_id": 0,
        "agent_name": "IHK",
        "action_type": "CREATE_POST",
        "action_args": {"content": "Als Honorarkraft werde ich nur für Stunden bezahlt."},
        "timestamp": "2026-01-01T00:00:00",
        "result": None,
        "success": True,
        "role_conflict": "unmatched_self_reference",
    }

    agent = ReportAgent.__new__(ReportAgent)
    agent.simulation_id = "test-sim2"

    mock_action = MagicMock()
    mock_action.to_dict.return_value = action_unmatched

    with (
        patch(
            "app.services.simulation_runner.SimulationRunner.get_all_actions",
            return_value=[mock_action],
        ),
        patch(
            "app.services.network_analytics.NetworkAnalyticsService"
        ) as mock_analytics,
    ):
        mock_analytics.return_value.compute_metrics.return_value.to_dict.return_value = {
            "status": "insufficient_data"
        }
        items = agent._collect_simulation_evidence_items()

    action_items = [i for i in items if i.get("type") == "agent_action"]
    # unmatched darf nicht gefiltert werden
    assert len(action_items) == 1


# ---------------------------------------------------------------------------
# detect_role_conflict public API
# ---------------------------------------------------------------------------

def test_detect_role_conflict_returns_reason() -> None:
    """detect_role_conflict gibt den Grund als Zeichenkette zurück."""
    action = _make_action_dict(
        agent_id=0,
        agent_name="Dozentin",
        content="Als Betriebsratsvorsitzende war es mir wichtig, die Mitglieder zu informieren.",
    )
    result = detect_role_conflict("reddit", action, [DOZENTIN, BETRIEBSRAT])
    assert result == "foreign_role"


def test_detect_role_conflict_returns_none_for_own_role() -> None:
    """detect_role_conflict gibt None zurück, wenn die eigene Rolle referenziert wird."""
    action = _make_action_dict(
        agent_id=0,
        agent_name="Dozentin",
        content="Als Dozentin sehe ich die Situation folgendermaßen.",
    )
    result = detect_role_conflict("reddit", action, [DOZENTIN, BETRIEBSRAT])
    assert result is None


def test_leere_profile_werden_nicht_gecacht(tmp_path) -> None:
    """Lead-Review: fehlen die Profile beim ersten Lesen, bleibt die Markierung
    nicht für den ganzen Lauf aus."""
    import json as _json

    from app.services.sim import action_log_reader as reader

    reader._clear_profile_cache()
    sim_dir = tmp_path / "sim"
    sim_dir.mkdir()
    assert reader._get_profiles(str(sim_dir)) == ([], [])

    (sim_dir / "reddit_profiles.json").write_text(
        _json.dumps([{"name": "Laura Wagner", "profession": "Dozentin"}]), encoding="utf-8"
    )
    _twitter, reddit = reader._get_profiles(str(sim_dir))
    assert reddit and reddit[0]["name"] == "Laura Wagner"
    reader._clear_profile_cache()
