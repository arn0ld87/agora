"""Contracts für ``/api/status`` — SSoT für den Frontend-Zod-Spiegel.

Bislang war die Antwort von ``/api/status`` handgeschrieben und der
Zod-Spiegel in ``frontend/src/contracts/systemStatusContract.ts`` hatte keine
Gegenseite, gegen die der Schema-Drift-Gate hätte prüfen können. Dieses Modul
schließt diese Lücke zunächst für den Ollama-Teilbaum, dessen Shape sich mit
dem Provider-Gating geändert hat (``reachable`` ist jetzt dreiwertig).

Die übrigen Teilbäume (``backend``, ``neo4j``, ``disk``, ``gpu``) sind
weiterhin ungedeckt — ihre Migration gehört in einen eigenen Slice und würde
den Scope dieses Fixes sprengen.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# Muss mit ``HttpDetectedProvider`` aus app.llm.providers.registry
# konsistent bleiben. Bewusst ``str`` statt Literal: der Wert wandert in einen
# i18n-Lookup mit Fallback, ein neuer Provider darf den Status nicht
# invalidieren.
SkippedProviderKind = str


class SystemStatusOllama(BaseModel):
    """Ollama-Teilbaum von ``/api/status``.

    ``reachable`` ist dreiwertig:

    * ``True``  — ``/api/tags`` beantwortet
    * ``False`` — Probe lief, Server nicht erreichbar (``error`` gesetzt)
    * ``None``  — Probe bewusst übersprungen, weil der aktive Provider keine
      ``/api/tags``-Route bedient (``skipped=True``, ``skipped_provider``
      gesetzt). Das ist ausdrücklich KEIN Fehlerzustand; Consumer dürfen
      ``None`` nicht als "offline" rendern.
    """

    model_config = ConfigDict(extra="forbid")

    reachable: bool | None = None
    skipped: bool = False
    # Maschinenlesbar für den i18n-Lookup im Frontend. ``reason`` bleibt
    # daneben als menschenlesbares Debug-Feld erhalten, wird aber nicht in der
    # UI gerendert — hartkodierte Backend-Prosa in der Oberfläche verstößt
    # gegen die vue-i18n-Pflicht aus AGENTS.md.
    skipped_provider: SkippedProviderKind | None = None
    reason: str | None = None
    base_url: str | None = None
    models_available: list[str] = Field(default_factory=list)
    default_model: str | None = None
    error: str | None = None
