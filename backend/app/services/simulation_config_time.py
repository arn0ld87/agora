"""Implementation helpers extracted from SimulationConfigGenerator.

The public compatibility surface remains app.services.simulation_config_generator.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Tuple


from ..config import Config
from ..utils.logger import get_logger
from .simulation_activity_policy import (
    enforce_agents_per_hour_floor,
    resolve_agents_per_hour_ratios,
)
from .simulation_config_models import (
    DEFAULT_MINUTES_PER_ROUND,
    DEFAULT_TOTAL_SIMULATION_HOURS,
    TimeSimulationConfig,
)
from .simulation_config_schemas import (
    get_time_config_schema,
)

logger = get_logger("agora.simulation_config")

# Issue #1772: Obergrenze fuer ``total_simulation_hours`` der erzeugten
# Konfiguration. Standard = 1 Tag (24 Runden bei 60 Minuten je Runde). Mehr gibt
# es nur ueber eine hoehere Einstellung; eine LLM-Antwort darf die Grenze nie
# von sich aus ueberschreiten. Das Maximum 168 h entspricht dem Schema der
# LLM-Antwort (``simulation_config_schemas.get_time_config_schema``).
ENV_MAX_SIMULATION_HOURS = "AGORA_SIM_MAX_HOURS"
MAX_SIMULATION_HOURS_LIMIT = 168

# Responsibility group: time


def _settings_reader() -> Callable[[str], Any]:
    from .settings_layer import get_default_service

    return get_default_service().effective_value


def _as_hours(value: Any) -> Optional[int]:
    """Ganzzahl in ``1..168`` oder ``None`` (ungueltig); ``bool``/NaN/Text sind ungueltig."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip()
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number != int(number):
        return None
    hours = int(number)
    return hours if 1 <= hours <= MAX_SIMULATION_HOURS_LIMIT else None


def resolve_max_simulation_hours(read: Optional[Callable[[str], Any]] = None) -> int:
    """Wirksame Obergrenze fuer ``total_simulation_hours`` (Standard 24).

    Liest ``AGORA_SIM_MAX_HOURS`` ueber die Settings-Schicht (Env,
    ``instance/settings.json``, Laufzeit-Override). Gueltig ist eine ganze Zahl
    in ``1..168``; alles andere faellt mit Warnung auf den Standard zurueck.
    """
    reader = read if read is not None else _settings_reader()
    raw = reader(ENV_MAX_SIMULATION_HOURS)
    if raw is None:
        return DEFAULT_TOTAL_SIMULATION_HOURS
    hours = _as_hours(raw)
    if hours is None:
        logger.warning(
            "%s=%r ist ungueltig (erwartet ganze Zahl 1..%d); Standard %d wird verwendet",
            ENV_MAX_SIMULATION_HOURS,
            raw,
            MAX_SIMULATION_HOURS_LIMIT,
            DEFAULT_TOTAL_SIMULATION_HOURS,
        )
        return DEFAULT_TOTAL_SIMULATION_HOURS
    return hours


def _clamp_run_size(
    hours: int, minutes_per_round: int, max_hours: int
) -> Tuple[int, int, List[str]]:
    """Klemmt die Laufgroesse auf die Obergrenze; liefert Werte und Hinweise.

    Stunden ueber ``max_hours`` werden auf ``max_hours`` gesenkt. Die Rundenzahl
    (``hours * 60 / minutes_per_round``) darf ``max_hours`` nicht uebersteigen
    (Obergrenze bei 60 Minuten je Runde); kuerzere Runden werden dafuer auf den
    Standard von 60 Minuten angehoben.
    """
    notes: List[str] = []
    if hours > max_hours:
        notes.append(f"total_simulation_hours {hours} -> {max_hours}")
        hours = max_hours
    if minutes_per_round < DEFAULT_MINUTES_PER_ROUND and (
        hours * 60 // max(minutes_per_round, 1) > max_hours
    ):
        notes.append(f"minutes_per_round {minutes_per_round} -> {DEFAULT_MINUTES_PER_ROUND}")
        minutes_per_round = DEFAULT_MINUTES_PER_ROUND
    return hours, minutes_per_round, notes


def _apply_run_size_cap(result: Dict[str, Any], hours: int, minutes_per_round: int) -> Tuple[int, int]:
    """Wendet die Obergrenze auf die geparste Laufgroesse an und macht sie sichtbar.

    Bei einer Klemme: strukturierter Log-Eintrag und ein Hinweis, der an
    ``result['reasoning']`` angehaengt wird (``generate_config`` uebernimmt ihn in
    ``generation_reasoning``). Ein ausdruecklicher Nutzerwunsch fuer mehr
    Laufzeit wirkt erst beim Start (``simulation_days`` in
    ``POST /api/simulation/start``) und ueberschreibt die erzeugte Konfiguration.
    """
    max_hours = resolve_max_simulation_hours()
    hours, minutes_per_round, notes = _clamp_run_size(hours, minutes_per_round, max_hours)
    if notes:
        summary = "; ".join(notes)
        logger.warning(
            "Laufgroesse der Zeitkonfiguration begrenzt (Obergrenze %d h, %s): %s",
            max_hours,
            ENV_MAX_SIMULATION_HOURS,
            summary,
        )
        previous = str(result.get("reasoning") or "").strip()
        hint = (
            f"[Hinweis: Laufgroesse begrenzt ({summary}); Obergrenze {max_hours} h "
            f"ueber {ENV_MAX_SIMULATION_HOURS}]"
        )
        result["reasoning"] = f"{previous} {hint}".strip()
    return hours, minutes_per_round


def _generate_time_config(self, context: str, num_entities: int) -> Dict[str, Any]:
    """Generate time configuration"""
    context_truncated = context[:self.TIME_CONFIG_CONTEXT_LENGTH]
    max_agents_allowed = max(1, int(num_entities * 0.9))
    max_hours = resolve_max_simulation_hours()
    default_hours = DEFAULT_TOTAL_SIMULATION_HOURS
    time_profile = getattr(Config, 'TIME_PROFILE', 'dach_default')
    # Issue #1772: die Prompt-Angabe folgt der konfigurierten Untergrenze (Standard 25/50 %).
    min_ratio, max_ratio = resolve_agents_per_hour_ratios()
    min_pct = f'{min_ratio * 100:g}'
    max_pct = f'{max_ratio * 100:g}'
    prompt = f'Based on the following simulation requirements, generate time simulation configuration.\n\n{context_truncated}\n\n## Task\nPlease generate time configuration JSON.\n\n### Basic principles (profile: {time_profile}, Europe/Berlin)\n- Use DACH / German social media habits unless the scenario explicitly says otherwise\n- 0-5am almost no activity (activity coefficient 0.05)\n- 6-8am gradually active (activity coefficient 0.4)\n- 9-17 work time has reduced activity (activity coefficient 0.6)\n- 18-22 evening after-work period is peak activity (activity coefficient 1.5)\n- After 23 activity decreases (activity coefficient 0.5)\n- General rule: low activity early morning, gradually increasing morning, moderate work time, evening peak\n- **Important**: Example values below are for reference only, adjust specific time periods based on event nature and participant characteristics\n  - Example: student peak may be 21-23; media active all day; official institutions only during work hours\n  - Example: breaking news may cause late night discussions, off_peak_hours can be shortened appropriately\n\n### Return JSON format (no markdown)\n\nExample:\n{{\n    "total_simulation_hours": {default_hours},\n    "minutes_per_round": 60,\n    "agents_per_hour_min": 5,\n    "agents_per_hour_max": 50,\n    "peak_hours": [18, 19, 20, 21, 22],\n    "off_peak_hours": [0, 1, 2, 3, 4, 5],\n    "morning_hours": [6, 7, 8],\n    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16],\n    "reasoning": "Explanation of time configuration for this event"\n}}\n\nField description:\n- total_simulation_hours (int): Total simulation time in hours. Default and recommendation: {default_hours} (one day, {default_hours} rounds at 60 minutes per round). Shorter is fine for breaking news. Choose a longer duration ONLY if the simulation requirements explicitly ask for a longer duration; never lengthen it on your own for ongoing topics. Hard limit of {max_hours} hours: higher values are reduced automatically\n- minutes_per_round (int): Time per round, 30-120 minutes, recommend 60 minutes (more rounds than total_simulation_hours at 60 minutes are reduced automatically)\n- agents_per_hour_min (int): Minimum agents activated per hour (range: 1-{max_agents_allowed}; at least {min_pct}% of total agents — lower values are raised automatically)\n- agents_per_hour_max (int): Maximum agents activated per hour (range: 1-{max_agents_allowed}; at least {max_pct}% of total agents — lower values are raised automatically)\n- peak_hours (int array): Peak hours, adjust based on event participants\n- off_peak_hours (int array): Off-peak hours, usually late night/early morning\n- morning_hours (int array): Morning hours\n- work_hours (int array): Work hours\n- reasoning (string): Brief explanation for this configuration'
    system_prompt = 'You are a social media simulation expert. Return pure JSON. Use DACH / Europe-Berlin activity habits by default.'
    try:
        return self._call_llm_with_retry(prompt, system_prompt, get_time_config_schema(num_entities))
    except Exception as e:  # noqa: BLE001 — logged and intentionally converted to default config
        logger.warning(f'Time config LLM generation failed: {e}, using default configuration')
        return self._get_default_time_config(num_entities)


def _get_default_time_config(self, num_entities: int) -> Dict[str, Any]:
    """Get default time configuration (DACH / Europe-Berlin profile)"""
    return {'total_simulation_hours': DEFAULT_TOTAL_SIMULATION_HOURS, 'minutes_per_round': DEFAULT_MINUTES_PER_ROUND, 'agents_per_hour_min': max(1, num_entities // 15), 'agents_per_hour_max': max(5, num_entities // 5), 'peak_hours': [18, 19, 20, 21, 22], 'off_peak_hours': [0, 1, 2, 3, 4, 5], 'morning_hours': [6, 7, 8], 'work_hours': [9, 10, 11, 12, 13, 14, 15, 16], 'reasoning': 'Using default DACH / Europe-Berlin activity profile (1 hour per round)'}


def _coerce_int(value: Any, default: int) -> int:
    """Coerce LLM output to int. Some models (Gemma 4) return {"value": N, "reasoning": "..."} instead of N."""
    if isinstance(value, dict):
        for key in ('value', 'val', 'n', 'amount', 'count'):
            if key in value:
                value = value[key]
                break
        else:
            return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_int_list(value: Any, default: List[int]) -> List[int]:
    """Coerce LLM output to list of ints, tolerating nested dicts."""
    if isinstance(value, dict):
        for key in ('value', 'hours', 'list', 'items'):
            if key in value:
                value = value[key]
                break
        else:
            return default
    if not isinstance(value, list):
        return default
    out: List[int] = []
    for item in value:
        if isinstance(item, dict):
            for key in ('value', 'hour', 'n'):
                if key in item:
                    item = item[key]
                    break
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out or default


def _parse_time_config(self, result: Dict[str, Any], num_entities: int) -> TimeSimulationConfig:
    """Parse time configuration result and verify agents_per_hour doesn't exceed total agents"""
    agents_per_hour_min = self._coerce_int(result.get('agents_per_hour_min'), max(1, num_entities // 15))
    agents_per_hour_max = self._coerce_int(result.get('agents_per_hour_max'), max(5, num_entities // 5))
    if agents_per_hour_min > num_entities:
        logger.warning(f'agents_per_hour_min ({agents_per_hour_min}) exceeds total agents ({num_entities}), corrected')
        agents_per_hour_min = max(1, num_entities // 10)
    if agents_per_hour_max > num_entities:
        logger.warning(f'agents_per_hour_max ({agents_per_hour_max}) exceeds total agents ({num_entities}), corrected')
        agents_per_hour_max = max(agents_per_hour_min + 1, num_entities // 2)
    if agents_per_hour_min >= agents_per_hour_max:
        agents_per_hour_min = max(1, agents_per_hour_max // 2)
        logger.warning(f'agents_per_hour_min >= max, corrected to {agents_per_hour_min}')
    # Issue #1713 Slice S4: L2 (active_agent_share_median >= 40%) braucht einen
    # Ziel-Kandidatenpool, der strukturell gross genug ist — unabhaengig davon,
    # ob der Wert vom LLM oder aus dem Default-Pfad stammt (beide landen hier).
    agents_per_hour_min, agents_per_hour_max = enforce_agents_per_hour_floor(
        agents_per_hour_min, agents_per_hour_max, num_entities
    )
    # Issue #1772: Laufgroesse (Stunden x Runden) deterministisch NACH der LLM-Antwort klemmen.
    total_hours, minutes_per_round = _apply_run_size_cap(
        result,
        self._coerce_int(result.get('total_simulation_hours'), DEFAULT_TOTAL_SIMULATION_HOURS),
        self._coerce_int(result.get('minutes_per_round'), DEFAULT_MINUTES_PER_ROUND),
    )
    return TimeSimulationConfig(total_simulation_hours=total_hours, minutes_per_round=minutes_per_round, agents_per_hour_min=agents_per_hour_min, agents_per_hour_max=agents_per_hour_max, peak_hours=self._coerce_int_list(result.get('peak_hours'), [19, 20, 21, 22]), off_peak_hours=self._coerce_int_list(result.get('off_peak_hours'), [0, 1, 2, 3, 4, 5]), off_peak_activity_multiplier=0.05, morning_hours=self._coerce_int_list(result.get('morning_hours'), [6, 7, 8]), morning_activity_multiplier=0.4, work_hours=self._coerce_int_list(result.get('work_hours'), list(range(9, 19))), work_activity_multiplier=0.7, peak_activity_multiplier=1.5)
