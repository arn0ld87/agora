"""Faktenprüfung des sichtbaren Fließtexts.

Bis hierher war die Pipeline asymmetrisch: Claims wurden gegen Evidence
geprüft, der sichtbare Prosatext nicht. Der E2E-Lauf gegen
``sim_7058c126da03`` machte die Folge sichtbar — die Aussage

    "61 Prozent der Lehrkräfte bewerteten die zusätzliche Lernhilfe positiv
     und berichteten von einer Zeitersparnis …"

wurde vom Entailment korrekt verworfen, erzeugte null Claims und landete bei
den Hypothesen. Im gelesenen Report stand sie trotzdem, weil der Abschnitt
die rohe LLM-Prosa ist und die Claim-Extraktion nur ein nachgelagertes
Nebenprodukt.

Diese Stufe schließt die Lücke an derselben Engine, die auch die Claims
prüft: Jeder Satz, der einen quantitativen Fakt behauptet, muss von der
Evidence gedeckt sein. Was nicht gedeckt ist, verschwindet nicht still,
sondern wandert als Hypothese in den dafür vorgesehenen Slot.

Bewusst eng: Nur Sätze mit numerischen Fakten werden geprüft. Analytische
Prosa ohne Zahlenbehauptung bleibt unangetastet — sie ist Einordnung, nicht
Faktenbehauptung, und wird über das Confidence-Gating der Claims geführt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from ..evidence_entailment import (
    EntailmentJudge,
    EntailmentVerdict,
    classify_evidence,
    extract_numeric_facts,
)


@dataclass
class RejectedStatement:
    """Eine aus dem Fließtext entfernte, unbelegte Faktenbehauptung."""

    text: str
    verdict: EntailmentVerdict
    reason: str
    block_index: int = 0

    def as_hypothesis(self, index: int) -> Dict[str, Any]:
        return {
            "hypothesis_id": f"hypothesis_text_{index:02d}",
            "hypothesis_text": self.text[:1000],
            "rationale": (
                f"Aus dem Fließtext entfernt: {self.reason} "
                f"(Urteil: {self.verdict.value})."
            ),
            "suggested_evidence": [
                "Quelle mit übereinstimmender Zahl, Bezugsgruppe und Aussage nachreichen."
            ],
        }


@dataclass
class VerifiedProse:
    content: str
    rejected: List[RejectedStatement] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.rejected)


#: Satzgrenzen. Abkürzungen mit Punkt sind im Berichtsdeutsch selten genug,
#: dass eine einfache Segmentierung trägt; ein falsch getrennter Satz führt
#: höchstens dazu, dass ein Fragment ungeprüft bleibt, nie zu einem Fehlurteil.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

#: Zeilen, die keine Fließtextaussage sind und deshalb nicht geprüft werden:
#: Zitatblöcke tragen fremde Rede, Aufzählungsmarker und Fettschrift-Label
#: sind Struktur.
_QUOTE_PREFIXES = (">", "|")


def _is_structural(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith(_QUOTE_PREFIXES):
        return True
    if stripped.startswith("<") and stripped.endswith(">"):
        return True
    return bool(re.fullmatch(r"\*\*[^*]+\*\*:?", stripped))


def _has_factual_claim(sentence: str) -> bool:
    """Nur Sätze mit einer Zahl samt Bezugsgruppe sind prüfbare Faktenaussagen."""
    return bool(extract_numeric_facts(sentence))


def verify_prose(
    content: str,
    evidence_pool: Sequence[Dict[str, Any]],
    *,
    judge: Optional[EntailmentJudge] = None,
) -> VerifiedProse:
    """Entfernt quantitative Aussagen, die keine Quelle deckt.

    Ein Satz bleibt, wenn mindestens ein Evidence-Item ihn mit ``SUPPORTED``
    trägt. Findet sich kein Beleg, wird er entfernt und als
    :class:`RejectedStatement` zurückgegeben — der Aufrufer routet ihn in die
    Hypothesen.

    Ohne Evidence-Pool bleibt der Text unverändert: eine Prüfung ohne
    Vergleichsbasis darf nicht als bestandene Prüfung gelten und erst recht
    nicht den halben Bericht löschen.
    """
    if not content or not evidence_pool:
        return VerifiedProse(content=content or "")

    rejected: List[RejectedStatement] = []
    out_lines: List[str] = []

    for line in content.splitlines():
        if _is_structural(line):
            out_lines.append(line)
            continue

        sentences = _SENTENCE_SPLIT.split(line)
        kept: List[str] = []
        for sentence in sentences:
            if not sentence.strip() or not _has_factual_claim(sentence):
                kept.append(sentence)
                continue

            best: Optional[Any] = None
            for item in evidence_pool:
                result = classify_evidence(sentence, item, judge=judge)
                if result.verdict is EntailmentVerdict.SUPPORTED:
                    best = result
                    break
                if best is None or (
                    best.verdict is EntailmentVerdict.INSUFFICIENT
                    and result.verdict is EntailmentVerdict.CONTRADICTED
                ):
                    best = result

            if best is not None and best.verdict is EntailmentVerdict.SUPPORTED:
                kept.append(sentence)
                continue

            rejected.append(
                RejectedStatement(
                    text=sentence.strip(),
                    verdict=best.verdict if best else EntailmentVerdict.INSUFFICIENT,
                    reason=best.reason if best else "keine Evidence geprüft",
                    block_index=len(out_lines),
                )
            )

        rebuilt = " ".join(part for part in kept if part.strip())
        # Eine Zeile, deren Aussagen alle entfernt wurden, verschwindet ganz —
        # ein leerer Aufzählungspunkt wäre schlechter als keiner.
        if rebuilt.strip():
            out_lines.append(rebuilt)
        elif not sentences or not any(s.strip() for s in sentences):
            out_lines.append(line)

    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(out_lines)).strip()
    return VerifiedProse(content=cleaned, rejected=rejected)


__all__ = ["RejectedStatement", "VerifiedProse", "verify_prose"]
