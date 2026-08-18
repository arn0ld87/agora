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
from typing import List

#: Konjunktionen, an denen ein Satz in eigenständige Behauptungen zerfällt.
#: "sowie", "und zugleich", "während" verbinden Aussagen, die je für sich wahr
#: oder falsch sind. "oder" fehlt bewusst — eine Alternative ist eine Aussage.
_SPLIT_PATTERN = re.compile(
    r"(?:;|(?<=\s)(?:sowie|und\s+zugleich|und\s+gleichzeitig|während|wohingegen)\s+)",
    re.IGNORECASE,
)

_SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")

#: Ab wie vielen Inhaltswörtern ein Teil als eigenständige Behauptung zählt.
#: Darunter ist er ein Fragment ("und dann", "aber auch") und trägt nichts,
#: was sich belegen ließe.
MIN_ATOM_TOKENS = 3

_TOKEN_PATTERN = re.compile(r"[^\wäöüßÄÖÜ]+")


def _content_tokens(text: str) -> List[str]:
    return [
        token for token in _TOKEN_PATTERN.split((text or "").lower()) if len(token) > 3
    ]


def split_compound_claim(statement: str) -> List[str]:
    """Zerlegt eine zusammengesetzte Behauptung in ihre Teilaussagen.

    Zerlegt wird an Satzgrenzen und an Konjunktionen, die eigenständige
    Aussagen verbinden. Fragmente unterhalb :data:`MIN_ATOM_TOKENS` fallen
    weg — sie tragen nichts Belegbares und würden jede Prüfung an einem
    "und dann" scheitern lassen.

    Ein Claim, der sich nicht zerlegen lässt, kommt als einelementige Liste
    zurück; die Aufrufer brauchen keinen Sonderfall.
    """
    text = (statement or "").strip()
    if not text:
        return []

    parts: List[str] = []
    for sentence in _SENTENCE_PATTERN.split(text):
        for piece in _SPLIT_PATTERN.split(sentence):
            cleaned = piece.strip(" ,;:-–—")
            if cleaned and len(_content_tokens(cleaned)) >= MIN_ATOM_TOKENS:
                parts.append(cleaned)

    return parts or [text]


def is_compound(statement: str) -> bool:
    """Behauptet dieser Claim mehr als eine Sache?"""
    return len(split_compound_claim(statement)) > 1


__all__ = ["MIN_ATOM_TOKENS", "is_compound", "split_compound_claim"]
