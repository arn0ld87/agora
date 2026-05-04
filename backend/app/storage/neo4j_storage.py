"""
Neo4jStorage — Neo4j Community Edition implementation of GraphStorage.

Replaces all Zep Cloud API calls with local Neo4j Cypher queries.
Includes: CRUD, NER/RE-based text ingestion, hybrid search, retry logic.
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from neo4j import GraphDatabase
from neo4j.exceptions import (
    TransientError,
    ServiceUnavailable,
    SessionExpired,
)

from ..config import Config
from ..utils.retry import neo4j_call_with_retry
from .graph_storage import GraphStorage
from .embedding_service import EmbeddingService
from .ner_extractor import NERExtractor
from .neo4j_mappings import (
    edge_to_dict as _edge_to_dict_func,
    node_to_dict as _node_to_dict_func,
)
from .neo4j_read import Neo4jReadMixin
from .neo4j_search import Neo4jSearchMixin
from .neo4j_write import Neo4jWriteMixin
from .search_service import SearchService
from . import neo4j_schema

logger = logging.getLogger('agora.neo4j_storage')


class Neo4jStorage(Neo4jReadMixin, Neo4jWriteMixin, Neo4jSearchMixin, GraphStorage):
    """Neo4j CE implementation of the GraphStorage interface."""

    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 1.0  # seconds (initial backoff)

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        embedding_service: Optional[EmbeddingService] = None,
        ner_extractor: Optional[NERExtractor] = None,
    ):
        self._uri = uri or Config.NEO4J_URI
        self._user = user or Config.NEO4J_USER
        self._password = password or Config.NEO4J_PASSWORD

        self._driver = GraphDatabase.driver(
            self._uri, auth=(self._user, self._password)
        )
        self._embedding = embedding_service or EmbeddingService()
        self._ner = ner_extractor or NERExtractor()
        self._search = SearchService(
            self._embedding,
            vector_weight=Config.HYBRID_SEARCH_VECTOR_WEIGHT,
            keyword_weight=Config.HYBRID_SEARCH_KEYWORD_WEIGHT,
        )

        # Issue #11 Phase 2 — late-bound to avoid the
        # OntologyManager → Neo4jStorage circular dependency.
        # Container injects via :meth:`set_ontology_mutation_service` after
        # the manager is built. ``None`` means the hook is a no-op.
        self._ontology_mutation_service = None

        # Health-state tracking (exposed via properties for /api/status)
        self._is_connected: bool = True
        self._last_error: Optional[Exception] = None
        self._last_success_ts: Optional[datetime] = None

        # Fail fast when Neo4j is not reachable so Flask can expose a clean
        # "storage unavailable" state instead of spamming one warning per schema query.
        self._verify_connectivity()

        # Initialize schema (indexes, constraints)
        self._ensure_schema()

    def close(self):
        """Close the Neo4j driver connection."""
        self._driver.close()

    def set_ontology_mutation_service(self, service) -> None:
        """Late-bind the Issue #11 ``OntologyMutationService``.

        The container wires this *after* construction because the service
        depends on ``OntologyManager``, which itself holds a reference to
        this storage — direct constructor injection would deadlock the DI
        graph. Pass ``None`` to disable the hook again.
        """
        self._ontology_mutation_service = service

    # _evaluate_ontology_mutations lebt jetzt im Neo4jWriteMixin
    # (Issue #50, Sub-Slice 2).

    def _verify_connectivity(self):
        """Ensure the driver can actually reach Neo4j.

        Startup race: ``docker-compose`` brings ``agora-neo4j`` up in parallel
        with the backend. The compose healthcheck pings HTTP/7474, but Bolt/7687
        opens slightly later — and ``restart: unless-stopped`` ignores
        ``depends_on`` on auto-restart. A single transient ``Connection
        refused`` would otherwise pin ``Neo4jStorage`` to ``None`` for the
        whole process. Retry transient connect errors before giving up.
        """
        # Tunables (env-overridable for tests / slow hosts).
        max_retries = int(os.environ.get("NEO4J_STARTUP_RETRY_MAX", "5"))
        delay = float(os.environ.get("NEO4J_STARTUP_RETRY_DELAY", "2.0"))
        transient = (ServiceUnavailable, SessionExpired, TransientError, ConnectionError)

        attempt = 0
        while True:
            try:
                self._driver.verify_connectivity()
                if attempt > 0:
                    logger.info(
                        "Neo4j connectivity established after %d retr%s",
                        attempt,
                        "y" if attempt == 1 else "ies",
                    )
                return
            except transient as exc:
                if attempt >= max_retries:
                    try:
                        self._driver.close()
                    except Exception:
                        pass
                    raise
                attempt += 1
                logger.warning(
                    "Neo4j not reachable yet (attempt %d/%d): %s — retrying in %.1fs",
                    attempt,
                    max_retries,
                    exc,
                    delay,
                )
                time.sleep(delay)
            except Exception:
                # Non-transient (auth, config) — fail fast.
                try:
                    self._driver.close()
                except Exception:
                    pass
                raise

    # ----------------------------------------------------------------
    # Vector-index dimension guard  (Issue #263)
    # ----------------------------------------------------------------

    _SHOW_INDEX_DIM_QUERY = (
        "SHOW INDEXES YIELD name, options "
        "WHERE name = $name "
        "RETURN options.indexConfig.`vector.dimensions` AS dim"
    )

    def _ensure_vector_index_dim(self, session, index_name: str, expected_dim: int) -> None:
        """Drop a vector index whose stored dimension differs from *expected_dim*.

        Three cases:
        - Index absent          → no-op (caller's CREATE will handle it).
        - Index dim == expected → no-op.
        - Index dim != expected → DROP + log warning; caller will re-CREATE.
        """
        result = session.run(self._SHOW_INDEX_DIM_QUERY, name=index_name)
        row = result.single()
        if row is None:
            # Index does not exist yet.
            return
        stored_dim = row["dim"]
        if stored_dim == expected_dim:
            return
        logger.warning(
            "Vector index '%s' has dim=%s, expected_dim=%s -> dropping for recreation",
            index_name,
            stored_dim,
            expected_dim,
        )
        session.run(f"DROP INDEX {index_name}")

    _VECTOR_INDEX_NAMES = ("entity_embedding", "fact_embedding")

    def _ensure_schema(self):
        """Create indexes and constraints if they don't exist.

        Vector indexes are checked for dimension-drift before the CREATE
        statement runs.  If an index already exists with the wrong dimension
        it is dropped first so the subsequent CREATE builds it correctly.
        """
        with self._driver.session() as session:
            for query in neo4j_schema.ALL_SCHEMA_QUERIES:
                # Before each vector-index CREATE, validate stored dimension.
                for idx_name in self._VECTOR_INDEX_NAMES:
                    if f"CREATE VECTOR INDEX {idx_name}" in query:
                        try:
                            self._ensure_vector_index_dim(
                                session, idx_name, Config.VECTOR_DIM
                            )
                        except Exception as e:
                            logger.warning(
                                "Vector index dimension check for '%s' failed: %s",
                                idx_name,
                                e,
                            )
                        break
                try:
                    session.run(query)
                except Exception as e:
                    logger.warning("Schema query warning: %s", e)

    # ----------------------------------------------------------------
    # Health-status properties
    # ----------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """True when the last DB operation succeeded; False after a permanent failure."""
        return self._is_connected

    @property
    def last_error(self) -> Optional[Exception]:
        """The exception that caused the most recent permanent failure, or None."""
        return self._last_error

    @property
    def last_success_ts(self) -> Optional[datetime]:
        """Timestamp (UTC) of the most recent successful DB call, or None."""
        return self._last_success_ts

    # ----------------------------------------------------------------
    # Retry wrapper
    # ----------------------------------------------------------------

    def _call_with_retry(self, func, *args, **kwargs):
        """
        Execute *func* with exponential-backoff retry on Neo4j transient errors.

        Delegates to ``neo4j_call_with_retry`` from ``utils.retry`` (shared
        mechanism — no parallel retry implementations).  Updates the health
        state (``is_connected``, ``last_error``, ``last_success_ts``) so
        callers and the future /api/status endpoint can inspect it.
        """
        try:
            result = neo4j_call_with_retry(
                func,
                *args,
                max_retries=self.MAX_RETRIES,
                initial_delay=self.RETRY_DELAY_BASE,
                **kwargs,
            )
            # Success — record health state
            self._is_connected = True
            self._last_error = None
            self._last_success_ts = datetime.now(timezone.utc)
            return result
        except (TransientError, ServiceUnavailable, SessionExpired) as exc:
            # Retries exhausted — record failure state and re-raise
            self._is_connected = False
            self._last_error = exc
            raise

    # ----------------------------------------------------------------
    # Write-Pfad (create_graph, delete_graph, set_ontology, add_text,
    # _persist_episode, add_text_batch, wait_for_processing,
    # reinforce_relation, tombstone_relation, backfill_temporal_defaults,
    # _evaluate_ontology_mutations) lebt jetzt im Neo4jWriteMixin
    # (Issue #50, Sub-Slice 2).
    # ----------------------------------------------------------------

    # ----------------------------------------------------------------
    # Search-Pfad (search) lebt jetzt im Neo4jSearchMixin
    # (Issue #50, Sub-Slice 3).
    # ----------------------------------------------------------------

    # ----------------------------------------------------------------
    # get_graph_info, get_graph_data + Dict-Konversion (_node_to_dict /
    # _edge_to_dict) leben jetzt im Neo4jReadMixin bzw. in
    # storage/neo4j_mappings.py (Issue #50, Sub-Slice 1).
    # ----------------------------------------------------------------

    # Re-Export der Mapping-Funktionen als statische Methoden, falls
    # Subklassen oder externer Code historisch über die Klasse zugriff
    # (laut grep keine Caller, aber die Wire-Identity bleibt damit billig).
    _node_to_dict = staticmethod(_node_to_dict_func)
    _edge_to_dict = staticmethod(_edge_to_dict_func)
