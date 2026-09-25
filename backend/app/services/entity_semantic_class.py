"""Klassifikation von Entitäten in semantische Klassen (Issue #1470, Slice 4.3).

Deterministisch, kein LLM-Aufruf.  Wird vom Eligibility-Filter und der
Alias-Auflösung verwendet, um technology/location/concept-Entitäten aus dem
Persona-Pool auszuschließen und Alias-Cluster nur innerhalb derselben
semantischen Klasse zu bilden.

Klassifikations-Logik (Priorität absteigend):
  1. Kollektiv-Erkennung via ``is_collective_entity_type`` → POPULATION
  2. Typ-Keyword-Regeln: Person/Org/Tech/Location/Concept-Wörter im Type-Label
  3. Namens-Kopf-Überschreibung: wenn Klasse ORGANIZATION oder OTHER, aber der
     letzte Namensteil ein technisches Kompositum-Glied ist → TECHNOLOGY
     (geschützt durch Rechtsformendungen wie GmbH/AG/SE).

Alle Regellisten sind als Modulkonstanten pflegbar; keine verstreuten
Inline-Strings.
"""

from __future__ import annotations

import re

from ..contracts.entity_semantic_class_contract import SemanticEntityClass

# ---------------------------------------------------------------------------
# Rechtsform-Endungen — schützen echte Firmennamen vor Tech-Reklassifikation.
# Beispiel: "Datenbank-Consult GmbH" (endet auf "gmbh") bleibt ORGANIZATION.
# ---------------------------------------------------------------------------
_LEGAL_SUFFIXES: frozenset[str] = frozenset(
    {
        "gmbh",
        "ag",
        "se",
        "kg",
        "kgaa",
        "ohg",
        "eg",
        "ev",
        "gbr",
        "ug",
        "ltd",
        "inc",
        "corp",
        "llc",
        "plc",
        "mbh",
        "bv",
        "nv",
        "sa",
        "sas",
        "sarl",
        "spa",
    }
)

# ---------------------------------------------------------------------------
# Technische Namens-Köpfe — wenn der letzte Namensteil (oder ein Bindestrich-
# Glied davon) dieses Wort ist, ist die Entität ein technisches Artefakt.
# Nur Kleinbuchstaben; Vergleich nach casefold.
# Pflegbare Konstante statt verstreuter Strings.
# ---------------------------------------------------------------------------
_TECHNICAL_NAME_HEADS: frozenset[str] = frozenset(
    {
        # Deutsch
        "datenbank",
        "architektur",
        "authentifizierung",
        "autorisierung",
        "schnittstelle",
        "infrastruktur",
        "plattform",
        "anwendung",
        "software",
        "system",
        "algorithmus",
        "pipeline",
        "modell",
        "framework",
        "server",
        # "dienst" und "netzwerk" bewusst NICHT enthalten: "Kundendienst"
        # und "Kommunikationsnetzwerk" sind oft humane Organisationseinheiten.
        "modul",
        "komponente",
        "werkzeug",
        # Abkürzungen / Akronyme
        "api",
        "rag",
        "llm",
        "ki",
        "ai",
        "ml",
        "ui",
        "ux",
        "sdk",
        "cli",
        "orm",
        # Englisch
        "database",
        "architecture",
        "authentication",
        "authorization",
        "interface",
        "infrastructure",
        "platform",
        "application",
        "algorithm",
        "model",
        "cloud",
        # "service" bewusst NICHT hier: ``CustomerService`` ist eine Abteilung
        # mit menschlichem Träger (vgl. INELIGIBLE_TYPE_HEADS-Kommentar).
        "engine",
        "runtime",
        "cluster",
        "container",
        "repository",
        "vector",
        "embedding",
        # Bewusst NICHT enthalten: ``service`` ist mehrdeutig —
        # ``CustomerService`` ist eine Abteilung mit menschlichem Träger
        # (dieselbe Begründung wie in ``INELIGIBLE_TYPE_HEADS``).
    }
)

# ---------------------------------------------------------------------------
# Typ-Keyword-Regeln.  Geprüft wird das GESAMTE normalisierte Typ-Label via
# ``str.endswith`` oder ``in`` (für exakte Wörter).  Reihenfolge = Priorität
# innerhalb eines Durchlaufs.
# ---------------------------------------------------------------------------

# Typ-Wörter → PERSON (Ende des Typ-Labels)
_PERSON_TYPE_HEADS: frozenset[str] = frozenset(
    {
        "person",
        "individual",
        "employee",
        "worker",
        "staff",
        "manager",
        "director",
        "executive",
        "officer",
        "specialist",
        "expert",
        "consultant",
        "advisor",
        "analyst",
        "engineer",
        "developer",
        "professional",
        "practitioner",
        "researcher",
        "scientist",
        "administrator",
        "operator",
        "coordinator",
        "moderator",
        "facilitator",
        "coach",
        "trainer",
        "teacher",
        "principal",
        "representative",
        "agent",
        "member",
        "leader",
        # Deutsch
        "mitarbeiter",
        "angestellter",
        "angestellte",
        "beschäftigter",
        "beschäftigte",
        "fachkraft",
        "führungskraft",
        "leiter",
        "leiterin",
        "geschäftsführer",
        "geschäftsführerin",
        "vorstand",
        "sachbearbeiter",
        "sachbearbeiterin",
        "berater",
        "beraterin",
        "experte",
        "expertin",
        "spezialist",
        "spezialistin",
        "koordinator",
        "koordinatorin",
        "beauftragter",
        "beauftragte",
        "verantwortlicher",
        "verantwortliche",
    }
)

# Typ-Wörter → TECHNOLOGY (Ende des Typ-Labels)
_TECH_TYPE_HEADS: frozenset[str] = frozenset(
    {
        "technology",
        "technologie",
        "software",
        "platform",
        "plattform",
        "application",
        "anwendung",
        "tool",
        "werkzeug",
        "database",
        "datenbank",
        "system",
        "infrastructure",
        "infrastruktur",
        "architecture",
        "architektur",
        "pipeline",
        "algorithm",
        "algorithmus",
        "framework",
        "interface",
        "schnittstelle",
        "component",
        "komponente",
        "module",
        "modul",
        "dataset",
        "datensatz",
    }
)

# Typ-Wörter → LOCATION (Ende des Typ-Labels)
_LOCATION_TYPE_HEADS: frozenset[str] = frozenset(
    {
        "country",
        "nation",
        "state",
        "region",
        "city",
        "location",
        "place",
        "ort",
        # „stadt" und „land" fehlen bewusst: als Typ bezeichnen sie in
        # deutschen Ontologien oft die Verwaltung („Stadt Magdeburg",
        # „Land Sachsen-Anhalt" als Fördergeber) — einen Akteur, keinen Ort.
    }
)

# Typ-Wörter → CONCEPT (Ende des Typ-Labels)
_CONCEPT_TYPE_HEADS: frozenset[str] = frozenset(
    {
        "concept",
        "konzept",
        "topic",
        "theme",
        "thema",
        "method",
        "methode",
        "process",
        "prozess",
        "standard",
        "law",
        "regulation",
        "verordnung",
        "document",
        "dokument",
        "report",
        "bericht",
        "metric",
        "metrik",
        "event",
        "ereignis",
        "policy",
        "richtlinie",
        "criterion",
        "kriterium",
        "category",
        "kategorie",
        "requirement",
        "anforderung",
    }
)

# Typ-Wörter → ORGANIZATION (Ende des Typ-Labels).
# Bewusst eng gehalten: nur Typ-Köpfe, die NICHT in ``COLLECTIVE_HEAD_NOUNS``
# stehen — Typen, die dort erscheinen (committee, board, association, …),
# fallen durch auf den ``is_collective_entity_type``-Check → POPULATION.
# ``provider`` ist bewusst hier, weil ``AIServiceProvider`` eine Org ist;
# aber wenn der Name ein Tech-Kopf trägt, überschreibt der Namens-Check das.
_ORG_TYPE_HEADS: frozenset[str] = frozenset(
    {
        "organization",
        "organisation",
        "company",
        "corporation",
        "authority",
        "institute",
        "institution",
        "bureau",
        "center",
        "body",
        "provider",
        # Deutsch
        "unternehmen",
        "betrieb",
        "behörde",
        "behoerde",
        "träger",
        "trager",
        "trägerschaft",
        "einrichtung",
        "anbieter",
    }
)

_HYPHEN_RE = re.compile(r"[-–—]")


def _type_head(entity_type: str) -> str:
    """Letztes Wort des Entity-Typs (CamelCase und Sonderzeichen aufgelöst)."""
    # Split CamelCase, snake_case, kebab-case
    normalized = re.sub(r"[_\-]", " ", entity_type or "")
    normalized = re.sub(r"([A-Z])", r" \1", normalized)
    words = [w.casefold() for w in normalized.split() if w]
    return words[-1] if words else ""


def _name_last_compound(name: str) -> str:
    """Letztes Kompositum-Glied des Namens (Bindestrich- und Leerzeichen-Split).

    Beispiel: "zentrale Authentifizierung" → "authentifizierung"
              "RAG-Architektur" → "architektur"
              "Nexora GmbH" → "gmbh" (Rechtsform → schützt, kein Tech-Kopf)
    """
    # Split by space and hyphens, take last part
    parts = _HYPHEN_RE.split(name.strip())
    last_part = parts[-1].strip().casefold() if parts else ""
    # If last part is multi-word (space inside), take last word
    words = last_part.split()
    return words[-1] if words else ""


def _tech_name_override(name: str) -> bool:
    """Gibt True zurück, wenn der Namens-Kopf ein technisches Artefakt benennt.

    Rechtsformendungen (GmbH, AG, SE …) schützen echte Firmennamen vor
    der Tech-Reklassifikation.
    """
    last_compound = _name_last_compound(name)
    if not last_compound or last_compound in _LEGAL_SUFFIXES:
        return False
    if last_compound in _TECHNICAL_NAME_HEADS:
        return True
    # Kompositum-Check: "vektordatenbank" enthält "datenbank".
    # Mindestlänge 4 für den Suffix-Vergleich: kurze Abkürzungen wie "ai",
    # "ml", "ki" (≤3 Zeichen) würden sonst echte Firmennamen matchen
    # (z. B. "openai" endet auf "ai"). Abkürzungen werden nur als exaktes
    # letztes Kompositum-Glied erkannt (Schritt davor).
    return any(
        len(tech_head) >= 4
        and last_compound.endswith(tech_head)
        and len(last_compound) > len(tech_head)
        for tech_head in _TECHNICAL_NAME_HEADS
    )


def classify_entity(name: str, entity_type: str) -> SemanticEntityClass:
    """Klassifiziert eine Entität in eine semantische Klasse.

    Args:
        name: Anzeigename der Entität (z. B. "Dr. Miriam Vogt",
              "BFW Leipzig", "Vektordatenbank").
        entity_type: Ontologie-Typ-Label (z. B. "Person", "Organization",
                     "TechnologyProvider", "ExecutiveDirector").

    Returns:
        Eine ``SemanticEntityClass``.  Kein LLM-Aufruf, deterministisch.

    Priorität der Regeln:
      1. Explizite Typ-Kopf-Regeln (Person, Tech, Location, Concept, Org).
         Org-Typ-Köpfe werden VOR der Kollektiv-Prüfung geprüft, weil
         ``COLLECTIVE_HEAD_NOUNS`` auch "organization"/"company" enthält —
         plain „Organization" ist aber ein Organisations-Typ, kein Kollektiv.
      2. Kollektiv-Erkennung via ``is_collective_entity_type`` als Fallback
         für Composite-Typen wie „EmployeeGroup", „HospitalNetwork".
      3. Namens-Kopf-Überschreibung für Org/Other: tech. Artefakt mit
         Org-Typ → TECHNOLOGY (geschützt durch Rechtsformendungen).
      4. OTHER als konservativer Fallback.
    """
    # Lazy-import um Zirkelimporte zu vermeiden
    from .persona_domain_coherence import is_collective_entity_type

    head = _type_head(entity_type)

    # ------------------------------------------------------------------
    # Schritt 1: Explizite Typ-Kopf-Regeln (höchste Priorität).
    # Reihenfolge: Person → Tech → Location → Concept → Org.
    # Org VOR Kollektiv, weil "organization" in COLLECTIVE_HEAD_NOUNS.
    # ------------------------------------------------------------------
    if head in _PERSON_TYPE_HEADS:
        return SemanticEntityClass.PERSON

    if head in _TECH_TYPE_HEADS:
        return SemanticEntityClass.TECHNOLOGY

    if head in _LOCATION_TYPE_HEADS:
        return SemanticEntityClass.LOCATION

    if head in _CONCEPT_TYPE_HEADS:
        return SemanticEntityClass.CONCEPT

    if head in _ORG_TYPE_HEADS:
        # Namens-Kopf kann zu TECHNOLOGY überschreiben
        if _tech_name_override(name):
            return SemanticEntityClass.TECHNOLOGY
        return SemanticEntityClass.ORGANIZATION

    # ------------------------------------------------------------------
    # Schritt 2: Kollektiv-Erkennung für Composite-Typen
    # ("EmployeeGroup", "HospitalNetwork", …)
    # ------------------------------------------------------------------
    if is_collective_entity_type(entity_type):
        return SemanticEntityClass.POPULATION

    # ------------------------------------------------------------------
    # Schritt 3: Namens-Kopf-Überschreibung für unbekannte Typen
    # ------------------------------------------------------------------
    if _tech_name_override(name):
        return SemanticEntityClass.TECHNOLOGY

    # ------------------------------------------------------------------
    # Schritt 4: OTHER als konservativer Fallback
    # ------------------------------------------------------------------
    return SemanticEntityClass.OTHER


__all__ = ["SemanticEntityClass", "classify_entity"]
