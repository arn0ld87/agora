"""Wer eine Gruppe ist, wird keine Person — und wer aus der Klinik kommt, keine Werkhalle.

Der Referenzlauf ``report_cc2ef45da5e9`` erzeugte aus einem
``HospitalNetwork`` eine einzelne erfundene Person, aus einer
``EmployeeGroup`` eine "Sachbearbeiterin in der Fertigungsplanung" und aus
einem ``PatientAdvisoryCouncil`` einen "Schichtleiter Maschinenbau". Die
zugrunde liegende Quelle beschrieb einen Klinik-Rollout.

Zwei getrennte Fehler, die sich im Ergebnis addieren:

**Kollektiv als Einzelperson.** Die Erkennung lief gegen eine feste Liste von
neun Entitätstypen. Jeder Typ, den eine Ontologie darüber hinaus hervorbringt —
und ``HospitalNetwork``, ``EmployeeGroup``, ``PatientAdvisoryCouncil`` sind
genau solche — fiel durch und wurde zur Person mit Alter, Geschlecht und
erfundener Biografie. Statt die Liste immer weiter zu verlängern, prüft
:func:`is_collective_entity_type` das Grundwort: ein Typ, der auf *Network*,
*Group*, *Council*, *Committee* endet, benennt eine Mehrzahl. Das gilt für
jeden künftigen Typ mit, ohne dass ihn jemand nachträgt.

**Domänendrift.** Eine erfundene Biografie ist plausibel, solange man ihr Fach
nicht mit der Quelle vergleicht. ``detect_domain_drift`` tut genau das: es
meldet, wenn eine Persona Fachvokabular einer Domäne trägt, die in der Quelle
nicht vorkommt, während die Domäne der Quelle in ihr fehlt.

Beide Prüfungen melden und bereinigen konservativ; sie verwerfen keine
Persona. Ein Fehlalarm darf einen Lauf nicht kosten — und die Befunde selbst
sind das eigentliche Produkt, weil sie im Degradation-Protokoll landen.
"""

from __future__ import annotations

import re
from typing import Dict, FrozenSet, List, Sequence

#: Grundwörter, die eine Mehrzahl benennen. Geprüft wird das Wortende eines
#: Entitätstyps: ``HospitalNetwork`` → *network*, ``PatientAdvisoryCouncil`` →
#: *council*. Deutsche Formen stehen daneben, weil Ontologien aus deutschen
#: Quellen sie hervorbringen.
COLLECTIVE_HEAD_NOUNS: FrozenSet[str] = frozenset({
    "network", "netzwerk", "verbund",
    "group", "gruppe",
    "council", "rat", "beirat",
    "committee", "komitee", "ausschuss",
    "association", "verband", "verein",
    "board", "gremium",
    "department", "abteilung", "referat",
    "team",
    "union", "gewerkschaft",
    "alliance", "allianz", "buendnis", "bündnis",
    "federation", "foederation", "föderation",
    "panel", "forum", "assembly", "versammlung",
    "consortium", "konsortium",
    "agency", "agentur", "behoerde", "behörde",
    "authority",
    "society", "gesellschaft",
    "organization", "organisation",
    "institution", "einrichtung",
    "community", "gemeinschaft",
    "company", "unternehmen",
    "university", "universitaet", "universität", "hochschule",
    "school", "schule",
    "ministry", "ministerium",
    "office", "amt",
    "commission", "kommission",
    "chamber", "kammer",
    "cooperative", "genossenschaft",
    "workforce", "belegschaft",
})

#: Fachdomänen mit ihrem Leitvokabular. Bewusst klein und trennscharf: es geht
#: nicht darum, jede Branche zu erfassen, sondern die Verwechslungen zu fangen,
#: die im Referenzlauf tatsächlich auftraten — eine Klinik, aus der ein
#: Maschinenbaubetrieb wurde.
DOMAIN_MARKERS: Dict[str, FrozenSet[str]] = {
    "healthcare": frozenset({
        "klinik", "kliniken", "klinikum", "krankenhaus", "pflege", "pflegekraft",
        "patient", "patienten", "patientin", "ärztlich", "aerztlich", "arzt",
        "ärztin", "aerztin", "medizin", "medizinisch", "triage", "notaufnahme",
        "station", "stationär", "stationaer", "diagnose", "therapie", "visite",
        "gesundheitswesen", "hospital",
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
}

_TOKEN_RE = re.compile(r"[^\wäöüßÄÖÜ]+")
#: Trennt ``HospitalNetwork`` in *hospital* und *network*, ohne dass der Typ
#: eine bestimmte Schreibweise einhalten muss.
_CAMEL_RE = re.compile(r"[A-ZÄÖÜ][^A-ZÄÖÜ]*|[^A-ZÄÖÜ]+")


#: Trenner innerhalb eines Entitätstyps. Anders als :data:`_TOKEN_RE` zählt
#: hier der Unterstrich mit — ``patient_advisory_council`` ist derselbe Typ wie
#: ``PatientAdvisoryCouncil``, und ``\w`` würde ihn zusammenlassen.
_TYPE_SEPARATOR_RE = re.compile(r"[^A-Za-zÄÖÜäöüß]+")


def _type_words(entity_type: str) -> List[str]:
    parts: List[str] = []
    for chunk in _TYPE_SEPARATOR_RE.split(entity_type or ""):
        if not chunk:
            continue
        parts.extend(
            piece.strip().lower() for piece in _CAMEL_RE.findall(chunk) if piece.strip()
        )
    return [part for part in parts if part]


def is_collective_entity_type(entity_type: str) -> bool:
    """Benennt dieser Entitätstyp eine Mehrzahl?

    Entschieden wird am Grundwort, nicht an einer Namensliste: ``EmployeeGroup``
    ist eine Gruppe, weil sie auf *Group* endet, und ``HospitalNetwork`` ein
    Verbund, weil sie auf *Network* endet. Ein neuer Typ aus einer
    projektspezifischen Ontologie ist damit von vornherein abgedeckt — die
    feste Liste ließ genau solche Typen zu erfundenen Einzelpersonen werden.
    """
    words = _type_words(entity_type)
    if not words:
        return False
    # Nur das Grundwort zählt, nicht irgendein Bestandteil. "StaffMember" ist
    # ein Mensch, obwohl "Staff" darin vorkommt; entscheidend ist, worauf der
    # Typ endet. Ein Plural wird dabei mitgelesen ("EmployeeGroups").
    head = words[-1]
    return head in COLLECTIVE_HEAD_NOUNS or head.rstrip("s") in COLLECTIVE_HEAD_NOUNS


def _domains_in(text: str) -> FrozenSet[str]:
    tokens = {
        token for token in _TOKEN_RE.split((text or "").lower()) if len(token) > 3
    }
    found = set()
    for domain, markers in DOMAIN_MARKERS.items():
        # Direkter Treffer oder Kompositum: "Pflegepersonal" enthält "pflege",
        # "Fertigungsplanung" enthält "fertigung". Deutsche Quellen bilden sie
        # ständig, und ein reiner Token-Vergleich ginge daran vorbei.
        if tokens & markers or any(
            marker in token for token in tokens for marker in markers
        ):
            found.add(domain)
    return frozenset(found)


def detect_domain_drift(persona_text: str, source_text: str) -> List[str]:
    """Trägt die Persona ein Fach, das in ihrer Quelle nicht vorkommt?

    Gemeldet wird nur der eindeutige Fall: die Quelle weist eine Fachdomäne
    aus, die Persona eine andere — und die der Quelle fehlt bei ihr ganz. Eine
    Persona, die beide Domänen berührt, ist kein Drift, sondern eine
    Schnittstelle; und eine Quelle ohne erkennbares Fach kann nichts belegen
    und darf nichts beanstanden.

    Zurückgegeben werden die abgedrifteten Domänen, sortiert. Leer heißt sauber.
    """
    source_domains = _domains_in(source_text)
    if not source_domains:
        return []
    persona_domains = _domains_in(persona_text)
    if not persona_domains or persona_domains & source_domains:
        return []
    return sorted(persona_domains)


def coherence_findings(
    *,
    entity_type: str,
    entity_name: str,
    persona_kind: str,
    profession: str = "",
    persona_text: str = "",
    source_text: str = "",
) -> List[Dict[str, str]]:
    """Alle Kohärenzbefunde zu einer Persona vor ihrer Persistenz.

    Reine Feststellung, keine Änderung. Der Aufrufer entscheidet, was er damit
    tut — im Regelfall: die erfundenen Felder leeren und den Befund
    protokollieren.
    """
    findings: List[Dict[str, str]] = []

    if persona_kind != "collective" and is_collective_entity_type(entity_type):
        findings.append({
            "kind": "collective_materialised_as_individual",
            "detail": (
                f"'{entity_name}' ist vom Typ '{entity_type}' und benennt damit "
                "eine Mehrzahl, wurde aber als Einzelperson angelegt."
            ),
        })

    drift_source = " ".join(part for part in (profession, persona_text) if part)
    drifted = detect_domain_drift(drift_source, source_text)
    if drifted:
        findings.append({
            "kind": "domain_drift",
            "detail": (
                f"'{entity_name}' trägt Fachvokabular aus {', '.join(drifted)}, "
                "während die Quelle eine andere Domäne beschreibt."
            ),
        })

    return findings


def drifted_professions(
    professions: Sequence[str], source_text: str
) -> List[str]:
    """Welche Berufsangaben fachfremd sind — für die konservative Bereinigung."""
    return [
        profession
        for profession in professions
        if profession and detect_domain_drift(profession, source_text)
    ]


__all__ = [
    "COLLECTIVE_HEAD_NOUNS",
    "DOMAIN_MARKERS",
    "coherence_findings",
    "detect_domain_drift",
    "drifted_professions",
    "is_collective_entity_type",
]
