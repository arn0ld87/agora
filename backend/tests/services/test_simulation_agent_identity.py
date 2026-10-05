"""Issue #1778 — Konfigurations-Agenten und OASIS-Positionen.

OASIS nummeriert Agenten nach der Position ihres Profils in der Profildatei.
Im Lauf ``sim_b51b759f58f6`` fehlten die Profile der Agenten 6 und 16; ab
Position 6 trug jeder Beitrag den Namen eines anderen Agenten (449 von 522).
"""

from __future__ import annotations

import csv
import json
from typing import Any, Dict, List

from app.services.simulation_agent_identity import (
    align_config_to_profiles,
    load_simulation_profiles,
    position_by_config_agent_id,
)


def _config(names: List[str]) -> Dict[str, Any]:
    return {
        "simulation_id": "sim-1",
        "agent_configs": [
            {"agent_id": index, "entity_name": name, "stance": "neutral"}
            for index, name in enumerate(names)
        ],
        "event_config": {
            "initial_posts": [
                {"poster_agent_id": index, "content": f"Beitrag von {name}"}
                for index, name in enumerate(names)
            ]
        },
    }


def _profiles(user_ids: List[int]) -> List[Dict[str, Any]]:
    return [{"user_id": user_id, "name": f"Profil {user_id}"} for user_id in user_ids]


def _names_by_id(config: Dict[str, Any]) -> Dict[int, str]:
    return {entry["agent_id"]: entry["entity_name"] for entry in config["agent_configs"]}


def test_missing_profile_shifts_the_following_agents_to_their_oasis_position() -> None:
    config = _config(["Kreistag", "Hollerau", "Brenkhausen", "Moorhagen"])

    aligned, without_profile = align_config_to_profiles(config, _profiles([0, 2, 3]))

    # OASIS-Position 1 ist das Profil mit user_id 2, also „Brenkhausen".
    assert _names_by_id(aligned) == {0: "Kreistag", 1: "Brenkhausen", 2: "Moorhagen", 3: "Hollerau"}
    assert without_profile == [{"agent_id": 1, "entity_name": "Hollerau"}]


def test_agent_without_profile_gets_a_number_no_oasis_agent_has() -> None:
    config = _config(["A", "B", "C", "D"])
    profiles = _profiles([0, 3])

    aligned, _ = align_config_to_profiles(config, profiles)

    ids_without_profile = [
        entry["agent_id"] for entry in aligned["agent_configs"] if entry["entity_name"] in {"B", "C"}
    ]
    assert all(agent_id >= len(profiles) for agent_id in ids_without_profile)
    assert len(aligned["agent_configs"]) == 4
    assert len({entry["agent_id"] for entry in aligned["agent_configs"]}) == 4


def test_initial_posts_follow_their_agent() -> None:
    config = _config(["Kreistag", "Hollerau", "Brenkhausen"])

    aligned, _ = align_config_to_profiles(config, _profiles([0, 2]))

    names = _names_by_id(aligned)
    for post in aligned["event_config"]["initial_posts"]:
        assert post["content"] == f"Beitrag von {names[post['poster_agent_id']]}"


def test_complete_profiles_leave_the_config_unchanged() -> None:
    config = _config(["A", "B", "C"])

    aligned, without_profile = align_config_to_profiles(config, _profiles([0, 1, 2]))

    assert aligned == config
    assert without_profile == []


def test_profiles_missing_only_at_the_end_keep_all_numbers() -> None:
    """Der Fall des Laufs ``sim_c8c6b30aa652``: 54 Agenten, 50 Profile, Lücke am Ende."""
    config = _config(["A", "B", "C"])

    aligned, without_profile = align_config_to_profiles(config, _profiles([0, 1]))

    assert aligned == config
    assert without_profile == [{"agent_id": 2, "entity_name": "C"}]


def test_input_config_is_never_mutated() -> None:
    config = _config(["A", "B", "C"])
    before = json.loads(json.dumps(config))

    align_config_to_profiles(config, _profiles([0, 2]))

    assert config == before


def test_unknown_mapping_leaves_the_config_unchanged() -> None:
    """Ohne verwertbare ``user_id`` wird nichts geraten."""
    config = _config(["A", "B"])

    assert align_config_to_profiles(config, [])[0] == config
    assert align_config_to_profiles(config, [{"name": "ohne Nummer"}])[0] == config
    assert align_config_to_profiles(config, _profiles([1, 1]))[0] == config
    assert position_by_config_agent_id(_profiles([1, 1])) is None


def test_profiles_are_read_in_oasis_order_from_reddit_or_twitter(tmp_path) -> None:
    (tmp_path / "reddit_profiles.json").write_text(
        json.dumps(_profiles([0, 2])), encoding="utf-8"
    )
    assert [p["user_id"] for p in load_simulation_profiles(str(tmp_path))] == [0, 2]

    (tmp_path / "reddit_profiles.json").unlink()
    with open(tmp_path / "twitter_profiles.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["user_id", "name"])
        writer.writeheader()
        writer.writerows(_profiles([0, 2]))
    # Die CSV liefert Zeichenketten; die Zuordnung liest sie als Zahl.
    twitter = load_simulation_profiles(str(tmp_path))
    assert position_by_config_agent_id(twitter) == {0: 0, 2: 1}

    assert load_simulation_profiles(str(tmp_path / "fehlt")) == []


def test_interview_all_addresses_oasis_positions_and_skips_missing_agents(
    tmp_path, monkeypatch
) -> None:
    """„Alle befragen" schickte die Nummern der Konfiguration an OASIS."""
    from app.services.sim import interview_client

    sim_dir = tmp_path / "sim-1"
    sim_dir.mkdir()
    (sim_dir / "reddit_profiles.json").write_text(
        json.dumps(_profiles([0, 2, 3])), encoding="utf-8"
    )
    config = _config(["Kreistag", "Hollerau", "Brenkhausen", "Moorhagen"])

    class _Store:
        def exists(self, simulation_id: str, name: str) -> bool:
            return True

        def read_json(self, simulation_id: str, name: str, default: Any = None) -> Any:
            return config

    sent: Dict[str, Any] = {}

    def _batch(**kwargs: Any) -> Dict[str, Any]:
        sent.update(kwargs)
        return {"success": True}

    monkeypatch.setattr(interview_client, "_store", lambda: _Store())
    monkeypatch.setattr(interview_client, "interview_agents_batch", _batch)

    interview_client.interview_all_agents("sim-1", "Frage", run_state_dir=str(tmp_path))

    assert sorted(entry["agent_id"] for entry in sent["interviews"]) == [0, 1, 2]
