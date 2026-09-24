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

**Nachtrag #1471 — Hauptdomäne statt jedem Overlap.** Die ursprüngliche
Fassung von ``detect_domain_drift`` galt schon als entwarnt, sobald Persona-
und Quelldomänen sich in *irgendeinem* Punkt schnitten. Eine Persona mit
Hauptfach Gesundheitswesen und einer beiläufigen Nebendomäne Bildung galt
damit gegenüber einer reinen Bildungsquelle als unauffällig — obwohl ihr
eigentliches Fach fehlte. Jetzt zählt nur noch die Hauptdomäne der Persona
(das Fach mit den meisten *exakten* Markertreffern): deckt sie sich mit einer
Quelldomäne, ist ein Überschneiden in Nebendomänen weiterhin eine legitime
Schnittstellenrolle. Deckt sie sich nicht — auch bei Gleichstand ohne
eindeutigen Sieger —, ist es Drift.
"""

from __future__ import annotations

import re
from typing import Dict, FrozenSet, List, NamedTuple, Sequence

from .persona_domain_taxonomy import DOMAIN_MARKERS

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


def has_domain_markers(text: str) -> bool:
    """Trägt ``text`` erkennbares Fachvokabular einer Domäne (#1471, Nachtrag)?

    Trennt "quellengebundene" Akteure — die Quelle legt ihr Fach bereits fest
    — von "bewusst synthetischen", deren Domäne erst erfunden werden muss.
    Die Branchenquote (``build_industry_quota_prompt_block``) darf Letztere
    lenken, ohne einer Person oder Organisation mit erkennbarem Quellfach
    (etwa der BFW-Sicherheitsverantwortlichen aus der Spezifikation) ein
    fremdes Fach aufzudrängen.
    """
    return bool(_domains_in(text))


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


def _main_domains(text: str) -> FrozenSet[str]:
    """Die Domäne(n) mit den meisten *exakten* Markertreffern im Text.

    Gezählt werden nur exakte Token-Treffer, keine Kompositum-Treffer: ein
    Kompositum-Treffer ("Medizintechnik" für "medizin") ist ein schwächeres
    Signal als ein eigenständiges Fachwort und soll die Hauptdomäne nicht
    tragen. Ein Gleichstand liefert eine leere Menge zurück — bei #1471 hat
    sich gezeigt, dass "jeder Treffer schützt" zu nachsichtig war, also
    schützt bei Gleichstand *keine* der beiden Domänen mehr; das ist die
    bewusste Entscheidung an dieser Stelle.
    """
    tokens = [
        token for token in _TOKEN_RE.split((text or "").lower()) if len(token) > 3
    ]
    counts: Dict[str, int] = {}
    for token in tokens:
        for domain, markers in DOMAIN_MARKERS.items():
            if token in markers:
                counts[domain] = counts.get(domain, 0) + 1
    if not counts:
        return frozenset()
    top = max(counts.values())
    winners = frozenset(domain for domain, hits in counts.items() if hits == top)
    return winners if len(winners) == 1 else frozenset()


class DomainDriftResult(NamedTuple):
    """Ergebnis eines Domänenvergleichs.

    ``unverifiable`` heißt: die Quelle trägt kein erkennbares Fachvokabular,
    über sie lässt sich nichts sagen. Das ist ausdrücklich nicht dasselbe wie
    ein geprüftes, sauberes Ergebnis (``drifted == []`` bei
    ``unverifiable == False``) — nur Letzteres ist eine Entwarnung. Ein
    Aufrufer, der beide Fälle gleich behandelt, würde Ungeprüftes als geprüft
    ausgeben.
    """

    drifted: List[str]
    unverifiable: bool


def detect_domain_drift(persona_text: str, source_text: str) -> DomainDriftResult:
    """Trägt die Persona ein Fach, das in ihrer Quelle nicht vorkommt?

    Entscheidend ist die Hauptdomäne der Persona (das Fach mit den meisten
    exakten Markertreffern), nicht jede Überschneidung: deckt sie sich mit
    einer Quelldomäne, ist eine zusätzliche Nebendomäne eine legitime
    Schnittstellenrolle. Deckt sie sich nicht — auch bei Gleichstand ohne
    eindeutigen Sieger — ist es Drift, selbst wenn eine Nebendomäne der
    Persona zufällig zur Quelle passt (#1471).

    Eine Quelle ohne erkennbares Fach kann nichts belegen; das ist
    ``unverifiable``, keine Entwarnung. Eine Persona ohne Fachvokabular hat
    nichts, worüber sie abdriften könnte.
    """
    source_domains = _domains_in(source_text)
    if not source_domains:
        return DomainDriftResult(drifted=[], unverifiable=True)

    persona_domains = _domains_in(persona_text)
    if not persona_domains:
        return DomainDriftResult(drifted=[], unverifiable=False)

    persona_main = _main_domains(persona_text)
    if persona_main and persona_main & source_domains:
        return DomainDriftResult(drifted=[], unverifiable=False)

    foreign = sorted(persona_domains - source_domains)
    return DomainDriftResult(drifted=foreign, unverifiable=False)


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
    drift = detect_domain_drift(drift_source, source_text)
    # ``unverifiable`` wird hier bewusst nicht ausgewertet: eine Quelle ohne
    # erkennbares Fach liefert kein Kohärenzsignal, aber auch keinen Grund,
    # den Beruf zu bereinigen — das ist keine Entwarnung, sondern schlicht
    # nichts zu melden.
    if drift.drifted:
        findings.append({
            "kind": "domain_drift",
            "detail": (
                f"'{entity_name}' trägt Fachvokabular aus "
                f"{', '.join(drift.drifted)}, während die Quelle eine andere "
                "Domäne beschreibt."
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
        if profession and detect_domain_drift(profession, source_text).drifted
    ]


__all__ = [
    "COLLECTIVE_HEAD_NOUNS",
    "DOMAIN_MARKERS",
    "DomainDriftResult",
    "coherence_findings",
    "detect_domain_drift",
    "drifted_professions",
    "has_domain_markers",
    "is_collective_entity_type",
]
