"""LLMProvider — ``DecisionProvider``-Referenzadapter über ``LLMClient.chat_json``.

Mappt Choice/Score/Noul auf ein enges JSON-Schema und ruft ausschließlich
``LLMClient.chat_json`` auf (ADR-0017: kein zweiter roher LLM-Zugriffspfad).
Route-agnostisch: nimmt einen bereits konstruierten ``LLMClient`` entgegen
statt selbst zu routen — Provider-Detection und Stage/Run-Auflösung bleiben
bei ``registry.py::detect_provider`` und dem Aufrufer, der den Client baut
(``LLMClient(run_id=..., route_stage=...)``); dieser Adapter würde sonst
eine zweite Routing-Heuristik einführen.

Kosten: ``LLMClient.chat_json`` protokolliert Token-Verbrauch und Kosten
bereits selbst in das Run-Usage-Ledger, aber nur wenn der Client einen
``run_id`` trägt — ``_log_invocation_event`` (``llm/client.py``) kehrt
ohne ``run_id`` früh zurück. Dieser Adapter unterscheidet deshalb zwei
Fälle statt pauschal ``0`` zu melden:

- ``run_id`` gesetzt → ``cost_micros=0``: nicht "kostenlos", sondern
  "an anderer Stelle bereits gebucht, keine zweite Kostenwahrheit"
  (ADR-0016).
- kein ``run_id`` → ``cost_micros=None``: die Kosten sind entstanden,
  aber nirgends gebucht und hier nicht beziffert. Ein sichtbarer
  Unbekannt-Zustand, damit ein Aufruf ohne Ledger nicht als kostenlos
  durchgeht.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Literal

from ...contracts.decision_contract import (
    ChoiceQuestion,
    DecisionQuestion,
    DecisionResult,
    DecisionState,
    NoulQuestion,
    ScoreQuestion,
)


def _shape(value: Any) -> str:
    """Strukturbeschreibung statt Inhalt.

    Die Fehlermeldung landet über die Exception-Kette im Log. Eine
    LLM-Antwort auf einen Schemafehler kann Teile des Prompts spiegeln,
    und der Prompt trägt den Entscheidungskontext im Klartext — Telemetrie
    darf laut ADR-0016 nur den ``context_hash`` referenzieren. Deshalb
    beschreibt diese Funktion die Form der Antwort, nicht ihre Werte.
    """
    if isinstance(value, dict):
        return f"dict(keys={sorted(str(key) for key in value)})"
    if isinstance(value, list):
        return f"list(len={len(value)})"
    return type(value).__name__


def _digest(value: Any) -> str:
    """Diagnose für Fälle, in denen der Wert selbst die Diagnose IST — etwa
    eine Kategorie außerhalb der gesendeten Optionen.

    Review-Befund (Codex, PR #1547): eine gekürzte Wertdarstellung (vormals
    bis zu 80 Zeichen) reicht aus, um ein gespiegeltes Secret oder
    vertrauliches Fragment zu leaken — Kürzung ist keine Redaktion. Diese
    Funktion gibt deshalb NIE einen Ausschnitt des Werts zurück, nur Typ,
    Länge und einen irreversiblen Hash-Prefix zur Korrelation über mehrere
    Vorkommen hinweg (»ist das zweimal derselbe falsche Wert?«), ohne ihn
    je offenzulegen."""
    text = str(value)
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"{type(value).__name__}(len={len(text)}, sha256={digest})"


class DecisionLLMResponseError(RuntimeError):
    """Die LLM-Antwort erfüllte das angeforderte Schema nicht sinnvoll —
    z. B. eine Choice außerhalb der gesendeten Optionsliste. Wird laut
    geworfen statt eine ungültige Antwort als gültige neue Kategorie zu
    interpretieren (Benchmark-Spezifikation, Abschnitt Failure-Injection)."""


def _schema_for(question: DecisionQuestion) -> dict[str, Any]:
    """Rohes JSON-Schema (kein Pydantic-Modell) — ``options``/``min_stage``/
    ``max_stage`` sind Laufzeitwerte, ein dynamisch pro Frage gebautes
    Pydantic-Modell wäre hier mehr Aufwand für denselben Vertrag."""
    confidence_prop = {"type": "number", "minimum": 0.0, "maximum": 1.0}
    if isinstance(question, ChoiceQuestion):
        return {
            "type": "object",
            "properties": {
                "choice": {"type": "string", "enum": list(question.options)},
                "confidence": confidence_prop,
            },
            "required": ["choice", "confidence"],
            "additionalProperties": False,
        }
    if isinstance(question, ScoreQuestion):
        return {
            "type": "object",
            "properties": {
                "stage": {
                    "type": "integer",
                    "minimum": question.min_stage,
                    "maximum": question.max_stage,
                },
                "confidence": confidence_prop,
            },
            "required": ["stage", "confidence"],
            "additionalProperties": False,
        }
    if isinstance(question, NoulQuestion):
        return {
            "type": "object",
            "properties": {
                "probability_yes": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "confidence": confidence_prop,
            },
            "required": ["probability_yes", "confidence"],
            "additionalProperties": False,
        }
    raise TypeError(f"LLMProvider: unbekannte Frageform {type(question).__name__}")


def _build_prompt(state: DecisionState, question: DecisionQuestion) -> str:
    state_text = state.state if isinstance(state.state, str) else str(state.state)
    if isinstance(question, ChoiceQuestion):
        instruction = (
            "Wähle genau eine der folgenden Optionen: "
            + ", ".join(question.options)
        )
    elif isinstance(question, ScoreQuestion):
        legend_text = "; ".join(
            f"{stage}={label}" for stage, label in sorted(question.legend.items())
        )
        instruction = (
            f"Bewerte auf einer Stufe von {question.min_stage} bis "
            f"{question.max_stage} ({legend_text})."
        )
    else:
        instruction = "Beantworte mit der Wahrscheinlichkeit, dass die Aussage zutrifft."
    return f"{state_text}\n\n{instruction}"


def _result_from_response(
    question: DecisionQuestion,
    response: dict[str, Any],
    *,
    use_case_id: str,
    provider: Literal["llm_cheap", "llm_capable"],
    model_version: str | None,
    cost_micros: int | None,
    latency_ms: int,
) -> DecisionResult:
    confidence = response.get("confidence")
    if not isinstance(confidence, (int, float)):
        raise DecisionLLMResponseError(
            f"LLM-Antwort ohne gültiges 'confidence'-Feld: {_shape(response)}"
        )

    if isinstance(question, ChoiceQuestion):
        choice = response.get("choice")
        if choice not in question.options:
            raise DecisionLLMResponseError(
                f"LLM-Antwort {_digest(choice)} liegt außerhalb der gesendeten "
                f"Optionen {question.options!r}."
            )
        return DecisionResult(
            use_case_id=use_case_id,
            provider=provider,
            answer=choice,
            distribution={choice: float(confidence)},
            confidence=float(confidence),
            model_version=model_version,
            cost_micros=cost_micros,
            latency_ms=latency_ms,
            shadow=False,
        )
    if isinstance(question, ScoreQuestion):
        stage = response.get("stage")
        if not isinstance(stage, int) or not (question.min_stage <= stage <= question.max_stage):
            raise DecisionLLMResponseError(
                f"LLM-Antwort-Stufe {_digest(stage)} außerhalb "
                f"[{question.min_stage}, {question.max_stage}]."
            )
        return DecisionResult(
            use_case_id=use_case_id,
            provider=provider,
            answer=stage,
            confidence=float(confidence),
            model_version=model_version,
            cost_micros=cost_micros,
            latency_ms=latency_ms,
            shadow=False,
        )
    # NoulQuestion
    probability_yes = response.get("probability_yes")
    if not isinstance(probability_yes, (int, float)) or not (0.0 <= probability_yes <= 1.0):
        raise DecisionLLMResponseError(
            f"LLM-Antwort ohne gültiges 'probability_yes'-Feld: {_shape(response)}"
        )
    return DecisionResult(
        use_case_id=use_case_id,
        provider=provider,
        answer=None,
        probability_yes=float(probability_yes),
        confidence=float(confidence),
        model_version=model_version,
        cost_micros=cost_micros,
        latency_ms=latency_ms,
        shadow=False,
    )


class LLMProvider:
    """Siehe Moduldocstring. ``client`` ist ein bereits konstruierter,
    korrekt gerouteter ``LLMClient`` — dieser Adapter baut keinen eigenen."""

    def __init__(
        self,
        client: Any,
        *,
        provider_label: Literal["llm_cheap", "llm_capable"] = "llm_cheap",
    ) -> None:
        self._client = client
        self._provider_label = provider_label

    def decide(self, state: DecisionState, question: DecisionQuestion) -> DecisionResult:
        schema = _schema_for(question)
        prompt = _build_prompt(state, question)
        t0 = time.monotonic()
        response = self._client.chat_json(
            [{"role": "user", "content": prompt}],
            schema=schema,
            context="chat_json",
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        # Siehe Moduldocstring: 0 heißt "im Run-Usage-Ledger gebucht",
        # None heißt "entstanden, aber nirgends gebucht". Ohne ``run_id``
        # kehrt ``_log_invocation_event`` früh zurück, die Kosten wären
        # sonst unsichtbar verschwunden.
        cost_micros = 0 if getattr(self._client, "run_id", None) else None
        return _result_from_response(
            question,
            response,
            use_case_id=state.use_case_id,
            provider=self._provider_label,
            model_version=getattr(self._client, "model", None),
            cost_micros=cost_micros,
            latency_ms=latency_ms,
        )


__all__ = ["LLMProvider", "DecisionLLMResponseError"]
