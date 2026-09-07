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


# Kopfnomen, die einen Typ unabhaengig von seinen Bestimmungswoertern als
# nicht-menschlich ausweisen. Geprueft wird als **Suffix**, nicht als
# Teilstring — im Deutschen wie im Englischen steht der Kopf einer
# Nominalkomposition hinten: ``LearningTechnology`` -> ``technology``,
# ``Lernsystem`` -> ``system``.
#
# Der Unterschied ist tragend. Ein Teilstring-Vergleich wuerde
# ``AIServiceProvider`` ueber ``service`` blocken, obwohl das ein
# Unternehmen ist und sehr wohl eine Persona traegt; als Suffix greift dort
# ``provider``, das bewusst **nicht** in dieser Menge steht. Aus demselben
# Grund fehlen hier ``organization``, ``group``, ``team``, ``board``,
# ``committee``, ``association``, ``agency``, ``authority``, ``department``,
# ``office``, ``center``, ``representative`` und ``provider``: alles Koepfe,
# die auf einen menschlichen Traeger zeigen.
#
# Stufe 1 schliesst hart aus, ein Fehlurteil hier kostet eine legitime
# Persona ohne Rueckfrage. Deshalb stehen hier nur Koepfe, die in keiner
# plausiblen Lesart einen Menschen oder eine Personengruppe bezeichnen.
#
# Aus demselben Grund fehlt ``service``: ``AIService`` waere zwar richtig
# geblockt, ``CustomerService`` ist aber eine Abteilung mit Menschen. Solche
# mehrdeutigen Koepfe bleiben Stufe 2 ueberlassen.
INELIGIBLE_TYPE_HEADS: frozenset[str] = frozenset(
    {
        # Technik und Artefakte
        "technology",
        "technologie",
        "system",
        "software",
        "platform",
        "plattform",
        "application",
        "anwendung",
        "tool",
        "werkzeug",
        "interface",
        "schnittstelle",
        "component",
        "komponente",
        "module",
        "modul",
        "infrastructure",
        "infrastruktur",
        "architecture",
        "architektur",
        "pipeline",
        "algorithm",
        "algorithmus",
        "database",
        "datenbank",
        "dataset",
        "datensatz",
        # Mess- und Bewertungsgroessen
        "criterion",
        "kriterium",
        "metric",
        "metrik",
        "kennzahl",
        "score",
        "indicator",
        "indikator",
        # Verfahren und Abstrakta
        "method",
        "methode",
        "methodology",
        "verfahren",
        "process",
        "prozess",
        "workflow",
        "concept",
        "konzept",
        "category",
        "kategorie",
        "requirement",
        "anforderung",
        # Dokumente und Regelwerke
        "document",
        "dokument",
        "report",
        "bericht",
        "protocol",
        "protokoll",
        "standard",
        "format",
        "license",
        "lizenz",
        "regulation",
        "verordnung",
        # Domaenen- und Geschaeftsbegriffe. Abgeglichen gegen jeden Eintrag
        # von ``INELIGIBLE_ENTITY_TYPES``: ``product``, ``topic``/``theme``
        # und ``framework`` sind dort exakt gelistet, aber ``SoftwareProduct``,
        # ``DiscussionTopic`` und ``LegalFramework`` liefen als "unbekannter
        # Typ" durch die Stufe-1-Pruefung, weil der Vergleich nur exakt
        # matchte (Issue #1473, Review-Befund). ``event`` ist als Kopf
        # ebenfalls unproblematisch. Bewusst **nicht** aufgenommen: ``model``
        # (``RoleModel`` ist ein Mensch), ``law`` (``Outlaw`` ist ein
        # Mensch), sowie die geografischen Koepfe ``country``/``nation``/
        # ``state``/``region``/``city``/``location``/``place`` — ``nation``
        # kann ein Kollektiv mit menschlichem Traeger sein (``FirstNation``),
        # ``state`` kollidiert mit ``HeadOfState``; die uebrigen sind vom
        # gemeldeten Produktionsbefund nicht betroffen und bleiben aussen
        # vor, um die Aenderung eng am Befund zu halten.
        "product",
        "produkt",
        "topic",
        "theme",
        "thema",
        "framework",
        "rahmenwerk",
        "event",
        "ereignis",
    }
)


def _ineligible_head(normalized_type: str) -> Optional[str]:
    """Liefert das blockierende Kopfnomen eines Typs, sonst ``None``.

    Der laengste Treffer gewinnt, damit ein spezifischer Kopf einen
    kuerzeren, zufaellig ebenfalls passenden verdraengt.
    """
    matches = [
        head for head in INELIGIBLE_TYPE_HEADS if normalized_type.endswith(head)
    ]
    if not matches:
        return None
    return max(matches, key=len)


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
    unknown_types: list[tuple[str, str]] = []

    for entity in entities:
        entity_type = entity.get_entity_type() or "Entity"
        normalized = entity_type.strip().lower()

        blocking_head = None if normalized in INELIGIBLE_ENTITY_TYPES else _ineligible_head(normalized)
        if normalized in INELIGIBLE_ENTITY_TYPES or blocking_head is not None:
            if blocking_head is None:
                reason = (
                    f"entity_type '{entity_type}' hat keinen menschlichen Träger "
                    "(Blockliste, Issue #1034)"
                )
            else:
                reason = (
                    f"entity_type '{entity_type}' hat keinen menschlichen Träger "
                    f"— Kopfnomen '{blocking_head}' (Blockliste, Issue #1034)"
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
            # Issue #1177 (dritter Befund): Verglichen wird gegen eine feste
            # Typliste, waehrend die Ontologie ihre Typen frei und
            # deutschsprachig generiert — praktisch *jeder* Typ ist damit
            # "unbekannt". Auf INFO feuerte die Zeile fuer 100 % der
            # Entitaeten und markierte dadurch nichts; die tatsaechlichen
            # Ausschluesse gingen darin unter. Aggregiert wird sie nach der
            # Schleife einmal ausgegeben.
            unknown_types.append((entity.name, entity_type))
            logger.debug(
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

    if unknown_types:
        # Issue #1177: einmal aggregiert statt einmal pro Entitaet. Die
        # Einzelzeilen standen auf INFO und feuerten fuer praktisch jede
        # Entitaet — die tatsaechlichen Ausschluesse gingen darin unter.
        distinct = sorted({entity_type for _name, entity_type in unknown_types})
        logger.info(
            "Persona-Eligibility: %d von %d Entitaeten tragen einen entity_type "
            "ausserhalb der bekannten Liste und werden konservativ zugelassen "
            "(Issue #1034). Betroffene Typen: %s",
            len(unknown_types),
            len(entities),
            ", ".join(distinct),
        )

    return PersonaEligibilityResult(eligible=eligible, exclusions=exclusions)


__all__ = [
    "INELIGIBLE_ENTITY_TYPES",
    "EligibilityExclusion",
    "PersonaEligibilityResult",
    "filter_eligible_entities",
]
