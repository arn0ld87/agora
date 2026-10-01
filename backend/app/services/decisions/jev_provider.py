"""JevDecisionProvider — ``DecisionProvider``-Referenzadapter für TypeSafes
Jev (f005, ADR-0016/0017), gegen ``typesafe-sdk`` 0.7.0.

Gegen die echte API verifiziert (21.09.2026, drei reale Aufrufe mit
Choice/Score/Noul gegen ``https://api.typesafe.ai``), nicht aus der
öffentlichen Doku geraten — das war der Stand vor diesem Task und wich in
mehreren Punkten ab:

- ``questions`` ist ein Dict von Namen auf ``Choice``/``Score``/``Noul``-
  Objekten des SDK, keine Liste von Dicts mit ``id``/``type``.
- ``Score.criteria`` ist eine GEORDNETE Liste von Rubrik-Labels
  (``["niedrig", "mittel", "hoch"]``), kein ``dict[int, str]``. Die
  Antwort ``ScoreAnswer.score`` ist der wahrscheinlichkeitsgewichtete
  Mittelwert über die 0-basierten Indizes der Liste (kann zwischen zwei
  Stufen liegen) — dieser Adapter rundet auf den nächsten Index und bildet
  ihn auf ``[min_stage, max_stage]`` zurück.
- ``NoulAnswer`` hat KEIN eigenes ``confidence``-Feld, nur ``noul``
  (Wahrscheinlichkeit für Ja). Dieser Adapter leitet eine Confidence als
  Abstand von 0,5 ab (``2 * abs(noul - 0.5)``) — eine Antwort nahe 0
  oder 1 ist sicher, eine nahe 0,5 ist es nicht. Das ist eine eigene
  Interpretation, keine Anbieterangabe; dokumentiert, damit sie im
  Benchmark hinterfragt werden kann.
- Response ist ein ``SystemOneResponse``-Pydantic-Objekt (``.model``,
  ``.usage.input_tokens/.output_tokens``, ``.answers``, ``.request_id``,
  Convenience-Dicts ``.nouls``/``.choices``/``.scores``), kein rohes Dict.

``TypeSafeClient`` bringt eine eigene, konfigurierbare ``RetryPolicy``
mit (Default aktiv). Dieser Adapter wrappt den Aufruf deshalb NICHT in
eine zweite Retry-Schleife — die Anbieterdoku warnt ausdrücklich vor
verschachtelten Retry-Schleifen. Er ruft genau einmal auf; SDK-Exceptions
(``TypeSafeError`` für Client-seitige Fehler wie leere Fragen,
``TypeSafeAPIError`` mit ``.status``/``.request_id`` für HTTP-Fehler wie
401/429) laufen unverändert zum Aufrufer durch, der über die
Fallback-Kette entscheidet.

Kosten: über die bestehende ``PricingRegistry`` (Issue #764) aus
``usage``-Tokenzahlen berechnet — keine zweite Preislogik neben der
einen Preisquelle des Systems.

Secret-Management: :func:`resolve_jev_api_key` liest den Key über den
bestehenden verschlüsselten Provider-Secret-Store (``AGORA_SECRET_KEY``-
Fernet-Master, dieselbe Route wie andere Provider-Secrets laut
Architektur-SSoT). :func:`build_jev_client` baut daraus den echten
Client — vorher (Task ``jev-adapter``) fehlte diese Fabrik bewusst, weil
kein verifizierter Zugang bestand; der Benchmark-Task hat ihn.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, cast

from typesafe_sdk import Choice, JSONContent, Noul, Score, TypeSafeClient

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
#: gepinnt statt "jev-latest"/"jev-preview" (SDK-Default) — eine unbemerkte
#: Modelländerung zwischen Kalibration und Betrieb würde die kalibrierten
#: Fehlerraten sonst unsichtbar verschieben.
JEV_PINNED_MODEL_VERSION = "jev-1.13.0"

#: Fester Fragenname für den Einzelfrage-Aufruf dieses Ports (der Port
#: nimmt laut decision_contract.py genau eine Frage pro Aufruf entgegen,
#: Jevs eigene API ist dennoch namensbasiert-mehrfrageförmig). Kein
#: Nutzerinhalt, kein aus State abgeleiteter Wert.
_QUESTION_NAME = "decision"

#: Generische Anweisungstexte je Frageform — dieselbe Rolle wie
#: ``llm_provider._build_prompt``: der eigentliche Inhalt steht in
#: ``state.state``, hier steht nur die Aufgabenbeschreibung.
_CHOICE_INSTRUCTIONS = "Wähle die zutreffendste der angegebenen Kategorien für den State."
_SCORE_INSTRUCTIONS = "Bewerte den State auf der angegebenen Rubrik."
_NOUL_INSTRUCTIONS = "Beantworte mit der Wahrscheinlichkeit, dass die Aussage im State zutrifft."

#: Öffentliche Secret-Ref-Konstante für den Jev-Key im Provider-Secret-Store.
#: Aufrufer außerhalb dieses Moduls (z. B. ``scripts/bind_decision_secret.py``)
#: importieren diese Konstante statt den String ``"jev"`` ein zweites Mal zu
#: pflegen — zwei Kopien liefen sonst auseinander, sobald die Ref sich ändert.
JEV_SECRET_REF = "jev"  # noqa: S105 - Store-Schlüsselname, kein Secret

#: Schlüssel, unter dem der Jev-API-Key im Provider-Secret-Store liegt.
_SECRET_REF = JEV_SECRET_REF


def resolve_jev_api_key() -> str | None:
    """Liest den Jev-API-Key aus dem bestehenden verschlüsselten
    Provider-Secret-Store. ``None`` heißt: kein Key gebunden — ein
    sichtbarer Konfigurationszustand, keine Ausnahme, weil das Fehlen
    außerhalb eines aktiven Piloten der Normalfall ist (Flag-off/Default)."""
    return get_bound_store_api_key(_SECRET_REF)


def build_jev_client(
    *, model_version: str = JEV_PINNED_MODEL_VERSION, timeout: float = 30.0
) -> TypeSafeClient:
    """Baut den echten ``TypeSafeClient`` mit dem im Secret-Store
    hinterlegten Key. Wirft laut, wenn kein Key gebunden ist — ein
    Aufrufer, der einen Jev-Client anfordert, aber keinen Key hinterlegt
    hat, hat einen Konfigurationsfehler, keinen Laufzeitfall.

    Retry bleibt beim SDK-Default (siehe Moduldocstring); dieser Adapter
    konfiguriert hier keine eigene ``RetryPolicy``, weil "absolute
    Minimal-Konfiguration" für den Benchmark-Piloten reicht — eine
    use-case-spezifische Anpassung ist eine spätere, eigene Entscheidung.
    """
    api_key = resolve_jev_api_key()
    if not api_key:
        raise RuntimeError(
            f"Kein Jev-API-Key im Provider-Secret-Store unter '{_SECRET_REF}' gebunden."
        )
    return TypeSafeClient(api_key=api_key, model=model_version, timeout=timeout)


class DecisionJevResponseError(RuntimeError):
    """Jevs Antwort erfüllte das angeforderte Schema nicht sinnvoll — fehlende
    Antwort für die gestellte Frage oder eine Kategorie außerhalb der
    gesendeten Optionen. Wird laut geworfen statt eine unvollständige
    Antwort als vollständige zu behandeln: das SDK kann laut Anbieterdoku
    unbekannte Antwortarten warnend überspringen, AGORA lehnt das selbst ab."""


def _shape(value: Any) -> str:
    """Strukturbeschreibung statt Inhalt.

    Fehlermeldungen dieses Adapters landen über die Exception-Kette im Log.
    Eine Antwort eines externen Dienstes kann Teile der Anfrage spiegeln,
    und die Anfrage trägt den Entscheidungskontext — Telemetrie darf laut
    ADR-0016 nur den ``context_hash`` referenzieren, nie den Klartext.
    """
    if isinstance(value, dict):
        return f"dict(keys={sorted(str(key) for key in value)})"
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


def _question_for(question: DecisionQuestion) -> Choice | Score | Noul:
    """Baut das SDK-eigene Fragenobjekt für ``_QUESTION_NAME``."""
    if isinstance(question, ChoiceQuestion):
        return Choice(
            instructions=_CHOICE_INSTRUCTIONS,
            criteria={option: None for option in question.options},
        )
    if isinstance(question, ScoreQuestion):
        criteria = [question.legend[stage] for stage in range(question.min_stage, question.max_stage + 1)]
        return Score(instructions=_SCORE_INSTRUCTIONS, criteria=criteria)
    if isinstance(question, NoulQuestion):
        return Noul(instructions=_NOUL_INSTRUCTIONS)
    raise TypeError(f"JevDecisionProvider: unbekannte Frageform {type(question).__name__}")


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
    unbekannter Preis wird niemals als 0 ausgegeben.
    """
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    if input_tokens is None or output_tokens is None:
        return None
    quote = get_pricing_registry().resolve("jev", model_version)
    return quote.cost_micros(int(input_tokens), int(output_tokens))


def _result_from_response(
    question: DecisionQuestion,
    response: Any,
    *,
    use_case_id: str,
    latency_ms: int,
) -> DecisionResult:
    model_version = str(response.model)
    request_id = str(response.request_id) if response.request_id else None
    cost_micros = _cost_micros_for(response.usage, model_version)

    if isinstance(question, ChoiceQuestion):
        answer = response.choices.get(_QUESTION_NAME)
        if answer is None:
            raise DecisionJevResponseError(
                f"Jev-Antwort enthält keine Choice-Antwort für '{_QUESTION_NAME}': "
                f"{_shape(response.answers)}"
            )
        if answer.choice not in question.options:
            raise DecisionJevResponseError(
                f"Jev-Antwort {_digest(answer.choice)} liegt außerhalb der gesendeten "
                f"Optionen {question.options!r}."
            )
        return DecisionResult(
            use_case_id=use_case_id,
            provider="jev",
            answer=answer.choice,
            distribution=dict(answer.probabilities),
            confidence=float(answer.confidence),
            model_version=model_version,
            request_id=request_id,
            cost_micros=cost_micros,
            latency_ms=latency_ms,
            shadow=False,
        )
    if isinstance(question, ScoreQuestion):
        answer = response.scores.get(_QUESTION_NAME)
        if answer is None:
            raise DecisionJevResponseError(
                f"Jev-Antwort enthält keine Score-Antwort für '{_QUESTION_NAME}': "
                f"{_shape(response.answers)}"
            )
        # answer.score ist der wahrscheinlichkeitsgewichtete Mittelwert über
        # 0-basierte Rubrik-Indizes (kann zwischen zwei Stufen liegen,
        # siehe Moduldocstring) — gerundet und auf [min_stage, max_stage]
        # zurückgebildet, weil dieser Vertrag eine diskrete Stufe verlangt.
        stage_count = question.max_stage - question.min_stage + 1
        rounded_index = max(0, min(stage_count - 1, round(answer.score)))
        stage = question.min_stage + rounded_index
        return DecisionResult(
            use_case_id=use_case_id,
            provider="jev",
            answer=stage,
            confidence=float(answer.confidence),
            model_version=model_version,
            request_id=request_id,
            cost_micros=cost_micros,
            latency_ms=latency_ms,
            shadow=False,
        )
    # NoulQuestion
    answer = response.nouls.get(_QUESTION_NAME)
    if answer is None:
        raise DecisionJevResponseError(
            f"Jev-Antwort enthält keine Noul-Antwort für '{_QUESTION_NAME}': "
            f"{_shape(response.answers)}"
        )
    # Kein eigenes confidence-Feld bei Noul (siehe Moduldocstring) — Abstand
    # von 0,5 als Ersatzmaß: nahe 0/1 ist sicher, nahe 0,5 ist es nicht.
    confidence = 2 * abs(answer.noul - 0.5)
    return DecisionResult(
        use_case_id=use_case_id,
        provider="jev",
        answer=None,
        probability_yes=float(answer.noul),
        confidence=float(confidence),
        model_version=model_version,
        request_id=request_id,
        cost_micros=cost_micros,
        latency_ms=latency_ms,
        shadow=False,
    )


class JevDecisionProvider:
    """Siehe Moduldocstring. ``client`` ist ein bereits konstruierter
    ``TypeSafeClient`` (siehe :func:`build_jev_client`) — dieser Adapter
    baut keinen eigenen und wrappt seinen Aufruf nicht in eigene Retries."""

    def __init__(self, client: TypeSafeClient) -> None:
        self._client = client

    def decide(self, state: DecisionState, question: DecisionQuestion) -> DecisionResult:
        t0 = time.monotonic()
        # Kein try/except hier: der Client wirft (TypeSafeError,
        # TypeSafeAPIError mit .status/.request_id) und dieser Adapter
        # reicht das unverändert an den Aufrufer weiter — siehe
        # Moduldocstring zu verschachtelten Retry-Schleifen.
        response = self._client.system_one(
            # DecisionState.state ist bewusst als `str | dict[str, object] |
            # list[object]` typisiert (Vertrag, gilt für alle Provider), das
            # SDK verlangt das engere `JSONContent`. Ein Aufrufer, der hier
            # nicht-JSON-serialisierbare Objekte einfüllt, bekommt den Fehler
            # zur Laufzeit vom SDK/HTTP-Client — dieser Cast erweitert den
            # Vertrag nicht, er löst nur den mypy-Konflikt zwischen zwei
            # bewusst unterschiedlich engen Signaturen auf.
            state=cast(JSONContent, state.state),
            questions={_QUESTION_NAME: _question_for(question)},
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        return _result_from_response(
            question,
            response,
            use_case_id=state.use_case_id,
            latency_ms=latency_ms,
        )


__all__ = [
    "JevDecisionProvider",
    "DecisionJevResponseError",
    "JEV_PINNED_MODEL_VERSION",
    "build_jev_client",
    "resolve_jev_api_key",
]
