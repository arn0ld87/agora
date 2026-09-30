"""Aktivitaets-Untergrenzen und Runden-Auswahl fuer Simulationen.

Issue [#1713](https://github.com/arn0ld87/agora/issues/1713) Slice S4:
Baseline-Laeufe blieben bei 0,16-0,22 Aktionen/Agent/Runde (L1-Ziel >= 0,6,
``docs/runbooks/simulation-liveness.md``) und rund 25 % aktiven
Agenten/Runde (L2-Ziel >= 40 %). Ursache waren drei Konfigurationswerte,
die LLM-Output *und* Regel-Fallback unabhaengig voneinander unterschreiten
konnten:

- ``agents_per_hour_min``/``agents_per_hour_max`` (Zeitkonfiguration)
  bestimmen den Ziel-Kandidatenpool je Runde.
- ``activity_level`` (Agentenkonfiguration) bestimmt je Agent die
  Wahrscheinlichkeit, in einer aktiven Stunde ueberhaupt Kandidat zu
  werden.
- ``active_hours`` (Agentenkonfiguration) grenzt Agenten auf enge
  Tagesfenster ein (z. B. Behoerden nur 9-17 Uhr) und leert den
  Kandidatenpool in allen uebrigen Stunden — unabhaengig von
  ``activity_level``.

Diese Untergrenzen erhoehen ausschliesslich den *Erwartungswert* aktiver
Agenten pro Runde, um die L1/L2-Zielwerte erreichbar zu machen. Sie
behaupten keine Aussage ueber reales Stakeholder-Verhalten (ADR-0002) —
Agora sagt kein menschliches Verhalten vorher, siehe ``CONTEXT.md``.
"""

from __future__ import annotations

import math
import random
from typing import Any, Dict, Iterable, List, Protocol, Sequence, Tuple

# L2 (active_agent_share_median) verlangt >= 40 % aktive Agenten je Runde,
# ueber den gesamten Lauf gemessen. agents_per_hour_max begrenzt den
# Ziel-Kandidatenpool nach oben; ohne Untergrenze konnte ein LLM- oder
# Regel-Fallback-Wert (z. B. 5 von 500 Agenten) L2 strukturell
# unerreichbar machen, unabhaengig von activity_level. 0,7 liegt bewusst
# ueber dem 0,4-Minimum, damit ``random.sample`` im Median genug Spielraum
# hat, auch wenn ein Teil der Kandidaten durch active_hours/activity_level
# ausscheidet.
AGENTS_PER_HOUR_MIN_RATIO = 0.4
AGENTS_PER_HOUR_MAX_RATIO = 0.7

# activity_level ist die Pro-Agent-Wahrscheinlichkeit, in einer aktiven
# Stunde ueberhaupt Kandidat zu werden (siehe select_active_agent_ids).
# 0.5 haelt genug Typ-Differenzierung im Prompt sinnvoll (z. B. Medien
# weiterhin aktiver als Behoerden), ohne die Untergrenze wertlos zu
# machen.
ACTIVITY_LEVEL_FLOOR = 0.5

# 0-5 Uhr bleibt der DACH-Nachtruhe-Fallback (off_peak_activity_multiplier
# in simulation_config_time.py). Alle anderen simulierten Stunden duerfen
# fuer keinen Agenten strukturell leer bleiben — sonst bricht der
# Kandidatenpool ausgerechnet in den Stunden ein, in denen der Runner die
# meisten Runden ausfuehrt (peak/work/morning). CORE_ACTIVE_HOURS ist die
# Untergrenze, kein Ersatz fuer ein LLM-/Regel-generiertes active_hours —
# schmalere Typ-Fenster (z. B. Behoerden 9-17 Uhr) werden ergaenzt, nicht
# ersetzt.
CORE_ACTIVE_HOURS: frozenset[int] = frozenset(range(6, 24))

# Twitter-Feed (oasis.Platform, siehe oasis/environment/env.py). Der
# OASIS-Default haelt den Feed sehr eng (refresh_rec_post_count=2,
# max_rec_post_len=2, following_post_count=3) — ein Agent sieht pro
# Refresh nur 2 empfohlene und 3 Follow-Posts. Das verknappt den
# Diskursanlass strukturell: wer nichts im Feed sieht, hat nichts zu
# beantworten, unabhaengig von activity_level. 5/5/5 vergroessert den
# Diskursanlass-Pool ohne den Recsys-Call-Umfang zu vervielfachen — die
# TwHIN-BERT-Anfrage bleibt eine Anfrage pro Refresh, nur mit mehr
# zurueckgegebenen Kandidaten (linearer Antwortumfang, kein zusaetzlicher
# LLM-Call). Reddit bleibt beim OASIS-Default (dort bereits grosszuegig,
# max_rec_post_len=100).
TWITTER_REFRESH_REC_POST_COUNT = 5
TWITTER_MAX_REC_POST_LEN = 5
TWITTER_FOLLOWING_POST_COUNT = 5


def enforce_agents_per_hour_floor(
    agents_per_hour_min: int,
    agents_per_hour_max: int,
    num_entities: int,
) -> Tuple[int, int]:
    """Hebt ``agents_per_hour_min``/``agents_per_hour_max`` auf die L2-Untergrenze an.

    Gilt fuer LLM-Output und Regel-Fallback gleichermassen, weil beide in
    ``simulation_config_time.py::_parse_time_config`` denselben Pfad
    durchlaufen (der Regel-Fallback fuellt lediglich das Eingabe-Dict).
    Nach oben bleibt ``num_entities`` die harte Grenze; ``min < max``
    bleibt erhalten (degeneriert bei ``num_entities <= 1`` zu
    ``min == max``, dort ist keine echte Bandbreite moeglich).
    """
    if num_entities <= 0:
        return agents_per_hour_min, agents_per_hour_max

    floor_min = min(num_entities, max(1, math.ceil(num_entities * AGENTS_PER_HOUR_MIN_RATIO)))
    raw_floor_max = max(
        floor_min + 1 if floor_min < num_entities else floor_min,
        math.ceil(num_entities * AGENTS_PER_HOUR_MAX_RATIO),
    )
    floor_max = min(num_entities, raw_floor_max)

    result_min = min(num_entities, max(agents_per_hour_min, floor_min))
    result_max = min(num_entities, max(agents_per_hour_max, floor_max))

    if result_min >= result_max:
        result_min = max(1, result_max - 1) if result_max > 1 else result_max

    return result_min, result_max


def enforce_activity_level_floor(activity_level: float) -> float:
    """Hebt ``activity_level`` auf ``ACTIVITY_LEVEL_FLOOR`` an, deckelt bei 1.0."""
    return min(1.0, max(activity_level, ACTIVITY_LEVEL_FLOOR))


def enforce_active_hours_floor(active_hours: Iterable[int]) -> List[int]:
    """Erweitert ``active_hours`` um ``CORE_ACTIVE_HOURS`` (06-23 Uhr).

    Verhindert, dass ein enges Typ-Fenster (z. B. Behoerden 9-17 Uhr) den
    Kandidatenpool in allen uebrigen Tagesstunden leert. 0-5 Uhr bleibt
    bewusst aussen vor (DACH-Nachtruhe, siehe Modul-Docstring).
    """
    return sorted(set(active_hours) | CORE_ACTIVE_HOURS)


class RandomLike(Protocol):
    """Strukturelle Schnittstelle fuer Auswahl-Zufall.

    Erfuellt sowohl vom ``random``-Modul (Standardfall — Simulationen
    seeden den globalen Zustand ueber ``seed_simulation_rng``, siehe
    ``backend/scripts/_sim_common.py``) als auch von einer eigenen
    ``random.Random``-Instanz (Tests: deterministisch ohne den globalen
    Zustand zu beruehren).
    """

    def uniform(self, a: float, b: float) -> float: ...

    def random(self) -> float: ...

    def sample(self, population: Sequence[int], k: int) -> List[int]: ...


def select_active_agent_ids(
    time_config: Dict[str, Any],
    agent_configs: Iterable[Dict[str, Any]],
    current_hour: int,
    rng: RandomLike = random,
) -> List[int]:
    """Waehlt aktive Agent-IDs fuer eine Simulationsrunde.

    Gemeinsamer Kern fuer ``platform_runner.py::SinglePlatformRunner.
    _get_active_agents_for_round`` und ``run_parallel_simulation.py::
    get_active_agents_for_round`` — beide Runner fuehrten bis Issue #1713
    Slice S4 dieselbe Auswahllogik als Kopie. ``rng`` macht die Auswahl in
    Tests deterministisch seedbar, ohne den globalen ``random``-Zustand zu
    beruehren; im Produktivpfad bleibt der Default (globales ``random``,
    seeded via ``seed_simulation_rng``) unveraendert.

    Aendert nichts an der Auswahl-Mechanik selbst (Zeitfenster-Multiplikator
    -> Ziel-Kandidatenzahl -> Kandidaten nach active_hours/activity_level ->
    ``sample``) — nur die Duplizierung entfaellt. Die L2-Untergrenze wirkt
    ueber die Eingabewerte (``enforce_agents_per_hour_floor``,
    ``enforce_activity_level_floor``, ``enforce_active_hours_floor``), nicht
    ueber einen Override hier.
    """
    base_min = time_config.get("agents_per_hour_min", 5)
    base_max = time_config.get("agents_per_hour_max", 20)

    peak_hours = time_config.get("peak_hours", [9, 10, 11, 14, 15, 20, 21, 22])
    off_peak_hours = time_config.get("off_peak_hours", [0, 1, 2, 3, 4, 5])

    if current_hour in peak_hours:
        multiplier = time_config.get("peak_activity_multiplier", 1.5)
    elif current_hour in off_peak_hours:
        multiplier = time_config.get("off_peak_activity_multiplier", 0.3)
    else:
        multiplier = 1.0

    target_count = int(rng.uniform(base_min, base_max) * multiplier)

    candidates: List[int] = []
    for cfg in agent_configs:
        agent_id = cfg.get("agent_id", 0)
        active_hours = cfg.get("active_hours", list(range(8, 23)))
        activity_level = cfg.get("activity_level", 0.5)

        if current_hour not in active_hours:
            continue

        if rng.random() < activity_level:
            candidates.append(agent_id)

    if not candidates:
        return []

    return rng.sample(candidates, min(target_count, len(candidates)))
