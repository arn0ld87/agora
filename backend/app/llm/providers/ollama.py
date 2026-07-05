"""
Native Ollama ``/api/chat`` schema path.

Extracted verbatim (parametrized instead of ``self``) from
``_flatten_pydantic_schema_for_ollama`` / ``LLMClient._ollama_chat_with_schema``
in ``app/utils/llm_client.py`` as part of issue #582 (mechanical split — no
behavior change).
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from ...utils.logger import get_logger

logger = get_logger("agora.llm_client")


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


def chat_with_schema(
    *,
    base_url: Optional[str],
    model: Optional[str],
    api_key: Optional[str],
    think: bool,
    num_ctx: int,
    messages: List[Dict[str, Any]],
    schema: type[BaseModel],
    temperature: float,
    max_tokens: int,
) -> str:
    """Direkter Aufruf gegen Ollamas /api/chat mit format=<schema>.

    Garantiert Schema-Enforcement laut Ollama-Doku, im Gegensatz zum
    OpenAI-Kompat-Wrapper, der response_format=type=json_schema
    schweigend droppen kann.

    Returns response message content (str). Raises httpx.HTTPError bei
    Netz-/4xx-/5xx-Fehlern, ValueError bei Schema-Reject durch Ollama.
    """
    import httpx  # lazy import (httpx ist via openai-SDK ohnehin transitive Dep)
    base_root = (base_url or "").rstrip("/")
    if base_root.endswith("/v1"):
        base_root = base_root[:-3]
    url = f"{base_root}/api/chat"

    flattened = _flatten_pydantic_schema_for_ollama(schema)

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "format": flattened,
        "stream": False,
        "options": {
            "num_ctx": num_ctx,
            "temperature": temperature,
            "num_predict": max_tokens,
        },
        "think": think,
    }

    logger.info(
        "LLMClient._ollama_chat_with_schema: POST %s schema=%s model=%s",
        url, schema.__name__, model,
    )

    # Ollama Cloud (ollama.com) verlangt Authorization: Bearer <api_key>.
    # Lokales Ollama (Port 11434) ignoriert den Header. Den OpenAI-SDK-Pfad
    # macht das automatisch via self.client.api_key; der native httpx-Call
    # muss den Header selbst setzen.
    headers: Dict[str, str] = {}
    if api_key and api_key.lower() != "ollama":
        headers["Authorization"] = f"Bearer {api_key}"

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
