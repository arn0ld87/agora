"""Persona-Eligibility-Filter — schließt Entitäten aus, die keine
handlungsfähigen Stakeholder eines Szenarios sind.

Issue #1034 (Teilpunkt 1) · 2026-08-03

Ursache: ``EntityReader.filter_defined_entities`` filtert rein
label-technisch — jede Entität, die irgendein Label außer ``Entity``/
``Node`` trägt, gilt als "definiert" und geht in die Persona-Generierung.
Ontologie-Typen wie ``Country`` oder ``Product`` haben aber keinen
menschlichen Träger. ``OasisProfileGenerator._generate_profile_with_llm``
fängt jeden nicht in ``INDIVIDUAL_ENTITY_TYPES``/``GROUP_ENTITY_TYPES``
gelisteten Typ trotzdem über den institutionellen ``else``-Zweig ab und
erzeugt eine Person, die "FOR the following organization/group" spricht —
so entstehen Personas wie "Mitarbeiter:in bei USA" oder "bei Agora" (der
Name der Analyseplattform selbst).

Zwei Stufen, bewusst konservativ:

1. Harte Blockliste über ``entity_type`` (``INELIGIBLE_ENTITY_TYPES``) —
   Typen, die keinen menschlichen Träger haben können.
2. Unbekannte Typen (weder Blockliste noch
   ``OasisProfileGenerator.INDIVIDUAL_ENTITY_TYPES``/``GROUP_ENTITY_TYPES``)
   passieren den Filter, werden aber auf INFO-Ebene protokolliert. Eine
   harte Allowlist würde bei freien, auch deutschsprachigen
   Ontologie-Labels (``Behörde``, ``Verband``) den kompletten Pool leeren
   — genau die Fehlerklasse stiller Degradierung, die Issue #1029 gerade
   beseitigt hat.

Öffentliche Funktion für beide Aufrufpfade, die dieselbe Menge filtern
müssen — keine zweite Kopie der Filterlogik:

* Preview-Pfad: ``api/simulation_prepare.py``
* Laufpfad: ``services/prepare_service.py::_phase_read_entities``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from ..contracts.pipeline_degradation_contract import (
    DegradationKind,
    DegradationSeverity,
)
from ..utils.logger import get_logger
from .degradation_collector import DegradationCollector
from .entity_reader import EntityNode

logger = get_logger("agora.persona_eligibility")


# Stufe 1 — harte Blockliste. Case-insensitiv gegen den normalisierten
# entity_type geprüft. Konstante, kein verstreuter Inline-Check.
INELIGIBLE_ENTITY_TYPES: frozenset[str] = frozenset(
    {
        "country",
        "nation",
        "state",
        "region",
        "city",
        "location",
        "place",
        "product",
        "service",
        "software",
        "platform",
        "tool",
        "application",
        "technology",
        "concept",
        "topic",
        "theme",
        "method",
        "framework",
        "standard",
        "law",
        "regulation",
        "document",
        "report",
        "dataset",
        "metric",
        "event",
        "date",
        "currency",
    }
)


def _known_entity_types() -> frozenset[str]:
    """``INDIVIDUAL_ENTITY_TYPES``/``GROUP_ENTITY_TYPES`` — Single Source
    of Truth im Generator, hier nur für die Stufe-2-Klassifikation
    (unbekannt vs. bekannt) gelesen.

    Lazy importiert: Aufrufer, die nur die Blockliste brauchen, ziehen
    sich damit nicht den (schwereren) ``oasis_profile_generator``-Import
    ins Modul.
    """
    from .oasis_profile_generator import OasisProfileGenerator

    return frozenset(
        entity_type.lower()
        for entity_type in (
            *OasisProfileGenerator.INDIVIDUAL_ENTITY_TYPES,
            *OasisProfileGenerator.GROUP_ENTITY_TYPES,
        )
    )


@dataclass(frozen=True)
class EligibilityExclusion:
    """Eine von der Persona-Generierung ausgeschlossene Entität."""

    entity_name: str
    entity_type: str
    reason: str


@dataclass
class PersonaEligibilityResult:
    """Ergebnis des Eignungsfilters."""

    eligible: list[EntityNode]
    exclusions: list[EligibilityExclusion] = field(default_factory=list)

    @property
    def excluded_count(self) -> int:
        return len(self.exclusions)


def filter_eligible_entities(
    entities: Sequence[EntityNode],
    *,
    degradations: Optional[DegradationCollector] = None,
) -> PersonaEligibilityResult:
    """Schließt Entitäten aus, die keine handlungsfähigen Stakeholder sind.

    Args:
        entities: bereits label-gefilterte Entitäten (Output von
            ``EntityReader.filter_defined_entities``).
        degradations: optionaler Sammler für stille Teilausfälle
            (Issue #1029). Ein einzelner Ausschluss ist kein
            Degradations-Befund — erst die vollständige Leerung eines
            zuvor nicht-leeren Pools wird als ``BLOCKING`` gemeldet.

    Returns:
        ``PersonaEligibilityResult`` mit den verbleibenden Entitäten und
        den Ausschlussgründen.
    """
    known_types = _known_entity_types()
    eligible: list[EntityNode] = []
    exclusions: list[EligibilityExclusion] = []

    for entity in entities:
        entity_type = entity.get_entity_type() or "Entity"
        normalized = entity_type.strip().lower()

        if normalized in INELIGIBLE_ENTITY_TYPES:
            reason = (
                f"entity_type '{entity_type}' hat keinen menschlichen Träger "
                "(Blockliste, Issue #1034)"
            )
            exclusions.append(
                EligibilityExclusion(
                    entity_name=entity.name,
                    entity_type=entity_type,
                    reason=reason,
                )
            )
            logger.info(
                "Persona-Eligibility: Entität ausgeschlossen name=%s type=%s reason=%s",
                entity.name,
                entity_type,
                reason,
            )
            continue

        if normalized not in known_types:
            logger.info(
                "Persona-Eligibility: unbekannter entity_type name=%s type=%s "
                "— wird NICHT ausgeschlossen (konservativ, siehe Issue #1034)",
                entity.name,
                entity_type,
            )

        eligible.append(entity)

    total_before = len(entities)
    if total_before > 0 and not eligible and degradations is not None:
        excluded_types = sorted({exclusion.entity_type for exclusion in exclusions})
        degradations.record(
            kind=DegradationKind.GRAPH_BELOW_THRESHOLD,
            severity=DegradationSeverity.BLOCKING,
            detail=(
                f"Der Eignungsfilter hat alle {total_before} Entitäten "
                "ausgeschlossen — keine handlungsfähigen Stakeholder im "
                f"Pool. Betroffene Typen: {', '.join(excluded_types)}."
            ),
            context={
                "entities_before": total_before,
                "entities_after": 0,
                "excluded_types": ", ".join(excluded_types),
            },
        )

    return PersonaEligibilityResult(eligible=eligible, exclusions=exclusions)


__all__ = [
    "INELIGIBLE_ENTITY_TYPES",
    "EligibilityExclusion",
    "PersonaEligibilityResult",
    "filter_eligible_entities",
]
