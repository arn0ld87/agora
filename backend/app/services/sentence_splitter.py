"""Satzzerlegung, die Ordinalzahlen und Datumsangaben nicht zerreißt.

Der naive Trenner ``(?<=[.!?])\\s+`` hielt den Punkt hinter einer Ordinalzahl
für ein Satzende. Aus „… bevor der Kreistag den Standort zum 30. Juni 2027
aufgibt." wurden „… zum 30." und „Juni 2027 aufgibt.". Beide Fragmente
wanderten als Hypothesen, Ledger-Fakten und Data Gaps durch die Pipeline
(Issue #1766).

Die Regeln stammen aus der Fließtext-Prüfung (Issues #1356/#1360), wo sie
zuerst gebraucht wurden. Sie leben hier, weil der Claim-Atomizer, das
Entailment und die Fließtext-Prüfung dieselbe Satzgrenze brauchen — und weil
``evidence_entailment`` die Prüfung in ``report_agent.text_verification`` nicht
importieren kann, ohne einen Zyklus zu erzeugen.

Reine Funktionen, keine Abhängigkeit auf andere Service-Module.
"""

from __future__ import annotations

import re
from typing import List

#: Abkürzungen, deren Punkt kein Satzende ist. Einzelne Buchstaben ("z. B.",
#: "u. a.") deckt die Längenprüfung in :func:`_is_false_boundary` ab.
_ABBREVIATIONS = frozenset({
    "bzw", "ca", "vgl", "ggf", "evtl", "inkl", "exkl", "max", "min",
    "nr", "abs", "art", "bspw", "etc", "usw", "sog", "insb", "zzgl",
    "jan", "feb", "mrz", "apr", "jun", "jul", "aug", "sep", "okt", "nov", "dez",
})

#: Monatsnamen. Ein großgeschriebenes Wort hinter einer Zahl beendet den Satz
#: normalerweise ("umfasste 14. Danach …"); ein Monat tut das nicht ("14. Juni").
_MONTHS = frozenset({
    "januar", "februar", "märz", "maerz", "april", "mai", "juni", "juli",
    "august", "september", "oktober", "november", "dezember",
    "jan", "feb", "mrz", "apr", "jun", "jul", "aug", "sep", "sept", "okt", "nov", "dez",
})

#: Zeitraum- und Reihenfolge-Substantive, die eine Ordinalzahl regieren ("im 2. Quartal",
#: "1. bis 3. Runde"). Großgeschrieben wie jedes deutsche Substantiv, deshalb
#: reicht die Kleinschreibungs-Regel allein nicht. Bewusst kurz: jedes Wort
#: hier kann auch einen Satz eröffnen, der auf eine Kardinalzahl folgt.
_ORDINAL_NOUNS = frozenset({
    "quartal", "halbjahr", "trimester", "semester", "runde", "stufe",
    "sitzung", "jahrhundert",
})

#: Eine Ordinalzahl hat höchstens zwei Stellen ("30. Juni", "2. Quartal").
#: Eine vierstellige Zahl vor dem Punkt ist eine Jahreszahl und endet den Satz
#: ("… im Jahr 2027. Danach …").
_MAX_ORDINAL_DIGITS = 2


def _is_ordinal_boundary(text: str, dot_index: int, token_start: int) -> bool:
    """Ist die Ziffernfolge vor dem Punkt eine Ordinalzahl statt eines Satzendes?

    Eine Zahl allein entscheidet das nicht — ``Die Stichprobe umfasste 14.``
    endet einen Satz, ``am 14. Juni`` nicht. Würde jede Ziffer die Satzgrenze
    unterdrücken, verschmölzen zwei Sätze zu einer Prüfeinheit, und ein
    widerlegter Fakt im zweiten risse den ersten mit heraus (Codex-Review
    PR #1360, P2). Entschieden wird deshalb am Kontext:

    * Ziffer am Zeilenanfang — ein Aufzählungsmarker ("1. Erfolgreicher …").
    * Folgewort kleingeschrieben oder mit Ziffer beginnend — Ordinalzahl
      ("3. bis 14. Juni", "1. 2. Runde").
    * Folgewort ist ein Monatsname — Datum ("14. Juni") — oder ein
      Zeitraum-/Reihenfolge-Substantiv aus :data:`_ORDINAL_NOUNS` ("2. Quartal").

    Sonst ist der Punkt ein Satzende, auch nach einer Zahl.
    """
    if not text[:token_start].strip():
        return True
    following = re.match(r"\s*(\S+)", text[dot_index + 1:])
    if not following:
        return False
    word = following.group(1).strip(",.;:()\"'„»")
    if not word:
        return False
    if word[:1].islower() or word[:1].isdigit():
        return True
    lowered = word.lower().rstrip(".")
    return lowered in _MONTHS or lowered in _ORDINAL_NOUNS


def _is_false_boundary(text: str, dot_index: int) -> bool:
    """Steht der Punkt an ``dot_index`` für eine Abkürzung statt ein Satzende?

    Drei Fälle, alle im Referenzlauf belegt: eine Ordinalzahl ("14. Juni",
    "3. bis"), eine Listennummer ("1. Erfolgreicher …") und eine Abkürzung
    ("z. B.", "Nr. 3"). Jeder von ihnen zerlegte einen intakten Satz in zwei
    Fragmente, von denen eines die Zahlen trug und deshalb verschwand.
    """
    match = re.search(r"(\S+)$", text[:dot_index])
    if not match:
        return False
    # Öffnende Klammern und Anführungszeichen gehören nicht zum Token:
    # in "(3. bis 14. Juni" ist die Ordinalzahl sonst "(3" und damit keine
    # Ziffer mehr — genau daran zerbrach der Satz im Referenzlauf.
    token = match.group(1).lstrip("([{\"'„»‚‹")
    if not token:
        return False
    if token.isdigit():
        if len(token) > _MAX_ORDINAL_DIGITS:
            return False
        # ``token_start`` zeigt hinter die abgestreiften Klammern — nur so
        # erkennt die Zeilenanfangs-Prüfung einen echten Aufzählungsmarker.
        token_start = match.end() - len(token)
        return _is_ordinal_boundary(text, dot_index, token_start)
    # Nur *einzelne* Buchstaben sind Abkürzungspunkte ("z. B.", "u. a.").
    # Zwei Buchstaben deckt die Liste ab — "ab", "an", "zu" sind gewöhnliche
    # Wörter und dürfen ein Satzende nicht verhindern.
    if len(token) == 1 and token.isalpha():
        return True
    return token.lower() in _ABBREVIATIONS


def split_sentences(line: str) -> List[str]:
    """Zerlegt einen Text in Sätze, ohne Ordinalzahlen zu zerreißen.

    Gibt die Sätze getrimmt zurück; leere Fragmente entfallen. Ein falsch
    zusammengelassener Satz kostet höchstens Prüfschärfe, ein falsch
    getrennter dagegen zerstört den gelesenen Text — die Heuristik ist
    deshalb bewusst konservativ.
    """
    sentences: List[str] = []
    start = 0
    for match in re.finditer(r"[.!?]+\s+", line):
        if _is_false_boundary(line, match.start()):
            continue
        chunk = line[start:match.end()].strip()
        if chunk:
            sentences.append(chunk)
        start = match.end()
    tail = line[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


__all__ = ["split_sentences"]
