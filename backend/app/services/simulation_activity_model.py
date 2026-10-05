"""Aktivitätsmodell der Simulation: belegte Tagesraten statt Zufallsniveau (#1779).

Hintergrund: Ein Lauf mit 30 Agenten erzeugte in 10 simulierten Stunden 440
Textbeiträge (Median 14,5 je Agent). Belegte Raten für Akteure politischer
Debatten liegen bei rund einem Textbeitrag je Tag oder darunter. Die Auswahl
der aktiven Agenten je Runde (``simulation_activity_policy.select_active_agent_ids``)
kannte diese Raten nicht: sie würfelte mit ``activity_level`` und einer
Zielzahl aus ``agents_per_hour_min/max``, und jeder aktive Agent durfte in
einem Modellaufruf beliebig viele Aktionen ausführen.

Dieses Modul hält an einer Stelle:

- die Tagesraten je Akteursklasse für die beiden Modi (``realistic``,
  ``active``) mit Quelle je Wert,
- das Stundenprofil (Ortszeit),
- die Obergrenzen je Aktivierung,
- die reine Auswahlfunktion nach Rate und die gemeinsame Ziehung für beide
  Plattformen.

Quellenlage und Rechnung: ``docs/research/simulation-aktivitaet-belege.md``.
Werte, die dort ohne Messung stehen, sind hier ausdrücklich als **Setzung**
gekennzeichnet. Das Modell ist eine Annahme über Schreibraten und sagt kein
menschliches Verhalten vorher; ein gleicher Seed erzeugt außerdem nicht
denselben Lauf, weil die Antworten der Sprachmodelle nicht festgelegt sind.
"""

from __future__ import annotations

import random
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Protocol, Sequence, Tuple

from ..contracts.simulation_activity_contract import (
    HOURS_PER_DAY,
    ActivityMode,
    ActivityModelConfig,
    ActorClass,
)
from ..utils.logger import get_logger
from .persona_domain_coherence import is_collective_entity_type
from .simulation_activity_policy import select_active_agent_ids

logger = get_logger("agora.simulation_activity_model")

ENV_ACTIVITY_MODE = "AGORA_SIM_ACTIVITY_MODE"
DEFAULT_ACTIVITY_MODE = ActivityMode.REALISTIC

# --- Tagesraten (Textbeiträge je Tag und Akteur) -----------------------------------------
# Zählung: Beitrag, Kommentar und Zitat (``TEXT_ACTION_NAMES``). Reposts und
# Likes sind Reaktionen und stehen nicht in der Rate. Quellen und Rechnung:
# docs/research/simulation-aktivitaet-belege.md

# Modus ``realistic``: möglichst realistisch, an belegten Mittelwerten.
TEXT_POSTS_PER_DAY_REALISTIC: Dict[ActorClass, float] = {
    # Einzelpersonen: 0,5. #btw21-Datensatz Sept. 2021: 272.548 Tweets von
    # 55.429 Konten in 32 Tagen = 0,15 je Konto und Tag (mit Retweets).
    # Pew 2021: die aktivsten 25 % der US-Nutzer im Median 65 Tweets im
    # Monat, davon 47 % Text (rechnerisch rund 1,0 Textbeitrag je Tag).
    # Gewählt zwischen beiden Werten.
    ActorClass.INDIVIDUAL: 0.5,
    # Politiker: 1,0. EPINetz, Bundestagswahlkampf 2021: 426.614 Tweets in 161
    # Tagen, 44 % Retweets, mindestens 0,6 Textbeiträge je Konto und Tag.
    # EU Matrix, April 2025: 14.519 Nachrichten von 431 MdEP = 1,1 je Tag.
    ActorClass.POLITICIAN: 1.0,
    # Behörden: 1,0. 119 Konten von Staatskanzleien und Landesministerien:
    # Mittel 1,41 Tweets je Tag, Ressorts 0,56 bis 2,59 (Abschlussarbeit
    # Hannover 2023, Lebenszeit-Durchschnitt).
    ActorClass.AUTHORITY: 1.0,
    # Organisationen: 1,0. SETZUNG ohne Beleg, wie ``authority``; für Verbände,
    # Gewerkschaften, Kliniken und Initiativen wurde keine Messung gefunden.
    ActorClass.ORGANISATION: 1.0,
    # Medien: 3,0. SETZUNG ohne Beleg; für Medienkonten wurde keine Messung
    # gefunden.
    ActorClass.MEDIA: 3.0,
}

# Modus ``active``: aktive Akteure, oberes Ende der belegten Spanne.
TEXT_POSTS_PER_DAY_ACTIVE: Dict[ActorClass, float] = {
    # Einzelpersonen: 2,0. Pew 2021: aktivste 25 % Median 65 Tweets im Monat =
    # 2,2 je Tag (mit Retweets). Failla/Rossetti 2024 (Bluesky): rund 2
    # Einträge je Nutzer an aktiven Tagen. Oberes Ende der belegten Spanne.
    ActorClass.INDIVIDUAL: 2.0,
    # Politiker: 3,0. Parlamentarier in 26 Ländern, Daten 2017 bis 2019: Mittel
    # 2,8 Tweets je Tag (Spanne 0,7 bis 6,6; Retweet-Anteil nicht geprüft).
    ActorClass.POLITICIAN: 3.0,
    # Behörden: 2,5. Landesministerien: Ressorts bis 2,59 Tweets je Tag
    # (Abschlussarbeit Hannover 2023).
    ActorClass.AUTHORITY: 2.5,
    # Organisationen: 2,5. SETZUNG ohne Beleg, wie ``authority``.
    ActorClass.ORGANISATION: 2.5,
    # Medien: 6,0. SETZUNG ohne Beleg; orientiert an der Obergrenze der
    # Parlamentarier-Spanne (6,6).
    ActorClass.MEDIA: 6.0,
}

TEXT_POSTS_PER_DAY_BY_MODE: Dict[ActivityMode, Dict[ActorClass, float]] = {
    ActivityMode.REALISTIC: TEXT_POSTS_PER_DAY_REALISTIC,
    ActivityMode.ACTIVE: TEXT_POSTS_PER_DAY_ACTIVE,
}

# --- Stundenprofil -----------------------------------------------------------------------
# Anteil der Tweets je Ortszeit-Stunde 0 bis 23, in Prozent. Scheffler/Kyba,
# ICWSM 2016, deutsche Tweets August/September 2014, aus Abb. 3 abgelesen
# (Ablesegenauigkeit ±0,1 Mio. Tweets je Stunde). Die Prozentwerte summieren
# sich nicht exakt auf 100; ``HOURLY_WEIGHTS`` normiert sie auf Summe 1,0.
HOURLY_PROFILE_PERCENT: Tuple[float, ...] = (
    4.0, 2.8, 1.3, 1.1, 1.0, 1.1, 1.7, 2.5, 3.2, 3.8, 4.3, 4.7,
    5.1, 5.3, 5.3, 5.3, 5.3, 5.5, 5.9, 6.0, 6.4, 6.5, 6.5, 5.5,
)
_PROFILE_TOTAL = sum(HOURLY_PROFILE_PERCENT)
HOURLY_WEIGHTS: Tuple[float, ...] = tuple(value / _PROFILE_TOTAL for value in HOURLY_PROFILE_PERCENT)

# --- Obergrenzen je Aktivierung ----------------------------------------------------------
# 1 Textaktion: folgt aus den Tagesraten. Ein Akteur mit höchstens einem
# Textbeitrag je Tag schreibt nicht mehrere in einer Stunde.
MAX_TEXT_ACTIONS_PER_ACTIVATION = 1
# 2 Reaktionen: Pew 2021 (Aktionsmix der aktivsten 25 %: 14 % Original, 33 %
# Antwort, 49 % Retweet) und Pew 2019 (rund 0,5 Likes je Tweet): auf einen
# Textbeitrag kommen rund ein Repost und ein Like.
MAX_REACTIONS_PER_ACTIVATION = 2

# Aktionsnamen im OASIS-Vokabular (``ActionType``-Werte = Namen der Tool-Funktionen).
# Textaktionen und Reaktionen sind begrenzt; lesende Aktionen (search_posts,
# search_user, trend, refresh, do_nothing) bleiben unbegrenzt.
TEXT_ACTION_NAMES: frozenset[str] = frozenset({"create_post", "create_comment", "quote_post"})
REACTION_ACTION_NAMES: frozenset[str] = frozenset(
    {
        "like_post",
        "like_comment",
        "dislike_post",
        "dislike_comment",
        "repost",
        "follow",
        "mute",
    }
)


class _RandomLike(Protocol):
    def random(self) -> float: ...


# --- Modus und Modell --------------------------------------------------------------------


def _settings_reader() -> Callable[[str], Any]:
    from .settings_layer import get_default_service

    return get_default_service().effective_value


def parse_activity_mode(value: Any) -> Optional[ActivityMode]:
    """Liest einen Modus aus Text oder Enum; ``None`` bei jedem anderen Wert."""
    if isinstance(value, ActivityMode):
        return value
    if isinstance(value, str):
        try:
            return ActivityMode(value.strip().lower())
        except ValueError:
            return None
    return None


def resolve_activity_mode(
    requested: Any = None,
    read: Optional[Callable[[str], Any]] = None,
) -> ActivityMode:
    """Wirksamer Modus: Aufrufparameter, ersatzweise ``AGORA_SIM_ACTIVITY_MODE``.

    Ein ungültiger Aufrufparameter oder Env-Wert fällt mit Warnung auf den
    nächsten Schritt zurück, am Ende auf ``realistic``.
    """
    if requested is not None:
        mode = parse_activity_mode(requested)
        if mode is not None:
            return mode
        logger.warning(
            "activity_mode=%r ist ungültig (erwartet %s); Einstellung %s wird geprüft",
            requested,
            "|".join(item.value for item in ActivityMode),
            ENV_ACTIVITY_MODE,
        )
    reader = read if read is not None else _settings_reader()
    raw = reader(ENV_ACTIVITY_MODE)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return DEFAULT_ACTIVITY_MODE
    mode = parse_activity_mode(raw)
    if mode is None:
        logger.warning(
            "%s=%r ist ungültig (erwartet %s); Standard %s wird verwendet",
            ENV_ACTIVITY_MODE,
            raw,
            "|".join(item.value for item in ActivityMode),
            DEFAULT_ACTIVITY_MODE.value,
        )
        return DEFAULT_ACTIVITY_MODE
    return mode


def build_activity_model(mode: ActivityMode) -> ActivityModelConfig:
    """Aktivitätsmodell mit dem Ratensatz des Modus und den Standard-Obergrenzen."""
    return ActivityModelConfig(
        mode=mode,
        max_text_actions_per_activation=MAX_TEXT_ACTIONS_PER_ACTIVATION,
        max_reactions_per_activation=MAX_REACTIONS_PER_ACTIVATION,
        text_posts_per_day=dict(TEXT_POSTS_PER_DAY_BY_MODE[mode]),
        hourly_weights=list(HOURLY_WEIGHTS),
    )


def activity_model_dict(mode: ActivityMode) -> Dict[str, Any]:
    """Das serialisierte Modell für ``time_config.activity_model``."""
    return build_activity_model(mode).model_dump(mode="json")


def activity_model_from_time_config(time_config: Mapping[str, Any]) -> Optional[ActivityModelConfig]:
    """Liest ``time_config.activity_model``; ``None`` für Altkonfigurationen.

    Ein vorhandenes, aber ungültiges Feld wird laut gemeldet und wie ein
    fehlendes behandelt: der Lauf bricht nicht ab, nutzt dann aber den
    bisherigen Auswahlpfad.
    """
    raw = time_config.get("activity_model")
    if raw is None:
        return None
    try:
        return ActivityModelConfig.model_validate(raw)
    except ValueError as exc:
        logger.warning(
            "time_config.activity_model ist ungültig, bisheriger Auswahlpfad wird verwendet: %s",
            exc,
        )
        return None


# --- Akteursklasse -----------------------------------------------------------------------


def coerce_actor_class(value: Any) -> Optional[ActorClass]:
    """Liest eine Akteursklasse aus Text oder Enum; ``None`` bei jedem anderen Wert."""
    if isinstance(value, ActorClass):
        return value
    if isinstance(value, str):
        try:
            return ActorClass(value.strip().lower())
        except ValueError:
            return None
    return None


def fallback_actor_class(entity_type: Optional[str]) -> ActorClass:
    """Klasse ohne gültige Angabe des Assistenten: Kollektiv oder Einzelperson.

    Nutzt die vorhandene Unterscheidung Einzelperson/Kollektiv
    (``persona_domain_coherence.is_collective_entity_type``): ein Kollektiv
    schreibt wie eine ``organisation``, alles andere wie eine ``individual``.
    """
    if is_collective_entity_type(entity_type or ""):
        return ActorClass.ORGANISATION
    return ActorClass.INDIVIDUAL


def resolve_agent_actor_class(agent_config: Mapping[str, Any]) -> ActorClass:
    """Klasse eines Agenten aus der Konfiguration; ohne gültigen Wert ``individual``."""
    return coerce_actor_class(agent_config.get("actor_class")) or ActorClass.INDIVIDUAL


# --- Auswahl der aktiven Agenten ---------------------------------------------------------


def activation_probability(model: ActivityModelConfig, actor_class: ActorClass, hour: int) -> float:
    """Wahrscheinlichkeit, in dieser Stunde aktiv zu sein.

    ``p = min(1, Tagesrate(Klasse) * Stundengewicht(Stunde))``. Eine Runde ist
    eine Stunde; das Stundengewicht ist der Anteil der Tagesrate, der auf die
    Stunde fällt. Über 24 Stunden ergibt die Summe der Wahrscheinlichkeiten
    die Tagesrate (solange kein ``min`` greift).
    """
    rate = model.text_posts_per_day[actor_class]
    return min(1.0, rate * model.hourly_weights[hour % HOURS_PER_DAY])


def select_active_agent_ids_by_rate(
    agent_configs: Iterable[Mapping[str, Any]],
    model: ActivityModelConfig,
    current_hour: int,
    rng: _RandomLike,
) -> List[int]:
    """Agent-IDs, die in dieser Runde aktiv werden: je Agent eine Ziehung gegen ``p``.

    Reine Funktion: kein globaler Zufallszustand, keine Plattform. Die Ziehung
    folgt der Reihenfolge von ``agent_configs``.
    """
    active: List[int] = []
    for cfg in agent_configs:
        probability = activation_probability(model, resolve_agent_actor_class(cfg), current_hour)
        if rng.random() < probability:
            active.append(cfg.get("agent_id", 0))
    return active


def activity_round_rng(seed: int, round_num: int, stream: str) -> random.Random:
    """Eigener Zufallsstrom für ``(Seed, Runde, Zweck)``.

    Ein String-Seed wird von ``random.Random`` über SHA-512 abgeleitet, nicht
    über ``hash()``: das Ergebnis hängt nicht an ``PYTHONHASHSEED`` und ist
    in jedem Prozess gleich. Die Ziehung berührt den globalen Zustand von
    ``random`` nicht.
    """
    return random.Random(f"agora-activity:{stream}:{seed}:{round_num}")


def select_active_agent_ids_for_platform(
    model: ActivityModelConfig,
    agent_configs: Sequence[Mapping[str, Any]],
    current_hour: int,
    round_num: int,
    seed: int,
    *,
    platform: str,
    platforms: Sequence[str],
) -> List[int]:
    """Aktive Agenten einer Plattform bei einer Ziehung je Runde für alle Plattformen.

    Beide Plattformschleifen rufen unabhängig auf und müssen dasselbe Ergebnis
    der Ziehung sehen, ohne sich abzusprechen. Deshalb hängt die Ziehung nur an
    ``(seed, round_num)``: Zuerst wird die Menge der Aktiven bestimmt, danach
    jedem Aktiven deterministisch genau eine der aktivierten Plattformen
    zugewiesen (gleichverteilt). Ein Agent ist damit in einer Runde auf
    höchstens einer Plattform aktiv. Läuft nur eine Plattform, bekommt sie
    alle Aktiven.
    """
    ordered = sorted(set(platforms))
    if platform not in ordered:
        raise ValueError(f"Plattform {platform!r} nicht in den aktivierten Plattformen {ordered}")
    active = select_active_agent_ids_by_rate(
        agent_configs, model, current_hour, activity_round_rng(seed, round_num, "draw")
    )
    if len(ordered) == 1:
        return active
    split_rng = activity_round_rng(seed, round_num, "split")
    return [
        agent_id
        for agent_id in active
        if ordered[split_rng.randrange(len(ordered))] == platform
    ]


def select_round_agent_ids(
    config: Mapping[str, Any],
    current_hour: int,
    round_num: int,
    *,
    seed: int,
    platform: str,
    platforms: Sequence[str],
    rng: Any = random,
) -> List[int]:
    """Gemeinsamer Einstieg beider Runner für die Auswahl der aktiven Agenten.

    Mit ``time_config.activity_model`` gilt die Auswahl nach Rate. Ohne das
    Feld (Konfigurationen vor #1779) gilt unverändert
    ``select_active_agent_ids`` mit ``rng`` (Standard: globales ``random``,
    geseedet über ``seed_simulation_rng``).
    """
    time_config = config.get("time_config") or {}
    agent_configs = config.get("agent_configs") or []
    model = activity_model_from_time_config(time_config)
    if model is None:
        return select_active_agent_ids(time_config, agent_configs, current_hour, rng)
    return select_active_agent_ids_for_platform(
        model,
        agent_configs,
        current_hour,
        round_num,
        seed,
        platform=platform,
        platforms=platforms,
    )


# --- Satz für den Agenten-Prompt ---------------------------------------------------------


def describe_activity_limits(model: Optional[ActivityModelConfig]) -> str:
    """Satz mit den Grenzen je Aktivierung für den Profiltext; leer ohne Modell."""
    if model is None:
        return ""
    texts = model.max_text_actions_per_activation
    reactions = model.max_reactions_per_activation
    text_part = (
        "höchstens einen Beitrag, Kommentar oder ein Zitat"
        if texts == 1
        else f"höchstens {texts} Beiträge, Kommentare oder Zitate"
    )
    if reactions == 0:
        reaction_part = "und reagierst nicht mit Like, Dislike, Repost, Folgen oder Stummschalten"
    elif reactions == 1:
        reaction_part = "und höchstens eine Reaktion (Like, Dislike, Repost, Folgen, Stummschalten)"
    else:
        reaction_part = (
            f"und höchstens {reactions} Reaktionen (Like, Dislike, Repost, Folgen, Stummschalten)"
        )
    return (
        f"Bei jeder Aktivierung schreibst du {text_part} {reaction_part}; "
        "weitere Aktionen dieser Art werden nicht ausgeführt. Lesen, Suchen und Nichtstun "
        "sind unbegrenzt."
    )
