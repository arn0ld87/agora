"""Implementation helpers extracted from SimulationConfigGenerator.

The public compatibility surface remains app.services.simulation_config_generator.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from pydantic import BaseModel, ValidationError as PydanticValidationError

from ..utils.logger import get_logger

logger = get_logger("agora.simulation_config")

# Responsibility group: llm

def _call_llm_with_retry(self, prompt: str, system_prompt: str, schema: Any) -> Dict[str, Any]:
    """LLM call with retry using LLMClient.chat_json and Pydantic schema validation.

        Retry-Strategie (Issue aus PR #936, Codex P2): ``LLMClient.chat_json``
        und ``LLMClient.chat`` besitzen bereits einen Transport-Retry
        (``llm_call_with_retry`` mit bis zu 4 Versuchen). Die äußere Schleife
        hier retried daher **nur Schema-/JSON-Fehler** (``ValueError``,
        ``pydantic.ValidationError``), die auf inhaltsseitige Probleme
        hindeuten — nicht auf transiente Transportstörungen. Auth-Fehler (4xx)
        oder finale 5xx nach internem Retry werden sofort durchgereicht, statt
        sie hier nochmals zu multiplizieren (sonst bis zu 24 Requests pro
        Konfigurationsschritt). Der Regex-Reparatur-Fallback bleibt für
        Provider ohne ``json_schema``-Support erhalten.
        """
    max_attempts = 3
    last_error: Optional[Exception] = None
    for attempt in range(max_attempts):
        try:
            return self.llm_client.chat_json(messages=[{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': prompt}], temperature=0.7 - attempt * 0.1, schema=schema, context='graph')
        except (ValueError, PydanticValidationError) as e:
            logger.warning('LLM chat_json/validation failed (attempt %d): %s', attempt + 1, str(e)[:80])
            last_error = e
            try:
                raw_text = self.llm_client.chat(messages=[{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': prompt}], temperature=0.7 - attempt * 0.1, context='graph')
                fixed = self._try_fix_config_json(raw_text)
                if fixed:
                    if isinstance(schema, type) and issubclass(schema, BaseModel):
                        return schema.model_validate(fixed).model_dump(mode='json')
                    return fixed
            except (ValueError, PydanticValidationError) as fallback_err:
                logger.warning('Fallback regex repair/validation failed: %s', fallback_err)
            except Exception as fallback_err:  # noqa: BLE001 — transport errors are already internally retried
                logger.warning('Fallback chat() hit transport error (already retried internally by llm_call_with_retry): %s', fallback_err)
            import time
            time.sleep(2 * (attempt + 1))
    raise last_error or Exception('LLM call failed')


def _fix_truncated_json(self, content: str) -> str:
    """Fix truncated JSON"""
    content = content.strip()
    open_braces = content.count('{') - content.count('}')
    open_brackets = content.count('[') - content.count(']')
    if content and content[-1] not in '",}]':
        content += '"'
    content += ']' * open_brackets
    content += '}' * open_braces
    return content


def _try_fix_config_json(self, content: str) -> Optional[Dict[str, Any]]:
    """Try to fix configuration JSON"""
    import re
    content = self._fix_truncated_json(content)
    json_match = re.search('\\{[\\s\\S]*\\}', content)
    if json_match:
        json_str = json_match.group()

        def fix_string(match):
            s = match.group(0)
            s = s.replace('\n', ' ').replace('\r', ' ')
            s = re.sub('\\s+', ' ', s)
            return s
        json_str = re.sub('"[^"\\\\]*(?:\\\\.[^"\\\\]*)*"', fix_string, json_str)
        try:
            return json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            json_str = re.sub('[\\x00-\\x1f\\x7f-\\x9f]', ' ', json_str)
            json_str = re.sub('\\s+', ' ', json_str)
            try:
                return json.loads(json_str)
            except (json.JSONDecodeError, ValueError):
                pass
    return None
