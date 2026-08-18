"""Die Haltung einer Interviewantwort, von der Persona selbst genannt (#1363).

Eine Mengenaussage über Stakeholder — „die Mehrheit lehnt den ungestaffelten
Vollstart ab" — ist von keinem einzelnen Zitat belegbar. Jedes trägt eine
Stimme; die Menge steht nirgends. Auszählen lässt sich nur, was eine Richtung
hat, und genau die fehlte: ``sentiment_score`` existiert im Vertrag, wird von
``confidence_calculator._extract_sentiment_scores`` gelesen — und war im
7-Sektionen-Referenzlauf bei **0 von 99 Items** gesetzt. Damit lief auch die
Widerspruchs-Penalty dort (``std > 0.6 → -0.2``) seit ihrer Einführung leer.

Die Persona nennt ihre Haltung jetzt selbst, als letzte Zeile ihrer Antwort.
Gegen die beiden Alternativen: eine Markerliste wäre genau das lexikalische
Raten, das #1357 im Entailment abgeschafft hat, und ein eigener Judge-Call je
Interview kostet im Referenzlauf 32 zusätzliche Calls. Dass die Persona sich
selbst einschätzt, ist hier kein Mangel — gefragt ist ihre Haltung, nicht ein
Urteil über sie.

**Fehlt die Zeile, bleibt der Wert ``None``.** Nicht ``0.0``: eine Antwort
ohne erkennbare Richtung ist keine Enthaltung, und sie als eine zu zählen
würde die Grundgesamtheit mit Stimmen füllen, die niemand abgegeben hat.
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple

#: Die Zeile, um die der Interview-Prompt bittet. Bewusst am Antwortende und
#: in einer Form, die im Fließtext nicht zufällig entsteht.
STANCE_LINE_RE = re.compile(
    r"^[ \t>*_-]*STANCE\s*[:=]\s*(?P<value>[+-]?\d+(?:[.,]\d+)?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

#: Der Prompt-Zusatz. Englisch wie der übrige Interview-Prompt.
STANCE_PROMPT_REQUIREMENT = (
    "7. After your last answer, add one final line in exactly this form:\n"
    "   STANCE: <number>\n"
    "   where the number is between -1.0 and 1.0 and expresses your overall "
    "position on the subject of these questions: -1.0 clearly opposed, 0.0 "
    "undecided or torn, 1.0 clearly in favour. Give the number that matches "
    "what you actually said. Write this line only once, at the very end.\n"
)


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def extract_stance(response: str) -> Tuple[Optional[float], str]:
    """Trennt die Haltungszeile von der Antwort.

    Liefert ``(wert, antwort_ohne_zeile)``. Ohne verwertbare Zeile ist der
    Wert ``None`` und die Antwort unverändert.

    Nennt eine Antwort die Zeile mehrfach — Modelle wiederholen Anweisungen
    gern —, zählt die **letzte**: sie steht dort, wo der Prompt sie verlangt
    hat, während frühere Vorkommen meist Echos der Anweisung sind.
    """
    if not response:
        return None, response or ""

    matches = list(STANCE_LINE_RE.finditer(response))
    if not matches:
        return None, response

    value: Optional[float] = None
    for match in reversed(matches):
        try:
            value = _clamp(float(match.group("value").replace(",", ".")))
        except ValueError:
            continue
        break

    cleaned = STANCE_LINE_RE.sub("", response).strip()
    return value, cleaned


def split_platform_answers(
    platform_answers: Sequence[Tuple[str, str]],
) -> Tuple[List[Tuple[str, str]], Optional[float]]:
    """Trennt die Haltungszeilen von den Plattformantworten.

    Liefert die bereinigten Antworten (leere fallen weg) und die Haltung der
    Persona. Mehrere Plattformen liefern mehrere Werte; gemittelt wird, weil
    es dieselbe Person zur selben Frage ist. Auf dem Direktpfad — dem
    Normalfall fuer abgeschlossene Simulationen — gibt es ohnehin nur einen.

    Ohne eine einzige Zeile bleibt der Wert ``None``, nicht ``0.0``.
    """
    stances: List[float] = []
    cleaned: List[Tuple[str, str]] = []
    for label, text in platform_answers:
        stance, without_line = extract_stance(text)
        if stance is not None:
            stances.append(stance)
        if without_line.strip():
            cleaned.append((label, without_line))
    return cleaned, (sum(stances) / len(stances) if stances else None)


__all__ = [
    "STANCE_LINE_RE",
    "STANCE_PROMPT_REQUIREMENT",
    "extract_stance",
    "split_platform_answers",
]
