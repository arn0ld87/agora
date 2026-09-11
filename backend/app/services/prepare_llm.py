"""LLM route resolution for simulation preparation."""

from __future__ import annotations

from typing import Optional

from ..contracts.llm_routing_contract import ResolvedRoute
from ..contracts.provider_types import PROVIDER_CODEX_CLI
from .llm_routing_seed import resolve_route_api_key
from .llm_runtime import RuntimeLlmConfig

LlmRuntimeInput = RuntimeLlmConfig | ResolvedRoute

def _resolve_llm_connection(
    llm_runtime: Optional[LlmRuntimeInput],
    *,
    require: bool = True,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Loest Key, Endpoint und Provider-Typ aus der Route — oder bricht ab.

    Fruehere Fassung gab bei nicht aufloesbarer Route ``(None, None)`` zurueck.
    Das sah harmlos aus, war aber der Ausloeser einer stillen Provider-
    Vertauschung: ``OasisProfileGenerator.__init__`` fuellt fehlende Werte aus
    ``Config.LLM_BASE_URL``/``Config.LLM_API_KEY`` auf, waehrend ``model_name``
    aus der Route weitergereicht wird. Ergebnis war eine Halb-Uebergabe —
    Modell aus der UI-Route, Endpoint und Key aus der ``.env`` — die das Modell
    an einen fremden Provider schickte (beobachtet: ``deepseek-v4-flash:0731``
    an ``https://api.minimax.io/v1`` → HTTP 401). Nach aussen meldete der Lauf
    trotzdem "30 Personas erfolgreich generiert", weil jeder Einzelfehler still
    auf ``rule-based generation`` zurueckfiel.

    Der ``#778``-Schutz in ``OasisProfileGenerator`` greift hier nicht: er
    verhindert nur, dass der ``.env``-Key zu einer *uebergebenen* Fremd-URL
    einspringt. Wird gar keine URL uebergeben, sind beide aus der ``.env`` —
    formal "dieselbe Quelle", sachlich die falsche.

    Issue #1418: ``codex_cli`` (transport="cli", #1405) hat by design weder
    ``base_url`` noch ``api_key`` — die dritte Rueckgabe traegt den
    Provider-Typ deshalb explizit weiter, statt ihn wie bisher stillschweigend
    zu verlieren. Ohne sie las ``OasisProfileGenerator`` ein fehlendes
    ``base_url`` als "nicht aufgeloest" und fuellte ``Config.LLM_BASE_URL``
    auf — das Modell aus der codex_cli-Route ging an den .env-HTTP-Endpoint
    (beobachtet: ``gpt-5.6-luna`` an ``https://api.minimax.io/v1`` → HTTP 400).

    Args:
        llm_runtime: Aufgeloeste Route oder Legacy-Runtime-Override.
        require: Wenn ``True`` (Default), ist eine nicht aufloesbare Route ein
            Fehler. ``False`` nur fuer Pfade, die bewusst ohne LLM laufen
            (``use_llm_for_profiles=False``) — dort ist regelbasiert das
            gewollte Ergebnis und kein Notbehelf.

    Raises:
        ValueError: ``require`` ist gesetzt und weder eine ``ResolvedRoute``
            noch ein aktiver Runtime-Override liegt vor, oder die
            ``ResolvedRoute`` selbst keine aufloesbare ``base_url_sanitized``
            traegt und ihr Provider keinen CLI-Transport nutzt (#1104: zweite
            Verteidigungslinie gegen die Halb-Uebergabe, falls der
            Store-Lookup in ``StageModelRouter`` keine Base-URL findet — z. B.
            eine deaktivierte oder geloeschte Connection).
    """
    if isinstance(llm_runtime, ResolvedRoute):
        base_url = llm_runtime.base_url_sanitized
        from .llm_provider_registry import LlmProviderRegistry

        definition = LlmProviderRegistry.connection_definition(llm_runtime.provider_id)
        provider_type = definition.provider_kind if definition else None
        is_cli_transport = definition is not None and definition.transport == "cli"
        if require and not base_url and not is_cli_transport:
            raise ValueError(
                f"kein Endpoint für Provider '{llm_runtime.provider_id}' aufgelöst: die "
                "Route nennt Modell und Provider, aber keine Basis-URL. Ohne Endpoint "
                "würde die Anfrage an die .env-Konfiguration statt an die konfigurierte "
                "Verbindung gehen, während Modell und Schlüssel aus der Route stammen — "
                "diese Mischung erreicht den falschen Provider. Bitte unter Einstellungen "
                f"→ LLM-Anbieter die Verbindung '{llm_runtime.provider_id}' prüfen."
            )
        return resolve_route_api_key(llm_runtime), base_url, provider_type
    if llm_runtime and llm_runtime.enabled:
        provider_type = PROVIDER_CODEX_CLI if llm_runtime.provider == PROVIDER_CODEX_CLI else None
        return llm_runtime.api_key, llm_runtime.base_url, provider_type
    if require:
        raise ValueError(
            "kein LLM-Provider aufgelöst: die Vorbereitung erwartet eine "
            "aufgelöste Route oder einen aktiven Runtime-Override. Ohne beides "
            "würden Endpoint und Schlüssel aus der .env stammen, während das "
            "Modell aus der Route kommt — diese Mischung erreicht den falschen "
            "Provider. Bitte unter Einstellungen → LLM-Anbieter eine aktive "
            "Verbindung wählen."
        )
    return None, None, None
