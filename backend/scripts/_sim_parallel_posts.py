"""Configuration loading and initial posts setup for parallel simulation."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

try:
    from oasis import ActionType, ManualAction
except ImportError:
    from oasis.social_platform.typing import ActionType  # type: ignore[import-not-found]
    ManualAction = None  # type: ignore[assignment]

from app.services.simulation_agent_identity import (
    align_config_to_profiles,
    load_simulation_profiles,
)
from app.services.simulation_activity_model import (
    agent_ids_in_graph,
    select_round_agent_ids_from_config,
)

try:
    from ._sim_common import derive_simulation_seed
except ImportError:
    from _sim_common import derive_simulation_seed

def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration file"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_aligned_config(config_path: str) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Lädt die Konfiguration und schreibt sie auf OASIS-Positionen um (#1778).

    OASIS nummeriert die Agenten nach der Position ihres Profils in der
    Profildatei. Fehlt ein Profil, rücken alle folgenden Agenten vor, und ein
    Zugriff mit der OASIS-Nummer in ``agent_configs`` trifft den falschen
    Agenten: falscher Name im Aktionsprotokoll, fremde Aktivitäts- und
    Haltungswerte, Startbeitrag unter fremdem Namen. Alle Zugriffe dieses
    Runners auf ``agent_configs`` und ``initial_posts`` laufen deshalb über die
    hier umgeschriebene Konfiguration.

    Rückgabe: ``(Konfiguration, Agenten ohne Profil)``.
    """
    config = load_config(config_path)
    profiles = load_simulation_profiles(os.path.dirname(config_path) or ".")
    return align_config_to_profiles(config, profiles)


def build_initial_post_actions(
    initial_posts: List[Dict[str, Any]],
    agent_graph,
    *,
    on_published=None,
):
    """Baut die Agent->Aktion(en)-Struktur fuer die Seed-Posts beider Plattformen.

    Issue #1245: Der Twitter-Zweig wies hier per ``initial_actions[agent] = ...``
    zu. Mehrere Posts desselben Agenten ueberschrieben sich damit gegenseitig —
    der letzte gewann, alle vorherigen verschwanden ersatzlos, ohne Fehler und
    ohne Warnung. Der Reddit-Zweig behandelte dieselbe Kollision bereits korrekt;
    es war ein Copy-Paste-Divergenzfehler, kein Designunterschied. Beide Zweige
    benutzen jetzt diesen Helfer, damit die Vorlage nicht wieder auseinanderlaeuft.

    Die Struktur bleibt bewusst heterogen (Einzelwert oder Liste) — genau das
    erwartet ``env.step``. Ohne Kollision entsteht kein zusaetzliches Wrapping.

    Args:
        initial_posts: ``event_config.initial_posts`` aus der Simulationsconfig.
        agent_graph: OASIS-Agentengraph mit ``get_agent(agent_id)``.
        on_published: optionaler Callback ``(agent_id, content)`` je
            veroeffentlichtem Post — nicht je Agent.

    Returns:
        ``(initial_actions, published_count)``. ``published_count`` zaehlt Posts,
        nicht Dict-Eintraege; die Differenz ist genau das, was die alte Logzeile
        verschleierte.
    """
    initial_actions: Dict[Any, Any] = {}
    published_count = 0

    for post in initial_posts:
        agent_id = post.get("poster_agent_id", 0)
        content = post.get("content", "")
        try:
            agent = agent_graph.get_agent(agent_id)
        except Exception:
            # Ein nicht aufloesbarer Agent darf die uebrigen Posts nicht mitreissen.
            continue

        action = ManualAction(
            action_type=ActionType.CREATE_POST,
            action_args={"content": content},
        )
        existing = initial_actions.get(agent)
        if existing is None:
            initial_actions[agent] = action
        elif isinstance(existing, list):
            existing.append(action)
        else:
            initial_actions[agent] = [existing, action]

        published_count += 1
        if on_published is not None:
            on_published(agent_id, content)

    return initial_actions, published_count


def format_initial_posts_log(published_count: int, distinct_agents: int) -> str:
    """Formuliert die Publish-Meldung so, dass ein Kollaps im Log sichtbar ist.

    Die alte Zeile gab ``len(initial_actions)`` aus und nannte den Wert
    "initial posts" — sie zaehlte also Agenten. Bei neun auf einen Agenten
    kollabierten Posts meldete sie "Published 1 initial posts", was wie ein
    Erfolg aussah und den Defekt aus #1226 verdeckte. Beide Groessen getrennt
    auszuweisen macht denselben Fall auf den ersten Blick lesbar.
    """
    post_word = "post" if published_count == 1 else "posts"
    agent_word = "agent" if distinct_agents == 1 else "agents"
    return (
        f"Published {published_count} initial {post_word} "
        f"from {distinct_agents} distinct {agent_word}"
    )


def get_active_agents_for_round(
    env,
    config: Dict[str, Any],
    current_hour: int,
    round_num: int
) -> List:
    """Decide which Agents to activate this round based on time and configuration"""
    # Geteilte Auswahl-Logik mit platform_runner.py (#1713 Slice S4). Mit
    # ``time_config.activity_model`` waehlt sie nach Rate, eine Ziehung je Runde
    # fuer beide Plattformen (#1779); ohne das Feld gilt der bisherige Pfad.
    # Konfigurationen ohne OASIS-Agent (kein Profil) kommen im Altpfad vor der
    # Ziehung aus dem Kandidatenpool (#1779).
    selected_ids = select_round_agent_ids_from_config(
        config,
        current_hour,
        round_num,
        fallback_seed=derive_simulation_seed(config),
        existing_agent_ids=agent_ids_in_graph(env.agent_graph),
    )

    active_agents = []
    for agent_id in selected_ids:
        try:
            agent = env.agent_graph.get_agent(agent_id)
            active_agents.append((agent_id, agent))
        except Exception as exc:
            # Nach der Vorfilterung ist ein fehlender Agent unerwartet; nicht
            # still verwerfen, sondern sichtbar machen (#1779).
            logging.getLogger("agora.run_parallel_simulation").warning(
                "Runde %s: Agent %s nicht aktivierbar (%s: %s)",
                round_num, agent_id, type(exc).__name__, exc,
            )

    return active_agents

