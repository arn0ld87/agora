"""Regressionstests fuer die Twitter-Aktionslisten (#1713 S5).

Sichert:
- CREATE_COMMENT und LIKE_COMMENT sind in beiden Twitter-Aktionslisten aktiviert.
- DISLIKE_POST und DISLIKE_COMMENT sind NICHT in den Twitter-Listen (Twitter
  kennt dieses Konzept nicht).
- AVAILABLE_ACTIONS und AVAILABLE_ACTION_NAMES in run_twitter_simulation.py
  sind synchron (gleiche Laenge, gleiche Reihenfolge).
- TWITTER_ACTIONS in run_parallel_simulation.py stimmt mit AVAILABLE_ACTIONS ueberein.
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import run_parallel_simulation as rps  # type: ignore[import-not-found]  # noqa: E402
import run_twitter_simulation as rts  # type: ignore[import-not-found]  # noqa: E402
from oasis.social_platform.typing import ActionType  # type: ignore[import-not-found]  # noqa: E402


class TestTwitterActionLists:
    """Twitter-Aktionslisten: Inhalt und Konsistenz."""

    def test_twitter_actions_contains_create_comment(self) -> None:
        assert ActionType.CREATE_COMMENT in rps.TWITTER_ACTIONS, (
            "TWITTER_ACTIONS muss CREATE_COMMENT enthalten (#1713 S5)"
        )

    def test_twitter_actions_contains_like_comment(self) -> None:
        assert ActionType.LIKE_COMMENT in rps.TWITTER_ACTIONS, (
            "TWITTER_ACTIONS muss LIKE_COMMENT enthalten (#1713 S5)"
        )

    def test_twitter_actions_no_dislike_post(self) -> None:
        assert ActionType.DISLIKE_POST not in rps.TWITTER_ACTIONS, (
            "TWITTER_ACTIONS darf DISLIKE_POST NICHT enthalten (Twitter hat kein Dislike)"
        )

    def test_twitter_actions_no_dislike_comment(self) -> None:
        assert ActionType.DISLIKE_COMMENT not in rps.TWITTER_ACTIONS, (
            "TWITTER_ACTIONS darf DISLIKE_COMMENT NICHT enthalten (Twitter hat kein Dislike)"
        )

    def test_single_runner_available_actions_contains_create_comment(self) -> None:
        assert ActionType.CREATE_COMMENT in rts.TwitterSimulationRunner.AVAILABLE_ACTIONS

    def test_single_runner_available_actions_contains_like_comment(self) -> None:
        assert ActionType.LIKE_COMMENT in rts.TwitterSimulationRunner.AVAILABLE_ACTIONS

    def test_single_runner_no_dislike_post(self) -> None:
        assert ActionType.DISLIKE_POST not in rts.TwitterSimulationRunner.AVAILABLE_ACTIONS

    def test_single_runner_no_dislike_comment(self) -> None:
        assert ActionType.DISLIKE_COMMENT not in rts.TwitterSimulationRunner.AVAILABLE_ACTIONS

    def test_available_action_names_in_sync_with_available_actions(self) -> None:
        """AVAILABLE_ACTIONS und AVAILABLE_ACTION_NAMES muessen gleich lang und konsistent sein."""
        actions = rts.TwitterSimulationRunner.AVAILABLE_ACTIONS
        names = rts.TwitterSimulationRunner.AVAILABLE_ACTION_NAMES
        assert len(actions) == len(names), (
            f"AVAILABLE_ACTIONS ({len(actions)}) und AVAILABLE_ACTION_NAMES ({len(names)}) "
            "haben unterschiedliche Laenge"
        )
        # Namen muessen den ActionType-Values entsprechen (case-insensitive)
        for action, name in zip(actions, names):
            assert action.name == name, (
                f"Reihenfolge-Mismatch: ActionType.{action.name} vs Name '{name}'"
            )

    def test_parallel_runner_twitter_actions_subset_of_single_runner(self) -> None:
        """TWITTER_ACTIONS (parallel) und AVAILABLE_ACTIONS (single) muessen gleich sein."""
        parallel_set = set(rps.TWITTER_ACTIONS)
        single_set = set(rts.TwitterSimulationRunner.AVAILABLE_ACTIONS)
        assert parallel_set == single_set, (
            f"TWITTER_ACTIONS != AVAILABLE_ACTIONS:\n"
            f"  Nur in parallel: {parallel_set - single_set}\n"
            f"  Nur in single:   {single_set - parallel_set}"
        )
