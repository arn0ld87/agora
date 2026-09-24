"""``pg_cli`` gibt das Passwort nie als Argument weiter (#1583)."""

from __future__ import annotations

import subprocess
from unittest import mock

from app.infrastructure.postgres import pg_cli
from app.infrastructure.postgres.pg_cli import build_command, parse_connection_params


def test_driver_suffix_is_ignored_and_parts_are_split():
    params = parse_connection_params('postgresql+psycopg://agora:geheim@db.intern:6543/agora_db')

    assert (params.host, params.port, params.user, params.dbname) == (
        'db.intern',
        6543,
        'agora',
        'agora_db',
    )


def test_password_goes_only_to_the_environment():
    params = parse_connection_params('postgresql+psycopg://agora:geheim@db:5432/agora')

    assert not any('geheim' in arg for arg in params.cli_args())
    assert params.environ() == {'PGPASSWORD': 'geheim'}


def test_no_password_means_no_pgpassword():
    params = parse_connection_params('postgresql+psycopg://agora@db/agora')

    assert params.environ() == {}
    assert params.port == 5432


def test_commands_carry_no_password():
    params = parse_connection_params('postgresql+psycopg://agora:geheim@db:5432/agora')

    dump = build_command('dump', params, '/b/postgres.dump')
    restore = build_command('restore', params, '/b/postgres.dump')

    assert dump[0] == 'pg_dump' and '-n' in dump and 'agora' in dump and '-Fc' in dump
    assert restore[0] == 'pg_restore' and '--clean' in restore and '--if-exists' in restore
    assert not any('geheim' in arg for arg in dump + restore)


def test_main_passes_password_only_via_child_environment(monkeypatch, capsys):
    """CodeQL-Befund auf #1602: das Passwort darf nie auf stdout landen."""
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://agora:geheim@db:5432/agora')
    calls = []

    def fake_run(cmd, env, check):
        calls.append((cmd, env))
        return subprocess.CompletedProcess(cmd, 0)

    with mock.patch.object(pg_cli.subprocess, 'run', fake_run):
        assert pg_cli.main(['dump', '--file', '/b/postgres.dump']) == 0

    (cmd, env), = calls
    assert env['PGPASSWORD'] == 'geheim'
    assert 'DATABASE_URL' not in env
    assert not any('geheim' in arg for arg in cmd)
    out = capsys.readouterr()
    assert 'geheim' not in out.out and 'geheim' not in out.err


def test_main_without_database_url_fails(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)

    assert pg_cli.main(['restore', '--file', '/b/postgres.dump']) == 1
