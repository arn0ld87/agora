from __future__ import annotations

import re
from typing import List, Optional

from ..evidence_entailment import ENUMERATION_WORDS
from .text_verification_types import UNVERIFIED_MARKER

#: Zeilen, die keine Fließtextaussage sind und deshalb nicht geprüft werden:
#: Zitatblöcke tragen fremde Rede, Aufzählungsmarker und Fettschrift-Label
#: sind Struktur.
_QUOTE_PREFIXES = (">", "|")

#: Aufzählungs- und Nummerierungspräfix einer Listenzeile. Es wird vor der
#: Satzzerlegung abgetrennt und danach unverändert wieder vorangestellt —
#: sonst wird "1." zum eigenen Satz und überlebt seinen eigenen Inhalt.
_LIST_PREFIX = re.compile(r"^(\s*(?:[-*+]|\d+[.)])\s+)(.*)$")

#: Nummerierte Listenzeile, für den Renummerierungs-Nachlauf.
_ORDERED_ITEM = re.compile(r"^(?P<indent>\s*)(?P<number>\d+)(?P<sep>[.)])(?P<space>\s+)(?P<rest>.*)$")

#: Kanonische Schreibweise der ausgeschriebenen Aufzählung, in Zählreihenfolge.
#: Aus dieser Sequenz wird nach einer Entfernung neu gesetzt.
_ENUMERATION_SEQUENCE = (
    "Erstens",
    "Zweitens",
    "Drittens",
    "Viertens",
    "Fünftens",
    "Sechstens",
    "Siebtens",
    "Achtens",
    "Neuntens",
    "Zehntens",
)

#: Wort → Position, inklusive der Schreibvarianten aus ``ENUMERATION_WORDS``.
#: Die Sequenz oben ist die Ausgabeform, diese Tabelle die Lesart.
_ENUMERATION_ORDINALS = {
    "erstens": 0,
    "zweitens": 1,
    "drittens": 2,
    "viertens": 3,
    "fünftens": 4,
    "fuenftens": 4,
    "sechstens": 5,
    "siebtens": 6,
    "siebentens": 6,
    "achtens": 7,
    "neuntens": 8,
    "zehntens": 9,
}

#: Ein Aufzählungswort am Satzanfang — am Zeilenanfang oder hinter einem
#: Satzzeichen. Gruppe 1 ist der Vorlauf und bleibt unverändert stehen.
#:
#: Die Alternativen kommen aus :data:`_ENUMERATION_ORDINALS`, nicht aus
#: ``ENUMERATION_WORDS``: nur wofür eine Zählposition bekannt ist, darf hier
#: treffen. Sonst fände die Regex ein Wort, das der Lookup unten nicht kennt,
#: und ``_renumber_enumeration`` risse mit einem ``KeyError`` mitten in der
#: Abschnittsverarbeitung ab.
_ENUMERATION_AT_SENTENCE_START = re.compile(
    r"(^|[.!?]['\"\)\]]?\s+)("
    + "|".join(sorted(_ENUMERATION_ORDINALS, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)

#: Beide Mengen müssen deckungsgleich bleiben. ``ENUMERATION_WORDS`` steuert,
#: was ``evidence_entailment`` als Aufzählungswort aus der Bezugsgruppe
#: heraushält; ``_ENUMERATION_ORDINALS`` steuert die Zählung hier. Läuft eine
#: der beiden Listen der anderen davon, zählt der Sanitizer entweder falsch
#: oder gar nicht.
assert set(_ENUMERATION_ORDINALS) == set(ENUMERATION_WORDS), (
    "ENUMERATION_WORDS und _ENUMERATION_ORDINALS sind auseinandergelaufen: "
    f"{set(ENUMERATION_WORDS) ^ set(_ENUMERATION_ORDINALS)}"
)

#: Code-Fence. Innerhalb eines Blocks wird nichts geprüft und nichts entfernt.
_FENCE = re.compile(r"^\s*(```|~~~)")


def is_markup_or_quote_line(stripped: str) -> bool:
    """Leere Zeile, Zitatblock-Präfix oder vollständig getaggte Zeile.

    Gemeinsame Teilprüfung für ``_is_structural`` (Fließtext-Validator, hier)
    und ``is_claim_candidate`` (Claim-Extraktion in ``sections.py``,
    Issue #1316) — beide verwerfen dieselben drei Zeilenformen, bevor sie
    ihre je eigene Zusatzlogik anwenden. ``stripped`` erwartet bereits
    getrimmten Text.
    """
    if not stripped:
        return True
    if stripped.startswith(_QUOTE_PREFIXES):
        return True
    if stripped.startswith("<") and stripped.endswith(">"):
        return True
    return False


def _is_structural(line: str) -> bool:
    stripped = line.strip()
    if is_markup_or_quote_line(stripped):
        return True
    return bool(re.fullmatch(r"\*\*[^*]+\*\*:?", stripped))


#: Der Marker als eigenständiges Vorkommen, inklusive führendem Leerraum.
_MARKER_RE = re.compile(rf"\s*{re.escape(UNVERIFIED_MARKER)}")


def _strip_marker(text: str) -> str:
    """Entfernt bereits gesetzte Marker.

    Die Prüfung muss idempotent sein: ein zweiter Durchlauf über denselben
    Text darf keinen zweiten Marker anhängen. Da die Segmentierung nach dem
    Satzpunkt trennt, landet ein angehängter Marker sonst in einem eigenen
    Fragment, der Satz selbst gilt wieder als unmarkiert und bekommt einen
    weiteren.
    """
    return _MARKER_RE.sub("", text)


def _mark_unverified(sentence: str) -> str:
    """Hängt den Marker an, ohne ihn zu verdoppeln."""
    return f"{_strip_marker(sentence).rstrip()} {UNVERIFIED_MARKER}"


def _renumber_block(lines: List[str], anchor: int, indent: str) -> None:
    """Nummeriert den Listenblock um ``anchor`` herum neu ab 1.

    Läuft nur über Blöcke, aus denen tatsächlich eine Zeile entfernt wurde.
    Eine intakte Liste, die bewusst bei einer anderen Zahl beginnt, bleibt
    damit unangetastet.
    """
    def belongs(index: int) -> bool:
        if not 0 <= index < len(lines):
            return False
        match = _ORDERED_ITEM.match(lines[index])
        return bool(match) and match.group("indent") == indent

    start = anchor
    while belongs(start - 1):
        start -= 1
    end = anchor
    while belongs(end):
        end += 1

    counter = 1
    for index in range(start, end):
        match = _ORDERED_ITEM.match(lines[index])
        if not match:
            continue
        lines[index] = (
            f"{match.group('indent')}{counter}{match.group('sep')}"
            f"{match.group('space')}{match.group('rest')}"
        )
        counter += 1


def _leading_ordinal(sentence: str) -> Optional[int]:
    """Zählposition, falls der Satz mit einem Aufzählungswort beginnt."""
    match = re.match(r"\s*([A-Za-zÄÖÜäöüß]+)", sentence)
    if not match:
        return None
    return _ENUMERATION_ORDINALS.get(match.group(1).lower())


def _paragraph_bounds(lines: List[str], anchor: int) -> tuple[int, int]:
    """Grenzen des Absatzes um ``anchor``; Leerzeilen trennen.

    Eine Aufzählung endet am Absatzende. Zwei durch eine Leerzeile getrennte
    Blöcke sind zwei Aufzählungen — der zweite darf nicht umgezählt werden,
    nur weil im ersten etwas fehlte.
    """
    start = min(anchor, len(lines))
    while start > 0 and lines[start - 1].strip():
        start -= 1
    end = min(anchor, len(lines) - 1) if lines else 0
    while end + 1 < len(lines) and lines[end + 1].strip():
        end += 1
    return start, min(end + 1, len(lines))


def _renumber_enumeration(lines: List[str], anchor: int, removed_ordinal: int) -> None:
    """Zählt die ausgeschriebene Aufzählung des Absatzes lückenlos neu.

    Der Referenzlauf ``report_cc2ef45da5e9`` hinterließ "Erstens … Zweitens …
    Viertens": der dritte Punkt war als widerlegt entfernt worden, die Zählung
    blieb stehen. Für den Leser ist das ein Fehler im Bericht — er kann nicht
    wissen, dass dort etwas geprüft und verworfen wurde. Nummerierte Listen
    schützt :func:`_renumber_block` seit #1356 genauso.

    Der Startwert ist bewusst nicht fest 1: ein Absatz, der bei "Zweitens"
    einsetzt, weil der erste Punkt darüber steht, soll dort bleiben. Gezählt
    wird ab dem kleinsten Wert, der im Absatz vorkam — das entfernte Element
    eingeschlossen, sonst rutschte die Aufzählung nach oben, wenn ausgerechnet
    ihr erster Punkt wegfiel.
    """
    start, end = _paragraph_bounds(lines, anchor)
    positions: List[tuple[int, re.Match[str]]] = [
        (index, match)
        for index in range(start, end)
        for match in _ENUMERATION_AT_SENTENCE_START.finditer(lines[index])
    ]
    if not positions:
        return

    found = [
        _ENUMERATION_ORDINALS[match.group(2).lower()] for _, match in positions
    ]
    counter = min(min(found), removed_ordinal)
    if counter + len(positions) > len(_ENUMERATION_SEQUENCE):
        # Mehr Punkte, als die Sequenz Wörter kennt. Lieber die vorhandene
        # Zählung stehen lassen als sie mit einem IndexError abzubrechen.
        return

    for index in range(start, end):
        def _replace(match: re.Match[str]) -> str:
            nonlocal counter
            word = _ENUMERATION_SEQUENCE[counter]
            counter += 1
            return f"{match.group(1)}{word}"

        lines[index] = _ENUMERATION_AT_SENTENCE_START.sub(_replace, lines[index])

