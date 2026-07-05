"""
Provider detection.

Extracted verbatim (parametrized on base_url/model instead of ``self``) from
``LLMClient._is_ollama`` / ``LLMClient._detect_provider`` in
``app/utils/llm_client.py`` as part of issue #582 (mechanical split — no
behavior change).
"""

from typing import Literal, Optional


def is_ollama(base_url: Optional[str]) -> bool:
    """Check if we're talking to an Ollama server (local or cloud).

    Ollama Cloud hostet denselben /api/chat-Endpoint unter
    ``https://ollama.com/api`` mit identischem Body-Format (inkl.
    ``format=<schema>``). Beide Hosts müssen erkannt werden, damit
    der Native-Schema-Pfad in chat_json sowohl bei lokalem Ollama
    (Port 11434) als auch bei Cloud (ollama.com) ziehen kann.
    """
    base = (base_url or "").lower()
    return "11434" in base or "ollama.com" in base


def detect_provider(
    base_url: Optional[str], model: Optional[str]
) -> Literal["ollama", "cloud", "openai", "google", "unknown"]:
    """Infer the LLM provider from base_url and model name.

    Heuristics (in priority order):
    1. Base URL contains ``ollama.com`` → ``"cloud"`` (Ollama Cloud proxy).
    2. Model suffix ``:cloud`` → ``"cloud"`` (Ollama Cloud Model-Tag-Hint —
       wird VOR der Port-Heuristik geprüft, weil Cloud-Modelle auch über
       den lokalen ollama-Proxy auf :11434 laufen können).
    3. Base URL contains ``11434`` → ``"ollama"`` (local Ollama).
    4. Base URL contains ``openai.com`` or ``api.openai`` → ``"openai"``.
    5. Base URL contains ``googleapis.com`` or ``generativelanguage`` →
       ``"google"`` (Gemini-OpenAI-Compat-Layer — unterstützt natives
       ``tools=`` / ``tool_choice=``; siehe ``_chat_with_tools``-Branch.
       Ohne diesen Pfad fiel der Tool-Call auf XML-im-Prompt zurück, was
       Gemini's Function-Filter mit MALFORMED_FUNCTION_CALL ablehnt).
    6. Fallback → ``"unknown"``.
    """
    model_name = model or ""
    base = (base_url or "").lower()
    if "ollama.com" in base:
        return "cloud"
    if model_name.endswith(":cloud"):
        return "cloud"
    if "11434" in base:
        return "ollama"
    if "openai.com" in base or "api.openai" in base:
        return "openai"
    if "googleapis.com" in base or "generativelanguage" in base:
        return "google"
    return "unknown"
