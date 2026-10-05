"""Zuordnung von Konfigurations-Agenten zu OASIS-Agenten (Issue #1778).

Drei Nummern meinen denselben Agenten und sind nicht immer gleich:

* ``agent_configs[].agent_id`` in ``simulation_config.json``,
* ``user_id`` im Profil (``reddit_profiles.json``, ``twitter_profiles.csv``),
* die ``agent_id`` in OASIS — sie ist die **Position** des Profils in der
  Profildatei; ``user_id`` liest OASIS nicht.

``agent_id`` der Konfiguration und ``user_id`` des Profils stammen beide aus
dem Index der Entität und stimmen überein. Fehlt ein Profil (abgelehnte
Persona, #1759), rücken in OASIS alle folgenden Agenten eine Position vor.
Der Runner griff trotzdem mit der OASIS-Position in die Konfiguration: Name,
Aktivität, Haltung und Startbeitrag gehörten dann zum falschen Agenten.

Im Lauf ``sim_b51b759f58f6`` fehlten die Profile der Agenten 6 und 16. 449 von
522 Beiträgen trugen den Namen eines anderen Agenten — „Moorhagen" schrieb mit
der Persona des Gemeinsamen Bundesausschusses.

:func:`align_config_to_profiles` schreibt die Konfiguration auf OASIS-Positionen
um. Reine Funktionen ohne Abhängigkeit auf andere Service-Module: der
Simulations-Subprozess importiert dieses Modul.
"""

from __future__ import annotations

import copy
import csv
import json
import os
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

REDDIT_PROFILE_FILENAME = "reddit_profiles.json"
TWITTER_PROFILE_FILENAME = "twitter_profiles.csv"


def load_simulation_profiles(simulation_dir: str) -> List[Dict[str, Any]]:
    """Die Profile eines Laufs in OASIS-Reihenfolge; leer, wenn keine lesbar sind.

    Beide Plattformdateien führen dieselben Agenten in derselben Reihenfolge.
    Gelesen wird die Reddit-Datei, ersatzweise die Twitter-Datei.
    """
    reddit_path = os.path.join(simulation_dir, REDDIT_PROFILE_FILENAME)
    try:
        with open(reddit_path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, list):
            return [row for row in loaded if isinstance(row, dict)]
    except (OSError, ValueError):
        pass
    twitter_path = os.path.join(simulation_dir, TWITTER_PROFILE_FILENAME)
    try:
        with open(twitter_path, "r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except (OSError, ValueError):
        return []


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def position_by_config_agent_id(profiles: Sequence[Mapping[str, Any]]) -> Optional[Dict[int, int]]:
    """``agent_id`` der Konfiguration → OASIS-Position.

    ``None``, wenn die Profile keine verwertbare ``user_id`` tragen (fehlend
    oder doppelt): dann ist die Zuordnung unbekannt, und der Aufrufer lässt die
    Konfiguration unverändert, statt eine zu raten.
    """
    positions: Dict[int, int] = {}
    for position, profile in enumerate(profiles):
        user_id = _as_int(profile.get("user_id"))
        if user_id is None or user_id in positions:
            return None
        positions[user_id] = position
    return positions


def align_config_to_profiles(
    config: Mapping[str, Any],
    profiles: Sequence[Mapping[str, Any]],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Schreibt die Agenten-Nummern der Konfiguration auf OASIS-Positionen um.

    Rückgabe: ``(Konfiguration, Agenten ohne Profil)``.

    * Ein Agent mit Profil bekommt als ``agent_id`` die Position seines Profils.
    * Ein Agent ohne Profil existiert in OASIS nicht. Er bleibt in der
      Konfiguration, damit Zählungen über ``agent_configs`` gleich bleiben, und
      bekommt eine Nummer hinter dem letzten Profil — dort kann er mit keinem
      OASIS-Agenten verwechselt werden. Er steht zusätzlich in der zweiten
      Rückgabe (``agent_id`` vorher, ``entity_name``).
    * ``event_config.initial_posts[].poster_agent_id`` wird ebenso umgeschrieben.

    Stimmen alle Nummern bereits, oder ist die Zuordnung unbekannt (keine
    Profile, keine verwertbare ``user_id``), kommt die Konfiguration
    unverändert zurück. Die Eingabe wird nie verändert.
    """
    agent_configs = config.get("agent_configs")
    if not isinstance(agent_configs, list) or not profiles:
        return dict(config), []
    positions = position_by_config_agent_id(profiles)
    if positions is None:
        return dict(config), []

    new_id_by_old: Dict[int, int] = {}
    without_profile: List[Dict[str, Any]] = []
    next_free = len(profiles)
    for agent_config in agent_configs:
        if not isinstance(agent_config, Mapping):
            continue
        old_id = _as_int(agent_config.get("agent_id"))
        if old_id is None or old_id in new_id_by_old:
            continue
        if old_id in positions:
            new_id_by_old[old_id] = positions[old_id]
            continue
        new_id_by_old[old_id] = next_free
        next_free += 1
        without_profile.append(
            {"agent_id": old_id, "entity_name": agent_config.get("entity_name")}
        )

    if all(old == new for old, new in new_id_by_old.items()):
        return dict(config), without_profile

    aligned = copy.deepcopy(dict(config))
    for agent_config in aligned["agent_configs"]:
        if isinstance(agent_config, dict):
            old_id = _as_int(agent_config.get("agent_id"))
            if old_id in new_id_by_old:
                agent_config["agent_id"] = new_id_by_old[old_id]
    event_config = aligned.get("event_config")
    initial_posts = event_config.get("initial_posts") if isinstance(event_config, dict) else None
    for post in initial_posts if isinstance(initial_posts, list) else []:
        if isinstance(post, dict):
            old_id = _as_int(post.get("poster_agent_id"))
            if old_id in new_id_by_old:
                post["poster_agent_id"] = new_id_by_old[old_id]
    return aligned, without_profile


__all__ = [
    "REDDIT_PROFILE_FILENAME",
    "TWITTER_PROFILE_FILENAME",
    "align_config_to_profiles",
    "load_simulation_profiles",
    "position_by_config_agent_id",
]
