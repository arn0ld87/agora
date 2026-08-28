"""Ein Claim, der drei Dinge behauptet, braucht Belege für drei Dinge.

Im Referenzlauf ``report_cc2ef45da5e9`` trugen einzelne Claims gleichzeitig
einen Seed-Fakt, eine Stakeholder-Aussage, eine Ableitung und einen Hinweis
auf eine Datenlücke. Eine Evidence-ID kann davon höchstens einen Teil tragen —
und trug ihn auch, weshalb der Claim als belegt durchging. Belegt war ein
Drittel davon.

``coverage_ratio`` misst die Deckung über den ganzen Claim und fängt den
groben Fall bereits ab. Was ihm entgeht, ist der lange Claim mit einem kurzen
unbelegten Anhängsel: dessen Wörter gehen in der Gesamtdeckung unter, während
die Behauptung selbst unbelegt bleibt.

Dieses Modul zerlegt deshalb in Teilaussagen und verlangt, dass *jede* von
ihnen wenigstens thematisch in der Quelle vorkommt. Bewusst nur diese
schwächere Bedingung: ein voller Deckungsnachweis je Teilsatz würde an
Paraphrasen scheitern und die belegten Aussagen mitnehmen, um die es hier
gerade nicht geht.
"""

from __future__ import annotations

import re
from typing import List, Optional

#: Konjunktionen, an denen ein Satz in eigenständige Behauptungen zerfällt.
#: "sowie", "und zugleich", "während" verbinden Aussagen, die je für sich wahr
#: oder falsch sind. "oder" fehlt bewusst — eine Alternative ist eine Aussage.
_SPLIT_PATTERN = re.compile(
    r"(?:;|(?<=\s)(?:sowie|und\s+zugleich|und\s+gleichzeitig|während|wohingegen)\s+)",
    re.IGNORECASE,
)

_SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")

#: Bindestrich-/Sternchen-/Nummern-Aufzaehlung (#1346). Eine Zeile wie
#: "- S-17 behoben" oder "1. S-17 behoben".
_LIST_ITEM_PATTERN = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.+)$")

#: Ab wie vielen Inhaltswörtern ein Teil als eigenständige Behauptung zählt.
#: Darunter ist er ein Fragment ("und dann", "aber auch") und trägt nichts,
#: was sich belegen ließe.
MIN_ATOM_TOKENS = 3

_TOKEN_PATTERN = re.compile(r"[^\wäöüßÄÖÜ]+")


def _content_tokens(text: str) -> List[str]:
    return [
        token for token in _TOKEN_PATTERN.split((text or "").lower()) if len(token) > 3
    ]


def _split_list_block(text: str) -> Optional[List[str]]:
    """Doppelpunkt-Einleitung + Bullet-Aufzaehlung → eine Teilaussage je Zeile.

    Nur ausgeloest, wenn die Zeile(n) vor der Aufzaehlung mit ``:`` enden —
    das ist das konservative Signal, dass die folgenden Zeilen tatsaechlich
    Teilaussagen derselben Einleitung sind ("Rollout nur wenn: ..."), nicht
    ein Fliesstext-Absatz, der zufaellig mit einem Gedankenstrich weitergeht.
    Jede Teilaussage traegt die Einleitung weiter — ein blosses "S-17
    behoben" ist ohne den Bezug weder ein vollstaendiger Claim noch lang
    genug fuer :data:`MIN_ATOM_TOKENS`.

    Kein Treffer (keine Bullet-Zeile, oder Einleitung ohne ``:``) → ``None``,
    der Aufrufer faellt auf die gewoehnliche Satz-/Konjunktionszerlegung
    zurueck.
    """
    lines = text.splitlines()
    item_indices = [i for i, line in enumerate(lines) if _LIST_ITEM_PATTERN.match(line)]
    if not item_indices:
        return None

    intro = " ".join(line.strip() for line in lines[: item_indices[0]] if line.strip())
    if not intro.rstrip().endswith(":"):
        return None
    intro = intro.rstrip(":").strip()

    items: List[str] = []
    for index in item_indices:
        match = _LIST_ITEM_PATTERN.match(lines[index])
        item_text = match.group(1).strip() if match else ""
        if not item_text:
            continue
        items.append(f"{intro} {item_text}".strip() if intro else item_text)

    return items or None


def _split_prose(text: str) -> List[str]:
    parts: List[str] = []
    for sentence in _SENTENCE_PATTERN.split(text):
        for piece in _SPLIT_PATTERN.split(sentence):
            cleaned = piece.strip(" ,;:-–—")
            if cleaned and len(_content_tokens(cleaned)) >= MIN_ATOM_TOKENS:
                parts.append(cleaned)
    return parts


def split_compound_claim(statement: str) -> List[str]:
    """Zerlegt eine zusammengesetzte Behauptung in ihre Teilaussagen.

    Zerlegt wird an Bullet-Aufzaehlungen mit Doppelpunkt-Einleitung
    (:func:`_split_list_block`, #1346), sonst an Satzgrenzen und an
    Konjunktionen, die eigenständige Aussagen verbinden. Fragmente
    unterhalb :data:`MIN_ATOM_TOKENS` fallen weg — sie tragen nichts
    Belegbares und würden jede Prüfung an einem "und dann" scheitern lassen.

    Ein Claim, der sich nicht zerlegen lässt, kommt als einelementige Liste
    zurück; die Aufrufer brauchen keinen Sonderfall.
    """
    text = (statement or "").strip()
    if not text:
        return []

    list_items = _split_list_block(text)
    if list_items is not None:
        parts: List[str] = []
        for item in list_items:
            parts.extend(_split_prose(item))
        return parts or [text]

    return _split_prose(text) or [text]


def is_compound(statement: str) -> bool:
    """Behauptet dieser Claim mehr als eine Sache?"""
    return len(split_compound_claim(statement)) > 1


def split_claim_chunks(chunks: List[str]) -> List[str]:
    """``split_compound_claim`` auf jeden Chunk angewandt, Ergebnis geflacht.

    Eigene Funktion statt einer Inline-Comprehension am Aufrufer (#1346):
    ``_build_claims_for_section`` liegt bereits am Komplexitäts-Deckel
    (radon-allowlist.txt), eine verschachtelte Comprehension dort hätte ihn
    gerissen.
    """
    return [atom for chunk in chunks for atom in split_compound_claim(chunk)]


__all__ = ["MIN_ATOM_TOKENS", "is_compound", "split_claim_chunks", "split_compound_claim"]
