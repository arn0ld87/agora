"""Was eine Datenlücke ist — und was bloß eine gescheiterte Bindung.

Der Referenzlauf ``report_cc2ef45da5e9`` exportierte 159 Data Gaps: 107 mit
``no_evidence_bound``, 52 mit ``related_evidence_only``. Beide Gründe sagen
etwas über den *Matcher* aus, nichts über die *Quellenlage*. Mindestens ein
so gemeldeter Fall stand wörtlich im Seed-Dokument.

Das ist keine Ungenauigkeit, sondern eine Bedeutungsumkehr. Ein Data Gap ist
eine Aussage über die Welt: "diese Information liegt uns nirgends vor". Wer
daraus "unser Matcher hat nichts gefunden" macht, verkauft ein Werkzeugproblem
als Erkenntnis — und der Leser richtet seine Recherche danach aus.

Vier Ausgänge sind zu trennen, wenn ein Claim keinen Beleg findet:

``unsupported_claim`` / ``hypothesis``
    Die Aussage bleibt, aber unbelegt. Das passiert im Aufrufer und ist
    unabhängig von der Frage hier.
``binding_failure``
    Die Information steht in den Quellen, die Bindung hat sie nicht
    gefunden oder nicht als tragend eingestuft. **Kein Data Gap.**
``source_information_absent``
    In keiner verfügbaren Quelle steht etwas zum Thema. **Nur das** ist ein
    Data Gap.

Die Unterscheidung läuft bewusst deterministisch: die numerische Prüfung über
:mod:`app.services.numeric_evidence`, die inhaltliche über dieselbe
Deckungsmessung, die auch das Entailment verwendet. Ein LLM-Urteil wäre hier
falsch — es geht nicht um Bedeutung, sondern um Vorhandensein.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Sequence

from ..evidence_entailment import coverage_ratio
from ..numeric_evidence import source_mentions_claim_numbers

#: Ab welcher Deckung eine Quelle als "zum Thema vorhanden" gilt.
#:
#: Bewusst niedrig und bewusst dieselbe Schwelle, unter der das Entailment
#: eine Quelle für "nicht einmal thematisch verwandt" erklärt
#: (``QUALITATIVE_RELATED_THRESHOLD``). Die Frage hier ist die schwächere:
#: nicht "belegt das?", sondern "kommt das Thema überhaupt vor?". Wer sie
#: strenger stellt, erzeugt genau die künstlichen Lücken zurück, die dieses
#: Modul verhindert.
TOPIC_PRESENCE_THRESHOLD = 0.10


class ClaimGapKind(str, Enum):
    """Warum ein Claim ohne stützende Evidence dasteht."""

    BINDING_FAILURE = "binding_failure"
    """Die Quelle ist da, die Bindung nicht. Kein Data Gap."""

    SOURCE_INFORMATION_ABSENT = "source_information_absent"
    """In keiner Quelle steht etwas dazu. Ein echter Data Gap."""


def _pool_texts(evidence_pool: Sequence[Dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for item in evidence_pool:
        if not isinstance(item, dict):
            continue
        parts = [
            str(item.get(key) or "")
            for key in ("snippet", "quote", "value", "content", "text")
        ]
        joined = " ".join(part for part in parts if part).strip()
        if joined:
            texts.append(joined)
    return texts


def classify_claim_gap(
    claim_text: str,
    *,
    related_evidence_count: int,
    evidence_pool: Sequence[Dict[str, Any]],
) -> ClaimGapKind:
    """Fehlt die Information — oder nur ihre Bindung?

    ``related_evidence_count`` ist die Zahl der Quellen, die an den Claim
    gebunden wurden, ohne ihn zu stützen. Jede einzelne davon beweist bereits,
    dass das Thema in den Quellen vorkommt: sie wurde ja gefunden.

    Ohne solche Quellen wird der gesamte Pool geprüft — erst auf die Zahlen
    des Claims, dann auf inhaltliche Deckung. Nur wenn beides leer ausgeht,
    ist die Information tatsächlich nirgends vorhanden.
    """
    if related_evidence_count > 0:
        return ClaimGapKind.BINDING_FAILURE

    claim = (claim_text or "").strip()
    if not claim:
        return ClaimGapKind.SOURCE_INFORMATION_ABSENT

    pool = list(evidence_pool or [])
    if source_mentions_claim_numbers(claim, pool):
        return ClaimGapKind.BINDING_FAILURE

    for text in _pool_texts(pool):
        if coverage_ratio(claim, text) >= TOPIC_PRESENCE_THRESHOLD:
            return ClaimGapKind.BINDING_FAILURE

    return ClaimGapKind.SOURCE_INFORMATION_ABSENT


__all__ = [
    "TOPIC_PRESENCE_THRESHOLD",
    "ClaimGapKind",
    "classify_claim_gap",
]
