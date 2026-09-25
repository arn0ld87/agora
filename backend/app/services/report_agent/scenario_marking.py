"""Szenario-Text in der Tool-Ausgabe kennzeichnen (Issue #1240).

``classify_evidence`` verhindert, dass Szenario-, Frage- oder Erwartungstext
einen *Claim* stützt. Der Fließtext entsteht aber vorher: das Modell liest die
gerenderte Tool-Ausgabe, und dort stand ein Satz wie „Die IHK sieht generierte
Übungsaufgaben unkritisch" gleichberechtigt neben echten Domänenfakten — unter
der Überschrift „Key Facts (Please quote these verbatim in the report)". Der
Report zitierte ihn danach als „überraschendsten" Befund.

Die Kennzeichnung ändert weder Retrieval noch Evidence-Index; sie macht in der
Beobachtung sichtbar, welche Fakten aus Dokumenten mit nicht stützender Rolle
stammen. Der Prompt-Block ``<evidence_gating>`` (ADR-0002 Anker 1) bleibt
unberührt — der Hinweis steht in der Beobachtung selbst.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from ...contracts.document_manifest_contract import NON_SUPPORTING_DOCUMENT_ROLES
from ..graph.graph_dtos import (
    InsightForgeResult,
    PanoramaResult,
    SearchResult,
    provenance_at,
)
from .evidence import document_role_of

SCENARIO_FACT_MARKER = "[Vorgabe des Testfalls – kein Simulationsbefund]"

SCENARIO_FACT_NOTICE = (
    f"\n\nHinweis: Mit {SCENARIO_FACT_MARKER} gekennzeichnete Fakten stammen aus "
    "Szenario-, Frage- oder Erwartungstext des Eingabedokuments. Sie beschreiben "
    "den Testfall und dürfen nicht als Ergebnis der Simulation oder als Beleg "
    "zitiert werden."
)


def _fact_lists(result: Any) -> Iterable[Tuple[List[str], List[Optional[Dict[str, Any]]]]]:
    if isinstance(result, InsightForgeResult):
        yield result.semantic_facts, result.semantic_facts_provenance
    elif isinstance(result, PanoramaResult):
        yield result.active_facts, result.active_facts_provenance
        yield result.historical_facts, result.historical_facts_provenance
    elif isinstance(result, SearchResult):
        yield result.facts, result.fact_provenance


def scenario_facts(result: Any, document_roles: Optional[Dict[str, str]]) -> List[str]:
    """Fakten des Ergebnisses, deren Quelldokument eine nicht stützende Rolle hat."""
    if not document_roles:
        return []
    found: List[str] = []
    for facts, provenance in _fact_lists(result):
        for index, fact in enumerate(facts):
            role = document_role_of(provenance_at(provenance, index), document_roles)
            if role in NON_SUPPORTING_DOCUMENT_ROLES and fact and fact not in found:
                found.append(fact)
    return found


def mark_scenario_facts(rendered: str, facts: List[str]) -> str:
    """Setzt den Marker vor jede Nennung der betroffenen Fakten.

    Längere Fakten zuerst, damit ein Fakt, der Teil eines anderen ist, den
    längeren nicht zerschneidet. Bereits markierte Stellen bleiben unverändert.
    """
    if not facts or not rendered:
        return rendered
    marked = rendered
    for fact in sorted(facts, key=len, reverse=True):
        placeholder = f"\x00{len(fact)}\x00"
        marked = marked.replace(f"{SCENARIO_FACT_MARKER} {fact}", placeholder)
        marked = marked.replace(fact, f"{SCENARIO_FACT_MARKER} {fact}")
        marked = marked.replace(placeholder, f"{SCENARIO_FACT_MARKER} {fact}")
    if marked != rendered and SCENARIO_FACT_NOTICE not in marked:
        marked += SCENARIO_FACT_NOTICE
    return marked


def annotate_scenario_facts(
    result: Any, rendered: str, document_roles: Optional[Dict[str, str]]
) -> str:
    """Gerenderte Tool-Ausgabe mit gekennzeichnetem Szenario-Text."""
    return mark_scenario_facts(rendered, scenario_facts(result, document_roles))


__all__ = [
    "SCENARIO_FACT_MARKER",
    "SCENARIO_FACT_NOTICE",
    "annotate_scenario_facts",
    "mark_scenario_facts",
    "scenario_facts",
]
