"""Implementation helpers extracted from SimulationConfigGenerator.

The public compatibility surface remains app.services.simulation_config_generator.
"""

from __future__ import annotations

from typing import Any, Dict, List


from ..config import Config
from ..utils.logger import get_logger
from .simulation_config_models import (
    TimeSimulationConfig,
)
from .simulation_config_schemas import (
    get_time_config_schema,
)

logger = get_logger("agora.simulation_config")

# Responsibility group: time

def _generate_time_config(self, context: str, num_entities: int) -> Dict[str, Any]:
    """Generate time configuration"""
    context_truncated = context[:self.TIME_CONFIG_CONTEXT_LENGTH]
    max_agents_allowed = max(1, int(num_entities * 0.9))
    time_profile = getattr(Config, 'TIME_PROFILE', 'dach_default')
    prompt = f'Based on the following simulation requirements, generate time simulation configuration.\n\n{context_truncated}\n\n## Task\nPlease generate time configuration JSON.\n\n### Basic principles (profile: {time_profile}, Europe/Berlin)\n- Use DACH / German social media habits unless the scenario explicitly says otherwise\n- 0-5am almost no activity (activity coefficient 0.05)\n- 6-8am gradually active (activity coefficient 0.4)\n- 9-17 work time has reduced activity (activity coefficient 0.6)\n- 18-22 evening after-work period is peak activity (activity coefficient 1.5)\n- After 23 activity decreases (activity coefficient 0.5)\n- General rule: low activity early morning, gradually increasing morning, moderate work time, evening peak\n- **Important**: Example values below are for reference only, adjust specific time periods based on event nature and participant characteristics\n  - Example: student peak may be 21-23; media active all day; official institutions only during work hours\n  - Example: breaking news may cause late night discussions, off_peak_hours can be shortened appropriately\n\n### Return JSON format (no markdown)\n\nExample:\n{{\n    "total_simulation_hours": 72,\n    "minutes_per_round": 60,\n    "agents_per_hour_min": 5,\n    "agents_per_hour_max": 50,\n    "peak_hours": [18, 19, 20, 21, 22],\n    "off_peak_hours": [0, 1, 2, 3, 4, 5],\n    "morning_hours": [6, 7, 8],\n    "work_hours": [9, 10, 11, 12, 13, 14, 15, 16],\n    "reasoning": "Explanation of time configuration for this event"\n}}\n\nField description:\n- total_simulation_hours (int): Total simulation time, 24-168 hours, short for breaking news, long for ongoing topics\n- minutes_per_round (int): Time per round, 30-120 minutes, recommend 60 minutes\n- agents_per_hour_min (int): Minimum agents activated per hour (range: 1-{max_agents_allowed})\n- agents_per_hour_max (int): Maximum agents activated per hour (range: 1-{max_agents_allowed})\n- peak_hours (int array): Peak hours, adjust based on event participants\n- off_peak_hours (int array): Off-peak hours, usually late night/early morning\n- morning_hours (int array): Morning hours\n- work_hours (int array): Work hours\n- reasoning (string): Brief explanation for this configuration'
    system_prompt = 'You are a social media simulation expert. Return pure JSON. Use DACH / Europe-Berlin activity habits by default.'
    try:
        return self._call_llm_with_retry(prompt, system_prompt, get_time_config_schema(num_entities))
    except Exception as e:  # noqa: BLE001 — logged and intentionally converted to default config
        logger.warning(f'Time config LLM generation failed: {e}, using default configuration')
        return self._get_default_time_config(num_entities)


def _get_default_time_config(self, num_entities: int) -> Dict[str, Any]:
    """Get default time configuration (DACH / Europe-Berlin profile)"""
    return {'total_simulation_hours': 72, 'minutes_per_round': 60, 'agents_per_hour_min': max(1, num_entities // 15), 'agents_per_hour_max': max(5, num_entities // 5), 'peak_hours': [18, 19, 20, 21, 22], 'off_peak_hours': [0, 1, 2, 3, 4, 5], 'morning_hours': [6, 7, 8], 'work_hours': [9, 10, 11, 12, 13, 14, 15, 16], 'reasoning': 'Using default DACH / Europe-Berlin activity profile (1 hour per round)'}


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
    return TimeSimulationConfig(total_simulation_hours=self._coerce_int(result.get('total_simulation_hours'), 72), minutes_per_round=self._coerce_int(result.get('minutes_per_round'), 60), agents_per_hour_min=agents_per_hour_min, agents_per_hour_max=agents_per_hour_max, peak_hours=self._coerce_int_list(result.get('peak_hours'), [19, 20, 21, 22]), off_peak_hours=self._coerce_int_list(result.get('off_peak_hours'), [0, 1, 2, 3, 4, 5]), off_peak_activity_multiplier=0.05, morning_hours=self._coerce_int_list(result.get('morning_hours'), [6, 7, 8]), morning_activity_multiplier=0.4, work_hours=self._coerce_int_list(result.get('work_hours'), list(range(9, 19))), work_activity_multiplier=0.7, peak_activity_multiplier=1.5)
