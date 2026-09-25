"""Config-Vertrag für ``AGORA_AUTH_BACKEND`` und Supabase-JWT (ADR-0018, #1613).

Die Kernzusage: Supabase-JWTs werden nur angenommen, wenn alle fünf
Metadaten-Ablagen auf PostgreSQL stehen. Mit einem Datei-Backend gäbe es
keine Workspace-Isolation.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.config import (
    AUTH_BACKENDS,
    WORKSPACE_SCOPED_BACKENDS,
    supabase_jwt_configured,
    supabase_jwt_settings,
    validate_auth_backend,
)

URL = 'postgresql+psycopg://u:p@host:5432/db'
ISSUER = 'https://supabase.example.test/auth/v1'
SECRET = 's' * 40
BACKEND_DIR = Path(__file__).resolve().parents[2]
ALL_POSTGRES = {attr: 'postgres' for _, attr in WORKSPACE_SCOPED_BACKENDS}


def _config(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        'AUTH_BACKEND': 'hybrid',
        'SUPABASE_JWT_ISSUER': '',
        'SUPABASE_JWT_AUDIENCE': 'authenticated',
        'SUPABASE_JWKS_URL': '',
        'SUPABASE_JWT_SECRET': '',
        'DATABASE_URL': '',
        'LLM_PROFILE_BACKEND': 'sqlite',
        'PROJECT_BACKEND': 'file',
        'SIMULATION_BACKEND': 'file',
        'RUN_BACKEND': 'file',
        'REPORT_BACKEND': 'file',
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _jwt_ready(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        'SUPABASE_JWT_ISSUER': ISSUER,
        'SUPABASE_JWT_SECRET': SECRET,
        'DATABASE_URL': URL,
        **ALL_POSTGRES,
    }
    values.update(overrides)
    return _config(**values)


@pytest.fixture(autouse=True)
def _no_anonymous(monkeypatch):
    monkeypatch.delenv('AGORA_ALLOW_ANONYMOUS', raising=False)


@pytest.fixture
def isolation(monkeypatch):
    """Die Workspace-Isolation aus #1614 als vorhanden annehmen."""
    monkeypatch.setattr('app.config.TENANT_ISOLATION_AVAILABLE', True)


def test_jwt_is_refused_without_workspace_isolation(monkeypatch):
    """Ohne Workspace-Isolation sähe ein JWT-Nutzer den ganzen Bestand. Die
    Sperre bleibt als Mechanismus erhalten, falls die Isolation je fehlt."""
    monkeypatch.setattr('app.config.TENANT_ISOLATION_AVAILABLE', False)

    errors = validate_auth_backend(_jwt_ready())

    assert any('not available yet' in e and '#1614' in e for e in errors)


def test_workspace_isolation_is_available_since_1614():
    from app.config import TENANT_ISOLATION_AVAILABLE

    assert TENANT_ISOLATION_AVAILABLE is True
    assert validate_auth_backend(_jwt_ready()) == []


def test_modes_are_exactly_legacy_hybrid_supabase():
    assert AUTH_BACKENDS == frozenset({'legacy', 'hybrid', 'supabase'})


def test_workspace_scoped_backends_are_the_five_metadata_switches():
    assert [env for env, _ in WORKSPACE_SCOPED_BACKENDS] == [
        'AGORA_LLM_PROFILE_BACKEND',
        'AGORA_PROJECT_BACKEND',
        'AGORA_SIMULATION_BACKEND',
        'AGORA_RUN_BACKEND',
        'AGORA_REPORT_BACKEND',
    ]


def test_default_is_hybrid_without_environment_or_dotenv():
    env = {k: v for k, v in os.environ.items() if not k.startswith(('AGORA_AUTH_BACKEND', 'AGORA_SUPABASE_'))}
    probe = (
        'import dotenv; dotenv.load_dotenv = lambda *a, **k: False; '
        'from app.config import Config, supabase_jwt_configured; '
        'print(Config.AUTH_BACKEND, supabase_jwt_configured(Config))'
    )
    result = subprocess.run(
        [sys.executable, '-c', probe],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == 'hybrid False'


@pytest.mark.parametrize('mode', ['legacy', 'hybrid'])
def test_without_jwt_settings_legacy_and_hybrid_need_nothing(mode):
    assert validate_auth_backend(_config(AUTH_BACKEND=mode)) == []


def test_unknown_mode_is_an_error_not_a_fallback():
    errors = validate_auth_backend(_config(AUTH_BACKEND='jwt'))

    assert len(errors) == 1 and 'unknown value' in errors[0]


def test_supabase_mode_without_jwt_locks_everyone_out():
    errors = validate_auth_backend(_config(AUTH_BACKEND='supabase'))

    assert errors and 'requires Supabase JWT settings' in errors[0]


@pytest.mark.parametrize(
    'stray', [{'SUPABASE_JWT_SECRET': SECRET}, {'SUPABASE_JWKS_URL': 'https://a.test/jwks'}]
)
def test_half_configured_jwt_is_an_error(stray):
    errors = validate_auth_backend(_config(**stray))

    assert errors and 'without AGORA_SUPABASE_JWT_ISSUER' in errors[0]


@pytest.mark.parametrize('mode', ['hybrid', 'supabase'])
def test_jwt_with_every_backend_on_postgres_is_valid(isolation, mode):
    config = _jwt_ready(AUTH_BACKEND=mode)

    assert validate_auth_backend(config) == []
    assert supabase_jwt_configured(config)
    settings = supabase_jwt_settings(config)
    assert settings is not None and settings.algorithms == ('HS256',)


@pytest.mark.parametrize(('env_name', 'attr'), WORKSPACE_SCOPED_BACKENDS)
def test_jwt_with_any_file_backend_is_rejected(isolation, env_name, attr):
    legacy_value = 'sqlite' if attr == 'LLM_PROFILE_BACKEND' else 'file'
    errors = validate_auth_backend(_jwt_ready(**{attr: legacy_value}))

    assert any('every metadata backend on postgres' in e and env_name in e for e in errors)


def test_jwt_without_database_url_is_rejected(isolation):
    errors = validate_auth_backend(_jwt_ready(DATABASE_URL=''))

    assert 'Supabase JWT auth requires DATABASE_URL' in errors


def test_legacy_with_jwt_is_a_contradiction(isolation):
    errors = validate_auth_backend(_jwt_ready(AUTH_BACKEND='legacy'))

    assert any('legacy ignores Supabase JWT settings' in e for e in errors)


def test_jwt_and_anonymous_mode_are_exclusive(isolation, monkeypatch):
    monkeypatch.setenv('AGORA_ALLOW_ANONYMOUS', 'true')

    errors = validate_auth_backend(_jwt_ready())

    assert any('AGORA_ALLOW_ANONYMOUS' in e for e in errors)


def test_jwt_and_cors_allow_all_are_exclusive(isolation, monkeypatch):
    """Offene Registrierung (#1616): keine fremde Origin im Namen eines Nutzers."""
    monkeypatch.setenv('AGORA_CORS_ALLOW_ALL', 'true')

    errors = validate_auth_backend(_jwt_ready())

    assert any('AGORA_CORS_ALLOW_ALL' in e for e in errors)
    monkeypatch.setenv('AGORA_CORS_ALLOW_ALL', 'false')
    assert validate_auth_backend(_jwt_ready()) == []


def test_invalid_jwt_settings_do_not_echo_the_secret(isolation):
    short = 'geheim-und-kurz'
    errors = validate_auth_backend(_jwt_ready(SUPABASE_JWT_SECRET=short))

    assert errors and all(short not in e for e in errors)


def test_both_key_sources_are_rejected(isolation):
    errors = validate_auth_backend(_jwt_ready(SUPABASE_JWKS_URL='https://a.test/jwks'))

    assert any('exactly one of' in e for e in errors)
