"""Belegdichte der Claims eines Berichts (Issue #1779, Schritt 2.1).

Zählt aus der fertigen Evidence-Map, wie dicht die Claims belegt sind, und
legt das Ergebnis als ``evidence_density.json`` im Berichtsverzeichnis ab.
Die Berechnung ist rein: kein Modellaufruf, kein I/O. Sie ändert weder
Confidence noch Status — sie macht nur messbar, was sonst ein Handskript
nachzählen müsste.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from typing import Any, Dict, List, Mapping, Optional

from ...contracts.evidence_density_contract import EvidenceDensity
from ...utils.logger import get_logger
from ..confidence_calculator import _count_independent_sources
from .storage import write_json_atomic

logger = get_logger("agora.report_agent.evidence_density")

#: Dateiname der Zählung im Berichtsverzeichnis.
EVIDENCE_DENSITY_FILENAME = "evidence_density.json"

#: Ein-Quellen-Deckel des Confidence-Rechners (``_apply_single_source_cap``).
_SINGLE_SOURCE_CAP = 0.59
_CAP_TOLERANCE = 1e-9

#: Belegart einer beobachteten Simulationshandlung.
_ACTION_TYPE = "agent_action"


def _supporting_entries(
    claim: Mapping[str, Any],
    evidence_index: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    """Stützende Belege eines Claims, je ``evidence_id`` einmal.

    Der Beleg im Claim trägt nur ``evidence_id`` und Bindungsfelder; ``type``,
    ``source`` und ``voice_key`` stehen im Index. Beides wird zusammengeführt:
    Felder des Index, überschrieben von gesetzten Feldern des Claim-Eintrags.
    """
    merged: Dict[str, Dict[str, Any]] = {}
    for entry in claim.get("evidence") or []:
        if not isinstance(entry, Mapping):
            continue
        evidence_id = entry.get("evidence_id")
        if not evidence_id or entry.get("supports_claim") is not True:
            continue
        key = str(evidence_id)
        if key in merged:
            continue
        record = evidence_index.get(key)
        combined: Dict[str, Any] = dict(record) if isinstance(record, Mapping) else {}
        combined.update({k: v for k, v in entry.items() if v is not None})
        merged[key] = combined
    return list(merged.values())


def _is_at_single_source_cap(claim: Mapping[str, Any]) -> bool:
    score = claim.get("confidence_score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return False
    return abs(float(score) - _SINGLE_SOURCE_CAP) <= _CAP_TOLERANCE


def _ratio(count: int, total: int) -> Optional[float]:
    return count / total if total else None


def compute_evidence_density(evidence_map: Mapping[str, Any]) -> EvidenceDensity:
    """Zählt die Belegdichte der Claims einer Evidence-Map.

    Fehlende Schlüssel und Einträge, die kein Mapping sind, werden
    übersprungen. Ohne Claims sind alle Zähler 0 und alle Quoten ``None``:
    eine 0,0 würde „keine Dichte" behaupten, wo nichts gemessen wurde.
    """
    raw_index = evidence_map.get("evidence_index") if isinstance(evidence_map, Mapping) else None
    evidence_index: Mapping[str, Any] = raw_index if isinstance(raw_index, Mapping) else {}
    raw_sections = evidence_map.get("sections") if isinstance(evidence_map, Mapping) else None

    total = without = single = multi = multi_independent = at_cap = with_action = 0
    links_by_type: Counter[str] = Counter()

    for section in raw_sections or []:
        if not isinstance(section, Mapping):
            continue
        for claim in section.get("claims") or []:
            if not isinstance(claim, Mapping):
                continue
            total += 1
            at_cap += _is_at_single_source_cap(claim)
            supporting = _supporting_entries(claim, evidence_index)
            if not supporting:
                without += 1
                continue
            kinds = [str(entry.get("type") or "unknown") for entry in supporting]
            links_by_type.update(kinds)
            if len(supporting) == 1:
                single += 1
            else:
                multi += 1
                multi_independent += _count_independent_sources(supporting) >= 2
            with_action += _ACTION_TYPE in kinds

    return EvidenceDensity(
        claims_total=total,
        claims_without_support=without,
        claims_single_support=single,
        claims_multi_support=multi,
        claims_multi_independent=multi_independent,
        claims_at_single_source_cap=at_cap,
        claims_with_action_support=with_action,
        supporting_links_by_type=dict(sorted(links_by_type.items())),
        single_support_ratio=_ratio(single, total),
        action_support_ratio=_ratio(with_action, total),
        single_source_cap_ratio=_ratio(at_cap, total),
        multi_independent_ratio=_ratio(multi_independent, total),
    )


def load_evidence_density(report_folder: str) -> Optional[EvidenceDensity]:
    """Liest eine gespeicherte Zählung; ``None``, wenn keine gültige vorliegt."""
    path = os.path.join(report_folder, EVIDENCE_DENSITY_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return EvidenceDensity.model_validate(json.load(handle))
    except (OSError, ValueError) as exc:
        logger.warning("Gespeicherte Belegdichte nicht lesbar (%s): %r", path, exc)
        return None


def save_evidence_density(report_folder: str, density: EvidenceDensity) -> str:
    """Schreibt die Zählung atomar als ``evidence_density.json`` und liefert den Pfad."""
    path = os.path.join(report_folder, EVIDENCE_DENSITY_FILENAME)
    write_json_atomic(path, density.model_dump(mode="json"))
    return path


__all__ = [
    "EVIDENCE_DENSITY_FILENAME",
    "compute_evidence_density",
    "load_evidence_density",
    "save_evidence_density",
]
