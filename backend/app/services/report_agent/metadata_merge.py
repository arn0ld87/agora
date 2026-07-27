"""Section-Metadaten in ReportV3-DTOs überführen.

``generate_section_metadata`` extrahiert pro Abschnitt strukturierte Daten
(Personas, Segmente, Reibungspunkte …) — bisher landeten sie ausschließlich
im Report-Logger. ReportV3 blieb leer, obwohl der Prosa-Report die Inhalte
zeigte. Dieses Modul schließt die Lücke: es macht die validierten
Section-Metadaten zur kanonischen Quelle für ReportV3 und damit für
JSON, Markdown, HTML und Frontend gleichermaßen.

Ungültige Einträge werden übersprungen statt den Report zu sprengen — ein
halluziniertes Feld darf keinen sonst gültigen Report verhindern.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Sequence

from pydantic import BaseModel, ValidationError

from ...contracts.report_v3 import (
    ChangeRecommendation,
    ContentIdea,
    FrictionPoint,
    Multiplier,
    Persona,
    PositioningVariant,
    ProjectImpact,
    Segment,
    TrustSignal,
)

logger = logging.getLogger(__name__)


#: Feldname in ReportV3 → DTO. Die Feldnamen entsprechen exakt den
#: ReportV3-Slots, damit `merge_section_metadata(...)` direkt einsetzbar ist.
STRUCTURED_SLOTS: Dict[str, type[BaseModel]] = {
    "personas": Persona,
    "segments": Segment,
    "multipliers": Multiplier,
    "friction_points": FrictionPoint,
    "trust_signals": TrustSignal,
    "change_recommendations": ChangeRecommendation,
    "project_impacts": ProjectImpact,
    "positioning_variants": PositioningVariant,
    "content_ideas": ContentIdea,
}


@dataclass
class MergedMetadata:
    """Gesammelte, validierte Struktur-Daten über alle Abschnitte."""

    personas: List[Persona] = field(default_factory=list)
    segments: List[Segment] = field(default_factory=list)
    multipliers: List[Multiplier] = field(default_factory=list)
    friction_points: List[FrictionPoint] = field(default_factory=list)
    trust_signals: List[TrustSignal] = field(default_factory=list)
    change_recommendations: List[ChangeRecommendation] = field(default_factory=list)
    project_impacts: List[ProjectImpact] = field(default_factory=list)
    positioning_variants: List[PositioningVariant] = field(default_factory=list)
    content_ideas: List[ContentIdea] = field(default_factory=list)
    rejected: List[str] = field(default_factory=list)

    def as_report_v3_kwargs(self) -> Dict[str, List[BaseModel]]:
        """Nur befüllte Slots — leere Listen sind ohnehin der DTO-Default."""
        return {
            slot: getattr(self, slot)
            for slot in STRUCTURED_SLOTS
            if getattr(self, slot)
        }


def _coerce_items[T: BaseModel](
    raw_items: Any,
    model: type[T],
    *,
    slot: str,
    seen_ids: set[str],
    rejected: List[str],
) -> List[T]:
    if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
        return []

    result: List[T] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        try:
            item = model.model_validate(raw)
        except ValidationError as exc:
            rejected.append(f"{slot}: {exc.error_count()} Feldfehler")
            logger.debug("metadata_merge: %s abgelehnt — %s", slot, exc.errors()[:2])
            continue
        item_id = str(getattr(item, "id", "") or "")
        if item_id:
            dedup_key = f"{slot}:{item_id}"
            if dedup_key in seen_ids:
                continue
            seen_ids.add(dedup_key)
        result.append(item)
    return result


def merge_section_metadata(sections: Iterable[Dict[str, Any]]) -> MergedMetadata:
    """Sammelt ``structured_metadata`` aller Abschnitte zu einem Ergebnis.

    Abschnitte werden in ihrer Reihenfolge verarbeitet; gleiche IDs aus
    mehreren Abschnitten erscheinen nur einmal.
    """
    merged = MergedMetadata()
    seen_ids: set[str] = set()

    for section in sections or []:
        if not isinstance(section, dict):
            continue
        metadata = section.get("structured_metadata")
        if not isinstance(metadata, dict):
            continue
        for slot, model in STRUCTURED_SLOTS.items():
            items = _coerce_items(
                metadata.get(slot),
                model,
                slot=slot,
                seen_ids=seen_ids,
                rejected=merged.rejected,
            )
            if items:
                getattr(merged, slot).extend(items)

    return merged


__all__ = ["MergedMetadata", "STRUCTURED_SLOTS", "merge_section_metadata"]
