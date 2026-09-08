"""Echter Neo4j-Integrationstest: Idempotenz des Episode/RELATION-Schreibpfads.

Bezug: Commit 673cc0a1 (``fix(graph-build): Episode und Relation idempotent
schreiben, damit Retries den Build nicht abreissen``, #1460). Der
produktive Schreibpfad liegt in
``app/storage/neo4j_write.py::Neo4jWriteMixin._persist_episode`` und nutzt
``MERGE ... ON CREATE SET`` auf ``uuid``, damit ein Retry (verlorene
Commit-Bestätigung) denselben Episode-Knoten bzw. dieselbe RELATION-Kante
nicht ein zweites Mal anlegt.

**Was dieser Test NICHT abdeckt:** ``_persist_episode`` ist ein privates
Mixin-Verfahren auf ``Neo4jStorage`` mit Embeddings, Entity-MERGE,
Retry-Wrapper (``_call_with_retry``) und Label-Handling; es hat keinen
Parameter, über den sich eine Test-Kennung (``agora_itest_run``) als
Property auf den geschriebenen Knoten durchreichen ließe, ohne den
produktiven Code zu ändern — das ist in diesem Slice nicht erlaubt. Statt
den privaten Pfad über Mocks/Monkeypatches zu verbiegen, führt dieser Test
dieselben beiden Cypher-Statements (Episode-``MERGE`` und
RELATION-``MERGE``, wörtlich aus ``neo4j_write.py`` übernommen) direkt
gegen eine echte Neo4j-Instanz aus, ergänzt um ``agora_itest_run`` als
Property für die Fixture-Cleanup. Er beweist damit die Kern-Zusicherung
("zweimaliges Schreiben derselben UUID erzeugt keinen zweiten Knoten/keine
zweite Kante"), NICHT aber, dass ``_persist_episode`` selbst exakt diese
Statements zur Laufzeit sendet — das müsste ein Test abdecken, der den
produktiven Pfad direkt aufruft (wie es
``tests/storage/test_persist_episode_retry_idempotent.py`` mit einem
Fake-Driver bereits unit-testet). Ändert sich die Cypher-Struktur in
``neo4j_write.py``, muss dieser Test manuell nachgezogen werden.
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration


def test_episode_and_relation_writes_are_idempotent(neo4j_session):
    session, run_id = neo4j_session

    episode_uuid = f"itest-episode-{uuid.uuid4().hex}"
    entity_a_uuid = f"itest-entity-a-{uuid.uuid4().hex}"
    entity_b_uuid = f"itest-entity-b-{uuid.uuid4().hex}"
    relation_uuid = f"itest-relation-{uuid.uuid4().hex}"

    def _write_episode() -> None:
        session.run(
            """
            MERGE (ep:Episode {uuid: $uuid})
            ON CREATE SET
                ep.agora_itest_run = $run_id,
                ep.graph_id = $graph_id,
                ep.data = $data,
                ep.processed = true
            """,
            uuid=episode_uuid,
            run_id=run_id,
            graph_id=f"itest-graph-{run_id}",
            data="idempotenz-testtext",
        )

    def _write_entities() -> None:
        for entity_uuid, name in (
            (entity_a_uuid, "TestEntityA"),
            (entity_b_uuid, "TestEntityB"),
        ):
            session.run(
                """
                MERGE (n:Entity {uuid: $uuid})
                ON CREATE SET
                    n.agora_itest_run = $run_id,
                    n.name = $name
                """,
                uuid=entity_uuid,
                run_id=run_id,
                name=name,
            )

    def _write_relation() -> None:
        session.run(
            """
            MATCH (src:Entity {uuid: $src_uuid})
            MATCH (tgt:Entity {uuid: $tgt_uuid})
            MERGE (src)-[r:RELATION {uuid: $uuid}]->(tgt)
            ON CREATE SET
                r.agora_itest_run = $run_id,
                r.name = $name,
                r.reinforced_count = 1
            """,
            src_uuid=entity_a_uuid,
            tgt_uuid=entity_b_uuid,
            uuid=relation_uuid,
            run_id=run_id,
            name="RELATES_TO",
        )

    # Erster Schreibdurchlauf.
    _write_episode()
    _write_entities()
    _write_relation()

    # Zweiter Durchlauf mit denselben UUIDs — simuliert einen Retry nach
    # verlorener Commit-Bestätigung (Produktionsbefund aus 673cc0a1).
    _write_episode()
    _write_entities()
    _write_relation()

    episode_count = session.run(
        "MATCH (ep:Episode {uuid: $uuid}) RETURN count(ep) AS c",
        uuid=episode_uuid,
    ).single()["c"]
    relation_count = session.run(
        """
        MATCH (:Entity {uuid: $src_uuid})-[r:RELATION {uuid: $uuid}]->(:Entity {uuid: $tgt_uuid})
        RETURN count(r) AS c
        """,
        src_uuid=entity_a_uuid,
        tgt_uuid=entity_b_uuid,
        uuid=relation_uuid,
    ).single()["c"]

    assert episode_count == 1, "MERGE auf uuid muss den Episode-Knoten nicht duplizieren"
    assert relation_count == 1, "MERGE auf uuid muss die RELATION-Kante nicht duplizieren"
