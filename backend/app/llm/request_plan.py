"""Bauen und Durchbringen eines Provider-Requests (Issue #1225).

``LLMClient.chat`` hat beides in einer 315-Zeilen-Methode gemacht: den Request
zusammensetzen und ihn gegen bekannte Provider-400er durchbringen. Beides lag
dort nicht allein — dasselbe Shaping stand nochmal in ``describe_image`` und in
``tool_calls._chat_with_tools``, dieselbe Fallback-Kaskade nochmal in beiden.
Jede Kopie hatte eine andere Lücke: der Tools-Pfad kennt den
``temperature``-Quirk aus #1096 nicht, der Vision-Pfad kennt MiniMax nicht.
Lücken dieser Art entstehen nicht durch Absicht, sondern dadurch, dass beim
Nachziehen eines Quirks eine der Kopien übersehen wird.

Hier stehen die beiden Hälften getrennt und je genau einmal:

``build_request``
    Rein, ohne I/O. Setzt ``temperature`` nur, wenn das Modell einen
    abweichenden Wert überhaupt akzeptiert, und wählt zwischen ``max_tokens``
    und ``max_completion_tokens``. Was der Aufruf über seine Umgebung braucht,
    kommt über ``RequestOptions`` herein — Seams mit Default-Bindung an die
    echten Implementierungen, dasselbe Options-Muster wie ``SectionContext``
    in ``app/services/report_agent/section_pipeline.py`` (#1212). Ein Test
    setzt Fakes in die Options, statt Modulnamen zu patchen.

``thinking_extra_body``
    Der provider-spezifische ``extra_body``: Ollamas ``options.num_ctx`` +
    ``think``, MiniMax' ``thinking.type``. Ebenfalls rein — welcher Provider
    vorliegt, entscheidet der Aufrufer und reicht es herein.

``execute``
    Die Fehlerbehandlung, ohne Shaping. Wickelt den Attempt von innen nach
    außen in je einen ``Quirk``; jeder versucht genau einmal neu, mit dem
    kwargs-Stand, den er selbst gesehen hat.

Dieses Modul trifft **keine** Provider-Detection. ``providers/registry.py::
detect_provider`` bleibt dafür Single Source of Truth; hier kommt das Ergebnis
als Parameter herein.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..utils.logger import get_logger
from .providers import openai as _provider_openai

logger = get_logger("agora.llm_client")


# ---------------------------------------------------------------------------
# Bauen
# ---------------------------------------------------------------------------


def _default_completion_token_key(model: str) -> str:
    """``max_completion_tokens`` oder ``max_tokens``, je nach Modellfamilie."""
    return (
        "max_completion_tokens"
        if _provider_openai.uses_max_completion_tokens(model)
        else "max_tokens"
    )


@dataclass(frozen=True)
class RequestOptions:
    """Was ``build_request`` über die Umgebung braucht.

    Die Felder sind Seams: im Betrieb zeigen sie auf die echten
    Provider-Heuristiken, im Test auf Fakes. Damit ist ``build_request`` ohne
    ``patch()`` auf Modulnamen prüfbar.
    """

    omits_temperature: Callable[[str], bool] = _provider_openai.omits_temperature
    completion_token_key: Callable[[str], str] = _default_completion_token_key


DEFAULT_REQUEST_OPTIONS = RequestOptions()


@dataclass(frozen=True)
class RequestPlan:
    """Der fertige Request — genau das, was an ``completions.create`` geht."""

    kwargs: Dict[str, Any] = field(default_factory=dict)


def build_request(
    *,
    model: Optional[str],
    messages: List[Dict[str, Any]],
    temperature: float,
    max_tokens: int,
    response_format: Optional[Dict[str, Any]] = None,
    extra_body: Optional[Dict[str, Any]] = None,
    stream: bool = False,
    extra: Optional[Dict[str, Any]] = None,
    options: RequestOptions = DEFAULT_REQUEST_OPTIONS,
) -> RequestPlan:
    """Baut die ``create()``-kwargs und wendet dabei die Shaping-Quirks an.

    Parameters:
        model: Zielmodell. Bestimmt auch, welche Quirks greifen.
        messages: Nachrichten in OpenAI-Form.
        temperature: Gewünschte Temperatur. Landet **nicht** im Request, wenn
            das Modell laut ``options.omits_temperature`` nur den Default
            akzeptiert (#1096) — sonst antwortet die GPT-5-/o-Reasoning-Familie
            400 ``unsupported_value``.
        max_tokens: Ausgabelimit. Der Schlüsselname kommt aus
            ``options.completion_token_key``.
        response_format: Optionales ``response_format``, unverändert übernommen.
        extra_body: Optionaler Provider-``extra_body``, üblicherweise aus
            :func:`thinking_extra_body`.
        stream: Wenn ``True``, wird ``stream=True`` gesetzt. Bei ``False``
            bleibt der Schlüssel weg statt auf ``False`` zu stehen — der
            Request soll aussehen wie vorher.
        extra: Weitere kwargs, die dieser Aufrufpfad braucht (``tools``,
            ``tool_choice``).
        options: Provider-Seams.

    Returns:
        RequestPlan: Der fertige Request.
    """
    target_model = model or ""
    kwargs: Dict[str, Any] = {"model": model, "messages": messages}
    if not options.omits_temperature(target_model):
        kwargs["temperature"] = temperature
    kwargs[options.completion_token_key(target_model)] = max_tokens
    if response_format:
        kwargs["response_format"] = response_format
    if extra_body:
        kwargs["extra_body"] = extra_body
    if extra:
        kwargs.update(extra)
    if stream:
        kwargs["stream"] = True
    return RequestPlan(kwargs=kwargs)


def thinking_extra_body(
    *,
    ollama: bool,
    minimax: bool,
    num_ctx: Optional[int] = None,
    think: bool = False,
) -> Optional[Dict[str, Any]]:
    """Der provider-spezifische ``extra_body`` für Reasoning und Kontextfenster.

    Ollama bekommt ``options.num_ctx`` (nur wenn gesetzt — sonst gilt der
    Serverdefault) und immer ein ``think``-Flag. MiniMax bekommt sein eigenes
    ``thinking``-Feld laut Spec. Alles andere bekommt keinen ``extra_body``.

    Welcher Provider vorliegt, entscheidet der Aufrufer: die Detection ist
    ``providers/registry.py``-Sache, nicht Sache dieses Moduls.
    """
    if ollama:
        body: Dict[str, Any] = {}
        if num_ctx:
            body["options"] = {"num_ctx": num_ctx}
        body["think"] = think
        return body
    if minimax:
        return {"thinking": {"type": "adaptive" if think else "disabled"}}
    return None


# ---------------------------------------------------------------------------
# Durchbringen
# ---------------------------------------------------------------------------


def _drop_temperature(kwargs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Kopie ohne ``temperature``, oder ``None`` wenn keins gesetzt war."""
    if "temperature" not in kwargs:
        return None
    dropped = dict(kwargs)
    dropped.pop("temperature", None)
    return dropped


@dataclass(frozen=True)
class Quirk:
    """Ein Provider-400 und die eine Umschreibung, die ihn behebt.

    ``matches`` entscheidet, ob dieser Quirk die Ursache ist; ``rewrite``
    liefert den korrigierten Request oder ``None``, wenn an diesem Request
    nichts zu korrigieren ist (dann propagiert der Fehler unverändert).
    """

    name: str
    remedy: str
    matches: Callable[[Exception], bool]
    rewrite: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]


TOKEN_KEY_QUIRK = Quirk(
    name="token-limit key",
    remedy="swapped key",
    matches=_provider_openai.is_token_key_400,
    rewrite=_provider_openai.swap_token_kwargs,
)
"""400 wegen ``max_tokens`` / ``max_completion_tokens``-Inkompatibilität.

``uses_max_completion_tokens`` deckt die bekannten Familien proaktiv ab; dieser
Fallback ist das Netz für neue Modelle und Proxies, die wir noch nicht kennen.
"""

TEMPERATURE_QUIRK = Quirk(
    name="temperature param",
    remedy="temperature dropped",
    matches=_provider_openai.is_temperature_400,
    rewrite=_drop_temperature,
)
"""400 wegen eines nicht unterstützten ``temperature``-Werts (#1096).

``omits_temperature`` fängt die bekannten Reasoning-Familien schon beim Bauen
ab; hier bleibt das Netz für die, die noch nicht in der Heuristik stehen.
"""


def _with_quirk[T](
    inner: Callable[[Dict[str, Any]], T],
    quirk: Quirk,
    label: Optional[str],
) -> Callable[[Dict[str, Any]], T]:
    """Legt *quirk* um *inner*: bei Treffer genau ein Neuversuch."""

    def wrapped(kwargs: Dict[str, Any]) -> T:
        try:
            return inner(kwargs)
        except Exception as exc:  # noqa: BLE001 — wir filtern selbst
            if not quirk.matches(exc):
                raise
            rewritten = quirk.rewrite(kwargs)
            if rewritten is None:
                raise
            logger.warning(
                "LLM 400 on %s%s — retrying once with %s (model=%s, msg=%s)",
                quirk.name,
                f" ({label})" if label else "",
                quirk.remedy,
                kwargs.get("model"),
                str(exc)[:200],
            )
            return inner(rewritten)

    return wrapped


def execute[T](
    plan: RequestPlan,
    attempt: Callable[[Dict[str, Any]], T],
    *,
    quirks: Sequence[Quirk] = (),
    label: Optional[str] = None,
) -> T:
    """Führt *attempt* mit dem Request aus *plan* aus, abgesichert durch *quirks*.

    ``attempt`` bekommt die kwargs und macht damit genau einen physischen
    Versuch — inklusive dessen, was dieser Aufrufpfad an Transient-Retry,
    Budget-Gate und Telemetrie um den Call legt. Dieses Modul kennt davon
    nichts; es entscheidet nur, ob ein 400 einen korrigierten zweiten Versuch
    wert ist.

    *quirks* steht von innen nach außen: ``quirks[0]`` sieht den Fehler zuerst,
    ``quirks[-1]`` zuletzt. Jeder Quirk versucht genau einmal neu, und zwar mit
    dem kwargs-Stand, den er selbst übergeben bekommen hat — ein äußerer Quirk
    setzt also auf dem Originalrequest auf, nicht auf der Korrektur eines
    inneren, und der innere steht dem korrigierten Lauf wieder zur Verfügung.

    *label* landet im Warn-Log und benennt den Aufrufpfad (``"vision"``,
    ``"tools"``), damit die Retries in den Logs unterscheidbar bleiben.
    """
    call = attempt
    for quirk in quirks:
        call = _with_quirk(call, quirk, label)
    return call(plan.kwargs)
