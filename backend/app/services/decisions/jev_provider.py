"""JevDecisionProvider — ``DecisionProvider``-Referenzadapter für TypeSafes
Jev (f005, ADR-0016/0017).

Kein Import eines Jev-SDK hier: wie ``LLMProvider`` bei ``LLMClient`` nimmt
dieser Adapter einen bereits konstruierten Client entgegen (``client: Any``)
und ruft dessen ``system_one``-Methode auf. Verifizierter TypeSafe-Zugang
ist laut ``docs/research/f005/jev-provider-evidence.md`` noch offen; eine
harte Abhängigkeit auf ``typesafe-sdk`` in ``pyproject.toml`` wird deshalb
erst ergänzt, wenn ein echter Pilotlauf sie tatsächlich braucht — der
Vertrag steht, der Aufruf ist möglich, das Paket fehlt bewusst noch.

``client.system_one(state=..., model=..., questions=[...])`` muss ein
Mapping zurückgeben, das dem verifizierten HTTP-Vertrag entspricht
(jev-provider-evidence.md, Abschnitt „Vertrag und Grenzen“): mindestens
``answers`` (Liste je Fragen-ID), ``model`` (tatsächlich verwendete
Version) und ``usage`` (Tokenverbrauch). Feldnamen darunter sind aus der
öffentlichen Doku abgeleitet, nicht gegen eine echte Response verifiziert
— das ist ein offener Punkt, den erst ein echter Pilotlauf schließt
(siehe ``docs/research/f005/decision-layer-design.md``, Abschnitt „Was
dieser Entwurf nicht entscheidet“).

Retries: TypeSafes eigenes SDK konfiguriert eine ``RetryPolicy``
(Backoff, Jitter, 429/529, Verbindungs-/Timeout-Fehler — siehe
jev-provider-evidence.md, Abschnitt SDK). Dieser Adapter wrappt den
Aufruf deshalb NICHT in eine zweite Retry-Schleife — die Anbieterdoku
warnt ausdrücklich vor verschachtelten Retry-Schleifen. Er ruft genau
einmal auf und übersetzt Erfolg oder Fehler; die Retry-Konfiguration des
Clients ist Sache der Factory, die ihn baut, nicht dieses Adapters.

Kosten: über die bestehende ``PricingRegistry`` (Issue #764) aus
``usage``-Tokenzahlen berechnet — keine zweite Preislogik neben der
einen Preisquelle des Systems.

Secret-Management: :func:`resolve_jev_api_key` liest den Key über den
bestehenden verschlüsselten Provider-Secret-Store (``AGORA_SECRET_KEY``-
Fernet-Master, dieselbe Route wie andere Provider-Secrets laut
Architektur-SSoT) — kein Klartext in Config oder Logs, keine zweite
Speicherstelle. Eine Fabrik, die daraus den echten ``typesafe_sdk``-Client
baut, fehlt hier bewusst: das SDK ist nicht installiert, sein tatsächlicher
Klassenname und Konstruktor sind gegen die öffentliche Doku nicht
verifiziert, und ein erratener Import wäre eine unbelegte Behauptung.
Diese Fabrik entsteht, sobald ein echter Pilotlauf sie braucht (verifizierter
Account-Zugang ist laut jev-provider-evidence.md, Abschnitt „Produktions-
nachweise vor Aktivierung“, noch offen).
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from ...contracts.decision_contract import (
    ChoiceQuestion,
    DecisionQuestion,
    DecisionResult,
    DecisionState,
    NoulQuestion,
    ScoreQuestion,
)
from ..pricing_registry import get_pricing_registry
from ..secret_resolver import get_bound_store_api_key

#: Jevs Version am Stand von jev-provider-evidence.md (21.09.2026). Explizit
#: gepinnt statt "jev-latest"/"jev-preview" — eine unbemerkte Modelländerung
#: zwischen Kalibration und Betrieb würde die kalibrierten Fehlerraten sonst
#: unsichtbar verschieben (decision-layer-design.md, Abschnitt
#: "Modellversion pinnen").
JEV_PINNED_MODEL_VERSION = "jev-1.13.0"

#: Feste Fragen-ID für den Einzelfrage-Aufruf dieses Ports (der Port nimmt
#: laut decision_contract.py genau eine Frage pro Aufruf entgegen, Jevs
#: eigene API ist dennoch fragen-batch-förmig). Kein Nutzerinhalt, kein aus
#: State abgeleiteter Wert.
_QUESTION_ID = "q1"

#: Schlüssel, unter dem der Jev-API-Key im Provider-Secret-Store liegt.
_SECRET_REF = "jev"  # noqa: S105 - Store-Schlüsselname, kein Secret


def resolve_jev_api_key() -> str | None:
    """Liest den Jev-API-Key aus dem bestehenden verschlüsselten
    Provider-Secret-Store. ``None`` heißt: kein Key gebunden — ein
    sichtbarer Konfigurationszustand, keine Ausnahme, weil das Fehlen
    außerhalb eines aktiven Piloten der Normalfall ist (Flag-off/Default)."""
    return get_bound_store_api_key(_SECRET_REF)


class DecisionJevResponseError(RuntimeError):
    """Jevs Antwort erfüllte das angeforderte Schema nicht sinnvoll — fehlende
    Fragen-ID, unbekannte Kategorie oder ungültige Verteilung. Wird laut
    geworfen statt eine unvollständige Antwort als vollständige zu
    behandeln: das SDK kann laut Anbieterangabe unbekannte Antwortarten
    warnend überspringen, AGORA lehnt das selbst ab."""


class DecisionJevAuthError(RuntimeError):
    """401/422 laut jev-provider-evidence.md — Auth- oder Validierungsfehler,
    die nie retryed werden dürfen. Der Aufrufer entscheidet über die
    Fallback-Kette; dieser Adapter versucht es nie ein zweites Mal selbst."""


def _shape(value: Any) -> str:
    """Strukturbeschreibung statt Inhalt.

    Fehlermeldungen dieses Adapters landen über die Exception-Kette im Log
    (der Shadow-Aufrufer ruft ``logger.exception``). Eine Antwort eines
    externen Dienstes kann Teile der Anfrage spiegeln, und die Anfrage
    trägt den Entscheidungskontext — Telemetrie darf laut ADR-0016 nur den
    ``context_hash`` referenzieren, nie den Klartext. Deshalb beschreibt
    diese Funktion die Form der Antwort (Typ, Schlüssel), nicht ihre Werte.
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
    Vorkommen hinweg, ohne ihn je offenzulegen. Identisch zu
    ``llm_provider._digest`` — bewusst dupliziert statt geteilt, siehe
    Entscheidung ``mapping-duplication-kept`` im Plan.
    """
    text = str(value)
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"{type(value).__name__}(len={len(text)}, sha256={digest})"


def _question_payload(question: DecisionQuestion) -> dict[str, Any]:
    """Jevs eigene Fragenform (nicht das AGORA-JSON-Schema aus ``llm_provider.py``)."""
    if isinstance(question, ChoiceQuestion):
        return {"id": _QUESTION_ID, "type": "choice", "options": list(question.options)}
    if isinstance(question, ScoreQuestion):
        return {
            "id": _QUESTION_ID,
            "type": "score",
            "min_stage": question.min_stage,
            "max_stage": question.max_stage,
            "legend": {str(stage): label for stage, label in question.legend.items()},
        }
    if isinstance(question, NoulQuestion):
        return {"id": _QUESTION_ID, "type": "noul"}
    raise TypeError(f"JevDecisionProvider: unbekannte Frageform {type(question).__name__}")


def _answer_for_question_id(response: dict[str, Any]) -> dict[str, Any]:
    """Holt die Antwort für ``_QUESTION_ID`` und prüft Vollständigkeit.

    Eine fehlende Fragen-ID ist ein Fehler, kein stiller Leerwert — siehe
    Moduldocstring."""
    answers = response.get("answers")
    if not isinstance(answers, list):
        raise DecisionJevResponseError(
            f"Jev-Antwort ohne 'answers'-Liste: {_shape(response)}"
        )
    for entry in answers:
        if isinstance(entry, dict) and entry.get("id") == _QUESTION_ID:
            return entry
    raise DecisionJevResponseError(
        f"Jev-Antwort enthält keine Antwort für Fragen-ID '{_QUESTION_ID}': "
        f"{_shape(response)}"
    )


def _result_from_answer(
    question: DecisionQuestion,
    answer: dict[str, Any],
    *,
    use_case_id: str,
    model_version: str,
    cost_micros: int | None,
    latency_ms: int,
    request_id: str | None,
) -> DecisionResult:
    confidence = answer.get("confidence")
    if not isinstance(confidence, (int, float)):
        raise DecisionJevResponseError(
            f"Jev-Antwort ohne gültiges 'confidence'-Feld: {_shape(answer)}"
        )

    if isinstance(question, ChoiceQuestion):
        choice = answer.get("choice")
        if choice not in question.options:
            raise DecisionJevResponseError(
                f"Jev-Antwort {_digest(choice)} liegt außerhalb der gesendeten "
                f"Optionen {question.options!r}."
            )
        return DecisionResult(
            use_case_id=use_case_id,
            provider="jev",
            answer=choice,
            distribution={choice: float(confidence)},
            confidence=float(confidence),
            model_version=model_version,
            request_id=request_id,
            cost_micros=cost_micros,
            latency_ms=latency_ms,
            shadow=False,
        )
    if isinstance(question, ScoreQuestion):
        stage = answer.get("stage")
        if not isinstance(stage, int) or not (question.min_stage <= stage <= question.max_stage):
            raise DecisionJevResponseError(
                f"Jev-Antwort-Stufe {_digest(stage)} außerhalb "
                f"[{question.min_stage}, {question.max_stage}]."
            )
        return DecisionResult(
            use_case_id=use_case_id,
            provider="jev",
            answer=stage,
            confidence=float(confidence),
            model_version=model_version,
            request_id=request_id,
            cost_micros=cost_micros,
            latency_ms=latency_ms,
            shadow=False,
        )
    # NoulQuestion
    probability_yes = answer.get("probability_yes")
    if not isinstance(probability_yes, (int, float)) or not (0.0 <= probability_yes <= 1.0):
        raise DecisionJevResponseError(
            f"Jev-Antwort ohne gültiges 'probability_yes'-Feld: {_shape(answer)}"
        )
    return DecisionResult(
        use_case_id=use_case_id,
        provider="jev",
        answer=None,
        probability_yes=float(probability_yes),
        confidence=float(confidence),
        model_version=model_version,
        request_id=request_id,
        cost_micros=cost_micros,
        latency_ms=latency_ms,
        shadow=False,
    )


def _cost_micros_for(usage: Any, model_version: str) -> int | None:
    """Kosten über die bestehende ``PricingRegistry`` — die einzige
    Preisquelle des Systems, keine zweite Schätzlogik hier.

    Bepreist wird das TATSÄCHLICH gemeldete Modell, nicht der Pin. Meldet
    Jev eine andere Version zurück als die angefragte (laut Anbieterdoku
    können ``jev-latest``/``jev-preview`` ohne Vorankündigung umziehen),
    wäre der Preis des gepinnten Modells schlicht der Preis eines anderen
    Modells.

    ``None`` heißt "Kosten unbekannt" und wird bewusst NICHT auf 0
    geglättet: ``pricing_registry`` hält dieselbe Regel fest — ein
    unbekannter Preis wird niemals als 0 ausgegeben, sonst ginge eine
    Preislücke als "kostenlos" durch. Ohne ``usage`` in der Antwort ist
    auch der Verbrauch unbekannt, nicht null.
    """
    if not isinstance(usage, dict):
        return None
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    quote = get_pricing_registry().resolve("jev", model_version)
    return quote.cost_micros(input_tokens, output_tokens)


class JevDecisionProvider:
    """Siehe Moduldocstring. ``client`` ist ein bereits konstruierter,
    mit Secret und Retry-Policy versehener Jev-Client — dieser Adapter
    baut keinen eigenen und wrappt seinen Aufruf nicht in eigene Retries."""

    def __init__(self, client: Any, *, model_version: str = JEV_PINNED_MODEL_VERSION) -> None:
        self._client = client
        self._model_version = model_version

    def decide(self, state: DecisionState, question: DecisionQuestion) -> DecisionResult:
        t0 = time.monotonic()
        # Kein try/except hier: der Client wirft (Timeout, Rate Limit,
        # DecisionJevAuthError bei 401/422, Verbindungsfehler) und dieser
        # Adapter reicht das unverändert an den Aufrufer weiter — siehe
        # Moduldocstring zu verschachtelten Retry-Schleifen.
        response = self._client.system_one(
            state=state.state,
            model=self._model_version,
            questions=[_question_payload(question)],
        )
        latency_ms = int((time.monotonic() - t0) * 1000)

        if not isinstance(response, dict):
            raise DecisionJevResponseError(
                f"Jev-Response ist kein Mapping: {_shape(response)}"
            )

        answer = _answer_for_question_id(response)
        model_version = str(response.get("model") or self._model_version)
        request_id = response.get("request_id")

        return _result_from_answer(
            question,
            answer,
            use_case_id=state.use_case_id,
            model_version=model_version,
            cost_micros=_cost_micros_for(response.get("usage"), model_version),
            latency_ms=latency_ms,
            request_id=str(request_id) if request_id is not None else None,
        )


__all__ = [
    "JevDecisionProvider",
    "DecisionJevResponseError",
    "DecisionJevAuthError",
    "JEV_PINNED_MODEL_VERSION",
    "resolve_jev_api_key",
]
