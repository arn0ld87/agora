"""Eine Textprojektion für Evidence-Items (#1766).

Ein Evidence-Item trägt seinen Text an mehreren Stellen: gekürzt in
``snippet`` (300 Zeichen) und ``quote`` (500 Zeichen), vollständig in ``raw``.
Bei einem Persona-Interview steht die gesamte Antwort in ``raw["response"]``.

Drei Module lasen bisher je eine eigene, unterschiedlich unvollständige
Auswahl dieser Felder:

* die Bindung (``evidence_binder.candidate_text``) ohne ``response``,
* das Entailment (``evidence_entailment._evidence_text``) ohne ``response``,
* die Data-Gap-Prüfung (``data_gap._pool_texts``) ganz ohne ``raw``.

Im Referenzlauf war der Vergleichstext aller 57 Interviews 303 Zeichen lang;
eine Aussage bei Zeichen 657 hatte keinen Bindungskandidaten und wurde als
Lücke geführt, obwohl sie wörtlich in der Quelle stand.

Diese Funktion ist die einzige Stelle, die entscheidet, was als Text eines
Evidence-Items gilt. Reine Funktion, keine Abhängigkeit auf andere
Service-Module — Binder, Entailment und Data-Gap können sie ohne Importzyklus
verwenden.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

#: Felder auf oberster Ebene des Items, in Lesereihenfolge.
_TOP_LEVEL_KEYS = ("snippet", "quote", "value", "content", "text")

#: Felder in ``raw`` (wenn ``raw`` ein Dict ist). ``response`` ist die volle
#: Interviewantwort. ``question`` fehlt mit Absicht: die Frage an die Persona
#: ist keine Evidence, und ein Claim, der nur die Frage wiederholt, darf nicht
#: durch sie "belegt" werden.
_RAW_KEYS = ("content", "text", "snippet", "summary", "name", "response")

_ELLIPSIS_TAIL = re.compile(r"\s*(?:…|\.\.\.)\s*$")
_WHITESPACE = re.compile(r"\s+")


def _comparable(part: str) -> str:
    """Vergleichsform eines Teils: ohne Kürzungs-Ellipse, Whitespace normalisiert."""
    return _WHITESPACE.sub(" ", _ELLIPSIS_TAIL.sub("", part)).strip()


def _drop_covered_parts(parts: List[str]) -> List[str]:
    """Entfernt Teile, die ein längerer Teil bereits vollständig enthält.

    ``snippet`` und ``quote`` sind gekürzte Kopien der Antwort; sie wieder
    anzuhängen verdoppelte Text und Zahlen und ließe den Vergleichstext wie
    drei Aussagen statt einer wirken. Gleiche Teile bleiben einmal stehen
    (das erste Vorkommen).
    """
    comparable = [_comparable(part) for part in parts]
    kept: List[str] = []
    for index, part in enumerate(parts):
        mine = comparable[index]
        if not mine:
            continue
        covered = any(
            other_index != index
            and (
                (len(other) > len(mine) and mine in other)
                or (other == mine and other_index < index)
            )
            for other_index, other in enumerate(comparable)
        )
        if not covered:
            kept.append(part.strip())
    return kept


def evidence_text(item: Dict[str, Any]) -> str:
    """Der vollständige Vergleichstext eines Evidence-Items.

    Liest ``snippet``, ``quote``, ``value``, ``content`` und ``text`` des Items
    sowie ``content``, ``text``, ``snippet``, ``summary``, ``name`` und
    ``response`` aus ``raw``; ist ``raw`` ein String, gilt er als Text. Teile,
    die in einem längeren Teil enthalten sind (gekürzte Kopien), entfallen.
    """
    if not isinstance(item, dict):
        return ""
    parts: List[str] = []
    for key in _TOP_LEVEL_KEYS:
        value = item.get(key)
        if value:
            parts.append(str(value))
    raw = item.get("raw")
    if isinstance(raw, dict):
        for key in _RAW_KEYS:
            value = raw.get(key)
            if isinstance(value, str) and value:
                parts.append(value)
    elif isinstance(raw, str) and raw:
        parts.append(raw)
    return " ".join(_drop_covered_parts(parts)).strip()


__all__ = ["evidence_text"]
