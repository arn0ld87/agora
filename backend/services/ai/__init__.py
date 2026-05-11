"""Multi-Provider AI Service Layer (openai / gemini / ollama).

API-Keys ausschließlich aus Umgebungsvariablen — kein Logging, keine Exceptions
mit Secret-Leak. Live-Model-Discovery, kein hardcoded Catalog.
"""

from .model_discovery import ModelInfo, discover_models
from .session import AISession, SwitchEvent
from .unified_client import UnifiedLLMClient

__all__ = [
    "AISession",
    "ModelInfo",
    "SwitchEvent",
    "UnifiedLLMClient",
    "discover_models",
]
