"""Schlanke Provider-Wrapper für OpenAI, Gemini, Ollama.

Jeder Wrapper bietet ``async complete(prompt, model, **opts) -> str``
und ist auf das Nötigste reduziert. Komplexere Logik (Routing, Retry,
Streaming) gehört in ``unified_client.UnifiedLLMClient``.
"""

from .gemini import GeminiClient
from .ollama import OllamaClient
from .openai import OpenAIClient

__all__ = ["GeminiClient", "OllamaClient", "OpenAIClient"]
