"""Config-Verträge für die PostgreSQL-Grundlage (docs/plans/supabase.md §8).

Der Kern dieser Datei ist der Default: mit `AGORA_METADATA_BACKEND=legacy`
darf eine fehlende `DATABASE_URL` nichts kosten. Genau das ist das
Abnahmekriterium von Phase 2 — Agora läuft unverändert weiter, obwohl die
Konfiguration existiert.

Die andere Richtung ist genauso wichtig: wer `postgres` einschaltet und die
URL vergisst, soll das beim Start erfahren und nicht beim ersten Zugriff.
"""

from __future__ import annotations

import pytest

from app import config as config_module
from app.config import LLM_PROFILE_BACKENDS, METADATA_BACKENDS, Config, validate_llm_profile_backend


@pytest.fixture
def config_without_unrelated_errors(monkeypatch):
    """Setzt alles, was `validate()` sonst zu Recht anmeckert.

    Ohne das trägt jede Assertion hier die Fehler von SECRET_KEY, LLM_API_KEY
    und NEO4J_PASSWORD mit, und der Test prüfte am Ende die falsche Liste.
    """
    monkeypatch.setattr(Config, 'DEBUG', True)
    monkeypatch.setattr(Config, 'SECRET_KEY', 'test-secret-not-a-placeholder')
    monkeypatch.setattr(Config, 'LLM_API_KEY', 'ollama')
    monkeypatch.setattr(Config, 'NEO4J_URI', 'bolt://localhost:7687')
    monkeypatch.setattr(Config, 'NEO4J_PASSWORD', 'test-password-not-a-placeholder')
    return Config


def _database_errors(errors: list[str]) -> list[str]:
    return [
        error
        for error in errors
        if 'DATABASE_URL' in error or 'AGORA_METADATA_BACKEND' in error
    ]


def test_legacy_backend_needs_no_database_url(config_without_unrelated_errors, monkeypatch):
    """Der Default kostet nichts. Das ist die Abnahme von Phase 2."""
    monkeypatch.setattr(Config, 'METADATA_BACKEND', 'legacy')
    monkeypatch.setattr(Config, 'DATABASE_URL', '')

    assert _database_errors(Config.validate()) == []


def test_postgres_backend_without_database_url_is_rejected(
    config_without_unrelated_errors, monkeypatch
):
    """`postgres` ohne URL ist eine halbe Konfiguration und bricht später."""
    monkeypatch.setattr(Config, 'METADATA_BACKEND', 'postgres')
    monkeypatch.setattr(Config, 'DATABASE_URL', '')

    errors = _database_errors(Config.validate())

    assert len(errors) == 1
    assert 'requires DATABASE_URL' in errors[0]


def test_postgres_backend_with_whitespace_only_url_is_rejected(
    config_without_unrelated_errors, monkeypatch
):
    """Ein Leerzeichen ist keine Verbindungszeichenkette."""
    monkeypatch.setattr(Config, 'METADATA_BACKEND', 'postgres')
    monkeypatch.setattr(Config, 'DATABASE_URL', '   ')

    assert 'requires DATABASE_URL' in _database_errors(Config.validate())[0]


def test_postgres_backend_rejects_psycopg2_scheme(
    config_without_unrelated_errors, monkeypatch
):
    """`postgresql://` wählt psycopg2, das hier nicht installiert ist.

    Ohne diese Prüfung fällt der Fehler erst beim ersten Verbindungsversuch
    und sieht nach einem fehlenden Paket aus statt nach einer falschen URL.
    """
    monkeypatch.setattr(Config, 'METADATA_BACKEND', 'postgres')
    monkeypatch.setattr(Config, 'DATABASE_URL', 'postgresql://user:pw@host:5432/db')

    errors = _database_errors(Config.validate())

    assert len(errors) == 1
    assert 'postgresql+psycopg://' in errors[0]


def test_postgres_backend_accepts_psycopg3_scheme(
    config_without_unrelated_errors, monkeypatch
):
    monkeypatch.setattr(Config, 'METADATA_BACKEND', 'postgres')
    monkeypatch.setattr(
        Config, 'DATABASE_URL', 'postgresql+psycopg://user:pw@supavisor:5432/postgres'
    )

    assert _database_errors(Config.validate()) == []


def test_unknown_metadata_backend_is_rejected(config_without_unrelated_errors, monkeypatch):
    """Ein Tippfehler darf nicht still auf `legacy` zurückfallen.

    Ein stiller Fallback sieht im Log aus wie eine bewusste Entscheidung.
    """
    monkeypatch.setattr(Config, 'METADATA_BACKEND', 'postgre')
    monkeypatch.setattr(Config, 'DATABASE_URL', '')

    errors = _database_errors(Config.validate())

    assert len(errors) == 1
    assert 'unknown value' in errors[0]
    # Die Meldung nennt die gültigen Werte — sonst rät der nächste Mensch.
    for backend in METADATA_BACKENDS:
        assert backend in errors[0]


def test_metadata_backends_are_exactly_legacy_and_postgres():
    """Hält die Menge fest, die `.env.example` und der Plan beschreiben."""
    assert METADATA_BACKENDS == frozenset({'legacy', 'postgres'})


def test_unknown_llm_profile_backend_is_rejected():
    """Ein Tippfehler in AGORA_LLM_PROFILE_BACKEND darf nicht still auf 'sqlite' zurückfallen."""
    errors = validate_llm_profile_backend('sqlit')

    assert len(errors) == 1
    assert 'unknown value' in errors[0]
    for backend in LLM_PROFILE_BACKENDS:
        assert backend in errors[0]


def test_postgres_llm_profile_backend_is_accepted_since_pr4():
    """Seit PR 4 gibt es den Adapter — eine Ablehnung hier hielte eine
    Installation davon ab, umzuschalten, obwohl alles bereitsteht."""
    assert validate_llm_profile_backend('postgres') == []


def test_a_backend_without_adapter_is_rejected_with_a_reason(monkeypatch):
    """Die Mechanik bleibt geprüft, auch wenn das Set gerade leer ist: der
    nächste Store durchläuft denselben Zwischenzustand — Wert schon gültig,
    Adapter noch nicht da. Ein stiller Fallback auf den Default sähe nach einer
    bewussten Entscheidung aus, die keine war."""
    monkeypatch.setattr(
        config_module, 'LLM_PROFILE_BACKENDS', frozenset({'sqlite', 'kuenftig'})
    )
    monkeypatch.setattr(
        config_module,
        'LLM_PROFILE_BACKENDS_NOT_YET_AVAILABLE',
        frozenset({'kuenftig'}),
    )

    errors = validate_llm_profile_backend('kuenftig')

    assert len(errors) == 1
    assert 'not available yet' in errors[0]
