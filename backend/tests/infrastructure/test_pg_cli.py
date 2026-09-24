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


def test_main_passes_password_only_via_child_environment(monkeypatch, capsys, tmp_path):
    """CodeQL-Befund auf #1602: das Passwort darf nie auf stdout landen."""
    from app.config import Config

    monkeypatch.setattr(
        Config, 'DATABASE_URL', 'postgresql+psycopg://agora:geheim@db:5432/agora'
    )
    manifest = tmp_path / 'postgres-manifest.json'
    manifest.write_text('{"revision": "abc123", "row_counts": {}}', encoding='utf-8')
    calls = []
    stamped = []

    def fake_run(cmd, env, check):
        calls.append((cmd, env))
        return subprocess.CompletedProcess(cmd, 0)

    with mock.patch.object(pg_cli.subprocess, 'run', fake_run), mock.patch(
        'alembic.command.stamp', lambda config, revision: stamped.append(revision)
    ):
        assert pg_cli.main(
            ['restore', '--file', '/b/postgres.dump', '--manifest', str(manifest)]
        ) == 0

    (cmd, env), = calls
    assert env['PGPASSWORD'] == 'geheim'
    assert 'DATABASE_URL' not in env
    assert not any('geheim' in arg for arg in cmd)
    assert stamped == ['abc123']
    out = capsys.readouterr()
    assert 'geheim' not in out.out and 'geheim' not in out.err


def test_main_without_database_url_fails(monkeypatch):
    from app.config import Config

    monkeypatch.setattr(Config, 'DATABASE_URL', '')

    assert pg_cli.main(['restore', '--file', '/b/x.dump', '--manifest', '/b/m.json']) == 1


def test_status_reports_missing_url_for_an_active_backend(monkeypatch, capsys):
    """Codex-Review auf #1602: die Entscheidung kommt aus ``Config`` (inkl.
    ``.env``), nicht aus der Umgebung der aufrufenden Shell."""
    from app.config import Config

    monkeypatch.setattr(Config, 'PROJECT_BACKEND', 'postgres')
    monkeypatch.setattr(Config, 'DATABASE_URL', '')

    assert pg_cli.main(['status']) == pg_cli.EXIT_MISSING_URL
    assert 'PROJECT_BACKEND' in capsys.readouterr().out


def test_dump_command_pins_the_exported_snapshot():
    params = parse_connection_params('postgresql+psycopg://agora@db:5432/agora')

    command = build_command('dump', params, '/b/postgres.dump', snapshot='00000003-1')

    assert '--snapshot=00000003-1' in command
