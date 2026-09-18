"""Vertrag des ersten PostgreSQL-Fachmodells für LLM-Profile."""
from __future__ import annotations

from unittest.mock import patch

from sqlalchemy import CheckConstraint

from app.infrastructure.postgres.models import Base, LlmProfileModel

EXPECTED_COLUMNS = {
    'id',
    'name',
    'provider',
    'base_url',
    'model_name',
    'is_default',
    'created_at',
    'updated_at',
}


def test_llm_profile_metadata_has_only_approved_fields():
    table = Base.metadata.tables['agora.llm_profiles']

    assert set(table.columns.keys()) == EXPECTED_COLUMNS
    assert 'api_key' not in table.columns
    assert 'workspace_id' not in table.columns


def test_llm_profile_constraints_are_named_and_complete():
    table = LlmProfileModel.__table__
    check_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert check_names == {
        'ck_llm_profiles_base_url_not_empty',
        'ck_llm_profiles_model_name_not_empty',
        'ck_llm_profiles_name_length',
        'ck_llm_profiles_provider_not_empty',
    }
    assert table.primary_key.name == 'pk_llm_profiles'


def test_only_one_default_profile_is_enforced_by_partial_index():
    table = LlmProfileModel.__table__
    index = next(iter(table.indexes))

    assert index.name == 'uq_llm_profiles_single_default'
    assert index.unique is True
    assert [column.name for column in index.columns] == ['is_default']
    assert str(index.dialect_options['postgresql']['where']) == 'is_default'


def test_legacy_startup_does_not_build_postgres_engine(monkeypatch):
    monkeypatch.setenv('FLASK_DEBUG', 'false')
    monkeypatch.setenv('AGORA_ALLOW_ANONYMOUS', 'true')
    monkeypatch.delenv('AGORA_CORS_ALLOW_ALL', raising=False)

    from app import create_app
    from app.config import Config

    with (
        patch.object(Config, 'validate', return_value=[]),
        patch(
            'app.storage.embedding_service.validate_embedding_configuration',
            return_value=768,
        ),
        patch('app.services.sim.reconciliation.run_startup_reconciliation'),
        patch('app.infrastructure.postgres.engine.create_engine') as create_engine,
    ):
        app = create_app()

    assert app is not None
    assert LlmProfileModel.__table__.schema == 'agora'
    create_engine.assert_not_called()
