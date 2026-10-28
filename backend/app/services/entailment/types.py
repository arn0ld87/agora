"""Datentypen und Enums für das Evidence-Entailment."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional


class EntailmentVerdict(str, Enum):
    """Urteil der zweiten Binding-Stufe."""

    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    RELATED_ONLY = "RELATED_ONLY"
    INSUFFICIENT = "INSUFFICIENT"


class FactModality(str, Enum):
    """Ist die Zahl ein berichteter Ist-Wert oder eine Zielvorgabe?

    "70 % der Lehrkräfte *sollen* geschult sein" ist eine Anforderung, kein
    gemessener Zustimmungswert. Diese Unterscheidung verhindert genau die
    Verfälschung aus dem Referenzlauf.
    """

    FACTUAL = "factual"
    NORMATIVE = "normative"


class BoundKind(str, Enum):
    """Beschreibt die Zahl einen Punktwert oder eine Schranke?

    "31 Prozent geschult" und "mindestens 80 Prozent geschult" sind nicht
    derselbe Aussagetyp. Der erste Satz misst, der zweite fordert. Ohne diese
    Unterscheidung las der Trust-Layer die Differenz 31 ≠ 80 als Widerspruch
    und löschte den Satz aus dem Fließtext — obwohl beide Angaben gleichzeitig
    zutreffen und der Satz genau diese Lücke benennt.
    """

    EXACT = "exact"
    AT_LEAST = "at_least"
    AT_MOST = "at_most"


@dataclass(frozen=True)
class NumericFact:
    """Eine Zahl zusammen mit ihrer Bezugsgruppe und ihrer Aussage."""

    value: float
    unit: str
    subject: str
    predicate: str
    modality: FactModality = FactModality.FACTUAL
    raw: str = ""
    bound: BoundKind = BoundKind.EXACT
    #: Einschränkende Zusätze aus dem Vorfeld ("Pflege-Nachtschicht",
    #: "erstes Quartal") in Originalschreibweise. Zwei Zahlen über dieselbe
    #: Bezugsgruppe, aber verschiedene Teilpopulationen oder Zeiträume, sind
    #: keine widersprüchlichen Angaben über denselben Sachverhalt.
    #:
    #: Bewusst ungestemmt: ``text_verification._fact_probe`` baut aus einem
    #: Fakt wieder einen Prüftext, und der Scope muss dabei so wiederauftauchen,
    #: dass ihn dieselbe Extraktion erneut findet. Aus Stämmen ließe sich das
    #: nicht rekonstruieren, und der Scope-Schutz wäre im Fließtext-Pfad —
    #: also genau dort, wo der Referenzlauf Sätze verlor — wirkungslos.
    scope: frozenset[str] = frozenset()


@dataclass
class EntailmentResult:
    verdict: EntailmentVerdict
    reason: str
    matched_fact: Optional[NumericFact] = None
    claim_fact: Optional[NumericFact] = None
    checks: List[str] = field(default_factory=list)

    @property
    def supports(self) -> bool:
        return self.verdict is EntailmentVerdict.SUPPORTED


#: Begründungspräfix für Evidence aus Szenario-/Erwartungstext (#1240). Das
#: Hypothesen-Routing erkennt daran, dass ein Claim nur am Testfall hing.
SCENARIO_ROLE_REASON_PREFIX = "Szenario-/Erwartungstext des Eingabedokuments"

EntailmentJudge = Callable[[str, str], str]
"""Optionaler strukturierter Judge: (claim, evidence_text) -> Verdict-Name."""

__all__ = [
    "BoundKind",
    "EntailmentJudge",
    "EntailmentResult",
    "EntailmentVerdict",
    "FactModality",
    "NumericFact",
    "SCENARIO_ROLE_REASON_PREFIX",
]
