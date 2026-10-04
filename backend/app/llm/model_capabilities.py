"""
Modellnamenbasierte Faehigkeitsfragen -- Single Source of Truth (#1766).

Bis #1766 lebten diese Regeln doppelt: im App-Pfad
(``app/llm/providers/openai.py``, genutzt von ``LLMClient``) und im
Simulations-Subprozess (``backend/scripts/_sim_common.py``, genutzt von den
OASIS/CAMEL-Skripten). Jedes neue Modell musste an beiden Stellen getrennt
nachgezogen werden -- der GPT-6-Fehler (#1763) entstand genau so. Beide Pfade
lesen jetzt die Funktionen dieses Moduls; ``openai.py`` und ``_sim_common.py``
behalten ihre bisherigen Funktionsnamen nur als duenne Weiterleitungen.

Eigenschaften dieses Moduls:

- Reine Funktionen ueber den Modellnamen, nur Standardbibliothek. Keine
  Imports aus Flask, Pydantic oder ``app.config``; kein I/O, keine
  Seiteneffekte beim Import.
- KEINE Provider-Erkennung. Ob ein Request an OpenAI geht, entscheidet
  ausschliesslich ``app.llm.providers.registry.detect_provider``; Aufrufer
  verknuepfen diese Entscheidung bei Bedarf selbst mit den Funktionen hier
  (siehe ``providers/openai.py::reasoning_effort_kwargs``).
- Eingaben werden getrimmt und kleingeschrieben; ``None`` und ``""`` sind
  nie eine Reasoning-Familie.

Bewusst GETRENNTE Fragen (nicht vereinheitlichen -- die Antworten weichen fuer
dieselben Modellnamen heute ab, und beide Varianten sind testfixiert):

1. :func:`uses_max_completion_tokens` (App-Pfad) und
   :func:`uses_max_completion_tokens_hyphen_boundary` (Simulations-Pfad)
   beantworten dieselbe Frage, unterscheiden sich aber bei der o-Serie:
   Die App-Variante akzeptiert ``o1``/``o3``/``o4`` mit ``-``- ODER
   ``.``-Grenze (``o1.5-turbo`` -> True), die Simulations-Variante nur mit
   ``-``-Grenze (``o1.5-turbo`` -> False). Vereinheitlichung waere eine
   Verhaltensaenderung der Simulation und ist nicht Teil von #1766.
2. :func:`is_reasoning_family` (App: sendet ``reasoning_effort`` fuer die
   GESAMTE Familie, ``gpt-5`` ohne Minor eingeschlossen; ein 400 wird per
   Retry ohne Parameter abgefangen) und :func:`supports_reasoning_effort_none`
   (Simulation: setzt ``"none"`` nur, wo der Wert garantiert gueltig ist --
   ``gpt-5`` ohne Minor und die o-Serie bekommen ihn bewusst NICHT) sind
   verschiedene Fragen und bleiben verschiedene Funktionen.

Vorweggenommene Familien: ``gpt-7`` .. ``gpt-9`` sind noch nicht veroeffentlicht.
Die Regeln unterstellen fuer sie dasselbe Verhalten wie fuer GPT-6 (Token-Key,
temperature, ``reasoning_effort``) -- ungeprueft gegen reale Modelle. Das ist
heutiges Verhalten beider Pfade und wird hier nur an dieser einen Stelle
festgehalten.
"""

from __future__ import annotations

import re

#: ``gpt-5`` .. ``gpt-9`` mit ``-``/``.``-Grenze oder Stringende
#: (``gpt-6``, ``gpt-6-luna``, ``gpt-6.1-x``; NICHT ``gpt-500``, ``gpt-60``,
#: ``gpt-6o``, ``gpt-4o``). Einstellige Major-Version, siehe Modul-Docstring
#: zu den vorweggenommenen Familien.
_GPT_REASONING_MAJOR_RE = re.compile(r"^gpt-[5-9](?:$|[-.])")

#: Wie oben, aber mit Major/Minor-Capture fuer ``reasoning_effort: "none"``.
_GPT_REASONING_NONE_RE = re.compile(r"^gpt-([5-9])(?:\.(\d+))?(?:-|$)")

#: Reasoning-Modelle der o-Serie.
_O_SERIES_PREFIXES = ("o1", "o3", "o4")


def _normalize(model: str | None) -> str:
    return (model or "").strip().lower()


def is_reasoning_family(model: str | None) -> bool:
    """Whether *model* belongs to the GPT-5..GPT-9-/o1-/o3-/o4-Reasoning-Familie.

    Gemeinsame Erkennungsregel fuer den App-Pfad: Token-Key
    (:func:`uses_max_completion_tokens`), ``temperature``-Quirk
    (:func:`omits_temperature`) und top-level ``reasoning_effort``
    (``providers/openai.py::reasoning_effort_kwargs``).

    ``gpt-5`` bis ``gpt-9`` (einstellige Major-Version, ``-``/``.``-Grenze oder
    Stringende) sowie ``o1``/``o3``/``o4`` (exakt, oder gefolgt von ``-`` bzw.
    ``.``).
    """
    lowered = _normalize(model)
    if _GPT_REASONING_MAJOR_RE.match(lowered):
        return True
    return any(
        lowered == prefix or lowered.startswith((f"{prefix}-", f"{prefix}."))
        for prefix in _O_SERIES_PREFIXES
    )


def uses_max_completion_tokens(model: str | None) -> bool:
    """App-Pfad: *model* verlangt ``max_completion_tokens`` statt ``max_tokens``.

    OpenAI antwortet bei GPT-5..GPT-9 / o1 / o3 / o4 sonst 400 "Unsupported
    parameter: 'max_tokens'". Identisch zu :func:`is_reasoning_family`.
    Siehe :func:`uses_max_completion_tokens_hyphen_boundary` fuer die
    abweichende Simulations-Variante.
    """
    return is_reasoning_family(model)


def omits_temperature(model: str | None) -> bool:
    """*model* akzeptiert nur den Default-``temperature``-Wert (1) (#1096).

    Gleiche Modellfamilie wie :func:`uses_max_completion_tokens` (#1572).
    """
    return is_reasoning_family(model)


def uses_max_completion_tokens_hyphen_boundary(model: str | None) -> bool:
    """Simulations-Pfad: wie :func:`uses_max_completion_tokens`, aber o-Serie nur mit ``-``.

    Die GPT-Regel ist identisch (``gpt-5``..``gpt-9`` mit ``-``/``.``-Grenze
    oder Ende). Fuer ``o1``/``o3``/``o4`` gilt hier nur exakt oder
    ``-``-Grenze: ``o1.5-turbo`` und ``o3.1`` liefern ``False`` (App-Variante:
    ``True``). Testfixierte, bewusst erhaltene Divergenz (#1766).
    """
    lowered = _normalize(model)
    if _GPT_REASONING_MAJOR_RE.match(lowered):
        return True
    return any(
        lowered == prefix or lowered.startswith(f"{prefix}-")
        for prefix in _O_SERIES_PREFIXES
    )


def supports_reasoning_effort_none(model: str | None) -> bool:
    """Simulations-Pfad: *model* akzeptiert garantiert ``reasoning_effort: "none"``.

    GPT-5.x verlangt bei Function-Tools auf ``/v1/chat/completions`` ein
    explizites ``reasoning_effort: "none"`` (sonst 400 "Function tools with
    reasoning_effort are not supported ...").

    **Wichtig:** Das urspruengliche ``gpt-5`` (5.0, ohne Minor-Version) kennt
    ``"none"`` NICHT -- dort sind nur ``minimal``..``high`` gueltig. Erst ab
    Minor-Version 5.1 (``gpt-5.1``, ``gpt-5.6-luna``) ist ``"none"`` gueltig.
    Modelle ohne erkennbare Minor-Version (``gpt-5``, ``gpt-5-mini``) gelten
    als 5.0 und bekommen den Parameter NICHT. Ab Major 6 gilt ``"none"`` auch
    ohne Minor-Version. Die o-Serie bekommt ihn nicht.

    Das ist NICHT :func:`is_reasoning_family`: Der App-Pfad sendet
    ``reasoning_effort`` fuer die ganze Familie und faengt einen 400 per Retry
    ab; der Simulations-Pfad hat keinen Retry und setzt ihn nur, wo er sicher
    gueltig ist.
    """
    match = _GPT_REASONING_NONE_RE.match(_normalize(model))
    if match is None:
        return False
    if int(match.group(1)) >= 6:
        return True
    minor = match.group(2)
    if minor is None:
        return False
    return int(minor) >= 1
