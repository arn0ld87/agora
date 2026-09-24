"""Braucht ein Abschnittsentwurf noch Retrieval? (Issue #1294)

Der Section-ReACT-Loop wies einen fertigen Entwurf zurück, solange weniger
als ``min_tool_calls`` Werkzeugaufrufe gezählt waren. Die Zahl war ein
schlechter Stellvertreter für die eigentliche Frage: ein ergebnisloser
Aufruf erfüllte die Schwelle, ein Entwurf, dessen Aussagen bereits in der
vorab geladenen Evidence stehen, erfüllte sie nie.

Die Entscheidung hier fragt stattdessen die Evidence, gegen die der
Abschnitt anschließend gebunden wird — denselben Pool wie
``ReportAgent._build_claims_for_section``: die für den Abschnitt erhobenen
Items plus die ``global_evidence_refs`` der Evidence-Map. Ausreichend ist
ein Abschnitt, wenn

1. das Retrieval dieses Abschnitts bindbare Evidence registriert hat, oder
2. jede prüfbare Aussage des Entwurfs thematisch im vorab geladenen Pool
   vorkommt — gemessen mit :func:`classify_claim_gap`, also mit derselben
   Schwelle, mit der ``data_gap`` "Information vorhanden" von "fehlt in den
   Quellen" trennt.

Die Entscheidung ersetzt keines der nachgelagerten Gates: Bindung,
Entailment und Prosa-Prüfung laufen unverändert über jeden Claim. Sie
entscheidet nur, ob der Loop einen weiteren Retrieval-Schritt anfordert.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Sequence

from ...contracts.report_contract import FORBIDDEN_EVIDENCE_TYPES
from .data_gap import ClaimGapKind, classify_claim_gap
from .sections import (
    atomize_claim_chunk,
    is_atomic_claim,
    is_claim_candidate,
    is_discourse_sentence,
)


def _bindable(items: Optional[Sequence[Any]]) -> List[Dict[str, Any]]:
    """Evidence-Items, die der Claim-Binder annimmt (Modell-Output nicht)."""
    return [
        item for item in items or []
        if isinstance(item, dict) and item.get("type") not in FORBIDDEN_EVIDENCE_TYPES
    ]


def preloaded_evidence(evidence_map: Any) -> List[Dict[str, Any]]:
    """Die ``global_evidence_refs`` der Evidence-Map, aufgelöst im Index."""
    if not isinstance(evidence_map, Mapping):
        return []
    index = evidence_map.get("evidence_index") or {}
    return _bindable([
        index[evidence_id]
        for evidence_id in evidence_map.get("global_evidence_refs") or []
        if evidence_id in index
    ])


def draft_claim_units(draft: str) -> List[str]:
    """Prüfbare Aussagen eines Entwurfs.

    Dieselben Filter wie S3a/S3b in ``_build_claims_for_section``:
    Strukturmarkup fällt weg, Mehrsatz-Absätze werden atomisiert,
    Gliederungssätze ohne Substanz zählen nicht (#1316).
    """
    units: List[str] = []
    for chunk in re.split(r"\n\s*\n", (draft or "").strip()):
        chunk = chunk.strip()
        if not chunk or not is_claim_candidate(chunk):
            continue
        atoms = [atom for atom in atomize_claim_chunk(chunk) if is_atomic_claim(atom)]
        if atoms:
            units.extend(atoms)
        elif not is_discourse_sentence(chunk):
            units.append(chunk)
    return units


def section_has_sufficient_evidence(
    draft: str,
    *,
    section_evidence: Optional[Sequence[Any]],
    evidence_map: Any,
) -> bool:
    """Deckt die vorhandene Evidence den Entwurf, ohne weiteres Retrieval?

    ``section_evidence`` ist ``agent._active_section_evidence`` — was das
    Retrieval dieses Abschnitts registriert hat. Ein Entwurf ohne prüfbare
    Aussage ist nicht gedeckt: es gibt nichts, woran die Deckung zu messen
    wäre, und ein weiterer Retrieval-Schritt ist dann der richtige Weg.
    """
    if _bindable(section_evidence):
        return True
    pool = preloaded_evidence(evidence_map)
    units = draft_claim_units(draft)
    if not pool or not units:
        return False
    return all(
        classify_claim_gap(unit, related_evidence_count=0, evidence_pool=pool)
        is ClaimGapKind.BINDING_FAILURE
        for unit in units
    )


__all__ = [
    "draft_claim_units",
    "preloaded_evidence",
    "section_has_sufficient_evidence",
]
