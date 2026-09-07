"""Contracts für ``/api/status`` — SSoT für den Frontend-Zod-Spiegel.

Bislang war die Antwort von ``/api/status`` handgeschrieben und der
Zod-Spiegel in ``frontend/src/contracts/systemStatusContract.ts`` hatte keine
Gegenseite, gegen die der Schema-Drift-Gate hätte prüfen können. Dieses Modul
schließt diese Lücke zunächst für den Ollama-Teilbaum, dessen Shape sich mit
dem Provider-Gating geändert hat (``reachable`` ist jetzt dreiwertig).

Die übrigen Teilbäume (``backend``, ``neo4j``, ``disk``, ``gpu``) sind
weiterhin ungedeckt — ihre Migration gehört in einen eigenen Slice und würde
den Scope dieses Fixes sprengen. Issue #1458 strukturiert dort ausschließlich
den Fehler-Shape (``StatusCheckError``), nicht den jeweiligen Teilbaum selbst
— ``_get_neo4j_status``/``_get_disk_status`` in ``app/api/status.py`` geben
weiterhin rohe Dicts zurück, betten darin aber jetzt ``StatusCheckError``
statt eines rohen Exception-Strings ein.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

# Muss mit ``HttpDetectedProvider`` aus app.llm.providers.registry
# konsistent bleiben. Bewusst ``str`` statt Literal: der Wert wandert in einen
# i18n-Lookup mit Fallback, ein neuer Provider darf den Status nicht
# invalidieren.
SkippedProviderKind = str


class StatusErrorCode(str, Enum):
    """Geschlossene Fehlerklassifikation für Probe-Fehler in ``/api/status``.

    Der rohe Exception-Text (Dateipfade, Hostnamen, Treiberdetails) ist ein
    Informationsleck und für ein Frontend nicht darstellbar (Python-
    Traceback-Prosa) — er bleibt im strukturierten Log. Hier wandert nur ein
    Code, den das Frontend in einen lesbaren Satz übersetzt.

    Bewusst nicht ein Code je Exception-Klasse, sondern eine Klassifikation
    danach, wie ein Nutzer reagieren würde:

    * ``unreachable`` — Ziel (Host, Pfad) ist nicht erreichbar/vorhanden.
    * ``timeout`` — Probe hat das Zeitbudget überschritten.
    * ``auth`` — Authentifizierung/Berechtigung fehlgeschlagen.
    * ``unexpected`` — alles andere; Catch-all, damit ein neuer,
      unklassifizierter Fehler nicht crasht.
    """

    UNREACHABLE = "unreachable"
    TIMEOUT = "timeout"
    AUTH = "auth"
    UNEXPECTED = "unexpected"


class StatusCheckError(BaseModel):
    """Strukturierter Fehler-Shape für Probe-Fehler in ``/api/status``.

    Ersetzt den rohen ``str(exc)``, der bislang an drei Stellen (neo4j,
    ollama, disk) direkt in die HTTP-Antwort floss.
    """

    model_config = ConfigDict(extra="forbid")

    code: StatusErrorCode


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
    # Strukturiert seit #1458 — vorher roher ``str(exc)`` (Informationsleck,
    # fürs Frontend unrenderbarer Traceback-Text). Der Rohtext geht ins Log.
    error: StatusCheckError | None = None


class SystemStatusE2E(BaseModel):
    """E2E-Harness-Teilbaum von ``/api/status``.

    Meldet, ob der **Backend-Prozess** im E2E-Stub-Modus läuft, also ob
    ``LLMClient.chat_json`` statt eines echten Providers eine Konservenantwort
    liefert (``AGORA_E2E_LLM_MODE=stub``). Der Wert stammt aus der Umgebung des
    Backend-Prozesses und wird bei jedem Request frisch gelesen.

    Warum das an der API hängt und nicht nur im Container-Log steht: die
    E2E-Suite lief bisher gegen ``process.env.AGORA_E2E_LLM_MODE`` des
    *Playwright*-Prozesses — ein Wert, der über den Zustand des Backends
    nichts aussagt. Damit konnte eine Suite grün durchlaufen, die in
    Wirklichkeit gegen einen echten Provider (oder gegen gar keinen) lief.

    Kein Geheimnis: der Teilbaum sagt nur, welchen LLM-Pfad diese Instanz
    fährt. Für Betreiber ist das eher ein Sicherheitsgewinn — eine
    Produktivinstanz, die versehentlich mit Stub-LLM läuft, produziert sonst
    still erfundene Berichte, ohne dass es irgendwo sichtbar wäre.
    """

    model_config = ConfigDict(extra="forbid")

    # Rohwert von ``AGORA_E2E_LLM_MODE``; ``None``, wenn die Variable im
    # Backend-Prozess nicht gesetzt ist (Normalfall in Produktion).
    llm_mode: str | None = None
    # Abgeleitet: genau dann ``True``, wenn ``llm_mode == "stub"``. Der
    # E2E-Helper assertiert hierauf, damit er sich nicht auf String-Vergleiche
    # im Testcode verlassen muss.
    stub_active: bool = False
