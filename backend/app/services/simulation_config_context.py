"""Implementation helpers extracted from SimulationConfigGenerator.

The public compatibility surface remains app.services.simulation_config_generator.
"""

from __future__ import annotations

from typing import Dict, List


from ..utils.logger import get_logger
from .entity_reader import EntityNode

logger = get_logger("agora.simulation_config")

# Responsibility group: context

# Sicherheitsabstand zum harten Limit. Stammt aus der Vorgaengerfassung, wo er
# nur auf das Dokument wirkte; jetzt gilt er fuer den gesamten Kontext.
_CONTEXT_RESERVE = 500

_SECTION_TRUNCATED = '\n...(truncated)'
_DOCUMENT_TRUNCATED = '\n...(document truncated)'


def _truncate_body(body: str, available: int, marker: str, *, line_safe: bool) -> str | None:
    """Kuerzt ``body`` auf ``available`` Zeichen inklusive Marker.

    ``None`` heisst: es passt nicht einmal der Marker, der Abschnitt entfaellt
    ganz. ``line_safe`` schneidet an der letzten vollstaendigen Zeilengrenze —
    noetig fuer den zeilenstrukturierten Entity-Block, wo ein Schnitt mitten im
    Datensatz einen halben Entitaetsnamen erzeugt, der wie eine echte Entitaet
    aussieht.
    """
    if len(body) <= available:
        return body
    keep = available - len(marker)
    if keep <= 0:
        return None
    if line_safe:
        boundary = body.rfind('\n', 0, keep)
        if boundary > 0:
            keep = boundary
    return body[:keep] + marker


def _build_context(self, simulation_requirement: str, document_text: str, entities: List[EntityNode]) -> str:
    """Build LLM context, truncate the whole payload to ``MAX_CONTEXT_LENGTH``.

    Die Vorgaengerfassung kuerzte ausschliesslich ``document_text`` gegen das
    Restbudget. ``simulation_requirement`` und die Entity-Zusammenfassung gingen
    ungekuerzt hinein — zusammen konnten sie das Limit allein ueberschreiten, und
    die Restbudget-Rechnung wurde dann negativ, sodass das Dokument still ganz
    entfiel, ohne dass der Ueberlauf verschwand.

    Die Abschnitte werden jetzt in Prioritaetsreihenfolge gegen ein gemeinsames
    Budget gefuellt: Struktur/Header, dann Simulationsziel, dann Entitaeten,
    zuletzt das Originaldokument. Header werden nie angeschnitten — passt ein
    Abschnitt nicht mehr, entfaellt er als Ganzes mit Protokolleintrag.
    """
    entity_summary = self._summarize_entities(entities)

    budget = self.MAX_CONTEXT_LENGTH - _CONTEXT_RESERVE
    context_parts: List[str] = []
    used = 0

    def _append(header: str, body: str, marker: str, *, line_safe: bool = False) -> None:
        nonlocal used
        separator = 1 if context_parts else 0
        available = budget - used - separator - len(header)
        if available <= 0:
            logger.warning(
                'Kontextbudget erschoepft: Abschnitt %r entfaellt vollstaendig',
                header.strip(),
            )
            return
        fitted = _truncate_body(body, available, marker, line_safe=line_safe)
        if fitted is None:
            logger.warning(
                'Kontextbudget erschoepft: Abschnitt %r entfaellt vollstaendig',
                header.strip(),
            )
            return
        if len(fitted) < len(body):
            logger.info(
                'Kontext gekuerzt: Abschnitt %r von %d auf %d Zeichen',
                header.strip(), len(body), len(fitted),
            )
        context_parts.append(header + fitted)
        used += separator + len(header) + len(fitted)

    _append('## Simulation Requirements\n', simulation_requirement, _SECTION_TRUNCATED)
    _append(
        f'\n## Entity Information ({len(entities)})\n',
        entity_summary,
        _SECTION_TRUNCATED,
        line_safe=True,
    )
    if document_text:
        _append('\n## Original Document Content\n', document_text, _DOCUMENT_TRUNCATED)

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
