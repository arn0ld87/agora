from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ..evidence_entailment import (
    EntailmentResult,
    EntailmentVerdict,
    NumericFact,
)

#: Sichtbare Kennzeichnung einer Aussage, für die sich kein Beleg finden ließ.
#: Bewusst als Klartext und nicht als HTML-Tag: der Abschnitt wird auch als
#: rohe ``section_XX.md`` gelesen, und dort muss die Einschränkung ohne
#: Renderer erkennbar sein.
UNVERIFIED_MARKER = "[Beleg fehlt]"


@dataclass
class FlaggedStatement:
    """Eine Faktenbehauptung, die die Prüfung nicht bestanden hat."""

    text: str
    verdict: EntailmentVerdict
    reason: str
    block_index: int = 0

    def as_hypothesis(self, index: int) -> Dict[str, Any]:
        # ReportSectionHypothesisModel.hypothesis_id erzwingt
        # ^hypothesis_\d{2,}$ — ein sprechendes Präfix ("hypothesis_text_01")
        # lässt die gesamte EvidenceMap-Validierung scheitern.
        return {
            "hypothesis_id": f"hypothesis_{index:02d}",
            "hypothesis_text": self.text[:1000],
            "rationale": (
                f"{self._rationale_prefix}: {self.reason} "
                f"(Urteil: {self.verdict.value})."
            ),
            "suggested_evidence": [
                "Quelle mit übereinstimmender Zahl, Bezugsgruppe und Aussage nachreichen."
            ],
        }

    @property
    def _rationale_prefix(self) -> str:
        return "Aus dem Fließtext entfernt"


@dataclass
class RejectedStatement(FlaggedStatement):
    """Aus dem Fließtext entfernt — eine Quelle widerspricht ihr."""


@dataclass
class UnverifiedStatement(FlaggedStatement):
    """Im Fließtext belassen und markiert — es fand sich kein Beleg."""

    @property
    def _rationale_prefix(self) -> str:
        return "Im Fließtext als unbelegt markiert"


@dataclass
class VerifiedProse:
    content: str
    rejected: List[RejectedStatement] = field(default_factory=list)
    unverified: List[UnverifiedStatement] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.rejected or self.unverified)

    @property
    def flagged(self) -> List[FlaggedStatement]:
        """Alles, was in die Hypothesen gehört — entfernt wie markiert."""
        return [*self.rejected, *self.unverified]


def _fact_label(fact: NumericFact) -> str:
    """Kurzbezeichnung eines Fakts für Leser: die Zahl mit ihrer Bezugsgruppe."""
    head = f"{fact.value:g} %" if fact.unit == "percent" else f"{fact.value:g}"
    return " ".join(part for part in (head, fact.subject) if part).strip()


@dataclass(frozen=True)
class FactOutcome:
    """Das entscheidende Urteil eines Satzes samt auslösendem Fakt.

    Issue #1492: Der Marker entwertete den ganzen Satz, ohne zu sagen, welche
    seiner Zahlen unbelegt ist. Bei einem Satz mit drei Angaben, von denen zwei
    sauber belegt sind, ist das die falsche Auskunft — der Leser kann belegte
    und unbelegte Teile nicht mehr trennen. Die Zählung hier macht den
    Unterschied zwischen "gar kein Beleg" und "teilweise belegt" maschinenlesbar.
    """

    result: EntailmentResult
    fact: NumericFact
    supported: int
    checked: int

    @property
    def partially_supported(self) -> bool:
        """True, wenn mindestens eine Zahl des Satzes belegt ist."""
        return self.supported > 0

    @property
    def verdict(self) -> EntailmentVerdict:
        """Das Urteil des ausloesenden Fakts."""
        return self.result.verdict

    @property
    def reason(self) -> str:
        """Beanstandung mit konkreter Zahl und Belegstand des Satzes."""
        base = f"»{_fact_label(self.fact)}«: {self.result.reason}"
        if not self.partially_supported:
            return base
        verb = "ist" if self.supported == 1 else "sind"
        return (
            f"{base} — {self.supported} der {self.checked} Zahlenangaben "
            f"des Satzes {verb} belegt"
        )

