"""
LLM Client Wrapper
Unified OpenAI format API calls
Supports Ollama num_ctx parameter to prevent prompt truncation
"""

import json
import os
import re
import time as _time_mod
from functools import lru_cache
from typing import TYPE_CHECKING, Literal, Optional, Dict, Any, List, Type, Union
from openai import OpenAI
from pydantic import BaseModel

if TYPE_CHECKING:
    from ..contracts.llm_profile_contract import LlmProfile

from ..config import Config
from ..contracts.llm_routing_contract import ResolvedRoute, ReasoningEffort
from ..llm.providers.ollama import build_ollama_extra_body
from ..llm.providers.openai import uses_max_completion_tokens
from ..llm.providers.registry import detect_provider
from .logger import get_logger
from .retry import llm_call_with_retry

logger = get_logger("agora.llm_client")

JsonSchemaLike = Union[Type[BaseModel], Dict[str, Any]]

# Provider error messages that indicate strict json_schema is not supported.
# Sub-Slice 05.5 — Cloud-aware num_ctx-Heuristik.
#
# Frontend wählt Cloud-Modelle wie qwen3-coder-next:cloud (256 k) oder
# gemini-3-pro:cloud (1 M). Der bisherige hardcoded Default
# OLLAMA_NUM_CTX=8192 kappte diese Context-Windows in chat()/describe_image()/
# _chat_with_tools()/_ollama_chat_with_schema().
#
# Tabelle SYNCED mit backend/scripts/agent_tools.py::_MODEL_CONTEXT_HEURISTICS
# (TODO: in shared module extrahieren — heute Zirkular-Import-Sperre durch
# scripts → app.config). Bei Änderungen beide Stellen anfassen.
_MODEL_CONTEXT_HEURISTICS: tuple[tuple[str, int], ...] = (
    ("gemini-3", 1_048_576),       # Gemini 3 Pro / Flash: ~1M Tokens
    ("gemini-2.5", 1_048_576),
    ("gemini-2", 1_048_576),
    ("deepseek-v3", 131_072),      # DeepSeek-V3 / V3.1 / V3.2: 128k
    ("deepseek-v4", 1_048_576),    # DeepSeek-V4 (laut Vendor-Stand 2026)
    ("deepseek-r1", 131_072),
    ("qwen3-coder", 262_144),      # Qwen3-Coder / -Coder-Next: 256k
    ("qwen3", 131_072),
    ("qwen2.5", 131_072),
    ("llama-3.3", 131_072),
    ("llama3.3", 131_072),
    ("llama-3.1", 131_072),
    ("gpt-oss", 131_072),          # gpt-oss-Cloud-Familie: 128k
    ("gpt-4.1", 1_048_576),
    ("gpt-4o", 131_072),
    ("claude-opus-4", 200_000),
    ("claude-sonnet-4", 200_000),
    ("claude-haiku-4", 200_000),
    ("nemotron", 131_072),         # nvidia nemotron-3-nano:30b u. ä.
)


def heuristic_num_ctx_for_model(model_name: str) -> Optional[int]:
    """Best-effort Substring-Match für bekannte Modellfamilien.

    Liefert None, wenn das Modell unbekannt ist — Caller fällt dann auf
    OLLAMA_NUM_CTX (legacy) zurück und emittiert ein WARNING (einmalig pro
    Modell, dedupliziert via lru_cache auf _warn_legacy_fallback_once).

    Um den Warning für ein unbekanntes Modell zu unterdrücken, trage es entweder
    in _MODEL_CONTEXT_HEURISTICS ein oder setze LLM_MODEL_CONTEXT_LIMITS_JSON.
    """
    if not model_name:
        return None
    needle = model_name.lower()
    for prefix, limit in _MODEL_CONTEXT_HEURISTICS:
        if prefix in needle:
            return limit
    return None


@lru_cache(maxsize=64)
def _warn_legacy_fallback_once(model_name: str, fallback: int) -> None:
    """Emit a WARNING exactly once per unknown model name (lru_cache deduplicates).

    Called only when _resolve_num_ctx reaches the legacy OLLAMA_NUM_CTX / 8192
    fallback, i.e. no heuristic, no per-model env map, no LLM_CONTEXT_LIMIT, and
    no explicit provider_options matched. The cache prevents log spam when the
    same unknown model is used repeatedly within a process lifetime.
    """
    logger.warning(
        "llm_client._resolve_num_ctx: no heuristic for model=%r, "
        "falling back to %d. Set LLM_MODEL_CONTEXT_LIMITS_JSON to override.",
        model_name,
        fallback,
    )


def _resolve_num_ctx(
    model_name: Optional[str],
    provider_options_num_ctx: Any,
) -> int:
    """Resolve num_ctx mit Override-Hierarchie.

    1. provider_options.num_ctx (explizit per ResolvedRoute, höchste Prio)
    2. LLM_MODEL_CONTEXT_LIMITS_JSON (per-Modell-Map via env)
    3. Heuristik-Tabelle (Modell-Familie-Default)
    4. LLM_CONTEXT_LIMIT (Global-Override, sofern höher als Heuristik)
    5. OLLAMA_NUM_CTX env oder 8192 (Legacy-Fallback) — emits WARNING once per model
    """
    if provider_options_num_ctx is not None:
        try:
            return int(provider_options_num_ctx)
        except (TypeError, ValueError):
            pass

    raw_per_model = os.environ.get("LLM_MODEL_CONTEXT_LIMITS_JSON", "").strip()
    if raw_per_model and model_name:
        try:
            parsed = json.loads(raw_per_model)
            if isinstance(parsed, dict) and model_name in parsed:
                return int(parsed[model_name])
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    heuristic = heuristic_num_ctx_for_model(model_name or "")
    global_env = os.environ.get("LLM_CONTEXT_LIMIT")
    global_limit: Optional[int]
    try:
        global_limit = int(global_env) if global_env else None
    except ValueError:
        global_limit = None

    if heuristic is not None and global_limit is not None:
        return max(heuristic, global_limit)
    if heuristic is not None:
        return heuristic
    if global_limit is not None:
        return global_limit

    try:
        fallback = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))
    except ValueError:
        fallback = 8192
    if model_name:
        _warn_legacy_fallback_once(model_name, fallback)
    return fallback


_STRICT_UNSUPPORTED_HINTS = (
    "json_schema",
    "unsupported",
    "not supported",
    "unknown response_format",
)


def _flatten_pydantic_schema_for_ollama(model_cls: type[BaseModel]) -> Dict[str, Any]:
    """Pydantic-JSON-Schema inline-resolved fuer Ollamas /api/chat::format-Feld.

    Ollama akzeptiert das Schema-Objekt als JSON-Schema, kommt aber mit
    ``$defs``/``$ref`` nicht zuverlaessig klar. Diese Funktion macht zwei Dinge:

    1. ``$ref``-Verweise werden inline durch das Ziel-Schema aus ``$defs`` ersetzt
       (rekursiv, mit Zyklus-Stop).
    2. Schema-Meta-Keys werden entfernt: ``title``, ``$schema``, ``$defs``,
       ``description`` auf top-level (Property-``description``s bleiben — die helfen
       dem Modell beim Auffuellen).

    Returns das geflattete Schema-Dict, ready fuer POST /api/chat::format.
    """
    raw = model_cls.model_json_schema()
    defs = raw.pop("$defs", {})

    def _resolve(node: Any, seen: tuple[str, ...] = ()) -> Any:
        if isinstance(node, dict):
            if "$ref" in node and node["$ref"].startswith("#/$defs/"):
                ref_name = node["$ref"].split("/")[-1]
                if ref_name in seen:
                    return {"type": "object"}  # zyklisch — bewusst abkuerzen
                target = defs.get(ref_name, {})
                merged = {k: v for k, v in node.items() if k != "$ref"}
                merged.update(_resolve(target, seen + (ref_name,)))
                return merged
            return {k: _resolve(v, seen) for k, v in node.items() if k not in {"title", "$schema"}}
        if isinstance(node, list):
            return [_resolve(item, seen) for item in node]
        return node

    flattened = _resolve(raw)
    flattened.pop("title", None)
    flattened.pop("$schema", None)
    return flattened


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
    last_struct_pos = -1
    for idx, ch in enumerate(payload):
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
            last_struct_pos = idx
        elif ch in "}]":
            if not stack:
                return None
            stack.pop()
            last_struct_pos = idx
    if not stack and not in_string:
        return None  # already balanced — repair would not help
    truncated = payload[: last_struct_pos + 1] if last_struct_pos >= 0 else payload
    if in_string:
        truncated += '"'
    # Drop dangling ``,`` so the closer doesn't produce another parse error.
    truncated = truncated.rstrip().rstrip(",")
    truncated += "".join(reversed(stack))
    return truncated


class LLMClient:
    """LLM Client"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 300.0,
        reasoning_effort: Optional[ReasoningEffort] = None,
        provider_options: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
        routing_version: Optional[int] = None,
        route_stage: Optional[str] = None,
        route_provider_id: Optional[str] = None,
        use_active_config: bool = True,
        api_key_source: Optional[str] = None,
    ):
        # When no explicit model is set, fall back to the user's active
        # provider/model selection (Settings → LLM-Auswahl). Falls back to
        # Config.* if no active config exists. Resolves api_key+base_url via
        # SecretResolver/Provider-Registry analogous to from_route().
        # ``api_key_source`` ist eine Audit-Annotation für das einmalige
        # Init-Log am Ende dieses Konstruktors. Track 1c (Pure-Gosling).
        resolved_source: Optional[str] = api_key_source if api_key else None
        active_provider_id: Optional[str] = None
        if use_active_config and model is None:
            active = _read_active_config_safely()
            if active:
                active_provider_id = active.get("provider_id")
                active_model = active.get("model")
                active_base = active.get("base_url")
                if active_model:
                    model = active_model
                if active_base and not base_url:
                    base_url = active_base
                if active_provider_id and not api_key:
                    try:
                        from ..services.llm_provider_registry import LlmProviderRegistry
                        from ..services.secret_resolver import SecretResolver
                        registry = LlmProviderRegistry()
                        descriptor = next(
                            (p for p in registry.get_providers() if p.id == active_provider_id),
                            None,
                        )
                        if descriptor is not None:
                            if not base_url:
                                base_url = descriptor.base_url
                            resolver = SecretResolver()
                            api_key = resolver.get_api_key(active_provider_id, descriptor.type)
                            if api_key:
                                resolved_source = resolver.last_source
                    except Exception as exc:  # noqa: BLE001 — fall back to Config defaults
                        logger.warning(
                            "Failed to resolve active LLM config (provider=%s): %s",
                            active_provider_id,
                            exc,
                        )

        if api_key:
            self.api_key = api_key
            # resolved_source bleibt erhalten (passed_in oder vom Resolver)
        else:
            self.api_key = Config.LLM_API_KEY
            if self.api_key:
                resolved_source = "config_fallback"
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME
        self.reasoning_effort = reasoning_effort or "none"
        self.provider_options = provider_options or {}
        self.run_id = run_id or os.environ.get("AGORA_RUN_ID")
        self.routing_version = routing_version
        self.route_stage = route_stage
        self.route_provider_id = route_provider_id

        if not self.api_key:
            raise ValueError("LLM_API_KEY not configured")

        # Track 1c Audit-Log: einmalig pro LLMClient-Init. Niemals den Key-Wert
        # selbst loggen — nur die Quelle (session/store/env:NAME/config_fallback/
        # passed_in/unknown). Provider-Erkennung priorisiert ``active_provider_id``
        # vor ``route_provider_id``, damit die laufende Session-Auswahl Vorrang hat.
        self._api_key_source = resolved_source or "unknown"
        # Gemini-Review (security-medium) zu PR #559: ``base_url`` kann in
        # Edge-Cases (Azure-OpenAI-Query-Param, Userinfo) Secret-Material
        # tragen. SecretResolver.sanitize_url strippt userinfo+query+fragment
        # vor dem Log, ohne den Hostname zu maskieren.
        from ..services.secret_resolver import SecretResolver as _UrlSanitizer
        logger.info(
            "LLMClient initialized provider_id=%s model=%s base_url=%s api_key_source=%s",
            active_provider_id or route_provider_id or "unknown",
            self.model,
            _UrlSanitizer().sanitize_url(self.base_url) if self.base_url else None,
            self._api_key_source,
        )

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout,
        )

        # Ollama context window size — prevents prompt truncation.
        # Sub-Slice 05.5: Cloud-aware Heuristik statt fix OLLAMA_NUM_CTX=8192.
        # Vorher kappte 8192 Cloud-Modelle wie gemini-3:cloud (1M) oder
        # qwen3-coder-next:cloud (256k) auf einen Bruchteil ihrer Kapazität.
        self._num_ctx = _resolve_num_ctx(
            model_name=self.model,
            provider_options_num_ctx=self.provider_options.get("num_ctx"),
        )
        # Ollama thinking toggle (mapped from reasoning_effort).
        # OLLAMA_THINKING=false in der env überstimmt reasoning_effort —
        # konsistent zu backend/scripts/run_*_simulation.py, das dieselbe
        # Heuristik nutzt. Honcho-Pflicht-Env für Agent-Workflows; ohne
        # diese Verdrahtung liefern thinking-Modelle (qwen3, gpt-oss) bei
        # chat_json schemalose leere `content`-Outputs → `JSON parsing
        # failed: line 1 column 1 (char 0)`.
        self._think = self.reasoning_effort != "none"
        _think_env = os.environ.get("OLLAMA_THINKING", "").lower()
        if _think_env in ("0", "false", "no", "off"):
            self._think = False
        elif _think_env in ("1", "true", "yes", "on"):
            self._think = True

        # Transient-failure retry knobs (Ollama Cloud sometimes 5xx-flaps).
        self._max_retries = int(os.environ.get('LLM_MAX_RETRIES', '3'))
        self._retry_initial_delay = float(os.environ.get('LLM_RETRY_INITIAL_DELAY', '1.0'))
        self._retry_max_delay = float(os.environ.get('LLM_RETRY_MAX_DELAY', '30.0'))

    @classmethod
    def from_route(
        cls,
        route: ResolvedRoute,
        secret_resolver: Optional["Any"] = None,
        timeout: float = 300.0,
        run_id: Optional[str] = None,
        api_key_override: Optional[str] = None,
    ) -> "LLMClient":
        """Factory: create LLMClient from a resolved stage route.

        Resolves actual base_url and api_key from the provider configuration,
        falling back to sanitized/config defaults if no resolver is provided.
        """
        base_url = route.base_url_sanitized
        api_key = api_key_override
        api_key_source: Optional[str] = "passed_in" if api_key_override else None

        # If a secret resolver is provided, we try to get the real secrets.
        # This prevents leaking them into ResolvedRoute but allows LLMClient
        # to use them.
        if secret_resolver:
            # We need to know the provider type to resolve the key correctly.
            # ResolvedRoute only has provider_id.
            # In a full implementation, we'd look up the provider descriptor.
            # For now, we use the fallback logic in SecretResolver.
            from ..services.llm_provider_registry import LlmProviderRegistry
            registry = LlmProviderRegistry()
            descriptor = next((p for p in registry.get_providers() if p.id == route.provider_id), None)

            p_type = descriptor.type if descriptor else "unknown"
            if not api_key:
                api_key = secret_resolver.get_api_key(route.provider_id, p_type)
                api_key_source = getattr(secret_resolver, "last_source", None)

            # Use real base_url from provider_options if present, otherwise from descriptor
            real_base = route.provider_options.get("base_url") or (descriptor.base_url if descriptor else None)
            if real_base:
                base_url = real_base

        return cls(
            api_key=api_key,
            base_url=base_url,
            model=route.model,
            timeout=timeout,
            reasoning_effort=route.reasoning_effort,
            provider_options=route.provider_options,
            run_id=run_id,
            routing_version=route.routing_version,
            route_stage=route.stage,
            route_provider_id=route.provider_id,
            api_key_source=api_key_source,
        )

    def _is_ollama(self) -> bool:
        """Check if we're talking to an Ollama server (local or cloud).

        Ollama Cloud hostet denselben /api/chat-Endpoint unter
        ``https://ollama.com/api`` mit identischem Body-Format (inkl.
        ``format=<schema>``). Beide Hosts müssen erkannt werden, damit
        der Native-Schema-Pfad in chat_json sowohl bei lokalem Ollama
        (Port 11434) als auch bei Cloud (ollama.com) ziehen kann.
        """
        base = (self.base_url or "").lower()
        return "11434" in base or "ollama.com" in base

    @staticmethod
    def _uses_max_completion_tokens(model: str) -> bool:
        # Kanonische Heuristik lebt seit #590 im OpenAI-Adapter
        # (app.llm.providers.openai.uses_max_completion_tokens): striktes
        # Prefix-Matching ("gpt-5", "gpt-5-…") verhindert Mismatches wie
        # hypothetisches "gpt-500". Bekannte Divergenz zur Spiegel-Heuristik
        # in backend/scripts/_sim_common.py ist dort dokumentiert.
        return uses_max_completion_tokens(model)

    @staticmethod
    def _is_token_key_400(exc: Exception) -> bool:
        """True wenn ein OpenAI-/Proxy-400 auf eine Token-Limit-Key-Inkompatibilität hindeutet.

        Erkennt beide Richtungen, je nachdem welcher Schlüssel im Request stand:
        - „'max_tokens' is not supported with this model. Use 'max_completion_tokens'"
        - „'max_completion_tokens' is not supported …" / Unsupported parameter

        Wird von ``chat()`` als Fallback-Retry-Trigger genutzt — Heuristik
        kann z. B. bei einem neuen OpenAI-kompatiblen Proxy daneben liegen,
        und dann reicht der Wortlaut der Antwort als Fallback.
        """
        try:
            from openai import APIStatusError
        except ImportError:
            APIStatusError = ()  # type: ignore[assignment]

        if APIStatusError and isinstance(exc, APIStatusError):
            status = getattr(exc, "status_code", None)
            if status is None:
                response = getattr(exc, "response", None)
                status = getattr(response, "status_code", None)
            if status != 400:
                return False
        msg = str(exc).lower()
        if "max_tokens" not in msg and "max_completion_tokens" not in msg:
            return False
        return (
            "not supported" in msg
            or "unsupported parameter" in msg
            or "use 'max_completion_tokens'" in msg
            or "use 'max_tokens'" in msg
            or "use max_completion_tokens" in msg
            or "use max_tokens" in msg
        )

    @staticmethod
    def _swap_token_kwargs(kwargs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Liefert eine Kopie von *kwargs* mit getauschtem Token-Limit-Schlüssel,
        oder ``None`` wenn keiner der beiden Schlüssel gesetzt ist.
        """
        swapped = dict(kwargs)
        if "max_tokens" in swapped:
            value = swapped.pop("max_tokens")
            swapped["max_completion_tokens"] = value
            return swapped
        if "max_completion_tokens" in swapped:
            value = swapped.pop("max_completion_tokens")
            swapped["max_tokens"] = value
            return swapped
        return None

    def _completion_token_kwargs(
        self, max_tokens: int, model: Optional[str] = None
    ) -> Dict[str, int]:
        """Wire-Key für das Token-Limit pro Modell.

        Liefert ``{"max_completion_tokens": N}`` für GPT-5/o1/o3/o4 und
        ``{"max_tokens": N}`` für alle anderen Modelle. ``model`` überschreibt
        ``self.model`` — nötig im Vision-Pfad, der ein anderes Modell als das
        Default-Chat-Modell nutzen kann (z. B. ``gemini-3-flash-preview:cloud``
        bei einer GPT-5-Chat-Session).
        """
        target_model = model if model is not None else (self.model or "")
        key = (
            "max_completion_tokens"
            if self._uses_max_completion_tokens(target_model)
            else "max_tokens"
        )
        return {key: max_tokens}

    def _detect_provider(self) -> Literal["ollama", "cloud", "openai", "google", "unknown"]:
        """Infer the LLM provider from base_url and model name.

        Delegiert seit Issue #591 an die zentrale Registry
        (:func:`app.llm.providers.registry.detect_provider`, ``mode="http"``)
        — Heuristik-Dokumentation und Prioritäten dort. Die alte
        ``_chat_with_tools``-Begründung für den ``"google"``-Branch
        (natives ``tools=`` statt XML-Fallback, sonst MALFORMED_FUNCTION_CALL)
        gilt unverändert.
        """
        return detect_provider(self.base_url, self.model, mode="http")

    def _publish_model_active(
        self,
        context: Literal[
            "chat", "chat_json", "embedding", "report", "persona", "graph", "unknown"
        ],
        *,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> None:
        """Publish a :class:`ModelActiveEvent` to the module-level bus.

        Fail-safe: any exception is caught and logged as a warning so that LLM
        calls are never blocked by bus errors.
        """
        try:
            from ..services.model_event_bus import ModelActiveEvent, model_event_bus

            extra: Dict[str, Any] = {}
            if max_tokens is not None:
                extra["max_tokens"] = max_tokens
            if temperature is not None:
                extra["temperature"] = temperature

            event = ModelActiveEvent(
                model=self.model or "unknown",
                context=context,
                provider=self._detect_provider(),
                ts=_time_mod.time(),
                extra=extra if extra else None,
            )
            model_event_bus.publish(event)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "model_event_bus.publish failed (LLM call proceeds): %s", exc
            )

    def _log_invocation_event(
        self,
        *,
        stage: str,
        latency_ms: float,
        success: bool,
        error_type: Optional[str] = None,
        http_status: Optional[int] = None,
        remote_request_id: Optional[str] = None,
    ) -> None:
        """Persist LLM call telemetry for routed runs without blocking execution."""
        if not getattr(self, "run_id", None):
            return

        try:
            from ..services.llm_invocation_logger import LlmInvocationLogger

            logger_service = LlmInvocationLogger(self.run_id)
            logger_service.log_event(
                stage=getattr(self, "route_stage", None) or stage,
                provider_id=getattr(self, "route_provider_id", None) or self._detect_provider(),
                model=self.model or "unknown",
                base_url=self.base_url,
                routing_version=getattr(self, "routing_version", None) or 0,
                latency_ms=latency_ms,
                success=success,
                error_type=error_type,
                http_status=http_status,
                remote_request_id=remote_request_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm invocation logging failed (LLM call proceeds): %s", exc)

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
        context: Literal[
            "chat", "chat_json", "embedding", "report", "persona", "graph", "unknown"
        ] = "chat",
        force_no_thinking: bool = False,
    ) -> str:
        """
        Send chat request

        Args:
            messages: Message list
            temperature: Temperature parameter
            max_tokens: Max token count
            response_format: Response format (e.g., JSON mode)
            context: Logical call context label for observability (published
                to :mod:`app.services.model_event_bus` before the API call).
            force_no_thinking: Bei True und Ollama-Provider wird ``think=False``
                hart gesetzt, unabhaengig vom reasoning_effort-Profil.

        Returns:
            Model response text
        """
        self._publish_model_active(context, max_tokens=max_tokens, temperature=temperature)
        # E2E-Stub-Pfad für chat() — symmetrisch zum Stub-Pfad in chat_json().
        # Aktiviert ausschließlich via AGORA_E2E_LLM_MODE=stub.
        # Liefert deterministischen ReACT-Loop-String (Tool-Call oder Final Answer).
        if os.environ.get("AGORA_E2E_LLM_MODE") == "stub":
            from app.utils.llm_e2e_stub import e2e_stub_chat_response
            logger.info(
                "LLMClient.chat: E2E-Stub aktiv — ueberspringe LLM-Call (context=%s)",
                context,
            )
            return e2e_stub_chat_response(messages=messages)
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        kwargs.update(self._completion_token_kwargs(max_tokens))

        if response_format:
            kwargs["response_format"] = response_format

        # For Ollama: pass num_ctx via extra_body to prevent prompt truncation,
        # plus think flag to control reasoning output on capable models.
        # force_no_thinking=True überschreibt self._think hart auf False —
        # verhindert, dass Reasoning-Profile den Token-Cap mit Thoughts belegen.
        if self._is_ollama():
            kwargs["extra_body"] = build_ollama_extra_body(
                num_ctx=self._num_ctx,
                think=False if force_no_thinking else self._think,
            )

        # Force streaming for Ollama: the OpenAI-compatible endpoint in Ollama
        # 0.21.0 stalls on non-streaming completions for cloud models (e.g.
        # qwen3-coder-next:cloud, deepseek-v4-flash:cloud) — the call never
        # returns. Streaming bypasses the bug; we reassemble chunks below.
        # Configurable via LLM_FORCE_STREAM=false to opt out.
        force_stream = (
            self._is_ollama()
            and os.environ.get("LLM_FORCE_STREAM", "true").lower() in ("1", "true", "yes")
        )

        import time as _time
        _t0 = _time.monotonic()

        def _create(call_kwargs: Dict[str, Any]):
            """One-shot call mit transient-retry. KEINE 400-Behandlung — die macht der äußere Wrapper."""
            return llm_call_with_retry(
                self.client.chat.completions.create,
                max_retries=self._max_retries,
                initial_delay=self._retry_initial_delay,
                max_delay=self._retry_max_delay,
                **call_kwargs,
            )

        def _call_with_token_key_fallback(call_kwargs: Dict[str, Any]):
            """Fallback-Retry: bei 400 wg. max_tokens/max_completion_tokens-Inkompatibilität
            einmalig den anderen Schlüssel verwenden. Heuristik in
            ``_uses_max_completion_tokens`` deckt die bekannten Familien ab; der
            Fallback schützt vor neuen Modellen/Proxies, die wir noch nicht kennen.
            """
            try:
                return _create(call_kwargs)
            except Exception as exc:  # noqa: BLE001 — wir filtern selbst
                if not self._is_token_key_400(exc):
                    raise
                swapped = self._swap_token_kwargs(call_kwargs)
                if swapped is None:
                    raise
                logger.warning(
                    "LLM 400 on token-limit key — retrying once with swapped key (model=%s, msg=%s)",
                    self.model,
                    str(exc)[:200],
                )
                return _create(swapped)

        _usage_for_counter: Optional[Any] = None
        try:
            if force_stream:
                kwargs["stream"] = True
                stream = _call_with_token_key_fallback(kwargs)
                chunks: List[str] = []
                finish_reason = None
                completion_tokens = None
                for event in stream:
                    if not event.choices:
                        continue
                    delta = event.choices[0].delta
                    piece = getattr(delta, "content", None)
                    if piece:
                        chunks.append(piece)
                    if event.choices[0].finish_reason:
                        finish_reason = event.choices[0].finish_reason
                    usage = getattr(event, "usage", None)
                    if usage and getattr(usage, "completion_tokens", None) is not None:
                        completion_tokens = usage.completion_tokens
                        _usage_for_counter = usage
                content = "".join(chunks)
            else:
                response = _call_with_token_key_fallback(kwargs)
                choice = response.choices[0]
                finish_reason = getattr(choice, "finish_reason", None)
                usage = getattr(response, "usage", None)
                completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
                _usage_for_counter = usage
                content = choice.message.content or ""
        except Exception as exc:  # noqa: BLE001
            elapsed = _time.monotonic() - _t0
            self._log_invocation_event(
                stage=context,
                latency_ms=elapsed * 1000,
                success=False,
                error_type=exc.__class__.__name__,
                http_status=getattr(exc, "status_code", None),
            )
            raise
        elapsed = _time.monotonic() - _t0
        logger.info(
            "LLM chat returned model=%s finish=%s tokens_out=%s elapsed=%.1fs max_tokens=%s stream=%s",
            self.model, finish_reason, completion_tokens, elapsed, max_tokens, force_stream,
        )
        self._log_invocation_event(
            stage=context,
            latency_ms=elapsed * 1000,
            success=True,
        )
        # Token-Counter — nur bei vorhandenen Integer-Usage-Daten, kein Log-Spam bei fehlendem Usage.
        # isinstance-Check schützt gegen MagicMock-Attribute in Tests (Mock gibt immer
        # einen Sub-Mock zurück, kein None) und gegen nicht-numerische Provider-Antworten.
        if _usage_for_counter is not None:
            _prompt_tokens = getattr(_usage_for_counter, "prompt_tokens", None)
            _completion_tokens = getattr(_usage_for_counter, "completion_tokens", None)
            _provider_label = self._detect_provider()
            _model_label = self.model or "unknown"
            from ..observability import llm_token_counter as _llm_token_counter  # noqa: PLC0415
            _attrs: Dict[str, str] = {"provider": _provider_label, "model": _model_label}
            if isinstance(_prompt_tokens, int):
                _llm_token_counter().add(_prompt_tokens, {**_attrs, "direction": "in"})
            if isinstance(_completion_tokens, int):
                _llm_token_counter().add(_completion_tokens, {**_attrs, "direction": "out"})
        # Some models (like MiniMax M2.5, DeepSeek-R1) include <think>thinking content in response, need to remove
        content = re.sub(r'<think>[\s\S]*?</think>', '', content, flags=re.IGNORECASE).strip()
        return content

    def describe_image(
        self,
        image_b64: str,
        prompt: str,
        model: Optional[str] = None,
        mime: str = "image/png",
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        """
        Send a single image + prompt to a vision-capable model and return a
        plain-text description.

        Uses the OpenAI-compatible multimodal message shape:
            {"role": "user", "content": [
                {"type": "text", "text": ...},
                {"type": "image_url", "image_url": {"url": "data:<mime>;base64,<b64>"}}
            ]}

        Works against Ollama Cloud vision models (e.g. gemini-3-flash-preview:cloud).
        """
        vision_model = model or os.environ.get('VISION_MODEL_NAME') or self.model
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
            ],
        }]
        kwargs: Dict[str, Any] = {
            "model": vision_model,
            "messages": messages,
            "temperature": temperature,
        }
        kwargs.update(self._completion_token_kwargs(max_tokens, model=vision_model))
        if self._is_ollama():
            # num_ctx mind. 8192; think=False — never want reasoning noise in
            # vision output.
            kwargs["extra_body"] = build_ollama_extra_body(
                num_ctx=max(self._num_ctx, 8192),
                think=False,
            )

        def _create_vision(call_kwargs: Dict[str, Any]):
            return llm_call_with_retry(
                self.client.chat.completions.create,
                max_retries=self._max_retries,
                initial_delay=self._retry_initial_delay,
                max_delay=self._retry_max_delay,
                **call_kwargs,
            )

        try:
            response = _create_vision(kwargs)
        except Exception as exc:  # noqa: BLE001
            if not self._is_token_key_400(exc):
                raise
            swapped = self._swap_token_kwargs(kwargs)
            if swapped is None:
                raise
            logger.warning(
                "Vision LLM 400 on token-limit key — retrying once with swapped key (model=%s)",
                vision_model,
            )
            response = _create_vision(swapped)
        content = response.choices[0].message.content or ""
        content = re.sub(r'<think>[\s\S]*?</think>', '', content, flags=re.IGNORECASE).strip()
        return content

    def _maybe_validate(
        self,
        parsed: Dict[str, Any],
        schema: Optional[JsonSchemaLike],
    ) -> Dict[str, Any]:
        """Validate *parsed* against *schema* if it is a Pydantic model.

        When *schema* is a plain JSON-Schema dict validation is the caller's
        responsibility — we return *parsed* unchanged.  When *schema* is a
        Pydantic model class we call ``model_validate`` and re-serialise via
        ``model_dump(mode='json')`` so the caller receives JSON-compatible
        Python types.  ``ValidationError`` propagates unchanged.
        """
        if schema is None:
            return parsed
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            # ValidationError propagates — do NOT swallow.
            return schema.model_validate(parsed).model_dump(mode="json")
        # Plain dict schema: no server-side re-validation.
        return parsed

    def _ollama_chat_with_schema(
        self,
        messages: List[Dict[str, Any]],
        schema: type[BaseModel],
        temperature: float,
        max_tokens: int,
        force_no_thinking: bool = False,
    ) -> str:
        """Direkter Aufruf gegen Ollamas /api/chat mit format=<schema>.

        Garantiert Schema-Enforcement laut Ollama-Doku, im Gegensatz zum
        OpenAI-Kompat-Wrapper, der response_format=type=json_schema
        schweigend droppen kann.

        Returns response message content (str). Raises httpx.HTTPError bei
        Netz-/4xx-/5xx-Fehlern, ValueError bei Schema-Reject durch Ollama.
        """
        import httpx  # lazy import (httpx ist via openai-SDK ohnehin transitive Dep)
        base_root = (self.base_url or "").rstrip("/")
        if base_root.endswith("/v1"):
            base_root = base_root[:-3]
        url = f"{base_root}/api/chat"

        flattened = _flatten_pydantic_schema_for_ollama(schema)
        think_flag = False if force_no_thinking else self._think

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "format": flattened,
            "stream": False,
            "options": {
                "num_ctx": self._num_ctx,
                "temperature": temperature,
                "num_predict": max_tokens,
            },
            "think": think_flag,
        }

        logger.info(
            "LLMClient._ollama_chat_with_schema: POST %s schema=%s model=%s",
            url, schema.__name__, self.model,
        )

        # Ollama Cloud (ollama.com) verlangt Authorization: Bearer <api_key>.
        # Lokales Ollama (Port 11434) ignoriert den Header. Den OpenAI-SDK-Pfad
        # macht das automatisch via self.client.api_key; der native httpx-Call
        # muss den Header selbst setzen.
        headers: Dict[str, str] = {}
        if self.api_key and self.api_key.lower() != "ollama":
            headers["Authorization"] = f"Bearer {self.api_key}"

        with httpx.Client(timeout=300.0) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        message = data.get("message") or {}
        content = message.get("content", "")
        if not isinstance(content, str):
            raise ValueError(
                f"Ollama /api/chat unexpected message.content type: {type(content)}"
            )
        return content

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        schema: Optional[JsonSchemaLike] = None,
        schema_name: str = "structured_response",
        context: Literal[
            "chat", "chat_json", "embedding", "report", "persona", "graph", "unknown"
        ] = "chat_json",
        force_no_thinking: bool = False,
    ) -> Dict[str, Any]:
        """
        Send chat request and return JSON.

        Args:
            messages: Message list
            temperature: Temperature parameter
            max_tokens: Max token count
            schema: Optional Pydantic model class or JSON-Schema dict.
                When provided, attempts strict ``response_format={"type":
                "json_schema", ...}``.  On providers that do not support this
                format a single fallback to ``json_object`` is attempted with a
                warning log.  When *schema* is a Pydantic model the returned
                dict is also validated against it so that callers can rely on
                field types matching the model.
            schema_name: Name embedded in the strict json_schema request
                (used by some providers for caching / routing).
            context: Logical call context label for observability (forwarded
                to :meth:`chat` which publishes it to the model event bus).
            force_no_thinking: Wird an chat() weitergereicht — bei Ollama wird
                ``think=False`` hart gesetzt, unabhaengig vom Profil.

        Returns:
            Parsed JSON object (dict).

        Raises:
            ValueError: JSON cannot be parsed after optional repair.
            pydantic.ValidationError: Parsed JSON does not match *schema*
                when *schema* is a Pydantic model.
        """
        # E2E-Stub-Pfad — nur aktiv wenn AGORA_E2E_LLM_MODE=stub gesetzt.
        # Muss VOR Cache-Lookup, Token-Counter, Retry und allen LLM-Calls liegen.
        if os.environ.get("AGORA_E2E_LLM_MODE") == "stub":
            from app.utils.llm_e2e_stub import e2e_stub_response
            logger.info(
                "LLMClient.chat_json: E2E-Stub aktiv — ueberspringe LLM-Call (context=%s)",
                context,
            )
            # schema kann Pydantic-Klasse oder dict sein — Stub normalisiert intern
            schema_for_stub: Optional[Dict[str, Any]] = None
            if schema is not None:
                if isinstance(schema, type) and issubclass(schema, BaseModel):
                    schema_for_stub = schema.model_json_schema()
                elif isinstance(schema, dict):
                    schema_for_stub = schema
            return e2e_stub_response(
                schema=schema_for_stub,
                messages=list(messages),
            )

        # --- Env-Flag-Auswertung (Issue #593) -----------------------------------
        # LLM_DISABLE_JSON_OBJECT_MODE  → unterdrückt {type: "json_object"}
        # LLM_DISABLE_JSON_SCHEMA_MODE  → unterdrückt strict json_schema;
        #                                  fällt auf json_object + Pydantic zurück
        # LLM_DISABLE_JSON_MODE         → Legacy-Alias für OBJECT_MODE (Deprecation)
        disable_object_mode = _is_json_object_mode_disabled()
        disable_schema_mode = _is_json_schema_mode_disabled()

        # Legacy-Alias: Deprecation-Warning ausgeben, damit Betreiber migrieren können.
        if _env_flag('LLM_DISABLE_JSON_MODE') and not _env_flag('LLM_DISABLE_JSON_OBJECT_MODE'):
            import warnings as _warnings
            _warnings.warn(
                "LLM_DISABLE_JSON_MODE ist veraltet und wird in einer künftigen Version "
                "entfernt. Bitte LLM_DISABLE_JSON_OBJECT_MODE verwenden.",
                DeprecationWarning,
                stacklevel=2,
            )

        # schema=None + OBJECT_MODE disabled → kein response_format
        disable_json_mode = disable_object_mode and schema is None
        # schema=<Model> + SCHEMA_MODE disabled → json_object-Fallback statt strict
        schema_mode_fallback = schema is not None and disable_schema_mode

        if schema_mode_fallback:
            fallback_target = "Freitext" if disable_object_mode else "json_object"
            logger.info(
                "LLMClient.chat_json: LLM_DISABLE_JSON_SCHEMA_MODE aktiv — schema=%s "
                "fällt auf %s + Pydantic-Validierung zurück",
                schema.__name__ if isinstance(schema, type) else "dict",
                fallback_target,
            )

        if schema is not None:
            schema_label = schema.__name__ if isinstance(schema, type) else "dict"
            logger.info(
                "LLMClient.chat_json: schema=%s name=%s",
                schema_label,
                schema_name,
            )

        # Build response_format ---------------------------------------------------
        if disable_json_mode:
            response_format: Optional[Dict[str, Any]] = None
        elif schema_mode_fallback:
            # LLM_DISABLE_JSON_SCHEMA_MODE=true: Schema übergeben, aber strict-Mode
            # deaktiviert → json_object + post-hoc Pydantic-Validierung.
            # Falls auch OBJECT_MODE deaktiviert ist, fällt es auf Freitext (None) zurück.
            response_format = None if disable_object_mode else {"type": "json_object"}
        elif schema is not None:
            # OpenAI / Google strict-mode: $refs inline-resolven, $defs +
            # Meta-Keys droppen, additionalProperties:false + required-Liste
            # auf alle Object-Schemas erzwingen. Ollama nutzt den nativen
            # /api/chat::format-Pfad weiter unten und ist nicht betroffen.
            json_schema: Dict[str, Any] = _enforce_openai_strict_schema(schema)
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": json_schema,
                    "strict": True,
                },
            }
        else:
            response_format = {"type": "json_object"}

        # Call --------------------------------------------------------------------
        if not disable_json_mode and not schema_mode_fallback and schema is not None:
            # NATIVE Ollama-Pfad: /api/chat mit format=<schema> ist die einzige
            # autoritativ dokumentierte Methode, ein Schema bei Ollama zu erzwingen.
            # Bei Netz-/4xx-Fehler fall-through zum OpenAI-SDK-Pfad mit
            # json_object-Fallback (Resilienz, kein Hard-Fail).
            if self._is_ollama() and isinstance(schema, type) and issubclass(schema, BaseModel):
                try:
                    response = self._ollama_chat_with_schema(
                        messages=messages,
                        schema=schema,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        force_no_thinking=force_no_thinking,
                    )
                    cleaned_response = _strip_llm_json_envelope(response)
                    parsed: Dict[str, Any] = json.loads(cleaned_response)
                    return self._maybe_validate(parsed, schema)
                except Exception as exc:  # noqa: BLE001 — bewusst breit, Fallback ist sicher
                    logger.warning(
                        "LLMClient.chat_json: native Ollama /api/chat-Pfad fehlgeschlagen "
                        "(%s: %s), fallback auf OpenAI-Wrapper",
                        type(exc).__name__, exc,
                    )
                    # Fall through zum bestehenden Strict-OpenAI-Pfad
            # Strict-schema path: single fallback on unsupported-provider errors.
            try:
                response = self.chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    context=context,
                    force_no_thinking=force_no_thinking,
                )
            except Exception as exc:
                exc_lower = str(exc).lower()
                if any(hint in exc_lower for hint in _STRICT_UNSUPPORTED_HINTS):
                    logger.warning(
                        "LLMClient.chat_json: strict json_schema not supported by "
                        "provider, falling back to json_object (caller should not "
                        "rely on schema enforcement here)"
                    )
                    response = self.chat(
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        response_format={"type": "json_object"},
                        context=context,
                        force_no_thinking=force_no_thinking,
                    )
                else:
                    raise
        else:
            response = self.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                context=context,
                force_no_thinking=force_no_thinking,
            )
        # Codefences + Prosa-Envelope entfernen (Issue #556).
        cleaned_response = _strip_llm_json_envelope(response)

        try:
            parsed: Dict[str, Any] = json.loads(cleaned_response)
        except json.JSONDecodeError:
            repaired = _try_repair_truncated_json(cleaned_response)
            if repaired is not None:
                logger.warning(
                    "LLM JSON looked truncated; recovered with best-effort repair "
                    "(%d → %d chars). Consider raising the max_tokens budget for "
                    "this caller.",
                    len(cleaned_response), len(repaired),
                )
                try:
                    parsed = json.loads(repaired)
                except json.JSONDecodeError:
                    pass
                else:
                    return self._maybe_validate(parsed, schema)
            preview = cleaned_response[:400]
            tail = cleaned_response[-200:] if len(cleaned_response) > 600 else ""
            raise ValueError(
                "Invalid JSON format from LLM "
                f"(len={len(cleaned_response)}; likely truncated — "
                "try raising max_tokens). "
                f"Head: {preview}{'…' if tail else ''}"
                + (f" Tail: …{tail}" if tail else "")
            )
        return self._maybe_validate(parsed, schema)


# ---------------------------------------------------------------------------
# Native OpenAI Function-Calling (chat_with_tools)
# ---------------------------------------------------------------------------

from typing import TypedDict  # noqa: E402 — conditional import after class def


class ToolCallItem(TypedDict):
    id: str
    name: str
    arguments: dict


class ToolCallResponse(TypedDict):
    content: str
    tool_calls: List[ToolCallItem]
    finish_reason: str
    raw_response: Any


def _extract_tool_calls_from_message(message: Any) -> List[ToolCallItem]:
    """Normalisiert OpenAI-SDK ToolCall-Objekte zu ``ToolCallItem``-Dicts."""
    result: List[ToolCallItem] = []
    tool_calls = getattr(message, "tool_calls", None)
    if not tool_calls:
        return result
    for tc in tool_calls:
        tc_id = getattr(tc, "id", "") or ""
        func = getattr(tc, "function", None)
        name = getattr(func, "name", "") or ""
        args_raw = getattr(func, "arguments", "") or ""
        try:
            arguments: dict = json.loads(args_raw) if args_raw else {}
        except json.JSONDecodeError:
            logger.warning(
                "LLMClient: failed to parse tool arguments as JSON (tool=%s): %s",
                name,
                args_raw[:200],
            )
            arguments = {}
        result.append(ToolCallItem(id=tc_id, name=name, arguments=arguments))
    return result


def _accumulate_streaming_tool_calls(
    chunks: Any,
) -> tuple[str, List[ToolCallItem], str]:
    """Akkumuliert Streaming-Chunks und baut content + tool_calls zusammen.

    Gibt ``(content, tool_calls, finish_reason)`` zurück.
    """
    content_parts: List[str] = []
    finish_reason: str = "stop"

    # Indexed accumulator: index → {id, name, arguments_parts}
    tc_acc: dict[int, dict] = {}

    for chunk in chunks:
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        if choice.finish_reason:
            finish_reason = choice.finish_reason
        delta = choice.delta

        # Textinhalt akkumulieren
        piece = getattr(delta, "content", None)
        if piece:
            content_parts.append(piece)

        # Tool-Call-Deltas akkumulieren
        tc_deltas = getattr(delta, "tool_calls", None)
        if tc_deltas:
            for tc_delta in tc_deltas:
                idx = getattr(tc_delta, "index", 0) or 0
                if idx not in tc_acc:
                    tc_acc[idx] = {"id": "", "name": "", "arguments_parts": []}
                entry = tc_acc[idx]
                tc_id = getattr(tc_delta, "id", None)
                if tc_id:
                    entry["id"] = tc_id
                func_delta = getattr(tc_delta, "function", None)
                if func_delta:
                    fname = getattr(func_delta, "name", None)
                    if fname:
                        entry["name"] = fname
                    fargs = getattr(func_delta, "arguments", None)
                    if fargs:
                        entry["arguments_parts"].append(fargs)

    content = "".join(content_parts)

    tool_calls: List[ToolCallItem] = []
    for idx in sorted(tc_acc.keys()):
        entry = tc_acc[idx]
        args_str = "".join(entry["arguments_parts"])
        try:
            arguments = json.loads(args_str) if args_str else {}
        except json.JSONDecodeError:
            logger.warning(
                "LLMClient: failed to parse streaming tool arguments (tool=%s): %s",
                entry["name"],
                args_str[:200],
            )
            arguments = {}
        tool_calls.append(
            ToolCallItem(id=entry["id"], name=entry["name"], arguments=arguments)
        )

    return content, tool_calls, finish_reason


# P5.4: Native OpenAI function-calling method
# Wird in LLMClient eingebunden als Methode — hier als Funktion definiert,
# damit der TypedDict-Import nicht in der Klasse wiederholt werden muss.


def _chat_with_tools(
    self: "LLMClient",
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    tool_choice: str = "auto",
    temperature: float = 0.5,
    max_tokens: int = 4096,
    context: Literal[
        "chat", "chat_json", "embedding", "report", "persona", "graph", "unknown"
    ] = "report",
) -> ToolCallResponse:
    """Native OpenAI function-calling: sendet ``tools=`` + ``tool_choice=`` an die API.

    Streaming-Pfad (Ollama): Tool-Call-Deltas werden akkumuliert.
    Nicht-Streaming-Pfad: ``message.tool_calls`` direkt normalisiert.

    Bei Provider ``unknown`` oder wenn die API keine ``tool_calls`` zurückgibt,
    bleibt ``tool_calls=[]`` und ``content`` enthält den Freitext — der Caller
    kann dann auf den XML-Fallback-Parser zurückgreifen.

    E2E-Stub-Pfad: analog zu ``chat()`` via ``AGORA_E2E_LLM_MODE=stub``.
    """
    self._publish_model_active(context, max_tokens=max_tokens, temperature=temperature)

    # E2E-Stub-Pfad
    if os.environ.get("AGORA_E2E_LLM_MODE") == "stub":
        from app.utils.llm_e2e_stub import e2e_stub_chat_with_tools_response
        logger.info(
            "LLMClient.chat_with_tools: E2E-Stub aktiv — ueberspringe LLM-Call (context=%s)",
            context,
        )
        return e2e_stub_chat_with_tools_response(messages=messages, tools=tools)

    # Provider-Unknown-Short-Circuit: für nicht eindeutig identifizierbare Provider
    # (weder Ollama lokal noch Ollama-Cloud noch OpenAI) können wir nicht garantieren,
    # dass das Backend ``tools=``/``tool_choice=`` versteht. Statt einen 400er zu
    # provozieren, fallen wir auf einen ``chat()``-Call ohne Tools zurück und liefern
    # ``tool_calls=[]`` — der Caller (workflow.generate_section_react) erkennt das
    # und nutzt den XML-Fallback-Parser. So bleibt das ReACT-Loop-Verhalten stabil.
    provider = self._detect_provider()
    if provider == "unknown":
        logger.info(
            "LLMClient.chat_with_tools: provider=unknown (model=%s, base=%s) — "
            "skipping tools= and falling back to chat() for XML-tool-call parsing",
            self.model,
            self.base_url,
        )
        fallback_content = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            context=context,
        ) or ""
        return ToolCallResponse(
            content=fallback_content,
            tool_calls=[],
            finish_reason="stop",
            raw_response=None,
        )

    import time as _time
    _t0 = _time.monotonic()

    kwargs: Dict[str, Any] = {
        "model": self.model,
        "messages": messages,
        "temperature": temperature,
        "tools": tools,
        "tool_choice": tool_choice,
    }
    kwargs.update(self._completion_token_kwargs(max_tokens))

    if self._is_ollama():
        kwargs["extra_body"] = build_ollama_extra_body(
            num_ctx=self._num_ctx,
            think=self._think,
        )

    force_stream = (
        self._is_ollama()
        and os.environ.get("LLM_FORCE_STREAM", "true").lower() in ("1", "true", "yes")
    )

    def _create(call_kwargs: Dict[str, Any]) -> Any:
        return llm_call_with_retry(
            self.client.chat.completions.create,
            max_retries=self._max_retries,
            initial_delay=self._retry_initial_delay,
            max_delay=self._retry_max_delay,
            **call_kwargs,
        )

    def _create_with_fallback(call_kwargs: Dict[str, Any]) -> Any:
        try:
            return _create(call_kwargs)
        except Exception as exc:  # noqa: BLE001
            if not self._is_token_key_400(exc):
                raise
            swapped = self._swap_token_kwargs(call_kwargs)
            if swapped is None:
                raise
            logger.warning(
                "LLM 400 on token-limit key (tools path) — retrying once with swapped key "
                "(model=%s, msg=%s)",
                self.model,
                str(exc)[:200],
            )
            return _create(swapped)

    content: str = ""
    tool_calls: List[ToolCallItem] = []
    finish_reason: str = "stop"
    raw_response: Any = None

    try:
        if force_stream:
            kwargs["stream"] = True
            stream = _create_with_fallback(kwargs)
            content, tool_calls, finish_reason = _accumulate_streaming_tool_calls(stream)
        else:
            raw_response = _create_with_fallback(kwargs)
            choice = raw_response.choices[0]
            finish_reason = getattr(choice, "finish_reason", "stop") or "stop"
            message = choice.message
            content = getattr(message, "content", None) or ""
            tool_calls = _extract_tool_calls_from_message(message)
    except Exception as exc:  # noqa: BLE001
        elapsed = _time.monotonic() - _t0
        self._log_invocation_event(
            stage=context,
            latency_ms=elapsed * 1000,
            success=False,
            error_type=exc.__class__.__name__,
            http_status=getattr(exc, "status_code", None),
        )
        raise

    elapsed = _time.monotonic() - _t0
    logger.info(
        "LLM chat_with_tools returned model=%s finish=%s tool_call_count=%d elapsed=%.1fs stream=%s",
        self.model,
        finish_reason,
        len(tool_calls),
        elapsed,
        force_stream,
    )
    self._log_invocation_event(
        stage=context,
        latency_ms=elapsed * 1000,
        success=True,
    )

    # <think>...</think> aus Textinhalt entfernen (analog zu chat())
    content = re.sub(r"<think>[\s\S]*?</think>", "", content, flags=re.IGNORECASE).strip()

    return ToolCallResponse(
        content=content,
        tool_calls=tool_calls,
        finish_reason=finish_reason,
        raw_response=raw_response,
    )


# Methode in LLMClient einbinden
LLMClient.chat_with_tools = _chat_with_tools  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# P5.3: Profile-basierte Client-Factory
# ---------------------------------------------------------------------------

def build_client_from_profile(
    profile: "LlmProfile",
    *,
    run_id: Optional[str] = None,
    timeout: float = 300.0,
) -> LLMClient:
    """P5.3: LLMClient aus persistiertem LLM-Profil bauen (überschreibt Config).

    Ollama-Provider (localhost oder 'ollama' in base_url) dürfen api_key leer
    lassen — der Dummy-Wert 'ollama' wird gesetzt. Cloud-Provider ohne Key
    scheitern sofort mit einem ValueError, bevor ein HTTP-Request entsteht.
    """
    base_url_lower = profile.base_url.lower()
    is_local = any(
        h in base_url_lower
        for h in ("localhost", "127.0.0.1", "host.docker.internal", "ollama")
    )
    if not profile.api_key and not is_local:
        raise ValueError(
            f"LLM-Profil {profile.id!r}: api_key fehlt für Provider {profile.provider!r}"
        )
    return LLMClient(
        api_key=profile.api_key or "ollama",
        base_url=profile.base_url,
        model=profile.model_name,
        timeout=timeout,
        run_id=run_id,
    )
