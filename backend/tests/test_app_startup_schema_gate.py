"""Verdrahtung des Alembic-Drift-Gates in `create_app` (#1582).

Der Drift-Nachweis gegen eine echte Datenbank liegt in
``tests/integration/test_alembic_head_startup_gate.py``. Hier geht es nur um
die Verdrahtung: läuft das Gate überhaupt, und nur dann, wenn mindestens eine
Ablage auf ``postgres`` steht — mit Legacy-Defaults darf keine einzige
Verbindung entstehen (die Zusage aus ``backends.py``, Issue #1576).

Startumgebung analog ``tests/test_app_startup_reconciliation.py::
_prepare_startup_env``: ``create_app()`` muss ohne echtes Neo4j/Redis
durchlaufen, damit der Gate-Aufruf isoliert geprüft werden kann.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.run_registry import RunRegistry


def _prepare_startup_env(monkeypatch) -> None:
    monkeypatch.setenv("FLASK_DEBUG", "false")
    monkeypatch.setenv("AGORA_ALLOW_ANONYMOUS", "true")
    monkeypatch.delenv("AGORA_CORS_ALLOW_ALL", raising=False)

    from app.config import Config as _Config

    monkeypatch.setattr(_Config, "DEBUG", False)
    monkeypatch.setattr(_Config, "SECRET_KEY", "test-secret-key-not-a-placeholder")
    monkeypatch.setattr(_Config, "NEO4J_PASSWORD", "test-neo4j-password")

    monkeypatch.setattr(
        "app.storage.embedding_service.validate_embedding_configuration",
        lambda skip_probe=False: 768,
    )


def _reset_run_registry(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", str(tmp_path / "run_registry"))
    RunRegistry._instance = None


class TestLegacyDefaultsSkipTheGateEntirely:
    def test_no_engine_is_built_when_every_backend_is_legacy(self, tmp_path, monkeypatch):
        _prepare_startup_env(monkeypatch)
        _reset_run_registry(tmp_path, monkeypatch)

        from app.config import Config as _Config

        # Ausdruecklich auf Legacy halten, unabhaengig davon, was eine lokale
        # .env setzt — dieselbe Vorsicht wie in
        # tests/infrastructure/test_postgres_backends.py.
        monkeypatch.setattr(_Config, "METADATA_BACKEND", "legacy")
        monkeypatch.setattr(_Config, "LLM_PROFILE_BACKEND", "sqlite")
        monkeypatch.setattr(_Config, "PROJECT_BACKEND", "file")
        for name in dir(_Config):
            if name.endswith("_BACKEND") and getattr(_Config, name, None) == "postgres":
                monkeypatch.setattr(_Config, name, "file")

        create_engine_spy = MagicMock()
        monkeypatch.setattr(
            "app.infrastructure.postgres.schema_gate.create_engine", create_engine_spy
        )
        gate_spy = MagicMock()
        monkeypatch.setattr(
            "app.infrastructure.postgres.schema_gate.verify_schema_at_head", gate_spy
        )

        from app import create_app

        app = create_app()

        assert app is not None
        create_engine_spy.assert_not_called()
        gate_spy.assert_not_called()


class TestPostgresBackendTriggersTheGate:
    def test_create_app_calls_the_gate_with_the_configured_database_url(
        self, tmp_path, monkeypatch
    ):
        _prepare_startup_env(monkeypatch)
        _reset_run_registry(tmp_path, monkeypatch)

        from app.config import Config as _Config

        monkeypatch.setattr(_Config, "PROJECT_BACKEND", "postgres")
        monkeypatch.setattr(
            _Config, "DATABASE_URL", "postgresql+psycopg://user:pw@localhost:5432/db"
        )

        gate_spy = MagicMock()
        monkeypatch.setattr(
            "app.infrastructure.postgres.schema_gate.verify_schema_at_head", gate_spy
        )

        from app import create_app

        app = create_app()

        assert app is not None
        gate_spy.assert_called_once()
        called_url = gate_spy.call_args.args[0]
        assert called_url == "postgresql+psycopg://user:pw@localhost:5432/db"

    def test_create_app_propagates_schema_drift_as_a_startup_failure(
        self, tmp_path, monkeypatch
    ):
        _prepare_startup_env(monkeypatch)
        _reset_run_registry(tmp_path, monkeypatch)

        from app.config import Config as _Config
        from app.infrastructure.postgres.schema_gate import SchemaDriftError

        monkeypatch.setattr(_Config, "PROJECT_BACKEND", "postgres")
        monkeypatch.setattr(
            _Config, "DATABASE_URL", "postgresql+psycopg://user:pw@localhost:5432/db"
        )

        def boom(*args, **kwargs):
            raise SchemaDriftError(
                "Aktuelle Revision: abc123, erwartete Revision (Head): def456."
            )

        monkeypatch.setattr(
            "app.infrastructure.postgres.schema_gate.verify_schema_at_head", boom
        )

        from app import create_app

        with pytest.raises(SchemaDriftError, match="erwartete Revision"):
            create_app()


class TestRlsRoleGate:
    """#1615: Die Rollenprüfung ist im Tenant-Modus hart, sonst ein Hinweis."""

    def _app_with(self, tmp_path, monkeypatch, *, tenant: bool, gate):
        _prepare_startup_env(monkeypatch)
        _reset_run_registry(tmp_path, monkeypatch)
        from app.config import Config as _Config

        monkeypatch.setattr(_Config, "PROJECT_BACKEND", "postgres")
        monkeypatch.setattr(_Config, "DATABASE_URL", "postgresql+psycopg://user:pw@localhost:5432/db")
        monkeypatch.setattr("app.infrastructure.postgres.schema_gate.verify_schema_at_head", MagicMock())
        monkeypatch.setattr("app.infrastructure.postgres.rls_gate.verify_rls_role", gate)
        monkeypatch.setattr("app.security.principal_context.tenant_mode_active", lambda: tenant)
        from app import create_app

        return create_app()

    def test_unreachable_check_is_only_a_warning_without_tenant_mode(self, tmp_path, monkeypatch):
        gate = MagicMock(side_effect=OSError("down"))

        assert self._app_with(tmp_path, monkeypatch, tenant=False, gate=gate) is not None

    def test_unreachable_check_aborts_in_tenant_mode(self, tmp_path, monkeypatch):
        gate = MagicMock(side_effect=OSError("down"))

        with pytest.raises(OSError):
            self._app_with(tmp_path, monkeypatch, tenant=True, gate=gate)

    def test_bypassing_role_aborts_in_tenant_mode(self, tmp_path, monkeypatch):
        from app.infrastructure.postgres.rls_gate import RlsRoleError

        gate = MagicMock(side_effect=RlsRoleError("runtime database role bypasses row level security (superuser)"))

        with pytest.raises(RlsRoleError):
            self._app_with(tmp_path, monkeypatch, tenant=True, gate=gate)
