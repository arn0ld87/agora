"""``pg_cli`` gibt das Passwort nie als Argument weiter (#1583)."""

from __future__ import annotations

from app.infrastructure.postgres.pg_cli import parse_connection_params


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
