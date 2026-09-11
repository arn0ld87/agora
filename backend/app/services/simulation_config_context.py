"""Implementation helpers extracted from SimulationConfigGenerator.

The public compatibility surface remains app.services.simulation_config_generator.
"""

from __future__ import annotations

from typing import Dict, List


from ..utils.logger import get_logger
from .entity_reader import EntityNode

logger = get_logger("agora.simulation_config")

# Responsibility group: context

def _build_context(self, simulation_requirement: str, document_text: str, entities: List[EntityNode]) -> str:
    """Build LLM context, truncate to maximum length"""
    entity_summary = self._summarize_entities(entities)
    context_parts = [f'## Simulation Requirements\n{simulation_requirement}', f'\n## Entity Information ({len(entities)})\n{entity_summary}']
    current_length = sum(len(p) for p in context_parts)
    remaining_length = self.MAX_CONTEXT_LENGTH - current_length - 500
    if remaining_length > 0 and document_text:
        doc_text = document_text[:remaining_length]
        if len(document_text) > remaining_length:
            doc_text += '\n...(document truncated)'
        context_parts.append(f'\n## Original Document Content\n{doc_text}')
    return '\n'.join(context_parts)


def _summarize_entities(self, entities: List[EntityNode]) -> str:
    """Generate entity summary"""
    lines = []
    by_type: Dict[str, List[EntityNode]] = {}
    for e in entities:
        t = e.get_entity_type() or 'Unknown'
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(e)
    for entity_type, type_entities in by_type.items():
        lines.append(f'\n### {entity_type} ({len(type_entities)})')
        display_count = self.ENTITIES_PER_TYPE_DISPLAY
        summary_len = self.ENTITY_SUMMARY_LENGTH
        for e in type_entities[:display_count]:
            summary_preview = e.summary[:summary_len] + '...' if len(e.summary) > summary_len else e.summary
            lines.append(f'- {e.name}: {summary_preview}')
        if len(type_entities) > display_count:
            lines.append(f'  ... and {len(type_entities) - display_count} more')
    return '\n'.join(lines)
