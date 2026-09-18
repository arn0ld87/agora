"""Echter Alembic-Roundtrip für ``agora.llm_profiles``."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = BACKEND_DIR / 'migrations'
PREVIOUS_REVISION = 'e4d811c90e00'


def _alembic_config() -> Config:
    config = Config(str(MIGRATIONS_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    return config


def _profile_values(*, is_default: bool) -> dict[str, object]:
    return {
        'id': uuid.uuid4(),
        'name': 'Testprofil',
        'provider': 'ollama',
        'base_url': 'http://ollama:11434/v1',
        'model_name': 'test-model',
        'is_default': is_default,
    }


def test_llm_profile_migration_roundtrip(postgres_database_url, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', postgres_database_url)
    config = _alembic_config()

    command.upgrade(config, 'head')
    engine = create_engine(postgres_database_url)
    try:
        inspector = inspect(engine)
        columns = {
            column['name']
            for column in inspector.get_columns('llm_profiles', schema='agora')
        }

        assert columns == {
            'id',
            'name',
            'provider',
            'base_url',
            'model_name',
            'is_default',
            'created_at',
            'updated_at',
        }
        assert 'api_key' not in columns
        assert 'workspace_id' not in columns

        check_names = {
            constraint['name']
            for constraint in inspector.get_check_constraints(
                'llm_profiles',
                schema='agora',
            )
        }
        assert check_names == {
            'ck_llm_profiles_base_url_not_empty',
            'ck_llm_profiles_model_name_not_empty',
            'ck_llm_profiles_name_length',
            'ck_llm_profiles_provider_not_empty',
        }

        with engine.begin() as connection:
            connection.execute(text('CREATE TABLE public.external_control (id integer)'))
        command.check(config)

        insert_sql = text(
            'INSERT INTO agora.llm_profiles '
            '(id, name, provider, base_url, model_name, is_default) '
            'VALUES (:id, :name, :provider, :base_url, :model_name, :is_default)'
        )
        with engine.begin() as connection:
            connection.execute(insert_sql, _profile_values(is_default=True))

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(insert_sql, _profile_values(is_default=True))
    finally:
        engine.dispose()

    command.downgrade(config, PREVIOUS_REVISION)
    downgraded_engine = create_engine(postgres_database_url)
    try:
        assert not inspect(downgraded_engine).has_table(
            'llm_profiles',
            schema='agora',
        )
    finally:
        downgraded_engine.dispose()
