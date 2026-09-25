"""Der zentrale Datenbank-Adapter (docs/plans/supabase.md §8).

Ein Weg zu einer Session, und nur einer:

    from app.infrastructure.postgres import get_database

    with get_database().session() as session:
        session.execute(...)

Freie `psycopg.connect()`-Aufrufe quer durch Services sind ausdrücklich nicht
vorgesehen. Sie umgehen Pool, Konfiguration und Transaktionsgrenze, und jede
einzelne Stelle müsste ihre eigene Fehlerbehandlung mitbringen.

**Gevent.** Der Webprozess läuft unter einem gunicorn-Worker mit
gevent-Worker-Klasse. psycopg 3 ist im Synchronmodus nicht kooperativ: eine
laufende Query blockiert den Hub und damit jeden anderen Greenlet im Prozess.
Für kurze Metadaten-Abfragen ist das tragbar, für lange Scans nicht. Solange
`AGORA_METADATA_BACKEND=legacy` gilt, entsteht hier keine einzige Verbindung;
bevor in Phase 4 der erste Store umgestellt wird, gehört diese Frage
beantwortet (Timeouts, Query-Zuschnitt, oder der Weg über einen Thread).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from ...config import Config
from ...utils.logger import get_logger
from .engine import build_engine

logger = get_logger('agora.postgres')


#: Setzt die RLS-Werte für genau diese Transaktion (``is_local = true``).
#: Fester Text mit gebundenen Parametern — ``SET LOCAL`` nimmt keine.
_RLS_CONTEXT_SQL = text(
    "SELECT set_config('agora.workspace_id', :workspace_id, true), "
    "set_config('agora.system', :system, true)"
)


def rls_context() -> tuple[str, str]:
    """``(workspace_id, system)`` für die Policies aus #1615.

    Mit Principal (Request nach dem Guard): sein Workspace, kein
    System-Kontext. Sonst — Hintergrund-Threads, Start-Reconciliation,
    Migrationsskripte, die Mitgliedschaftsprüfung beim Anmelden — der
    System-Kontext. Dieselbe Trennung wie in ``workspace_scope``.
    """
    from flask import has_request_context

    from ...security.principal_context import current_principal

    if has_request_context():
        principal = current_principal()
        if principal is not None:
            return str(principal.workspace_id), 'off'
    return '', 'on'


def _bind_rls_context(session: Session) -> None:
    workspace_id, system = rls_context()
    session.execute(_RLS_CONTEXT_SQL, {'workspace_id': workspace_id, 'system': system})


class Database:
    """Besitzt Engine und Session-Factory für einen Prozess.

    Die Engine entsteht beim ersten Zugriff, nicht im Konstruktor: ein
    ungenutzter Adapter soll keine Ressourcen halten, und im Default-Betrieb
    (`AGORA_METADATA_BACKEND=legacy`) wird er nie benutzt.
    """

    def __init__(
        self,
        url: str,
        *,
        use_pool: bool = True,
        echo: bool = False,
        connect_timeout: float | None = None,
    ) -> None:
        self._url = url
        self._use_pool = use_pool
        self._echo = echo
        self._connect_timeout = connect_timeout
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None
        self._lock = threading.Lock()

    @property
    def engine(self) -> Engine:
        """Die Engine dieses Adapters, beim ersten Zugriff gebaut."""
        if self._engine is None:
            with self._lock:
                if self._engine is None:
                    self._engine = build_engine(
                        self._url,
                        use_pool=self._use_pool,
                        echo=self._echo,
                        connect_timeout=self._connect_timeout,
                    )
                    self._session_factory = sessionmaker(
                        bind=self._engine,
                        expire_on_commit=False,
                        future=True,
                    )
                    logger.info(
                        'PostgreSQL engine initialised (pool=%s)',
                        'yes' if self._use_pool else 'no',
                    )
        return self._engine

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Eine Session mit Transaktionsgrenze.

        Commit bei sauberem Austritt, Rollback bei jeder Exception, Close in
        beiden Fällen. Die Exception wird weitergereicht: ein fehlgeschlagener
        Schreibvorgang ist ein Fehler, keine leere Antwort.
        """
        _ = self.engine  # baut Engine und Factory, falls noch nicht geschehen
        factory = self._session_factory
        if factory is None:  # pragma: no cover — folgt aus `engine`
            raise RuntimeError('session factory missing after engine initialisation')
        session = factory()
        try:
            _bind_rls_context(session)
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def check_connection(self) -> bool:
        """`SELECT 1`. Für Healthchecks und die Abnahme von Phase 1."""
        try:
            with self.engine.connect() as connection:
                connection.execute(text('SELECT 1'))
            return True
        except SQLAlchemyError as exc:
            # Die URL trägt ein Passwort — nur der Fehlertyp und die Message
            # des Treibers, nie die Verbindungszeichenkette.
            logger.error('PostgreSQL connection check failed: %s', exc)
            return False

    def dispose(self) -> None:
        """Gibt alle gepoolten Verbindungen frei."""
        with self._lock:
            if self._engine is not None:
                self._engine.dispose()
                self._engine = None
                self._session_factory = None


_database: Database | None = None
_database_lock = threading.Lock()

#: Verbindungs-Timeout (Sekunden) des Prozess-Adapters. Seit #1587 liest die
#: Start-Reconciliation die Run-Registry — mit ``AGORA_RUN_BACKEND=postgres``
#: ist das ein Datenbankzugriff im Startpfad. Ohne Timeout wartet psycopg bei
#: einem stumm verworfenen Verbindungsaufbau rund 130 s (vgl. Schema-Gate,
#: Codex-Review auf #1599).
PROCESS_CONNECT_TIMEOUT = 10


def get_database() -> Database:
    """Der Adapter dieses Prozesses.

    Wirft, wenn `DATABASE_URL` fehlt. Das ist Absicht: wer hierher kommt, will
    die Datenbank benutzen, und eine leere URL ist dann keine Konfiguration,
    die man mit einem Default überbrücken sollte.
    """
    global _database
    if _database is None:
        with _database_lock:
            if _database is None:
                url = (Config.DATABASE_URL or '').strip()
                if not url:
                    raise RuntimeError(
                        'DATABASE_URL is not configured — required before using '
                        'the PostgreSQL adapter (AGORA_METADATA_BACKEND=postgres)'
                    )
                _database = Database(url, connect_timeout=PROCESS_CONNECT_TIMEOUT)
    return _database


def reset_database() -> None:
    """Verwirft den Prozess-Adapter. Für Tests und Config-Wechsel."""
    global _database
    with _database_lock:
        if _database is not None:
            _database.dispose()
        _database = None
