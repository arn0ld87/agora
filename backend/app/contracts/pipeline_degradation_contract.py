"""Pipeline-Degradierung — Layer-0-Contract für stille Teilausfälle.

Issue #1029 · 2026-08-02

An mehreren Stellen der Pipeline liefert ein Teilausfall ein Ergebnis, das
wie ein gutes aussieht: das Embedding fällt aus und alle Vektoren werden
leer, der Graph entsteht ohne eine einzige Kante, die Persona-Generierung
fällt nach drei LLM-Fehlversuchen auf ein regelbasiertes Platzhalterprofil
zurück. In allen drei Fällen meldete der Schritt bisher Erfolg, und der
Qualitätsverlust schlug erst mehrere Schritte später als scheinbar
unzusammenhängendes Symptom durch.

Dieser Vertrag ist die gemeinsame Sprache dafür. Ein Degradierungsereignis
sagt, *was* ausgefallen ist (``kind``), *wie schwer* das wiegt
(``severity``), *warum* (``detail``) und mit welchen Zahlen sich das belegen
lässt (``context``). Der Fallback selbst bleibt in allen drei Fällen
erhalten — er ist bewusst gewählt, er ist nur nicht länger unsichtbar.

Abgrenzung zu ``EvidenceDegradationModel`` (Issue #1006, report_contract):
das dort protokolliert die Abstufung eines einzelnen Claims im fertigen
Report. Hier geht es um den Ausfall eines Pipeline-Schritts, lange bevor
ein Report existiert.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(extra="forbid", populate_by_name=True)


class DegradationKind(str, Enum):
    """Art des Teilausfalls.

    Eng halten. Ein neuer Wert bedeutet, dass eine weitere Stelle der
    Pipeline still degradieren konnte — das gehört in einen eigenen Slice
    mit eigenem Regressionstest, nicht in einen Sammelwert.
    """

    EMBEDDING_UNAVAILABLE = "embedding_unavailable"
    """Batch-Embedding fehlgeschlagen, Vektoren sind leer (Issue #1029, B-05)."""

    GRAPH_BELOW_THRESHOLD = "graph_below_threshold"
    """Graph-Build unter der Qualitätsschwelle (Issue #1029, B-24)."""

    PERSONA_RULE_BASED_FALLBACK = "persona_rule_based_fallback"
    """Persona regelbasiert erzeugt statt vom LLM (Issue #1029, B-02)."""


class DegradationSeverity(str, Enum):
    """Wie schwer der Ausfall wiegt.

    Der Unterschied ist nicht kosmetisch: ``BLOCKING`` heißt, dass der
    Schritt den Zustand „bereit“ nicht erreichen darf, auch wenn technisch
    kein Fehler aufgetreten ist.
    """

    WARNING = "warning"
    """Ergebnis bleibt nutzbar, die Qualität ist nachweislich reduziert."""

    BLOCKING = "blocking"
    """Ergebnis darf nicht als „bereit“ gelten — Weiterarbeit lohnt nicht."""


class PipelineDegradationModel(BaseModel):
    """Ein Teilausfall, der ohne diesen Eintrag unsichtbar geblieben wäre.

    Gleichartige Ereignisse werden vom ``DegradationCollector``
    zusammengefasst: vierzig parallel verarbeitete Chunks, die alle am
    selben abwesenden Ollama scheitern, ergeben **einen** Eintrag mit
    ``occurrences=40``, nicht vierzig identische. ``occurred_at`` trägt
    dann den Zeitpunkt des ersten Auftretens.
    """

    model_config = _STRICT

    kind: DegradationKind
    severity: DegradationSeverity
    detail: str = Field(
        min_length=1,
        description="Menschenlesbare Ursache — geht so in die Oberfläche.",
    )
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Erstes Auftreten, nicht das letzte.",
    )
    occurrences: int = Field(
        default=1,
        ge=1,
        description="Wie oft dieses Ereignis zusammengefasst wurde.",
    )
    context: dict[str, str | int | float] = Field(
        default_factory=dict,
        description=(
            "Zahlen, die die Einstufung belegen — etwa node_count/edge_count "
            "bei einem Graph unter der Schwelle. Keine freien Objekte, damit "
            "der Zod-Spiegel eng bleibt."
        ),
    )

    @property
    def is_blocking(self) -> bool:
        return self.severity is DegradationSeverity.BLOCKING


class PipelineDegradationReport(BaseModel):
    """Alle Degradierungen eines Pipeline-Schritts.

    Wird als ``degradations`` in das Task-Ergebnis geschrieben und von dort
    an die Oberfläche gereicht. Ein leerer Report ist der Normalfall und
    bedeutet: nichts ist still ausgefallen.
    """

    model_config = _STRICT

    schema_version: int = Field(default=1, ge=1)
    events: list[PipelineDegradationModel] = Field(default_factory=list)

    @property
    def has_blocking(self) -> bool:
        return any(event.is_blocking for event in self.events)

    def __bool__(self) -> bool:
        """Ein Report ohne Ereignisse ist falsy — ``if degradations:`` liest sich richtig."""
        return bool(self.events)


__all__ = [
    "DegradationKind",
    "DegradationSeverity",
    "PipelineDegradationModel",
    "PipelineDegradationReport",
]
