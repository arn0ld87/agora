"""
Decision-Contract v1 (Pydantic v2) — Vertrag für die Decision-Layer-Pilotierung.

f005 (Jev-Decision-Layer und Neo4j-Ablösung), Slice `decision-pilot`, Task
`decision-contracts`. Aus ADR-0016/0017 und dem Decision-Layer-Entwurf
abgeleitet: genau drei Antwortformen — Choice, Score, Noul —, weil das
Jevs eigener Vertrag ist (`docs/research/f005/jev-provider-evidence.md`)
und exakt die Formen deckt, die die Decision Map für die elf `A`/`B`/`C`-
Kandidaten braucht. Ein Use Case, dessen Antwort keine dieser drei Formen
hat, gehört nicht hierher, sondern bleibt bei `LLMClient.chat_json`.

Scope-Korrektur gegenüber dem Architektur-Entwurf: `decide()` nimmt genau
EINE Frage pro Aufruf, nicht eine Liste. Der Pilot hat einen einzigen Use
Case; Batching mehrerer Fragen pro State ist eine echte API-Erweiterung
(mehrere Ergebnisse statt eines), die erst gebraucht wird, wenn ein
zweiter Use Case sie tatsächlich braucht — keine vorsorgliche Abstraktion.

Aufruf zum Schema-Dump: cd backend && uv run python -m app.contracts.dump_schemas
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

_STRICT = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=False)


class DecisionState(BaseModel):
    """Minimierter, redigierter Entscheidungskontext.

    ``state`` ist Datenmaterial, keine Anweisung (ADR-0016, Abschnitt
    Security) — Aufrufer sind verantwortlich, PII vor dem Befüllen zu
    minimieren; dieser Vertrag führt dafür keine Heuristik, das wäre eine
    neue, ungeprüfte Fehlerquelle.

    ``context_hash`` existiert, damit Telemetrie den Fall referenzieren
    kann, ohne den Klartext zu speichern (ADR-0016) — Aufrufer berechnen
    ihn (z. B. SHA-256 über eine kanonische Serialisierung von ``state``);
    dieser Vertrag erzwingt kein bestimmtes Hash-Verfahren.
    """

    model_config = _STRICT

    use_case_id: str = Field(min_length=1)
    state: str | dict[str, object] | list[object]
    context_hash: str = Field(min_length=1)


class ChoiceQuestion(BaseModel):
    """Auswahl aus bis zu 255 Optionen — Jevs Choice-Form."""

    model_config = _STRICT

    kind: Literal["choice"] = "choice"
    options: list[str] = Field(min_length=1, max_length=255)


class ScoreQuestion(BaseModel):
    """Erwartungswert über eine geordnete Rubrik, 2–10 Stufen — Jevs Score-Form.

    ``legend`` beschriftet jede Stufe zwischen ``min_stage`` und
    ``max_stage`` (inklusive) — eine fehlende Beschriftung ist ein
    Konfigurationsfehler des Aufrufers, kein Laufzeitfall, den dieser
    Vertrag stillschweigend tolerieren sollte.
    """

    model_config = _STRICT

    kind: Literal["score"] = "score"
    min_stage: int = Field(ge=1, le=9)
    max_stage: int = Field(ge=2, le=10)
    legend: dict[int, str] = Field(min_length=2)

    @model_validator(mode="after")
    def _stages_are_consistent(self) -> "ScoreQuestion":
        if self.max_stage <= self.min_stage:
            raise ValueError(
                f"ScoreQuestion: max_stage ({self.max_stage}) muss > "
                f"min_stage ({self.min_stage}) sein."
            )
        expected = set(range(self.min_stage, self.max_stage + 1))
        missing = expected - set(self.legend)
        if missing:
            raise ValueError(
                f"ScoreQuestion: legend fehlt Beschriftung für Stufe(n) "
                f"{sorted(missing)}."
            )
        return self


class NoulQuestion(BaseModel):
    """Wahrscheinlichkeit für Ja — Jevs Noul-Form. Keine weiteren Felder:
    die Frage selbst steht im Prompt-Text, den der Aufrufer an den
    jeweiligen Provider gibt, nicht in diesem Vertrag."""

    model_config = _STRICT

    kind: Literal["noul"] = "noul"


DecisionQuestion = Annotated[
    Union[ChoiceQuestion, ScoreQuestion, NoulQuestion],
    Field(discriminator="kind"),
]


class DecisionResult(BaseModel):
    """Ergebnis eines ``DecisionProvider.decide()``-Aufrufs.

    Genau eines von ``distribution``/``probability_yes`` ist gesetzt, je
    nach angefragter Frageform — kein Validator erzwingt das hier, weil
    die Zuordnung (Choice→distribution, Score→distribution über Stufen,
    Noul→probability_yes) beim Provider entsteht, der die passende Frage
    ohnehin kennt; ein Vertrags-Validator würde nur dieselbe Regel
    doppelt kodieren.

    ``shadow=True`` heißt: dieses Ergebnis wurde ermittelt, aber NICHT
    autoritativ verwendet (ADR-0016, Confidence-Zustand `shadow`) — der
    Aufrufer muss die tatsächlich wirksame Entscheidung aus seinem
    bisherigen Pfad nehmen, nicht aus diesem Resultat.

    ``provider="unresolved"`` ist der sichtbare Zustand, wenn die
    Fallback-Kette erschöpft ist (ADR-0016, Abschnitt Fallback-Kette) —
    niemals ein stiller Rückfall auf einen Platzhalterwert.
    """

    model_config = _STRICT

    use_case_id: str = Field(min_length=1)
    provider: Literal["rule", "llm_cheap", "llm_capable", "jev", "fake", "unresolved"]
    answer: str | int | float | None
    distribution: dict[str, float] | None = None
    probability_yes: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    model_version: str | None = None
    fallback_chain: list[str] = Field(default_factory=list)
    request_id: str | None = None
    cost_micros: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    shadow: bool


__all__ = [
    "DecisionState",
    "ChoiceQuestion",
    "ScoreQuestion",
    "NoulQuestion",
    "DecisionQuestion",
    "DecisionResult",
]
