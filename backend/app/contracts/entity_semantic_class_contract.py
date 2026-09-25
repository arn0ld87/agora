"""Semantische Entitätsklasse für den Persona-Pipeline-Filter (Issue #1470).

Diese Klasse dient als Brücke zwischen ontologischen Entity-Typen (frei
generiert, oft englisch oder deutsch, inkonsistent) und einem stabilen,
geschlossenen Werteraum für den Eligibility-Filter und die Alias-Auflösung.

Die Klassifikation erfolgt deterministisch per Keyword-Regelwerk — kein
LLM-Aufruf, keine externe Abhängigkeit.
"""

from __future__ import annotations

from enum import Enum


class SemanticEntityClass(str, Enum):
    """Semantische Klasse einer Entität im Persona-Generierungs-Kontext.

    Werte sind bewusst Kleinbuchstaben-Strings (``str``-Subklasse), damit sie
    direkt in Logging-Ausgaben und Dicts lesbar sind.
    """

    PERSON = "person"
    """Natürliche Person oder individuelle Rolle: Executive, Employee, Manager,
    Director, Berater, Experte usw."""

    ORGANIZATION = "organization"
    """Rechtliche oder faktische Organisation: Unternehmen, Behörde, Institut,
    Träger, Verband, Anbieter (Provider) — sofern der Name kein technisches
    Konzept benennt."""

    POPULATION = "population"
    """Kollektive Personengruppe: Betriebsrat, Belegschaft, Bevölkerung, Netz-
    werk, Community.  Wird durch ``is_collective_entity_type`` erkannt."""

    TECHNOLOGY = "technology"
    """Technisches Artefakt oder Konzept: Software, System, Plattform, Daten-
    bank, Architektur, API, Cloud-Dienst, KI-Modell usw. — nicht persona-
    fähig."""

    LOCATION = "location"
    """Geografische Entität: Land, Region, Stadt, Ort. — nicht persona-fähig."""

    CONCEPT = "concept"
    """Abstraktes Konzept oder Regelwerk: Methode, Prozess, Thema, Standard,
    Gesetz, Dokument. — nicht persona-fähig."""

    OTHER = "other"
    """Nicht klassifizierbar mit den verfügbaren Regeln. Konservativ erlaubt
    (Eligibility-Filter entscheidet über den Typ)."""


__all__ = ["SemanticEntityClass"]
