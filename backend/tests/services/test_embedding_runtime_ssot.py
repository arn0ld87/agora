"""Regression #1417: die aktive Embedding-Konfiguration steuert den Laufzeitpfad.

Root Cause: ``EmbeddingService()`` ohne Argumente las ausschliesslich
``Config.EMBEDDING_MODEL``/``_BASE_URL``/``_API_KEY``. Genau so konstruieren ihn
beide produktiven Consumer (``storage/neo4j_storage.py:69``,
``services/report_agent/evidence.py:239``). Die GUI konnte eine Konfiguration
anlegen, proben und aktivieren, ohne dass sich am laufenden Betrieb etwas
aenderte — verdrahtet war der Store nur fuer den Migrationslauf.

Das ist mehr als Kosmetik: der Migrationslauf bettet gegen die
Store-Konfiguration neu ein, der Betrieb gegen die Env. Bei zwei Modellen
gleicher Dimension faengt der Dimensionswaechter (#263) den Unterschied nicht —
es entstehen Vektoren zweier Modelle im selben Index.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

import pytest

from app.services.embedding_configurations import runtime as runtime_module
from app.services.embedding_configurations.runtime import (
    EmbeddingRuntimeConfigurationError,
    resolve_active_embedding_route,
)


@dataclass
class _Config:
    id: str = "cfg_active"
    provider_connection_id: str = "conn_1"
    model_id: str = "text-embedding-3-small"
    dimensions: int = 1536


@dataclass
class _Connection:
    id: str = "conn_1"
    base_url: Optional[str] = "https://api.example.test/v1"
    enabled: bool = True
    secret_ref: Optional[str] = None


def _install(monkeypatch, *, config: Any, connections: List[Any], secret: str = "sk-store") -> None:
    monkeypatch.setattr(
        "app.services.embedding_configuration_store.EmbeddingConfigurationStore",
        lambda: type("S", (), {"get_active_global_configuration": lambda _s: config})(),
    )
    monkeypatch.setattr(
        "app.services.provider_connection_store.ProviderConnectionStore",
        lambda: type("P", (), {"list_connections": lambda _s: connections})(),
    )
    monkeypatch.setattr(
        "app.services.llm_provider_secrets_store.get_llm_provider_secrets_store",
        lambda: type("K", (), {"get_plaintext": lambda _s, _ref: secret})(),
    )


class TestResolution:
    def test_active_configuration_wins_over_the_env(self, monkeypatch) -> None:
        _install(monkeypatch, config=_Config(), connections=[_Connection()])

        route = resolve_active_embedding_route()

        assert route is not None
        assert route.model == "text-embedding-3-small"
        assert route.base_url == "https://api.example.test/v1"
        assert route.configuration_id == "cfg_active"

    def test_secret_ref_is_resolved_from_the_secret_store(self, monkeypatch) -> None:
        _install(
            monkeypatch,
            config=_Config(),
            connections=[_Connection(secret_ref="ref_1")],
            secret="sk-from-store",
        )

        assert resolve_active_embedding_route().api_key == "sk-from-store"

    def test_no_active_configuration_keeps_the_legacy_env_view(self, monkeypatch) -> None:
        _install(monkeypatch, config=None, connections=[])

        assert resolve_active_embedding_route() is None


class TestBrokenActiveConfigurationIsLoud:
    """Eine aktive Konfiguration, deren Connection fehlt, ist keine Abwesenheit
    von Konfiguration — sie ist eine kaputte. Ein Rueckfall auf ``Config.*``
    wuerde Modell aus dem Store mit dem Endpoint aus der .env mischen."""

    def test_missing_connection_raises(self, monkeypatch) -> None:
        _install(monkeypatch, config=_Config(), connections=[])

        with pytest.raises(EmbeddingRuntimeConfigurationError, match="unbekannte Verbindung"):
            resolve_active_embedding_route()

    def test_disabled_connection_raises(self, monkeypatch) -> None:
        _install(monkeypatch, config=_Config(), connections=[_Connection(enabled=False)])

        with pytest.raises(EmbeddingRuntimeConfigurationError, match="deaktivierte"):
            resolve_active_embedding_route()

    def test_connection_without_base_url_raises(self, monkeypatch) -> None:
        _install(monkeypatch, config=_Config(), connections=[_Connection(base_url=None)])

        with pytest.raises(EmbeddingRuntimeConfigurationError, match="keine Basis-URL"):
            resolve_active_embedding_route()


class TestEmbeddingServiceUsesTheStore:
    """Der eigentliche Befund: der argumentlose Konstruktor."""

    def test_argumentless_service_takes_model_and_endpoint_from_the_store(
        self, monkeypatch
    ) -> None:
        from app.storage.embedding_service import EmbeddingService

        monkeypatch.setattr(
            runtime_module,
            "resolve_active_embedding_route",
            lambda: runtime_module.ResolvedEmbeddingRoute(
                model="text-embedding-3-small",
                base_url="https://api.example.test/v1",
                api_key="sk-store",
                configuration_id="cfg_active",
                dimensions=1536,
            ),
        )

        service = EmbeddingService()

        assert service.model == "text-embedding-3-small"
        assert service.base_url == "https://api.example.test/v1"
        assert service.api_key == "sk-store"

    def test_explicit_arguments_still_win(self, monkeypatch) -> None:
        """Der Migrationslauf übergibt seine Route ausdrücklich — die darf der
        Store nicht überschreiben."""
        from app.storage.embedding_service import EmbeddingService

        monkeypatch.setattr(
            runtime_module,
            "resolve_active_embedding_route",
            lambda: runtime_module.ResolvedEmbeddingRoute(
                model="store-model",
                base_url="https://store.example.test/v1",
                api_key="sk-store",
                configuration_id="cfg_active",
                dimensions=1536,
            ),
        )

        service = EmbeddingService(
            model="explicit-model", base_url="https://explicit.example.test/v1", api_key="sk-x"
        )

        assert service.model == "explicit-model"
        assert service.base_url == "https://explicit.example.test/v1"
        assert service.api_key == "sk-x"

    def test_without_an_active_configuration_the_env_still_applies(
        self, monkeypatch
    ) -> None:
        from app.config import Config
        from app.storage.embedding_service import EmbeddingService

        monkeypatch.setattr(runtime_module, "resolve_active_embedding_route", lambda: None)
        monkeypatch.setattr(Config, "EMBEDDING_MODEL", "env-model")
        monkeypatch.setattr(Config, "EMBEDDING_BASE_URL", "http://localhost:11434")
        monkeypatch.setattr(Config, "EMBEDDING_API_KEY", "")

        service = EmbeddingService()

        assert service.model == "env-model"
        assert service.base_url == "http://localhost:11434"

    def test_a_broken_active_configuration_does_not_silently_fall_back(
        self, monkeypatch
    ) -> None:
        from app.storage.embedding_service import EmbeddingService

        def _boom():
            raise EmbeddingRuntimeConfigurationError("Verbindung fehlt")

        monkeypatch.setattr(runtime_module, "resolve_active_embedding_route", _boom)

        with pytest.raises(EmbeddingRuntimeConfigurationError):
            EmbeddingService()


class TestActivateRejectsDimensionChangeWithoutMigration:
    """Issue #1417, Punkt 2: ein Klick darf das Modell nicht unter den
    vorhandenen Vektoren wegtauschen."""

    @staticmethod
    def _service(*, active_dim: int, versions: List[Any], config_dim: int):
        from app.services.embedding_configurations.service import (
            EmbeddingConfigurationService,
        )

        @dataclass
        class _Cfg:
            id: str = "cfg_new"
            scope: str = "global"
            project_id: Optional[str] = None
            status: str = "probed"
            dimensions: int = config_dim

        @dataclass
        class _Index:
            version: int
            dimensions: int

        class _Store:
            def __init__(self) -> None:
                self.status_updates: List[tuple] = []

            def get_configuration(self, _id):
                return _Cfg()

            def get_active_index_version(self):
                return _Index(version=1, dimensions=active_dim) if active_dim else None

            def list_index_versions(self):
                return versions

            def list_configurations(self, *, scope=None):
                return []

            def update_configuration_status(self, cid, **kw):
                self.status_updates.append((cid, kw))
                return _Cfg(status="active")

        store = _Store()
        service = EmbeddingConfigurationService(
            store=store, connection_store=object(), secrets_store=object()
        )
        return service, store

    def test_dimension_change_without_a_matching_index_is_rejected(self) -> None:
        from dataclasses import dataclass as _dc

        @_dc
        class _Index:
            version: int
            dimensions: int

        service, store = self._service(
            active_dim=768, versions=[_Index(1, 768)], config_dim=1536
        )

        with pytest.raises(ValueError, match="Dimensionen"):
            service.activate("cfg_new")
        assert store.status_updates == []

    def test_dimension_change_after_a_migration_is_allowed(self) -> None:
        from dataclasses import dataclass as _dc

        @_dc
        class _Index:
            version: int
            dimensions: int

        service, store = self._service(
            active_dim=768, versions=[_Index(1, 768), _Index(2, 1536)], config_dim=1536
        )

        service.activate("cfg_new")

        assert store.status_updates

    def test_same_dimension_stays_allowed(self) -> None:
        from dataclasses import dataclass as _dc

        @_dc
        class _Index:
            version: int
            dimensions: int

        service, store = self._service(
            active_dim=1536, versions=[_Index(1, 1536)], config_dim=1536
        )

        service.activate("cfg_new")

        assert store.status_updates

    def test_first_activation_without_any_index_is_allowed(self) -> None:
        service, store = self._service(active_dim=0, versions=[], config_dim=1536)

        service.activate("cfg_new")

        assert store.status_updates
