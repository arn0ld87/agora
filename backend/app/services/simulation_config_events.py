"""Implementation helpers extracted from SimulationConfigGenerator.

The public compatibility surface remains app.services.simulation_config_generator.
"""

from __future__ import annotations

from typing import Any, Dict, List


from ..utils.logger import get_logger
from .entity_reader import EntityNode
from .simulation_config_models import (
    AgentActivityConfig,
    EventConfig,
)
from .simulation_config_schemas import (
    EventConfigResponse,
)

logger = get_logger("agora.simulation_config")

# Responsibility group: events

def _generate_event_config(self, context: str, simulation_requirement: str, entities: List[EntityNode]) -> Dict[str, Any]:
    """Generate event configuration"""
    type_examples = {}
    for e in entities:
        etype = e.get_entity_type() or 'Unknown'
        if etype not in type_examples:
            type_examples[etype] = []
        if len(type_examples[etype]) < 3:
            type_examples[etype].append(e.name)
    type_info = '\n'.join([f"- {t}: {', '.join(examples)}" for t, examples in type_examples.items()])
    context_truncated = context[:self.EVENT_CONFIG_CONTEXT_LENGTH]
    prompt = f'Based on the following simulation requirements, generate event configuration.\n\nSimulation Requirements: {simulation_requirement}\n\n{context_truncated}\n\n## Available Entity Types and Examples\n{type_info}\n\n## Task\nPlease generate event configuration JSON:\n- Extract hot topic keywords\n- Describe opinion development direction\n- Design initial post content, **each post must specify poster_type (publisher type)**\n\n**Important**: poster_type must be selected from the "Available Entity Types" above so initial posts can be assigned to appropriate agents for publishing.\nExample: Official statements should be published by Official/University type, news by MediaOutlet, student opinions by Student type.\n\nReturn JSON format (no markdown):\n{{\n    "hot_topics": ["keyword1", "keyword2", ...],\n    "narrative_direction": "<description of opinion development direction>",\n    "initial_posts": [\n        {{"content": "post content", "poster_type": "entity type (must select from available types)"}},\n        ...\n    ],\n    "reasoning": "<brief explanation>"\n}}'
    system_prompt = 'You are an opinion analysis expert. Return pure JSON format. Note poster_type must match available entity types precisely.'
    try:
        return self._call_llm_with_retry(prompt, system_prompt, EventConfigResponse)
    except Exception as e:  # noqa: BLE001 — logged and intentionally converted to default config
        logger.warning(f'Event config LLM generation failed: {e}, using default configuration')
        return {'hot_topics': [], 'narrative_direction': '', 'initial_posts': [], 'reasoning': 'Using default configuration'}


def _parse_event_config(self, result: Dict[str, Any]) -> EventConfig:
    """Parse event configuration result"""
    return EventConfig(initial_posts=result.get('initial_posts', []), scheduled_events=[], hot_topics=result.get('hot_topics', []), narrative_direction=result.get('narrative_direction', ''))


def _assign_initial_post_agents(self, event_config: EventConfig, agent_configs: List[AgentActivityConfig]) -> EventConfig:
    """
        Assign appropriate publisher agents to initial posts

        Match agent_id based on each post's poster_type.

        Issue #1226: ``poster_type`` traegt je nach Lauf entweder Entity-Typen
        (``management``, ``retrainee``) oder Entity-**Namen** (``betriebsrat``,
        ``kostentraeger``) — welchen Namensraum das Event-Config-Modell waehlt,
        schwankt bei identischem Prompt und Testfall. Ein Index allein auf
        ``entity_type`` kann den Namensfall strukturell nie treffen; dort fiel
        vor diesem Fix jeder Seed-Post in den Fallback und damit auf denselben
        Agenten. Der Namens-Index deckt beide Ausgabeformen ab, unabhaengig vom
        NER-Vokabular des jeweiligen Laufs.
        """
    if not event_config.initial_posts:
        return event_config
    agents_by_name: Dict[str, List[AgentActivityConfig]] = {}
    agents_by_type: Dict[str, List[AgentActivityConfig]] = {}
    for agent in agent_configs:
        agents_by_name.setdefault(agent.entity_name.strip().lower(), []).append(agent)
        agents_by_type.setdefault(agent.entity_type.strip().lower(), []).append(agent)
    fallback_agents = sorted(agent_configs, key=lambda a: (-a.influence_weight, a.agent_id))
    type_aliases = {'official': ['official', 'university', 'governmentagency', 'government'], 'university': ['university', 'official'], 'mediaoutlet': ['mediaoutlet', 'media'], 'student': ['student', 'person'], 'professor': ['professor', 'expert', 'teacher'], 'alumni': ['alumni', 'person'], 'organization': ['organization', 'ngo', 'company', 'group'], 'person': ['person', 'student', 'alumni']}
    used_indices: Dict[str, int] = {}
    updated_posts = []
    for post in event_config.initial_posts:
        poster_type = post.get('poster_type', '').lower()
        content = post.get('content', '')
        matched_agent_id = None

        def _take(bucket: List[AgentActivityConfig], counter_key: str) -> int:
            """Naechster Agent aus ``bucket``, reihum ueber ``used_indices``."""
            idx = used_indices.get(counter_key, 0) % len(bucket)
            used_indices[counter_key] = idx + 1
            return bucket[idx].agent_id
        if poster_type in agents_by_name:
            matched_agent_id = _take(agents_by_name[poster_type], f'name:{poster_type}')
        elif poster_type in agents_by_type:
            matched_agent_id = _take(agents_by_type[poster_type], f'type:{poster_type}')
        else:
            for alias_key, aliases in type_aliases.items():
                if poster_type in aliases or alias_key == poster_type:
                    for alias in aliases:
                        if alias in agents_by_type:
                            matched_agent_id = _take(agents_by_type[alias], f'type:{alias}')
                            break
                if matched_agent_id is not None:
                    break
        if matched_agent_id is None:
            if fallback_agents:
                matched_agent_id = _take(fallback_agents, '__fallback__')
                logger.warning("No matching agent found for poster_type '%s' — round-robin fallback to agent_id=%s", poster_type, matched_agent_id)
            else:
                logger.warning("No agent configs available for poster_type '%s' — falling back to agent_id=0", poster_type)
                matched_agent_id = 0
        updated_posts.append({'content': content, 'poster_type': post.get('poster_type', 'Unknown'), 'poster_agent_id': matched_agent_id})
        logger.info(f"Initial post assigned: poster_type='{poster_type}' -> agent_id={matched_agent_id}")
    event_config.initial_posts = updated_posts
    return event_config
