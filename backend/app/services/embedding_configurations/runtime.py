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

Warum ein Modellwechsel hier (noch) nicht durchgereicht wird
------------------------------------------------------------
Codex-Befund P1 auf PR #1498, verifiziert: Lese- und Schreibpfad haengen fest
am *unversionierten* Legacy-Index. ``storage/neo4j_write.py`` schreibt
``n.embedding``, ``storage/search_service.py`` fragt ``entity_embedding`` und
``fact_embedding`` ab. Der Migrationslauf legt daneben ``entity_embedding_v{N}``
mit Property ``embedding_v{N}`` an — die liest niemand. Es gibt also keinen
Cutover: eine abgeschlossene Migration schaltet den Betrieb nicht um.

Damit gilt: das Modell allein umzustellen, ohne den Index mitzunehmen, waere
schlimmer als der Zustand davor. Bei gleicher Dimension landen Vektoren zweier
Modelle im selben Index (genau die Korruption, die #1417 beschreibt), bei
abweichender Dimension gehen inkompatible Query-Vektoren an den Altindex.

Diese Aufloesung laesst deshalb nur eine Konfiguration durch, die zu dem passt,
was der aktive Index tatsaechlich enthaelt — und wirft sonst. Die GUI hoert
damit auf zu luegen: sie kann das Modell weiterhin nicht wechseln, sagt das aber
laut, statt es vorzutaeuschen. Der Wechsel selbst braucht den Index-Cutover
(Reads/Writes auf die Versionsnamen umstellen plus einen Umschaltschritt) und
bleibt Folgearbeit an #1417.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from ...utils.logger import get_logger

if TYPE_CHECKING:  # pragma: no cover - nur fuer die Signatur
    from ...contracts.embedding_contract import EmbeddingConfiguration

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


def resolve_operational_vector_dim() -> int:
    """Loest die kanonische Dimension des Betriebsindex auf (#1417, Slice 2.3).

    Nach einem abgeschlossenen Cutover (Slice 2.2) traegt die aktive
    ``EmbeddingIndexVersion`` die tatsaechliche Dimension des Index, den
    Reads und Writes ueber ``resolve_active_entity_index``/
    ``resolve_active_fact_index`` ansprechen. ``Config.VECTOR_DIM`` ist ein
    Env-Wert, der nach einer Migration auf ein Modell anderer Dimension
    stehen bleibt — er aendert sich nicht mit dem Cutover. Ohne aktive
    Indexversion (Legacy-/Bootstrap-Zustand, siehe
    ``resolve_active_entity_index``) bleibt ``Config.VECTOR_DIM`` die
    einzige Quelle, weil dann kein Nachweis ueber den Inhalt des
    vorhandenen Legacy-Index existiert, der ihn ersetzen koennte.
    """
    from ...config import Config
    from ..embedding_configuration_store import EmbeddingConfigurationStore

    active_index = EmbeddingConfigurationStore().get_active_index_version()
    if active_index is not None:
        return active_index.dimensions
    return Config.VECTOR_DIM


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

    _reject_unmigrated_model_switch(config)

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


def _reject_unmigrated_model_switch(config: "EmbeddingConfiguration") -> None:
    """Laesst nur durch, was zum tatsaechlichen Inhalt des aktiven Index passt.

    Siehe Modul-Docstring: Reads und Writes haengen am unversionierten
    Legacy-Index, und es gibt keinen Cutover auf die Versionsnamen. Ein
    Modellwechsel darf deshalb den Laufzeitpfad nicht erreichen.

    Zwei Faelle:

    * Es gibt eine aktive Indexversion — sie kennt das Modell, mit dem die
      gespeicherten Vektoren erzeugt wurden. Die Konfiguration muss dazu passen.
    * Es gibt keine — dann existiert kein Nachweis darueber, was im Legacy-Index
      steht, ausser der Legacy-Sicht selbst (``Config.EMBEDDING_MODEL``,
      ``Config.VECTOR_DIM``, siehe ``embedding_configurations/legacy.py``). Die
      Konfiguration muss dann dieser entsprechen.
    """
    from ...config import Config
    from ..embedding_configuration_store import EmbeddingConfigurationStore

    active_index = EmbeddingConfigurationStore().get_active_index_version()
    if active_index is not None:
        if (
            active_index.model_id == config.model_id
            and active_index.dimensions == config.dimensions
        ):
            return
        raise EmbeddingRuntimeConfigurationError(
            f"Aktive Embedding-Konfiguration {config.id} nutzt "
            f"{config.model_id!r} ({config.dimensions} Dim.), der aktive Index "
            f"v{active_index.version} enthaelt aber Vektoren von "
            f"{active_index.model_id!r} ({active_index.dimensions} Dim.). "
            "Lese- und Schreibpfad haengen weiterhin am unversionierten "
            "Legacy-Index — ein Modellwechsel wuerde Vektoren zweier Modelle "
            "vermischen. Der Index-Cutover fehlt (#1417)."
        )

    if (
        config.model_id == Config.EMBEDDING_MODEL
        and config.dimensions == Config.VECTOR_DIM
    ):
        return
    raise EmbeddingRuntimeConfigurationError(
        f"Aktive Embedding-Konfiguration {config.id} nutzt {config.model_id!r} "
        f"({config.dimensions} Dim.), die Legacy-Sicht meldet aber "
        f"{Config.EMBEDDING_MODEL!r} ({Config.VECTOR_DIM} Dim.) — und es gibt "
        "keine Indexversion, die belegen wuerde, womit der vorhandene Index "
        "gefuellt wurde. Ohne Index-Cutover (#1417) wuerde der Wechsel Vektoren "
        "zweier Modelle vermischen."
    )


__all__ = [
    "EmbeddingRuntimeConfigurationError",
    "ResolvedEmbeddingRoute",
    "resolve_active_embedding_route",
    "resolve_operational_vector_dim",
]
