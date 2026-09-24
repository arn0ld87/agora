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
ein Abschnitt, wenn der Entwurf mindestens eine prüfbare Aussage enthält und

1. das Retrieval dieses Abschnitts bindbare Evidence registriert hat, oder
2. jede prüfbare Aussage des Entwurfs thematisch im vorab geladenen Pool
   vorkommt — gemessen mit :func:`topic_present_in_pool`, also mit derselben
   Schwelle, mit der ``data_gap`` "Information vorhanden" von "fehlt in den
   Quellen" trennt.

Bewusst nicht :func:`classify_claim_gap`: dessen Zahlen-Kurzschluss beantwortet
"könnte Retrieval das finden?" und lässt "90 Prozent der Lehrkräfte" durch
"90 Prozent Regenwahrscheinlichkeit" gedeckt erscheinen. Hier zählt nur die
thematische Deckung.

Die Entscheidung ersetzt keines der nachgelagerten Gates: Bindung,
Entailment und Prosa-Prüfung laufen unverändert über jeden Claim. Sie
entscheidet nur, ob der Loop einen weiteren Retrieval-Schritt anfordert.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Sequence

from ...contracts.report_contract import FORBIDDEN_EVIDENCE_TYPES
from ..claim_atomizer import split_claim_chunks
from .data_gap import topic_present_in_pool
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

    Dieselbe Zerlegung wie S3a–S3c in ``_build_claims_for_section``:
    Strukturmarkup fällt weg, Mehrsatz-Absätze werden atomisiert,
    Gliederungssätze ohne Substanz zählen nicht (#1316), Sammelclaims
    werden in ihre Teilaussagen gespalten (#1346) — jede Einheit, die der
    Binder später einzeln prüft, wird auch hier einzeln geprüft.
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
    return split_claim_chunks(units)


def section_has_sufficient_evidence(
    draft: str,
    *,
    section_evidence: Optional[Sequence[Any]],
    evidence_map: Any,
) -> bool:
    """Deckt die vorhandene Evidence den Entwurf, ohne weiteres Retrieval?

    ``section_evidence`` ist ``agent._active_section_evidence`` — was das
    Retrieval dieses Abschnitts registriert hat. Ein Entwurf ohne prüfbare
    Aussage ist nie gedeckt, auch nicht mit registrierter Evidence: es gibt
    nichts, woran der Beleg hängen könnte.
    """
    units = draft_claim_units(draft)
    if not units:
        return False
    if _bindable(section_evidence):
        return True
    pool = preloaded_evidence(evidence_map)
    return bool(pool) and all(topic_present_in_pool(unit, pool) for unit in units)


__all__ = [
    "draft_claim_units",
    "preloaded_evidence",
    "section_has_sufficient_evidence",
]
