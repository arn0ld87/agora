"""Retry-Sicherheit von ``_persist_episode`` (Produktionsbefund 2026-09-07).

Beobachtung auf armserver: Der Graph-Build brach mit

    neo4j.exceptions.ConstraintError:
    {code: Neo.ClientError.Schema.ConstraintValidationFailed}
    {message: Node(9574) already exists with label `Episode`
              and property `uuid` = '55f1a0e0-...'}

ab. Serverseitig stand zeitgleich ``Failed to transmit operation result:
Response write failure`` mit ``io.netty.channel.StacklessClosedChannelException``
— der Server hatte die Transaktion also ausgefuehrt, konnte die Bestaetigung
aber nicht mehr zustellen. Der Retry (``session.execute_write`` des Treibers
und zusaetzlich ``_call_with_retry``) fuehrt die tx-Funktion daraufhin erneut
aus. ``episode_id`` und ``r_uuid`` entstehen aber **ausserhalb** des Retries,
und beide Statements waren ``CREATE`` — die zweite Ausfuehrung traf damit auf
den ``episode_uuid``-Unique-Constraint (harter Abbruch des ganzen Builds) bzw.
legte dieselbe RELATION-Kante ein zweites Mal an (stille Dublette, weil auf
RELATION kein Constraint liegt).

Diese Tests bilden genau diese Lage nach: die erste Ausfuehrung wirkt, meldet
danach aber einen Verbindungsabbruch.
"""

from contextlib import contextmanager
from typing import Any, Dict, List

from neo4j.exceptions import ConstraintError, ServiceUnavailable

from app.storage.neo4j_write import Neo4jWriteMixin
from app.utils.retry import neo4j_call_with_retry


class _FakeResult:
    def __init__(self, record: Dict[str, Any] | None) -> None:
        self._record = record

    def single(self):
        return self._record


class _FakeGraph:
    """Minimaler Neo4j-Ersatz — nur so viel Semantik wie die Tests brauchen.

    Bildet den ``episode_uuid``-Unique-Constraint nach und zaehlt
    RELATION-Kanten je ``uuid``, damit Dubletten sichtbar werden.
    """

    def __init__(self) -> None:
        self.episodes: Dict[str, Dict[str, Any]] = {}
        self.entities: Dict[tuple, Dict[str, Any]] = {}
        self.relations: List[str] = []

    def run(self, query: str, **params: Any) -> _FakeResult:
        q = " ".join(query.split())
        if ":Episode" in q:
            uuid_ = params["uuid"]
            if q.startswith("CREATE (ep:Episode"):
                if uuid_ in self.episodes:
                    raise ConstraintError(
                        "{code: Neo.ClientError.Schema.ConstraintValidationFailed} "
                        f"{{message: Node(1) already exists with label `Episode` "
                        f"and property `uuid` = '{uuid_}'}}"
                    )
                self.episodes[uuid_] = dict(params)
            elif q.startswith("MERGE (ep:Episode"):
                self.episodes.setdefault(uuid_, dict(params))
            return _FakeResult(None)
        if "MERGE (n:Entity" in q:
            key = (params["gid"], params["name_lower"], params["entity_type"])
            self.entities.setdefault(key, dict(params))
            return _FakeResult({"uuid": self.entities[key]["uuid"]})
        if "SET n:" in q:
            return _FakeResult(None)
        if ":RELATION" in q:
            uuid_ = params["uuid"]
            if q.count("MERGE") and uuid_ in self.relations:
                return _FakeResult(None)
            self.relations.append(uuid_)
            return _FakeResult(None)
        return _FakeResult(None)


class _FlakySession:
    """``execute_write``, das die tx-Funktion anwendet und dann abbricht.

    ``fail_on`` nennt die Aufrufnummern (1-basiert), nach denen der
    Verbindungsabbruch gemeldet wird — die Wirkung ist zu diesem Zeitpunkt
    bereits eingetreten, genau wie bei einem verlorenen Commit-Ack.
    """

    def __init__(self, graph: _FakeGraph, fail_on: set[int]) -> None:
        self._graph = graph
        self._fail_on = fail_on
        self.calls = 0

    def execute_write(self, func, *args, **kwargs):
        self.calls += 1
        result = func(self._graph, *args, **kwargs)
        if self.calls in self._fail_on:
            raise ServiceUnavailable(
                "Failed to write data to connection IPv4Address(('neo4j', 7687))"
            )
        return result


class _Storage(Neo4jWriteMixin):
    """Traegt nur, was ``_persist_episode`` tatsaechlich benutzt."""

    def __init__(self, graph: _FakeGraph, fail_on: set[int]) -> None:
        self.session = _FlakySession(graph, fail_on)

    @contextmanager
    def _get_session(self, **_kwargs):
        yield self.session

    def _call_with_retry(self, func, *args, **kwargs):
        return neo4j_call_with_retry(
            func, *args, max_retries=3, initial_delay=0.0, **kwargs
        )


def _persist(storage: _Storage, episode_id: str, *, relations=None, entities=None):
    storage._persist_episode(
        graph_id="g1",
        episode_id=episode_id,
        text="Ein Satz.",
        now="2026-09-07T03:00:00+00:00",
        entities=entities or [],
        relations=relations or [],
        entity_embeddings=[[0.1]] * len(entities or []),
        relation_embeddings=[[0.2]] * len(relations or []),
        round_num=None,
    )


class TestPersistEpisodeSurvivesLostCommitAck:
    def test_episode_write_is_idempotent_across_retry(self):
        """Der Retry der Episode-Transaktion darf keinen ConstraintError ausloesen."""
        graph = _FakeGraph()
        storage = _Storage(graph, fail_on={1})

        _persist(storage, "55f1a0e0-61de-4d33-8eeb-9a5d1f26d27b")

        assert storage.session.calls == 2, "Retry muss stattgefunden haben"
        assert len(graph.episodes) == 1

    def test_relation_write_is_idempotent_across_retry(self):
        """Der Retry der Relations-Transaktion darf keine Dublette anlegen."""
        graph = _FakeGraph()
        entities = [
            {"name": "Alex", "entity_type": "Person", "attributes": {}},
            {"name": "Agora", "entity_type": "Organization", "attributes": {}},
        ]
        relations = [
            {"source": "Alex", "target": "Agora", "type": "LEADS", "fact": "Alex leitet Agora."}
        ]
        # Aufruf 1 = Episode, 2/3 = Entity-MERGE, 4/5 = Label-SET,
        # 6 = Relation. Genau die Relations-Transaktion bricht ab.
        storage = _Storage(graph, fail_on={6})

        _persist(storage, "aaaa1111-0000-4000-8000-000000000001",
                 entities=entities, relations=relations)

        assert len(graph.relations) == 1, (
            f"RELATION-Kante doppelt angelegt: {graph.relations}"
        )
