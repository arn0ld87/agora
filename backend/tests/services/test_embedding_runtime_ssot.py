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
from typing import Any, Dict, List, Optional

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
class _IndexVersion:
    version: int = 1
    model_id: str = "text-embedding-3-small"
    dimensions: int = 1536


_MATCHING_INDEX = object()


@dataclass
class _Connection:
    id: str = "conn_1"
    base_url: Optional[str] = "https://api.example.test/v1"
    enabled: bool = True
    secret_ref: Optional[str] = None


def _install(
    monkeypatch,
    *,
    config: Any,
    connections: List[Any],
    secret: str = "sk-store",
    index: Any = _MATCHING_INDEX,
) -> None:
    """Verdrahtet die drei Stores.

    ``index`` ist per Default eine aktive Indexversion, die zur Konfiguration
    passt — sonst greift der Riegel gegen den unmigrierten Modellwechsel und
    jeder Aufloesungstest wuerde an ihm scheitern statt an dem, was er prueft.
    """
    if index is _MATCHING_INDEX:
        index = (
            None
            if config is None
            else _IndexVersion(model_id=config.model_id, dimensions=config.dimensions)
        )
    monkeypatch.setattr(
        "app.services.embedding_configuration_store.EmbeddingConfigurationStore",
        lambda: type(
            "S",
            (),
            {
                "get_active_global_configuration": lambda _s: config,
                "get_active_index_version": lambda _s: index,
            },
        )(),
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


class TestUnmigratedModelSwitchIsRejected:
    """Codex-Befund P1 auf PR #1498, verifiziert.

    Lese- und Schreibpfad haengen am *unversionierten* Legacy-Index:
    ``storage/neo4j_write.py`` schreibt ``n.embedding``,
    ``storage/search_service.py`` fragt ``entity_embedding``/``fact_embedding``
    ab. Der Migrationslauf legt daneben ``entity_embedding_v{N}`` an, das liest
    niemand — es gibt keinen Cutover. Die Konfiguration darf den Laufzeitpfad
    deshalb nur erreichen, wenn sie zu dem passt, was im aktiven Index
    tatsaechlich steht.
    """

    def test_configuration_matching_the_active_index_passes(self, monkeypatch) -> None:
        _install(
            monkeypatch,
            config=_Config(model_id="text-embedding-3-small", dimensions=1536),
            connections=[_Connection()],
            index=_IndexVersion(model_id="text-embedding-3-small", dimensions=1536),
        )

        assert resolve_active_embedding_route().model == "text-embedding-3-small"

    def test_model_switch_at_equal_dimensions_raises(self, monkeypatch) -> None:
        """Genau der Fall, den der Dimensionswaechter (#263) nicht faengt:
        ``ada-002`` und ``3-small`` haben beide 1536 Dimensionen."""
        _install(
            monkeypatch,
            config=_Config(model_id="text-embedding-ada-002", dimensions=1536),
            connections=[_Connection()],
            index=_IndexVersion(model_id="text-embedding-3-small", dimensions=1536),
        )

        with pytest.raises(EmbeddingRuntimeConfigurationError, match="Index-Cutover fehlt"):
            resolve_active_embedding_route()

    def test_dimension_switch_against_the_active_index_raises(self, monkeypatch) -> None:
        _install(
            monkeypatch,
            config=_Config(model_id="nomic-embed-text", dimensions=768),
            connections=[_Connection()],
            index=_IndexVersion(model_id="text-embedding-3-small", dimensions=1536),
        )

        with pytest.raises(EmbeddingRuntimeConfigurationError, match="Index-Cutover fehlt"):
            resolve_active_embedding_route()

    def test_without_an_index_version_the_legacy_view_decides(self, monkeypatch) -> None:
        """``legacy.py`` legt keinen ``EmbeddingIndexVersion``-Datensatz an. Ohne
        einen solchen ist ``Config.*`` der einzige Nachweis darueber, womit der
        vorhandene Index gefuellt wurde."""
        from app.config import Config

        monkeypatch.setattr(Config, "EMBEDDING_MODEL", "legacy-model")
        monkeypatch.setattr(Config, "VECTOR_DIM", 1536)
        _install(
            monkeypatch,
            config=_Config(model_id="legacy-model", dimensions=1536),
            connections=[_Connection()],
            index=None,
        )

        assert resolve_active_embedding_route().model == "legacy-model"

    def test_without_an_index_version_a_deviating_model_raises(self, monkeypatch) -> None:
        from app.config import Config

        monkeypatch.setattr(Config, "EMBEDDING_MODEL", "legacy-model")
        monkeypatch.setattr(Config, "VECTOR_DIM", 1536)
        _install(
            monkeypatch,
            config=_Config(model_id="text-embedding-3-small", dimensions=1536),
            connections=[_Connection()],
            index=None,
        )

        with pytest.raises(EmbeddingRuntimeConfigurationError, match="Index-Cutover"):
            resolve_active_embedding_route()

    def test_the_guard_runs_before_the_secret_is_read(self, monkeypatch) -> None:
        """Ein Schluessel, der fuer eine abgelehnte Route entschluesselt wird, ist
        ein unnoetig entpackte Geheimnis."""
        reads: List[str] = []

        _install(
            monkeypatch,
            config=_Config(model_id="text-embedding-ada-002", dimensions=1536),
            connections=[_Connection(secret_ref="ref_1")],
            index=_IndexVersion(model_id="text-embedding-3-small", dimensions=1536),
        )
        monkeypatch.setattr(
            "app.services.llm_provider_secrets_store.get_llm_provider_secrets_store",
            lambda: type(
                "K",
                (),
                {"get_plaintext": lambda _s, ref: reads.append(ref) or "sk"},
            )(),
        )

        with pytest.raises(EmbeddingRuntimeConfigurationError):
            resolve_active_embedding_route()
        assert reads == []


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


class TestValidateEmbeddingConfigurationFollowsTheRoute:
    """Befund 3 (Review PR #1498): ``validate_embedding_configuration`` folgte
    vor der Korrektur nicht der aktiven Store-Konfiguration, sondern reichte
    immer ``Config.EMBEDDING_MODEL``/``_BASE_URL``/``_API_KEY`` *ausdruecklich*
    an ``EmbeddingService`` durch (siehe ``effective_model = model or
    Config.EMBEDDING_MODEL`` vor der Korrektur — die Store-Aufloesung wurde
    dabei nie befragt). Die Startup-Probe validierte damit das Env-Modell,
    waehrend der Betrieb (``EmbeddingService()`` ohne Argumente,
    ``storage/neo4j_storage.py`` + ``services/report_agent/evidence.py``)
    gegen das Store-Modell einbettete. Diese Klasse sichert die seither
    geltende Praezedenz: ausdrueckliche Argumente > aktive Store-Konfiguration
    > ``Config.*``. ``vector_dim`` folgt einer eigenen Praezedenz (#1417,
    Slice 2.3): nicht der zu pruefenden Route (das waere eine Tautologie),
    sondern ``resolve_operational_vector_dim()`` — aktive Indexversion, wenn
    vorhanden, sonst ``Config.VECTOR_DIM`` als Legacy-Ansicht.
    """

    @staticmethod
    def _capture_embed(monkeypatch, captured: Dict[str, Any], vector_len: int) -> None:
        """Ersetzt ``EmbeddingService.embed`` durch einen Spion statt eines
        echten Netzwerkaufrufs — haelt fest, mit welchem model/base_url/api_key
        die Probe tatsaechlich konstruiert wurde, ohne dafuer ein Netzwerk zu
        brauchen."""

        def fake_embed(self, text):  # noqa: ANN001 — Spion, keine echte API
            captured["model"] = self.model
            captured["base_url"] = self.base_url
            captured["api_key"] = self.api_key
            return [0.0] * vector_len

        monkeypatch.setattr(
            "app.storage.embedding_service.EmbeddingService.embed", fake_embed
        )

    def test_store_configuration_wins_over_config_when_args_are_missing(
        self, monkeypatch
    ) -> None:
        """Kernbefund: fehlen ``model``/``base_url``, muss die aktive
        Store-Route gewinnen, nicht ``Config.*``. Unter dem alten Code haette
        ``effective_model`` hier ``"env-model"`` ergeben (Config-Fallback ohne
        je die Route zu befragen) — der Test waere rot."""
        from app.config import Config
        from app.storage.embedding_service import validate_embedding_configuration

        monkeypatch.setattr(
            runtime_module,
            "resolve_active_embedding_route",
            lambda: runtime_module.ResolvedEmbeddingRoute(
                model="store-custom-model",
                base_url="https://store.example.test/v1",
                api_key="sk-store",
                configuration_id="cfg_active",
                dimensions=1536,
            ),
        )
        monkeypatch.setattr(Config, "EMBEDDING_MODEL", "env-model")
        monkeypatch.setattr(Config, "EMBEDDING_BASE_URL", "http://env-host:11434")
        monkeypatch.setattr(Config, "EMBEDDING_API_KEY", "env-key")
        monkeypatch.setattr(Config, "VECTOR_DIM", 42)

        captured: Dict[str, Any] = {}
        self._capture_embed(monkeypatch, captured, vector_len=42)

        actual_dim = validate_embedding_configuration()

        assert captured == {
            "model": "store-custom-model",
            "base_url": "https://store.example.test/v1",
            "api_key": "sk-store",
        }
        assert actual_dim == 42

    def test_vector_dim_is_not_taken_from_the_route(self, monkeypatch) -> None:
        """``vector_dim`` wird nicht aus der zu pruefenden Route genommen
        (Docstring von ``validate_embedding_configuration``): eine aktive
        Route mit einem Modell bekannter Dimension darf die Abweichung vom
        Betriebsindex nicht verschweigen. Ohne aktive Indexversion (dieser
        Test setzt keine) loest ``resolve_operational_vector_dim()`` auf
        ``Config.VECTOR_DIM`` auf — dieselbe Legacy-Ansicht wie vor Slice
        2.3. Unter dem alten Code (Route wurde nie befragt, ``effective_model``
        blieb bei ``Config.EMBEDDING_MODEL`` ohne bekannte Dimension) haette
        dieser Fall gar keine Exception ausgeloest — der Test waere rot."""
        from app.config import Config
        from app.storage.embedding_service import validate_embedding_configuration

        monkeypatch.setattr(
            runtime_module,
            "resolve_active_embedding_route",
            lambda: runtime_module.ResolvedEmbeddingRoute(
                model="qwen3-embedding:4b",  # bekannte Dimension: 2560
                base_url="https://store.example.test/v1",
                api_key="sk-store",
                configuration_id="cfg_active",
                dimensions=2560,
            ),
        )
        monkeypatch.setattr(Config, "EMBEDDING_MODEL", "legacy-model-without-known-dim")
        monkeypatch.setattr(Config, "VECTOR_DIM", 768)

        with pytest.raises(
            EmbeddingRuntimeConfigurationError, match=r"auf 768 Dimensionen angelegt"
        ):
            validate_embedding_configuration()

    def test_explicit_arguments_bypass_the_store_entirely(self, monkeypatch) -> None:
        """Der Migrationslauf (``api/embedding_migrations.py``) uebergibt
        Modell und Endpoint ausdruecklich — die Store-Aufloesung darf dafuer
        gar nicht erst angefragt werden (spiegelt
        ``EmbeddingService.__init__``). Reine Bewahrungsregel: unter dem alten
        Code wurde ``resolve_active_embedding_route`` an dieser Stelle ohnehin
        nie aufgerufen; dieser Test haelt fest, dass die neue Store-Anbindung
        den vollstaendig-expliziten Pfad nicht versehentlich mit erfasst."""
        from app.config import Config
        from app.storage.embedding_service import validate_embedding_configuration

        def _must_not_be_called():
            raise AssertionError(
                "resolve_active_embedding_route darf nicht befragt werden, "
                "wenn model UND base_url explizit uebergeben werden"
            )

        monkeypatch.setattr(
            runtime_module, "resolve_active_embedding_route", _must_not_be_called
        )
        monkeypatch.setattr(Config, "EMBEDDING_API_KEY", "env-key")

        captured: Dict[str, Any] = {}
        self._capture_embed(monkeypatch, captured, vector_len=999)

        actual_dim = validate_embedding_configuration(
            model="explicit-model",
            base_url="https://explicit.example.test/v1",
            vector_dim=999,
        )

        assert captured == {
            "model": "explicit-model",
            "base_url": "https://explicit.example.test/v1",
            "api_key": "env-key",
        }
        assert actual_dim == 999

    def test_without_an_active_configuration_the_legacy_config_view_applies(
        self, monkeypatch
    ) -> None:
        """Unveraendertes Verhalten: ohne aktive Store-Konfiguration bleibt
        ``Config.*`` die einzige Quelle — wie vor #1417. Kein Regressionsfund
        fuer sich, aber Teil derselben Praezedenzkette und schliesst die
        Luecke zwischen den beiden anderen Faellen."""
        from app.config import Config
        from app.storage.embedding_service import validate_embedding_configuration

        monkeypatch.setattr(runtime_module, "resolve_active_embedding_route", lambda: None)
        monkeypatch.setattr(Config, "EMBEDDING_MODEL", "env-model-without-known-dim")
        monkeypatch.setattr(Config, "EMBEDDING_BASE_URL", "http://env-host:11434")
        monkeypatch.setattr(Config, "EMBEDDING_API_KEY", "env-key")
        monkeypatch.setattr(Config, "VECTOR_DIM", 11)

        captured: Dict[str, Any] = {}
        self._capture_embed(monkeypatch, captured, vector_len=11)

        actual_dim = validate_embedding_configuration()

        assert captured == {
            "model": "env-model-without-known-dim",
            "base_url": "http://env-host:11434",
            "api_key": "env-key",
        }
        assert actual_dim == 11


class TestResolveOperationalVectorDim:
    """#1417, Slice 2.3: ``Config.VECTOR_DIM`` ist ein Env-Wert, der nach
    einem erfolgreichen Cutover auf ein Modell anderer Dimension stehen
    bleibt — er aendert sich nicht mit der Migration. Die kanonische
    Dimension des Betriebsindex muss deshalb aus der aktiven
    ``EmbeddingIndexVersion`` kommen, sobald eine existiert."""

    def test_falls_back_to_config_without_an_active_index_version(
        self, monkeypatch
    ) -> None:
        from app.config import Config
        from app.services.embedding_configurations.runtime import (
            resolve_operational_vector_dim,
        )

        monkeypatch.setattr(Config, "VECTOR_DIM", 768)

        assert resolve_operational_vector_dim() == 768

    def test_uses_the_active_index_version_after_a_cutover(
        self, tmp_path, monkeypatch
    ) -> None:
        """Regressionstest fuer den eigentlichen Bug: vor Slice 2.3 haette
        dieser Test ``768`` (den stehengebliebenen Env-Wert) geliefert,
        obwohl der aktive Index laengst auf 1536 Dimensionen migriert ist."""
        from app.config import Config
        from app.services.embedding_configuration_store import (
            EmbeddingConfigurationStore,
        )
        from app.services.embedding_configurations.runtime import (
            resolve_operational_vector_dim,
        )

        monkeypatch.setattr(Config, "VECTOR_DIM", 768)
        store = EmbeddingConfigurationStore(data_dir=tmp_path)
        store.upsert_index_version(
            version=1,
            provider_connection_id="conn_1",
            model_id="text-embedding-3-large",
            dimensions=1536,
            index_name="entity_embedding_v1",
            property_key="embedding_v1",
            status="active",
        )

        assert resolve_operational_vector_dim() == 1536
