"""
JSON-mode orchestration: strict json_schema enforcement, json_object/schema
env-toggles, and LLM-JSON envelope stripping/repair.

Extracted verbatim from ``app/utils/llm_client.py`` as part of issue #582
(mechanical split — no behavior change). The native Ollama ``/api/chat``
schema path lives separately in ``app.llm.providers.ollama``.
"""

import json
import os
import re
from typing import Any, Dict, Optional, Type, Union, List

from pydantic import BaseModel

from ..utils.logger import get_logger

logger = get_logger("agora.llm_client")

JsonSchemaLike = Union[Type[BaseModel], Dict[str, Any]]

_STRICT_UNSUPPORTED_HINTS = (
    "json_schema",
    "unsupported",
    "not supported",
    "unknown response_format",
)


_STRICT_DROP_KEYS = {
    # Reine Pydantic-Meta-Keys, die OpenAI/Google ohnehin ignorieren.
    "title",
    "$schema",
    # Defaults sind im strict-Mode unzulässig — alle Felder müssen vom
    # Modell explizit gefüllt werden (Pydantic-side fängt das via
    # default_factory ab, falls wir das Feld aus dem Schema droppen).
    "default",
    # JSON-Schema-Constraint-Keys, die OpenAI strict ablehnt
    # (https://platform.openai.com/docs/guides/structured-outputs#supported-schemas).
    # ``description`` bleibt erhalten — wird von OpenAI ausgewertet und
    # hilft dem Modell beim Auffuellen.
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "pattern",
    "format",
    "minItems",
    "maxItems",
    "uniqueItems",
    "multipleOf",
}


def _is_unsupported_open_object(node: Any) -> bool:
    """True, wenn *node* (oder ein Zweig in ``anyOf``/``allOf``) ein
    open-ended ``{"type":"object"}`` ohne ``properties`` ist.

    OpenAI strict-mode (und Google's OpenAI-kompat-Wrapper) lehnen
    diese Form als Property-Wert ab. Optional-Felder von Pydantic
    rendern als ``{"anyOf":[{"type":"object"}, {"type":"null"}]}``;
    der Toplevel-Type-Check würde das übersehen, deshalb wird hier
    in ``anyOf``/``allOf`` rekursiert (Gemini-Review HIGH zu PR #545).
    """
    if not isinstance(node, dict):
        return False
    if node.get("type") == "object" and "properties" not in node:
        return True
    for combinator in ("anyOf", "allOf", "oneOf"):
        branches = node.get(combinator)
        if isinstance(branches, list) and any(_is_unsupported_open_object(b) for b in branches):
            return True
    return False


def _enforce_openai_strict_schema(model_or_schema: Any) -> Dict[str, Any]:
    """Pydantic-Schema in das von OpenAI/Google ``json_schema``-strict-Mode
    geforderte Format überführen.

    OpenAI ``response_format={"type":"json_schema","strict":True}`` ist
    rigide:
    1. ``additionalProperties: false`` auf JEDEM ``"type":"object"``-Knoten.
    2. ALLE Property-Keys (auch optionale mit Pydantic-``default=``) müssen
       in ``required[]`` stehen — sonst 400 „'required' is required to be
       supplied and to be an array including every key in properties".
    3. ``$ref``/``$defs`` werden zwar dokumentiert unterstützt, in der
       Praxis aber unzuverlässig akzeptiert. Refs werden hier inline
       ausgelöst, ``$defs`` und Meta-Keys wie ``title``, ``description``,
       ``default``, Constraint-Keys (``minLength`` etc.) werden gestripped,
       weil OpenAI sie im strict-Mode teils ablehnt.

    Eingabe darf ein Pydantic-``BaseModel``-Subclass ODER ein bereits
    fertiges JSON-Schema-Dict sein. Rückgabe ist immer ein neues Dict
    (kein In-Place-Mutate).

    Der Ollama-Pfad (``/api/chat::format=<schema>``) nutzt separat
    ``_flatten_pydantic_schema_for_ollama`` und ist von diesem Helper
    nicht betroffen.
    """
    if isinstance(model_or_schema, type) and issubclass(model_or_schema, BaseModel):
        raw: Dict[str, Any] = model_or_schema.model_json_schema()
    elif isinstance(model_or_schema, dict):
        raw = dict(model_or_schema)
    else:
        raise TypeError(
            f"_enforce_openai_strict_schema expects BaseModel subclass or dict, got {type(model_or_schema).__name__}"
        )
    defs = raw.pop("$defs", {})

    def _walk(node: Any, seen: tuple[str, ...] = ()) -> Any:
        if isinstance(node, dict):
            if "$ref" in node and isinstance(node["$ref"], str) and node["$ref"].startswith("#/$defs/"):
                ref_name = node["$ref"].split("/")[-1]
                if ref_name in seen:
                    return {"type": "object", "additionalProperties": False}
                target = defs.get(ref_name, {})
                merged = {k: v for k, v in node.items() if k != "$ref"}
                for k, v in target.items():
                    merged.setdefault(k, v)
                return _walk(merged, seen + (ref_name,))
            out: Dict[str, Any] = {}
            for k, v in node.items():
                if k in _STRICT_DROP_KEYS:
                    continue
                if k == "properties" and isinstance(v, dict):
                    # Keys unter ``properties`` sind Property-NAMEN, keine
                    # Schema-Metadaten-Keywords. Sie dürfen nie gegen
                    # _STRICT_DROP_KEYS gefiltert werden — sonst verschwindet
                    # eine Property, die zufällig ``title`` (oder ``default``,
                    # ``format`` …) heißt. Die Feld-Schemata (values) werden
                    # weiter gewalkt, dort greift das Metadaten-Stripping normal.
                    out[k] = {pk: _walk(pv, seen) for pk, pv in v.items()}
                    continue
                out[k] = _walk(v, seen)
            if out.get("type") == "object":
                out["additionalProperties"] = False
                props = out.get("properties")
                if isinstance(props, dict):
                    # OpenAI strict-mode lehnt open-ended Objects
                    # (``Dict[str, Any]`` → ``{"type":"object"}`` ohne
                    # ``properties``) als Property-Wert ab, selbst wenn
                    # ``additionalProperties: false`` gesetzt ist. Solche
                    # Felder werden hier rausgenommen — Pydantic-side ist
                    # das harmlos, weil die referenzierten Felder einen
                    # ``default``/``default_factory`` haben (sonst hätten
                    # sie nie als open-ended deklariert werden können).
                    #
                    # Optionale Felder rendern als ``anyOf``/``allOf`` mit
                    # nested-object → rekursiv prüfen (Gemini-Review HIGH
                    # zu PR #545).
                    for pk in list(props):
                        if _is_unsupported_open_object(props[pk]):
                            del props[pk]
                    out["required"] = list(props.keys())
            return out
        if isinstance(node, list):
            return [_walk(item, seen) for item in node]
        return node

    return _walk(raw)


def _env_flag(name: str) -> bool:
    """Return True wenn die Env-Var *name* auf einen truthy-Wert gesetzt ist."""
    return os.environ.get(name, '').lower() in ('1', 'true', 'yes')


def _is_json_object_mode_disabled() -> bool:
    """Return True wenn ``response_format=json_object`` unterdrückt werden soll.

    Wertet aus (in dieser Reihenfolge):
    - ``LLM_DISABLE_JSON_OBJECT_MODE`` (neuer, präziser Name)
    - ``LLM_DISABLE_JSON_MODE`` (Legacy-Alias, Deprecation-Warning wird in
      ``chat_json`` bei Verwendung ausgegeben)
    """
    return _env_flag('LLM_DISABLE_JSON_OBJECT_MODE') or _env_flag('LLM_DISABLE_JSON_MODE')


def _is_json_schema_mode_disabled() -> bool:
    """Return True wenn strict ``response_format=json_schema`` unterdrückt werden soll.

    Gesetzt durch ``LLM_DISABLE_JSON_SCHEMA_MODE=true``. Wenn aktiv und ein
    Schema übergeben wurde, fällt ``chat_json`` auf ``json_object`` + post-hoc
    Pydantic-Validierung zurück.
    """
    return _env_flag('LLM_DISABLE_JSON_SCHEMA_MODE')


def should_disable_openai_json_mode(base_url: Optional[str]) -> bool:
    """Return True wenn ``response_format=json_object`` weggelassen werden soll.

    OpenAI-Reasoning-Modelle (z. B. ``gpt-5.4-nano``) liefern mit
    ``response_format=json_object`` zeitweise leeren ``content`` — der
    Reasoning-Token-Anteil frisst die Antwort auf. Ollama (auch Cloud) und
    Gemini (OpenAI-Adapter) supporten json_object stabil — dort bleibt das
    Verhalten unverändert.

    Trigger:
    - ``base_url`` zeigt auf ``api.openai.com`` UND
    - ``LLM_DISABLE_JSON_OBJECT_MODE`` oder ``LLM_DISABLE_JSON_MODE`` (Legacy)
      in (``1``, ``true``, ``yes``).
    """
    if not base_url or 'api.openai.com' not in base_url.lower():
        return False
    return _is_json_object_mode_disabled()


def _read_active_config_safely() -> Optional[Dict[str, Any]]:
    """Load the active LLM config without raising on missing/invalid file."""
    try:
        from ..api.llm_active import load_active_config
        cfg = load_active_config()
        return cfg or None
    except Exception:  # noqa: BLE001 — never block LLMClient construction
        return None


_CODEFENCE_HEAD_RE = re.compile(r"^```(?:json)?\s*", re.IGNORECASE)
_CODEFENCE_TAIL_RE = re.compile(r"\s*```\s*$")


def _strip_llm_json_envelope(text: str) -> str:
    """Entfernt Codefences + Prosa-Umrahmung um ein LLM-JSON-Payload.

    Issue #556: Gemini-Outputs liefern oft Preambles ("Sure, here is …")
    und/oder trailing prose ("Hope this helps!") um den eigentlichen
    JSON-Block. Der bisherige Pre-Parser entfernte nur Codefences an
    Anfang/Ende und produzierte ``JSONDecodeError`` bei Prosa-Rändern.

    Pipeline:
      1. Strip whitespace.
      2. Codefences entfernen (case-insensitive, ``json``-Label optional).
      3. Outer-Cut: erstes ``{`` oder ``[`` bis zum letzten passenden
         ``}`` oder ``]`` (Typ-Wahl nach dem zuerst auftretenden Bracket).

    Liefert bei fehlender JSON-Struktur den gestrippten Original-String —
    der Caller löst dann ``JSONDecodeError`` aus, was er sowieso tun würde.
    """
    if not text:
        return text
    s = text.strip()
    s = _CODEFENCE_HEAD_RE.sub("", s)
    s = _CODEFENCE_TAIL_RE.sub("", s)
    s = s.strip()
    if not s:
        return s

    first_obj = s.find("{")
    first_arr = s.find("[")
    if first_obj == -1 and first_arr == -1:
        return s

    if first_obj == -1:
        start, end_char = first_arr, "]"
    elif first_arr == -1:
        start, end_char = first_obj, "}"
    elif first_obj < first_arr:
        start, end_char = first_obj, "}"
    else:
        start, end_char = first_arr, "]"

    end = s.rfind(end_char)
    if end == -1 or end < start:
        # Truncated payload mit Preamble (z. B. ``Sure! {"a": 1``):
        # Prosa abschneiden, damit ``_try_repair_truncated_json`` im
        # Caller den unbalanced Rest reparieren kann.
        return s[start:]
    return s[start : end + 1]


def _parse_llm_json(cleaned_response: str) -> Dict[str, Any]:
    """Parse eine bereits envelope-bereinigte LLM-Antwort als JSON-Objekt.

    Gemeinsamer Pfad für alle ``chat_json``-Varianten (nativer Ollama-Schema-Pfad
    und OpenAI-kompatibler Pfad), damit Reparaturversuch und Diagnose überall
    identisch sind. Vorher parste der native Pfad direkt mit ``json.loads`` und
    warf einen nackten ``JSONDecodeError`` ohne jede Einordnung.

    Raises:
        ValueError: Antwort ist auch nach dem Reparaturversuch kein gültiges JSON.
    """
    try:
        return json.loads(cleaned_response)
    except json.JSONDecodeError:
        pass

    repaired = _try_repair_truncated_json(cleaned_response)
    if repaired is not None:
        # Kein max_tokens-Hinweis: chat_json ruft chat() mit
        # require_complete=True auf, eine am Token-Limit abgeschnittene Antwort
        # haette bereits LLMOutputTruncatedError geworfen. Was hier repariert
        # wird, ist unsauberes JSON einer vollstaendigen Antwort.
        logger.warning(
            "LLM JSON war unvollstaendig; per Best-Effort-Reparatur "
            "wiederhergestellt (%d → %d Zeichen). Antwort war laut Provider "
            "vollstaendig — Prompt, Schema oder json_schema-Support pruefen.",
            len(cleaned_response), len(repaired),
        )
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

    preview = cleaned_response[:400]
    tail = cleaned_response[-200:] if len(cleaned_response) > 600 else ""
    raise ValueError(
        "Invalid JSON format from LLM: provider returned a complete "
        "response (finish_reason != 'length') that is not valid JSON "
        f"(len={len(cleaned_response)}). Raising max_tokens will NOT "
        "help — check prompt, schema or provider json_schema support. "
        f"Head: {preview}{'…' if tail else ''}"
        + (f" Tail: …{tail}" if tail else "")
    )


def _try_repair_truncated_json(payload: str) -> Optional[str]:
    """Best-effort recovery for an LLM JSON answer cut off at the output cap.

    Closes any string still open, then balances brackets/braces by counting
    unescaped occurrences. Returns ``None`` when nothing reasonable can be
    rebuilt. The result is fed back through ``json.loads`` by the caller, so
    a wrong guess just falls through to the original error.
    """
    if not payload or payload[0] not in "[{":
        return None
    in_string = False
    escape = False
    stack: List[str] = []
    for ch in payload:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if not stack:
                return None
            stack.pop()
    if not stack and not in_string:
        return None  # already balanced — repair would not help
    # Den Body vollstaendig behalten. Frueher wurde hier auf das letzte
    # Strukturzeichen zurueckgeschnitten, wodurch ``{"a": 1,`` zu ``{}``
    # kollabierte: valides JSON, aber der Inhalt war weg und der Caller
    # hielt das Ergebnis fuer einen Erfolg.
    if in_string:
        # Innerhalb eines offenen Strings NICHT rstrip()en: Whitespace am Ende
        # gehoert zum uebertragenen Wert. ``"Maya arbeitet als `` wuerde sonst
        # sein abschliessendes Leerzeichen verlieren — eine stille Aenderung
        # am Inhalt, die der Repair gerade nicht machen darf.
        truncated = payload
        # Haengender Backslash: der Cap fiel in eine Escape-Sequenz hinein.
        # Bleibt er stehen, escaped er das Anfuehrungszeichen, das wir gerade
        # anhaengen wollen, und der String bleibt offen.
        if escape and truncated.endswith("\\"):
            truncated = truncated[:-1]
        truncated += '"'
    else:
        truncated = payload.rstrip()
    # Drop dangling ``,`` so the closer doesn't produce another parse error.
    truncated = truncated.rstrip().rstrip(",")
    truncated += "".join(reversed(stack))
    # Nur zurueckgeben, was auch parst. Ein Abbruch hinter einem Key-Doppelpunkt
    # oder mitten in einem Zahlen-Literal laesst sich nicht ehrlich schliessen —
    # dann ist ``None`` die richtige Antwort, nicht ein kaputter String.
    try:
        json.loads(truncated)
    except ValueError:
        return None
    return truncated
