"""Wiederkehrende Bio-Floskeln eines Batches sammeln und dem nächsten Prompt mitgeben.

Issue #1759, Befund A7: 19 von 30 Bios des Referenzlaufs enthielten
„verlässlich“. Das Modell wiederholt Lieblingswörter, solange es nicht weiß,
dass sie schon vergeben sind. Vorlage ist die Namensliste aus A1
(``generator._taken_display_names``): Der Generator führt pro Batch eine Zählung
(``generator._bio_word_counts``), ``register_taken_display_name`` füttert sie bei
jedem fertigen individuellen Profil, und der Persona-Prompt liest daraus die
Wörter, die schon in mindestens :data:`BIO_WORD_MIN_BIOS` Bios stehen.

Gezählt wird pro Bio höchstens einmal je Wort. Fachbegriffe der aktuellen
Entität bleiben außen vor: Steht ein Wort im Kontext der Entität, ist es
quellengebunden und keine Floskel.
"""

from __future__ import annotations

import re
from typing import Any, Dict, FrozenSet, List, Optional

#: Mindestlänge eines gezählten Wortes; kürzere sind fast immer Funktionswörter.
BIO_WORD_MIN_LENGTH = 6
#: In so vielen Bios muss ein Wort stehen, bevor es als Floskel gilt.
BIO_WORD_MIN_BIOS = 3
#: Obergrenze der Wörter im Prompt — eine lange Verbotsliste lenkt ab.
BIO_WORD_PROMPT_LIMIT = 12

#: Funktionswörter ab :data:`BIO_WORD_MIN_LENGTH` Zeichen, die keine Floskel sind.
BIO_WORD_STOPWORDS: FrozenSet[str] = frozenset({
    "dagegen", "dadurch", "dabei", "damit", "danach", "darauf", "darum",
    "deshalb", "dieser", "diesem", "diesen", "jedoch", "immer", "manchmal",
    "mehr", "nicht", "nichts", "schon", "sowie", "trotz", "ueber", "über",
    "unser", "unsere", "unseren", "wegen", "weiter", "welche", "wieder",
    "wenn", "werden", "wurde", "wurden", "einen",
    "einem", "einer", "eines", "ihren", "ihrer", "seine", "seiner", "seinen",
    "gegen", "bereits", "gerade", "sodass", "ebenso", "stets", "häufig",
    "haeufig", "oftmals", "aufgrund", "während", "waehrend", "bleibt",
})

_WORD_RE = re.compile(r"[A-Za-zÄÖÜäöüß]+")


def bio_words(text: Optional[str]) -> FrozenSet[str]:
    """Die zählbaren Wörter einer Bio (klein geschrieben, ohne Funktionswörter)."""
    return frozenset(
        word
        for word in (w.casefold() for w in _WORD_RE.findall(text or ""))
        if len(word) >= BIO_WORD_MIN_LENGTH and word not in BIO_WORD_STOPWORDS
    )


def register_bio_words(generator: Any, profile: Optional[Any]) -> None:
    """Verbucht die Wörter der Bio eines fertigen individuellen Profils.

    Ohne ``_bio_word_counts`` am Generator (kein Batch) passiert nichts —
    derselbe Vertrag wie bei ``register_taken_display_name``.
    """
    counts: Optional[Dict[str, int]] = getattr(generator, "_bio_word_counts", None)
    if profile is None or counts is None:
        return
    for word in bio_words(getattr(profile, "bio", None)):
        counts[word] = counts.get(word, 0) + 1


def overused_bio_words(generator: Any, context: str = "") -> Optional[List[str]]:
    """Wörter, die der Batch schon in mehreren Bios verbraucht hat (häufigste zuerst).

    ``None`` ohne Treffer. Wörter, die im ``context`` der aktuellen Entität
    stehen, gelten als quellengebunden und fehlen in der Liste.
    """
    counts: Optional[Dict[str, int]] = getattr(generator, "_bio_word_counts", None)
    if not counts:
        return None
    source = (context or "").casefold()
    frequent = [
        (word, count)
        for word, count in counts.items()
        if count >= BIO_WORD_MIN_BIOS and word not in source
    ]
    frequent.sort(key=lambda item: (-item[1], item[0]))
    words = [word for word, _ in frequent[:BIO_WORD_PROMPT_LIMIT]]
    return words or None


def avoid_words_prompt_block(words: Optional[List[str]], language: str) -> str:
    """Prompt-Absatz „bereits verwendet, vermeiden“; leer ohne Wörter."""
    if not words:
        return ""
    csv = ", ".join(words)
    if language == "de":
        return (
            "\n\nIn den bisherigen Bios dieses Laufs bereits verwendete Wörter — "
            f"in bio und persona vermeiden, eigene Worte finden: {csv}"
        )
    return (
        "\n\nWords already used in earlier bios of this run — avoid them in bio and "
        f"persona, find your own wording: {csv}"
    )
