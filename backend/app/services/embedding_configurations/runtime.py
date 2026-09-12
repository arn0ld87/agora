"""Aufloesung der *aktiven* Embedding-Konfiguration fuer den Laufzeitpfad (#1417).

Das Problem
-----------
``EmbeddingConfigurationStore``, ``EmbeddingConfigurationService``, die API und
die Settings-Ansicht existierten vollstaendig: man konnte dort eine
Konfiguration anlegen, proben und aktivieren — und der laufende Betrieb aenderte
sich dadurch nicht. ``EmbeddingService()`` ohne Argumente las ausschliesslich
``Config.EMBEDDING_MODEL``/``_BASE_URL``/``_API_KEY`` aus der Umgebung, und
genau so konstruieren ihn beide produktiven Consumer
(``storage/neo4j_storage.py``, ``services/report_agent/evidence.py``).
Verdrahtet war der Store nur fuer den Migrationslauf.

Das ist mehr als Kosmetik: der Migrationslauf bettet gegen die
Store-Konfiguration neu ein, der anschliessende Betrieb gegen die Env. Stimmen
beide nicht ueberein, entstehen Vektoren zweier verschiedener Modelle im selben
Index — und der Dimensionswaechter (``_ensure_vector_index_dim``, #263) faengt
nur den Dimensionswechsel, nicht den Modellwechsel bei gleicher Dimension
(``text-embedding-3-small`` und ``text-embedding-ada-002`` sind beide 1536).

Die Aufloesung
--------------
Store -> ProviderConnection -> Secret-Store, und erst wenn *keine* aktive
Konfiguration existiert, die Legacy-Sicht aus ``Config.*``. Die Env bleibt damit
der Startzustand, hoert aber auf, die einzige Wahrheit zu sein.

Warum eine unvollstaendige aktive Konfiguration wirft statt zurueckzufallen
--------------------------------------------------------------------------
Eine aktive Konfiguration, deren Connection fehlt oder deaktiviert ist, ist
keine Abwesenheit von Konfiguration — sie ist eine kaputte. Auf ``Config.*``
zurueckzufallen hiesse, Modell aus dem Store und Endpoint aus der ``.env`` zu
mischen: dieselbe stille Provider-Vertauschung, gegen die
``prepare_llm._resolve_llm_connection`` auf der Chat-Seite absichert. Lieber ein
lauter Fehler, der auf die Einstellungen zeigt, als ein Index aus zwei
Vektorraeumen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ...utils.logger import get_logger

logger = get_logger("agora.embedding.runtime")


class EmbeddingRuntimeConfigurationError(RuntimeError):
    """Die aktive Embedding-Konfiguration ist nicht aufloesbar."""


@dataclass(frozen=True)
class ResolvedEmbeddingRoute:
    """Vollstaendige Embedding-Route: Modell, Endpoint und Schluessel aus einer Quelle."""

    model: str
    base_url: str
    api_key: Optional[str]
    configuration_id: str
    dimensions: int


def resolve_active_embedding_route() -> Optional[ResolvedEmbeddingRoute]:
    """Loest die aktive globale Embedding-Konfiguration auf.

    Returns:
        ``None``, wenn keine aktive Konfiguration existiert — dann gilt die
        Legacy-Sicht aus ``Config.*`` wie bisher.

    Raises:
        EmbeddingRuntimeConfigurationError: Eine aktive Konfiguration existiert,
            laesst sich aber nicht vollstaendig aufloesen (Connection fehlt,
            ist deaktiviert oder traegt keine Base-URL).
    """
    from ..embedding_configuration_store import EmbeddingConfigurationStore
    from ..provider_connection_store import ProviderConnectionStore

    config = EmbeddingConfigurationStore().get_active_global_configuration()
    if config is None:
        return None

    connection = next(
        (
            candidate
            for candidate in ProviderConnectionStore().list_connections()
            if candidate.id == config.provider_connection_id
        ),
        None,
    )
    if connection is None:
        raise EmbeddingRuntimeConfigurationError(
            f"Aktive Embedding-Konfiguration {config.id} verweist auf die "
            f"unbekannte Verbindung {config.provider_connection_id!r}. Bitte unter "
            "Einstellungen → Embedding-Konfiguration eine gültige Verbindung "
            "wählen oder die Konfiguration zurückrollen."
        )
    if not connection.enabled:
        raise EmbeddingRuntimeConfigurationError(
            f"Aktive Embedding-Konfiguration {config.id} nutzt die deaktivierte "
            f"Verbindung {connection.id!r}. Ein Rückfall auf die .env-Werte würde "
            "das Modell aus dem Store mit einem fremden Endpoint mischen."
        )
    if not connection.base_url:
        raise EmbeddingRuntimeConfigurationError(
            f"Verbindung {connection.id!r} der aktiven Embedding-Konfiguration "
            f"{config.id} hat keine Basis-URL. Ohne Endpoint würde die Anfrage an "
            "die .env-Konfiguration gehen, während das Modell aus dem Store kommt."
        )

    api_key = None
    if connection.secret_ref:
        from ..llm_provider_secrets_store import get_llm_provider_secrets_store

        api_key = get_llm_provider_secrets_store().get_plaintext(connection.secret_ref)

    logger.info(
        "Embedding-Route aus dem Store aufgeloest: config=%s model=%s connection=%s",
        config.id, config.model_id, connection.id,
    )
    return ResolvedEmbeddingRoute(
        model=config.model_id,
        base_url=str(connection.base_url),
        api_key=api_key,
        configuration_id=config.id,
        dimensions=config.dimensions,
    )


__all__ = [
    "EmbeddingRuntimeConfigurationError",
    "ResolvedEmbeddingRoute",
    "resolve_active_embedding_route",
]
