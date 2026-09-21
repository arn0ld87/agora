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
        # Überzählige Stufen sind kein harmloser Zusatz: beide Adapter
        # serialisieren ``legend`` vollständig an den jeweiligen Provider
        # (``jev_provider._question_payload``, ``llm_provider._build_prompt``),
        # eine Stufe außerhalb von [min_stage, max_stage] ginge also
        # unbemerkt mit und böte dem Modell eine Antwort an, die der
        # Aufrufer anschließend als ungültig zurückweisen müsste.
        surplus = set(self.legend) - expected
        if surplus:
            raise ValueError(
                f"ScoreQuestion: legend beschriftet Stufe(n) außerhalb "
                f"[{self.min_stage}, {self.max_stage}]: {sorted(surplus)}."
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

    Welches Wahrscheinlichkeitsfeld gesetzt ist, hängt an der Frageform;
    der Vertrag erzwingt die Zuordnung nicht, weil sie beim Provider
    entsteht, der die passende Frage ohnehin kennt. Tatsächlich gilt bei
    den heutigen Referenzadaptern:

    - Choice → ``distribution`` (Verteilung über die gesendeten Optionen)
    - Score → nur ``answer`` (die Stufe) und ``confidence``
    - Noul → ``probability_yes``

    Score liefert bewusst **keine** ``distribution``: Jev meldet laut
    Anbieterdoku zwar eine Verteilung über die Stufen, aber deren
    Feldname ist ohne echten Zugang nicht verifiziert, und ein geratenes
    Feld zu parsen wäre eine unbelegte Behauptung (siehe Moduldocstring
    von ``services/decisions/jev_provider.py``). Sobald echter Zugang
    besteht, ist das Nachziehen der Stufen-Verteilung eine eigene,
    benannte Aufgabe — sie ist für die Kalibration des Benchmarks
    nützlich, aber nicht erfindbar.

    ``cost_micros`` unterscheidet drei Zustände, statt sie auf eine Null
    zu verflachen (dieselbe Regel wie in ``services/pricing_registry.py``,
    deren Docstring festhält: "unknown — wird niemals als 0 ausgegeben"):

    - ``0``   — tatsächlich kostenfrei (``RuleProvider``: reiner Python-Code)
      oder an anderer Stelle bereits gebucht (``LLMProvider`` mit ``run_id``,
      dessen Kosten ``chat_json`` selbst ins Run-Usage-Ledger schreibt).
    - ``> 0`` — von diesem Aufruf verursachte, bezifferte Kosten.
    - ``None`` — Kosten unbekannt. Kein Preis in der ``PricingRegistry``
      oder kein Ledger, das sie gebucht hätte. Ein sichtbarer Zustand,
      damit eine Kostenlücke nicht als "kostenlos" durchgeht.

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
    cost_micros: int | None = Field(default=None, ge=0)
    latency_ms: int = Field(ge=0)
    shadow: bool

    @model_validator(mode="after")
    def _distribution_values_are_probabilities(self) -> "DecisionResult":
        """``distribution`` trägt Wahrscheinlichkeiten, nicht beliebige Zahlen.

        ``probability_yes`` und ``confidence`` sind bereits auf ``[0, 1]``
        begrenzt; ohne diese Prüfung wäre ``distribution`` das einzige
        Wahrscheinlichkeitsfeld des Vertrags, das jeden Wert annimmt — und
        genau diese Verteilung wertet der Benchmark später zur Kalibration
        aus, wo ein Wert außerhalb des Einheitsintervalls kein erkennbarer
        Fehler mehr wäre, sondern eine verzerrte Kurve.
        """
        if self.distribution is None:
            return self
        invalid = {
            key: value
            for key, value in self.distribution.items()
            if not (0.0 <= value <= 1.0)
        }
        if invalid:
            raise ValueError(
                f"DecisionResult: distribution-Werte außerhalb [0, 1]: {invalid}."
            )
        return self


__all__ = [
    "DecisionState",
    "ChoiceQuestion",
    "ScoreQuestion",
    "NoulQuestion",
    "DecisionQuestion",
    "DecisionResult",
]
