"""Kanonische, secret-freie Provider-Probes und Model-Discovery-Adapter.

Protokollentscheidungen sind gegen die Primaerdokumentation verifiziert:

* OpenAI: https://developers.openai.com/api/reference/resources/models/methods/list
  dokumentiert ``GET /v1/models`` mit Bearer-Auth.
* Anthropic: https://platform.claude.com/docs/en/api/models/list dokumentiert
  ``GET /v1/models`` mit ``X-Api-Key`` und ``anthropic-version: 2023-06-01``.
* Gemini: https://ai.google.dev/gemini-api/docs/openai dokumentiert
  ``/v1beta/openai/models`` mit Bearer-Auth.
* MiniMax: https://platform.minimax.io/docs/api-reference/models/openai/list-models
  dokumentiert ``GET /v1/models`` mit Bearer-Auth.
* Ollama Cloud: https://docs.ollama.com/cloud dokumentiert ``/api/tags`` auf
  ollama.com mit Bearer-Auth; lokal verwendet derselbe Tags-Endpunkt keine Auth:
  https://docs.ollama.com/api/tags.
* OpenCode Go veroeffentlicht zwar eine Modell-URL, dokumentiert aber in der
  Go-Referenz keinen Header-Vertrag fuer einen direkten Probe-Request. Es bleibt
  daher bewusst ``unsupported`` statt eine Auth-Semantik zu erraten.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from app.contracts.ai_provider_contract import AiModel, ProviderConnection
from app.services.model_catalog_service import CatalogHttpResponse, fetch_catalog_json

ProviderProbeStatus = Literal[
    "available", "unavailable", "invalid_credentials", "degraded", "unsupported"
]
CatalogGetter = Callable[[str], CatalogHttpResponse]


@dataclass(frozen=True)
class ProviderProbeResult:
    """Normiertes Resultat ohne Transportdetails oder Secret-Werte."""

    status: ProviderProbeStatus
    status_message: str | None
    models: tuple[AiModel, ...] = ()


class ProviderConnectionAdapter(Protocol):
    def probe(
        self, connection: ProviderConnection, api_key: str | None
    ) -> ProviderProbeResult: ...


@dataclass(frozen=True)
class _AdapterProtocol:
    endpoint_path: str
    response_field: Literal["data", "models"]
    auth: Literal["bearer", "anthropic", "none"]


_PROTOCOLS: dict[str, _AdapterProtocol] = {
    "openai": _AdapterProtocol("/models", "data", "bearer"),
    "anthropic": _AdapterProtocol("/v1/models", "data", "anthropic"),
    "google": _AdapterProtocol("/models", "data", "bearer"),
    "minimax": _AdapterProtocol("/models", "data", "bearer"),
    "ollama_cloud": _AdapterProtocol("/api/tags", "models", "bearer"),
    "openai_compatible": _AdapterProtocol("/models", "data", "bearer"),
    "ollama": _AdapterProtocol("/api/tags", "models", "none"),
}


class _HttpModelsAdapter:
    def __init__(
        self,
        protocol: _AdapterProtocol,
        *,
        get_json: Callable[..., CatalogHttpResponse] = fetch_catalog_json,
    ) -> None:
        self._protocol = protocol
        self._get_json = get_json

    def probe(
        self, connection: ProviderConnection, api_key: str | None
    ) -> ProviderProbeResult:
        headers = self._headers(api_key)
        if headers is None:
            return ProviderProbeResult(
                status="invalid_credentials", status_message="API-Schluessel fehlt"
            )
        base_url = connection.base_url
        if not base_url:
            return ProviderProbeResult(
                status="unavailable", status_message="Base-URL fehlt"
            )
        try:
            response = self._get_json(
                f"{base_url.rstrip('/')}{self._protocol.endpoint_path}", headers=headers
            )
        except Exception:  # noqa: BLE001 - third-party transport boundary
            return ProviderProbeResult(
                status="unavailable", status_message="Modell-Discovery nicht erreichbar"
            )
        status = _status_from_http(response.status_code)
        if status != "available":
            return ProviderProbeResult(status=status, status_message=_message_for(status))
        model_ids = _model_ids(response.payload, self._protocol.response_field)
        return ProviderProbeResult(
            status="available",
            status_message=None,
            models=tuple(_ai_model(connection, model_id) for model_id in model_ids),
        )

    def _headers(self, api_key: str | None) -> dict[str, str] | None:
        if self._protocol.auth == "none":
            return {}
        if not api_key:
            return None
        if self._protocol.auth == "anthropic":
            return {"X-Api-Key": api_key, "anthropic-version": "2023-06-01"}
        return {"Authorization": f"Bearer {api_key}"}


class _UnsupportedAdapter:
    def probe(
        self, connection: ProviderConnection, api_key: str | None
    ) -> ProviderProbeResult:
        return ProviderProbeResult(
            status="unsupported",
            status_message="OpenCode Go ist in diesem Slice nicht unterstützt",
        )


def adapter_for_connection(
    provider_kind: str,
    *,
    get_json: Callable[..., CatalogHttpResponse] = fetch_catalog_json,
) -> ProviderConnectionAdapter:
    """Erzeugt den einzigen Discovery-Pfad fuer einen Provider-Typ."""
    # Die Registry ist die einzige Matrix fuer Provider-Kind und Adapter-Fabrik;
    # dieses Modul enthaelt nur die Protokollimplementierungen.
    from app.services.llm_provider_registry import LlmProviderRegistry

    definition = LlmProviderRegistry.connection_definition(provider_kind)
    if definition is None or definition.adapter_kind == "unsupported":
        return _UnsupportedAdapter()
    protocol = _PROTOCOLS.get(definition.adapter_kind)
    if protocol is None:
        return _UnsupportedAdapter()
    return _HttpModelsAdapter(protocol, get_json=get_json)


def _model_ids(
    payload: Mapping[str, object] | None, response_field: Literal["data", "models"]
) -> tuple[str, ...]:
    if not payload:
        return ()
    raw_models = payload.get(response_field)
    if not isinstance(raw_models, list):
        return ()
    key = "id" if response_field == "data" else "name"
    return tuple(
        item[key]
        for item in raw_models
        if isinstance(item, Mapping) and isinstance(item.get(key), str) and item[key]
    )


def _ai_model(connection: ProviderConnection, model_id: str) -> AiModel:
    return AiModel(
        provider_connection_id=connection.id,
        model_id=model_id,
        display_name=model_id,
        source="live",
        status="available",
        local_or_cloud="local" if connection.provider_kind == "ollama" else "cloud",
    )


def _status_from_http(status_code: int | None) -> ProviderProbeStatus:
    if status_code == 200:
        return "available"
    if status_code in {401, 403}:
        return "invalid_credentials"
    if status_code == 429:
        return "degraded"
    return "unavailable"


def _message_for(status: ProviderProbeStatus) -> str:
    return {
        "invalid_credentials": "Anmeldung abgelehnt",
        "degraded": "Anbieter ist ausgelastet",
        "unavailable": "Modell-Discovery nicht erreichbar",
    }.get(status, "Provider wird nicht unterstützt")
