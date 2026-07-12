"""Orchestriert Embedding-Probe und Lifecycle (Onboarding Slice 4.2).

Der ``EmbeddingConfigurationService`` ist die alleinige Schnittstelle
zwischen der API-Schicht, dem Store und den anbieter-spezifischen
Probe-Adaptern. Er fuehrt vier Aufgaben aus:

1. **Probe** — testet die Verbindung + Modell + Dimension, ohne Secrets
   zu loggen oder zu persistieren. Aktualisiert den Status der
   Konfiguration (``probed``, ``available``, ``unavailable`` etc.).
2. **Lifecycle-Wechsel** — schaltet eine Konfiguration auf ``active`` und
   markiert vorherige aktive Konfigurationen desselben Scopes als
   ``rolled_back``.
3. **Legacy-Sync** — liest die aktuelle ``Config.EMBEDDING_*``-Konfiguration
   ein und materialisiert eine kanonische ``EmbeddingConfiguration``, wenn
   noch keine aktive globale Konfiguration existiert.
4. **Eindeutigkeit** — pro ``scope`` (``global`` / ``project`` + project_id)
   ist hoechstens eine Konfiguration gleichzeitig ``active``. Diese Regel
   wird hier erzwungen, nicht im Vertrag, weil der Vertrag transiente
   Inkonsistenzen waehrend eines Switche erlaubt.

Secrets sind ausschliesslich im ``LlmProviderSecretsStore`` und werden
nur fuer den Probe-Aufruf an den Adapter durchgereicht — niemals in
die Konfiguration geschrieben.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from app.contracts.ai_provider_contract import ProviderConnection
from app.contracts.embedding_contract import (
    EmbeddingConfiguration,
    EmbeddingConfigurationStatus,
    EmbeddingProviderKind,
)
from app.services.embedding_configuration_store import EmbeddingConfigurationStore
from app.services.llm_provider_secrets_store import LlmProviderSecretsStore
from app.services.provider_connection_store import ProviderConnectionStore

from .adapters import (
    EmbeddingProbeAdapter,
    EmbeddingProbeResult,
    adapter_for_provider,
)

_PROBE_TO_STATUS: dict[str, EmbeddingConfigurationStatus] = {
    "available": "probed",
    "unavailable": "failed",
    "invalid_credentials": "failed",
    "degraded": "failed",
    "unsupported": "failed",
}


class EmbeddingConfigurationService:
    """Kapselt Probe, Lifecycle und Legacy-Sync."""

    def __init__(
        self,
        *,
        store: EmbeddingConfigurationStore,
        connection_store: ProviderConnectionStore,
        secrets_store: LlmProviderSecretsStore,
        adapter_factory: Callable[[EmbeddingProviderKind], EmbeddingProbeAdapter] = (
            adapter_for_provider
        ),
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._store = store
        self._connection_store = connection_store
        self._secrets_store = secrets_store
        self._adapter_factory = adapter_factory
        self._now = now

    # ------------------------------------------------------------------
    # Probe
    # ------------------------------------------------------------------

    def probe(
        self,
        configuration_id: str,
    ) -> tuple[EmbeddingConfiguration, EmbeddingProbeResult]:
        """Testet die Konfiguration und aktualisiert ihren Status.

        Wirft ``KeyError``, wenn die Konfiguration oder die zugehoerige
        ``ProviderConnection`` nicht existiert. Der Aufrufer (API-Layer)
        uebersetzt das in eine 404-Antwort.
        """
        config = self._store.get_configuration(configuration_id)
        if config is None:
            raise KeyError(f"Unbekannte Embedding-Konfiguration: {configuration_id}")
        connection = self._load_connection(config.provider_connection_id)
        api_key = (
            self._secrets_store.get_plaintext(connection.secret_ref)
            if connection.secret_ref
            else None
        )
        adapter = self._adapter_factory(config.provider_kind)
        result = adapter.probe(connection, config.model_id, api_key)

        # Status ableiten. Wenn die deklarierte Dimension nicht mit der
        # tatsaechlich gelieferten uebereinstimmt, ist die Konfiguration
        # "degraded" — wir koennen den Service nicht starten, ohne die
        # Konsistenz zu verletzen.
        new_status = _PROBE_TO_STATUS[result.status]
        status_message: str | None = result.status_message
        if (
            result.status == "available"
            and result.actual_dimensions is not None
            and result.actual_dimensions != config.dimensions
        ):
            new_status = "failed"
            status_message = (
                f"deklarierte Dimension {config.dimensions} weicht von "
                f"tatsaechlicher Dimension {result.actual_dimensions} ab"
            )

        last_validated_at = (
            self._now() if new_status == "probed" else None
        )
        updated = self._store.update_configuration_status(
            configuration_id,
            status=new_status,
            status_message=status_message,
            last_validated_at=last_validated_at,
        )
        return updated, result

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def activate(self, configuration_id: str) -> EmbeddingConfiguration:
        """Macht eine Konfiguration zur aktiven Konfiguration ihres Scopes.

        Vorhandene aktive Konfigurationen desselben Scopes werden auf
        ``rolled_back`` gesetzt. Das ist der einzige Weg, eine
        Konfiguration in den ``active``-Zustand zu bringen.
        """
        config = self._store.get_configuration(configuration_id)
        if config is None:
            raise KeyError(f"Unbekannte Embedding-Konfiguration: {configuration_id}")
        if config.status == "failed":
            raise ValueError(
                "Failed-Konfiguration kann nicht aktiviert werden; "
                "erst erfolgreichen Probe durchfuehren."
            )
        for other in self._store.list_configurations(scope=config.scope):
            if (
                other.id != config.id
                and other.status == "active"
                and other.project_id == config.project_id
            ):
                self._store.update_configuration_status(
                    other.id,
                    status="rolled_back",
                    status_message=(
                        f"abgeloest durch {config.id} am {self._now().isoformat()}"
                    ),
                )
        return self._store.update_configuration_status(
            configuration_id,
            status="active",
            status_message=None,
            last_validated_at=self._now(),
        )

    def rollback(self, configuration_id: str) -> EmbeddingConfiguration:
        """Markiert eine Konfiguration als ``rolled_back``.

        Operator-Entscheidung; der Slice-3-Stil ist hier analog.
        """
        config = self._store.get_configuration(configuration_id)
        if config is None:
            raise KeyError(f"Unbekannte Embedding-Konfiguration: {configuration_id}")
        return self._store.update_configuration_status(
            configuration_id,
            status="rolled_back",
            status_message=f"Operator-Rollback am {self._now().isoformat()}",
        )

    # ------------------------------------------------------------------
    # Legacy-Sync
    # ------------------------------------------------------------------

    def sync_legacy(
        self,
        *,
        provider_connection_id: str,
        provider_kind: EmbeddingProviderKind,
        model_id: str,
        dimensions: int,
    ) -> EmbeddingConfiguration | None:
        """Liest die Legacy-``Config.EMBEDDING_*``-Werte in eine kanonische
        Konfiguration. Tut nichts, wenn bereits eine aktive globale
        Konfiguration existiert.

        Gibt die synchronisierte Konfiguration zurueck, oder ``None``,
        wenn der Sync uebersprungen wurde (weil schon eine andere
        aktive Konfiguration existiert).
        """
        if self._store.get_active_global_configuration() is not None:
            return None
        config = self._store.upsert_configuration(
            configuration_id=None,
            provider_connection_id=provider_connection_id,
            provider_kind=provider_kind,
            model_id=model_id,
            dimensions=dimensions,
            scope="global",
            project_id=None,
            status="proposed",
            status_message="aus Config.EMBEDDING_* uebernommen",
        )
        return config

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_connection(self, connection_id: str) -> ProviderConnection:
        for connection in self._connection_store.list_connections():
            if connection.id == connection_id:
                return connection
        raise KeyError(
            f"Provider-Connection fuer Embedding-Konfiguration fehlt: {connection_id}"
        )


__all__ = [
    "EmbeddingConfigurationService",
    "EmbeddingProbeResult",
]
