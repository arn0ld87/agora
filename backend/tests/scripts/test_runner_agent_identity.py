"""Issue #1778 — der Runner beschriftet Aktionen mit dem richtigen Agenten.

``get_agent_names_from_config`` und ``agent_configs_by_id`` greifen mit der
OASIS-Nummer in die Konfiguration. Fehlt ein Profil, traf das den falschen
Agenten; der Runner lädt die Konfiguration deshalb über ``load_aligned_config``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import run_parallel_simulation as rps  # type: ignore[import-not-found]  # noqa: E402


def _write_run(tmp_path: Path, profile_user_ids: list[int]) -> str:
    names = ["Kreistag", "Hollerau", "Brenkhausen", "Moorhagen"]
    config = {
        "simulation_id": "sim-1",
        "agent_configs": [
            {"agent_id": index, "entity_name": name, "stance": "opposing" if index == 3 else "neutral"}
            for index, name in enumerate(names)
        ],
        "event_config": {"initial_posts": [{"poster_agent_id": 3, "content": "Moorhagen meldet sich"}]},
    }
    config_path = tmp_path / "simulation_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    (tmp_path / "reddit_profiles.json").write_text(
        json.dumps([{"user_id": user_id, "name": names[user_id]} for user_id in profile_user_ids]),
        encoding="utf-8",
    )
    return str(config_path)


def test_action_names_match_the_oasis_agent_when_a_profile_is_missing(tmp_path) -> None:
    config, without_profile = rps.load_aligned_config(_write_run(tmp_path, [0, 2, 3]))

    names = rps.get_agent_names_from_config(config)

    # OASIS-Agent 1 läuft mit dem Profil „Brenkhausen", Agent 2 mit „Moorhagen".
    assert names[0] == "Kreistag"
    assert names[1] == "Brenkhausen"
    assert names[2] == "Moorhagen"
    assert [entry["entity_name"] for entry in without_profile] == ["Hollerau"]


def test_agent_config_and_initial_post_follow_the_oasis_agent(tmp_path) -> None:
    config, _ = rps.load_aligned_config(_write_run(tmp_path, [0, 2, 3]))

    by_id = {entry["agent_id"]: entry for entry in config["agent_configs"]}

    assert by_id[2]["entity_name"] == "Moorhagen"
    assert by_id[2]["stance"] == "opposing"
    assert config["event_config"]["initial_posts"][0]["poster_agent_id"] == 2


def test_complete_profiles_keep_the_config_as_written(tmp_path) -> None:
    config_path = _write_run(tmp_path, [0, 1, 2, 3])

    config, without_profile = rps.load_aligned_config(config_path)

    assert config == rps.load_config(config_path)
    assert without_profile == []


def test_reddit_persona_gets_the_stance_of_its_own_agent(tmp_path) -> None:
    """Die Haltung im System-Prompt folgt dem Agenten, nicht der alten Nummer.

    Mit Lücke im Profil (``user_id`` 0, 2, 3) trägt OASIS-Agent 2 die Persona
    „Moorhagen". Ihre Haltung ``opposing`` muss in genau diesem Profil landen.
    """
    import agent_tools  # type: ignore[import-not-found]

    config, _ = rps.load_aligned_config(_write_run(tmp_path, [0, 2, 3]))
    profile_path = tmp_path / "reddit_profiles.json"
    profiles = json.loads(profile_path.read_text(encoding="utf-8"))
    for profile in profiles:
        profile["persona"] = f"Persona {profile['name']}"
    profile_path.write_text(json.dumps(profiles), encoding="utf-8")

    def personas(agent_configs: list[dict]) -> dict[str, str]:
        out_path = agent_tools.augment_profile_with_stance(
            str(profile_path), agent_configs, platform="reddit"
        )
        augmented = json.loads(Path(out_path).read_text(encoding="utf-8"))
        return {profile["name"]: profile["persona"] for profile in augmented}

    all_neutral = [dict(entry, stance="neutral") for entry in config["agent_configs"]]
    with_stance = personas(config["agent_configs"])
    baseline = personas(all_neutral)

    # Nur „Moorhagen" ist ``opposing``; nur ihr Profil weicht vom Neutralfall ab.
    assert with_stance["Moorhagen"] != baseline["Moorhagen"]
    assert with_stance["Brenkhausen"] == baseline["Brenkhausen"]
    assert with_stance["Kreistag"] == baseline["Kreistag"]
