"""SQLAlchemy-Engine für Agora (docs/plans/supabase.md §8).

Diese Datei baut Engines, sie hält keine. Der Prozess-Zustand — welche Engine
gerade existiert und wann sie entsteht — liegt in `session.py`, damit es genau
eine Stelle gibt, die ihn besitzt.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import NullPool

from ...config import DATABASE_URL_PREFIX
from ...utils.logger import get_logger

logger = get_logger('agora.postgres.engine')

# Ein Legacy-Schema wird korrigiert, nicht stillschweigend akzeptiert:
# 'postgresql://' wählt in SQLAlchemy psycopg2, das hier nicht installiert
# ist. Der Fehler fiele sonst erst beim ersten Verbindungsversuch und sähe
# nach einem fehlenden Paket aus statt nach einer falschen URL.
_LEGACY_PREFIXES = ('postgresql://', 'postgres://')


def normalize_database_url(url: str) -> str:
    """Bringt eine Verbindungszeichenkette auf `postgresql+psycopg://`.

    `Config.validate()` lehnt ein falsches Schema bereits beim Start ab. Diese
    Funktion ist für die Pfade, die ohne Flask-Config auskommen — Alembic und
    Wartungsskripte lesen `DATABASE_URL` direkt aus der Umgebung.
    """
    cleaned = (url or '').strip()
    if not cleaned:
        raise ValueError(
            'DATABASE_URL is empty — set it to '
            f'{DATABASE_URL_PREFIX}user:password@host:5432/dbname'
        )

    for legacy in _LEGACY_PREFIXES:
        if cleaned.startswith(legacy):
            corrected = DATABASE_URL_PREFIX + cleaned[len(legacy):]
            logger.warning(
                "DATABASE_URL uses '%s'; rewriting to '%s' so SQLAlchemy "
                "selects psycopg 3 instead of psycopg2.",
                legacy,
                DATABASE_URL_PREFIX,
            )
            return corrected

    if not cleaned.startswith(DATABASE_URL_PREFIX):
        raise ValueError(
            f"DATABASE_URL must start with '{DATABASE_URL_PREFIX}'; "
            'the supplied value was rejected'
        )
    return cleaned


def build_engine(
    url: str,
    *,
    pool_size: int = 5,
    max_overflow: int = 5,
    pool_timeout: float = 30.0,
    pool_recycle: int = 1800,
    echo: bool = False,
    use_pool: bool = True,
) -> Engine:
    """Baut eine Engine. Verbindet noch nicht — das passiert beim ersten Use.

    `pool_pre_ping` ist gesetzt, nicht aus Vorsicht, sondern aus derselben
    Erfahrung, die `NEO4J_LIVENESS_TIMEOUT` erzwungen hat: im Docker-Bridge-Netz
    verschwinden Sockets, die im Pool liegen, ohne dass eine Seite es merkt.
    Ohne Pre-Ping bekommt der erste Zugriff nach einer Idle-Phase einen toten
    Socket statt einer Verbindung.

    `pool_recycle` liegt unter den Timeouts, die Supavisor auf einer Verbindung
    durchsetzt; eine vom Pooler serverseitig geschlossene Verbindung soll der
    Pool vorher selbst wegwerfen.

    `use_pool=False` (NullPool) ist für kurzlebige Prozesse gedacht — Alembic,
    Wartungsskripte, Tests. Dort ist ein Pool nur eine Quelle offen bleibender
    Verbindungen.
    """
    normalized = normalize_database_url(url)

    if not use_pool:
        return create_engine(
            normalized,
            poolclass=NullPool,
            pool_pre_ping=True,
            echo=echo,
            future=True,
        )

    return create_engine(
        normalized,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_recycle=pool_recycle,
        pool_pre_ping=True,
        echo=echo,
        future=True,
    )
