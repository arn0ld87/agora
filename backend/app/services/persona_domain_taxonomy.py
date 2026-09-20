"""Fachdomänen-Taxonomie für die Persona-Domänenkohärenz (#1471).

Eigenes Modul statt Inline-Dict in ``persona_domain_coherence.py`` und statt
JSON/YAML: die Marker tragen erklärende Kommentare zu False-Positive-Fallen
(deutsche Komposita wie "Ladestation"/"Netzwerk"), und nur ein Python-Modul
kann diese Kommentare neben den Daten halten, ohne eine zweite Parser-Schicht
einzuführen. ``mypy`` prüft die Typen der Marker-Sets mit, das hätte ein
reines JSON nicht.

Bewusst klein und trennscharf: es geht nicht darum, jede Branche zu erfassen,
sondern eindeutiges Leitvokabular zu listen. Kurze Marker sind gefährlich
("werk" steckt in "Netzwerk", "bank" in "Datenbank", "amt" in vielen
Komposita) — deshalb stehen hier nur Wörter, die ihr Fach für sich genommen
eindeutig festlegen, auch als Bestandteil eines längeren Kompositums.
"""

from __future__ import annotations

from typing import Dict, FrozenSet

DOMAIN_MARKERS: Dict[str, FrozenSet[str]] = {
    "healthcare": frozenset({
        "klinik", "kliniken", "klinikum", "krankenhaus", "pflege", "pflegekraft",
        "patient", "patienten", "patientin", "ärztlich", "aerztlich", "arzt",
        "ärztin", "aerztin", "medizin", "medizinisch", "triage", "notaufnahme",
        # "station" steckt in "Ladestation", "Arbeitsstation", "Bahnstation" —
        # derselbe Fehlertyp wie "werk" in "Netzwerk". Die längeren Formen
        # sind eindeutig.
        "stationsleitung", "stationär", "stationaer", "bettenstation",
        "diagnose", "therapie", "visite", "gesundheitswesen", "hospital",
    }),
    # Kurze Marker sind hier gefährlich: "werk" steckt in "Netzwerk", "bank"
    # in "Datenbank". Ein Fehlalarm beschädigt eine korrekte Persona, deshalb
    # stehen hier nur Wörter, die ihr Fach eindeutig festlegen.
    "manufacturing": frozenset({
        "fertigung", "fertigungsplanung", "maschinenbau", "produktion",
        "produktionsleitung", "montage", "werkhalle", "fließband",
        "fliessband", "zerspanung", "anlagenbau", "instandhaltung",
        "manufacturing",
    }),
    "education": frozenset({
        "schule", "schulen", "lehrkraft", "lehrkräfte", "lehrkraefte",
        "unterricht", "schüler", "schueler", "kollegium", "lehrplan",
        "didaktik", "hochschule", "seminar", "curriculum",
    }),
    "logistics": frozenset({
        "logistik", "spedition", "lagerhalle", "kommissionierung", "fuhrpark",
        "frachtführer", "frachtfuehrer", "warehouse",
    }),
    "finance": frozenset({
        "sparkasse", "kreditinstitut", "wertpapier", "bilanzierung",
        "versicherung", "schadensregulierung",
    }),
    # "sicherheit" allein ist zu generisch (Arbeitssicherheit,
    # Patientensicherheit) — nur vollständige Komposita zählen.
    "it/security": frozenset({
        "cybersicherheit", "cyberangriff", "cyberkriminalitaet",
        "cyberkriminalität", "informationssicherheit",
        "schwachstellenmanagement", "penetrationstest", "firewall",
        "verschluesselung", "verschlüsselung", "phishing", "ransomware",
        "malware", "sicherheitsvorfall", "netzwerksicherheit", "intrusion",
    }),
    # "verwaltung" allein steckt auch in "Hausverwaltung" oder
    # "Datenverwaltung" — nur die staatsbezogenen Komposita zählen.
    "public-sector": frozenset({
        "kommunalverwaltung", "buergeramt", "bürgeramt", "ordnungsamt",
        "verwaltungsvorschrift", "verwaltungsverfahren", "verwaltungsakt",
        "amtsblatt", "landesverwaltung", "bundesbehoerde", "bundesbehörde",
        "buergerservice", "bürgerservice", "behoerdengang", "behördengang",
    }),
    "retail": frozenset({
        "einzelhandel", "filialleitung", "warenwirtschaft", "kassensystem",
        "verkaufsflaeche", "verkaufsfläche", "sortimentsplanung",
        "filialnetz", "regalbestueckung", "regalbestückung",
        "ladenoeffnungszeiten", "ladenöffnungszeiten",
        "einzelhandelsunternehmen",
    }),
    # "redaktion" ist trennscharf: "Reaktion" (Chemie/allgemein) hat kein
    # zusätzliches "d" und wird nicht getroffen.
    "media": frozenset({
        "redaktion", "redaktionsleitung", "pressemitteilung", "medienhaus",
        "rundfunkanstalt", "programmdirektion", "nachrichtenagentur",
        "chefredaktion", "sendeanstalt", "berichterstattung",
        "medienunternehmen", "pressekonferenz",
    }),
    # "recht" allein steckt auch in "Rechtschreibung" — nur die
    # vollständigen Fachkomposita zählen.
    "legal": frozenset({
        "kanzlei", "mandant", "mandantin", "rechtsanwalt", "rechtsanwältin",
        "rechtsanwaeltin", "gerichtsverfahren", "klageschrift",
        "vertragsrecht", "rechtsabteilung", "rechtsberatung",
        "prozessvertretung", "justiziar", "justiziarin",
    }),
    # "kraft" allein steckt in "Arbeitskraft", "Kraftfahrer" — nur die
    # vollständigen Energie-Komposita zählen.
    "energy": frozenset({
        "energiewende", "kraftwerk", "kraftwerksbetrieb", "stromnetz",
        "netzbetreiber", "energieversorger", "photovoltaikanlage",
        "windkraftanlage", "energieeffizienz", "netzausbau", "solarpark",
        "energieversorgung",
    }),
}

__all__ = ["DOMAIN_MARKERS"]
