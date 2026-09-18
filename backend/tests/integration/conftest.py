"""Fixtures für die echte Integrationsschicht (Slice 9, Tech-Review 2026-09-07).

Diese Tests laufen ausschließlich mit dem Marker ``integration`` (siehe
``pyproject.toml::addopts``, dort per ``-m 'not llm and not integration'``
standardmäßig ausgeschlossen — derselbe Mechanismus wie für ``llm``).

Beide Fixtures überspringen den Test (statt zu failen), wenn die jeweils
benötigten Umgebungsvariablen fehlen. Das ist der einzige in diesem Slice
erlaubte Skip-Grund.
"""

from __future__ import annotations

import os
import uuid
from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def _skip_or_fail(reason: str) -> None:
    """Ueberspringen — ausser die Umgebung verlangt ausdruecklich Dienste.

    Lokal ist ein Skip richtig: wer kein Neo4j/Redis laufen hat, soll die
    Suite trotzdem gruen bekommen. In CI ist er falsch. Der Job existiert
    genau dafuer, diese zwei Tests auszufuehren; kommt ein Service-Container
    nicht hoch, wuerde ein Skip den Job gruen melden, obwohl nichts geprueft
    wurde — ein Integrationsjob, der ohne Integration gruen wird, ist
    wertlos. ``AGORA_TEST_REQUIRE_SERVICES`` (in ``ci.yml`` gesetzt) macht
    daraus ein hartes Fail.
    """
    if os.environ.get("AGORA_TEST_REQUIRE_SERVICES") == "1":
        pytest.fail(
            f"{reason} AGORA_TEST_REQUIRE_SERVICES=1 verlangt echte Dienste "
            "— hier wird nicht uebersprungen.",
            pytrace=False,
        )
    pytest.skip(f"{reason} Integrationstest uebersprungen.")


@pytest.fixture
def redis_client():
    """Echter Redis-Client gegen ``AGORA_TEST_REDIS_URL``.

    Überspringt den Test, wenn die Env-Variable fehlt.
    """
    redis_url = os.environ.get("AGORA_TEST_REDIS_URL")
    if not redis_url:
        _skip_or_fail(
            "AGORA_TEST_REDIS_URL ist nicht gesetzt."
        )

    redis = pytest.importorskip("redis")
    client = redis.from_url(redis_url, decode_responses=True)
    try:
        client.ping()
    except Exception as exc:  # noqa: BLE001 — in Skip-Meldung umgewandelt
        _skip_or_fail(f"Redis unter {redis_url} nicht erreichbar: {exc}")

    yield client
    client.close()


@pytest.fixture
def neo4j_session() -> Iterator[tuple]:
    """Echte Neo4j-Session gegen ``AGORA_TEST_NEO4J_*``.

    Überspringt den Test, wenn eine der drei Env-Variablen fehlt. Da die
    Zieldatenbank produktive Daten enthalten kann, erzeugt die Fixture pro
    Lauf eine eindeutige Kennung (``run_id``) und räumt im Teardown
    AUSSCHLIESSLICH Knoten mit ``agora_itest_run: run_id`` ab — niemals ein
    pauschales ``MATCH (n) DETACH DELETE n``.

    Liefert ein Tupel ``(session, run_id)``.
    """
    uri = os.environ.get("AGORA_TEST_NEO4J_URI")
    user = os.environ.get("AGORA_TEST_NEO4J_USER")
    password = os.environ.get("AGORA_TEST_NEO4J_PASSWORD")
    if not uri or not user or not password:
        _skip_or_fail(
            "AGORA_TEST_NEO4J_URI/AGORA_TEST_NEO4J_USER/"
            "AGORA_TEST_NEO4J_PASSWORD sind nicht vollstaendig gesetzt."
        )

    neo4j = pytest.importorskip("neo4j")
    driver = neo4j.GraphDatabase.driver(uri, auth=(user, password))
    run_id = uuid.uuid4().hex

    try:
        driver.verify_connectivity()
    except Exception as exc:  # noqa: BLE001 — in Skip-Meldung umgewandelt
        driver.close()
        _skip_or_fail(f"Neo4j unter {uri} nicht erreichbar: {exc}")

    session = driver.session()
    try:
        yield session, run_id
    finally:
        session.close()
        cleanup_session = driver.session()
        try:
            cleanup_session.run(
                "MATCH (n {agora_itest_run: $run_id}) DETACH DELETE n",
                run_id=run_id,
            )
        finally:
            cleanup_session.close()
            driver.close()


@pytest.fixture
def postgres_database_url() -> Iterator[str]:
    """Erzeugt eine eigene disposable Datenbank für Alembic-Roundtrips."""
    admin_url = os.environ.get('AGORA_TEST_POSTGRES_URL')
    if not admin_url:
        _skip_or_fail('AGORA_TEST_POSTGRES_URL ist nicht gesetzt.')

    database_name = f'agora_itest_{uuid.uuid4().hex}'
    parsed_url = make_url(admin_url)
    test_url = parsed_url.set(database=database_name)
    admin_engine = create_engine(parsed_url, isolation_level='AUTOCOMMIT')

    try:
        with admin_engine.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    except Exception as exc:  # noqa: BLE001 — in Skip-Meldung umgewandelt
        admin_engine.dispose()
        _skip_or_fail(
            f'PostgreSQL-Testdatenbank konnte nicht erzeugt werden: '
            f'{type(exc).__name__}'
        )

    try:
        yield test_url.render_as_string(hide_password=False)
    finally:
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    'SELECT pg_terminate_backend(pid) '
                    'FROM pg_stat_activity '
                    'WHERE datname = :database_name '
                    'AND pid <> pg_backend_pid()'
                ),
                {'database_name': database_name},
            )
            connection.execute(text(f'DROP DATABASE "{database_name}"'))
        admin_engine.dispose()
