"""LLM-Profile SQLite-Store (P5.2).

Persistiert LlmProfile-Einträge in instance/llm_profiles.db.
Invariante: genau ein Profil hat is_default=True.
Bootstrap: beim ersten list()-Aufruf wird ein Standard-Profil aus LLM_*-Env-Variablen erzeugt.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..contracts.llm_profile_contract import LlmProfile, LlmProfileCreateRequest


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _instance_dir() -> Path:
    # Flask convention: instance/ liegt neben dem App-Package
    here = Path(__file__).resolve()
    # backend/app/services/ -> backend/instance/
    return here.parents[2] / "instance"


def _db_path() -> Path:
    return _instance_dir() / "llm_profiles.db"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_profiles (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    provider    TEXT NOT NULL,
    base_url    TEXT NOT NULL,
    model_name  TEXT NOT NULL,
    api_key     TEXT NOT NULL DEFAULT '',
    is_default  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


def _row_to_profile(row: sqlite3.Row) -> LlmProfile:
    return LlmProfile(
        id=row["id"],
        name=row["name"],
        provider=row["provider"],
        base_url=row["base_url"],
        model_name=row["model_name"],
        api_key="",  # niemals aus DB zuruckgeben
        is_default=bool(row["is_default"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _bootstrap_profile() -> dict:
    """Erzeugt Default-Profil aus LLM_*-Env-Variablen.

    Localhost-Falle: 'localhost' aus dem Host-.env resolved nicht innerhalb des
    Containers. Default daher 'host.docker.internal'; Provider-Detection muss
    den Host-Alias kennen.
    """
    base_url = os.environ.get("LLM_BASE_URL", "http://host.docker.internal:11434/v1")
    model = os.environ.get("LLM_MODEL_NAME", "qwen2.5:32b")
    if "openai.com" in base_url:
        provider = "openai"
    elif "googleapis.com" in base_url:
        provider = "gemini"
    elif "anthropic.com" in base_url:
        provider = "anthropic"
    elif any(h in base_url for h in ("localhost", "127.0.0.1", "host.docker.internal")):
        provider = "ollama"
    else:
        provider = "custom"
    return dict(
        id=uuid.uuid4().hex,
        name="Standard",
        provider=provider,
        base_url=base_url,
        model_name=model,
        api_key=os.environ.get("LLM_API_KEY", ""),
        is_default=1,
        created_at=_now().isoformat(),
        updated_at=_now().isoformat(),
    )


class LlmProfilesStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        _instance_dir().mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def list(self) -> list[LlmProfile]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM llm_profiles ORDER BY created_at DESC"
            ).fetchall()
            if not rows:
                bp = _bootstrap_profile()
                conn.execute(
                    "INSERT INTO llm_profiles VALUES "
                    "(:id,:name,:provider,:base_url,:model_name,:api_key,:is_default,:created_at,:updated_at)",
                    bp,
                )
                rows = conn.execute(
                    "SELECT * FROM llm_profiles ORDER BY created_at DESC"
                ).fetchall()
            return [_row_to_profile(r) for r in rows]

    def get(self, profile_id: str, include_api_key: bool = False) -> Optional[LlmProfile]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM llm_profiles WHERE id = ?", (profile_id,)
            ).fetchone()
            if row is None:
                return None
            profile = _row_to_profile(row)
            if include_api_key:
                profile = profile.model_copy(update={"api_key": row["api_key"]})
            return profile

    def create(self, req: LlmProfileCreateRequest) -> LlmProfile:
        profile_id = uuid.uuid4().hex
        now = _now().isoformat()
        with self._lock, self._connect() as conn:
            if req.is_default:
                conn.execute("UPDATE llm_profiles SET is_default = 0")
            conn.execute(
                "INSERT INTO llm_profiles VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    profile_id,
                    req.name,
                    req.provider,
                    req.base_url,
                    req.model_name,
                    req.api_key if req.api_key is not None else "",
                    int(req.is_default),
                    now,
                    now,
                ),
            )
        return self.get(profile_id)  # type: ignore[return-value]

    def update(self, profile_id: str, req: LlmProfileCreateRequest) -> Optional[LlmProfile]:
        now = _now().isoformat()
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM llm_profiles WHERE id = ?", (profile_id,)
            ).fetchone()
            if not existing:
                return None
            if req.is_default:
                conn.execute("UPDATE llm_profiles SET is_default = 0")
            # is not None unterscheidet 'weglassen' (None → bestehender Key bleibt)
            # von 'explizit leeren' ("" → Key wird entfernt).
            if req.api_key is not None:
                conn.execute(
                    "UPDATE llm_profiles SET name=?,provider=?,base_url=?,model_name=?,"
                    "api_key=?,is_default=?,updated_at=? WHERE id=?",
                    (
                        req.name,
                        req.provider,
                        req.base_url,
                        req.model_name,
                        req.api_key,
                        int(req.is_default),
                        now,
                        profile_id,
                    ),
                )
            else:
                conn.execute(
                    "UPDATE llm_profiles SET name=?,provider=?,base_url=?,model_name=?,"
                    "is_default=?,updated_at=? WHERE id=?",
                    (
                        req.name,
                        req.provider,
                        req.base_url,
                        req.model_name,
                        int(req.is_default),
                        now,
                        profile_id,
                    ),
                )
        return self.get(profile_id)

    def delete(self, profile_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM llm_profiles WHERE id = ?", (profile_id,)
            )
            return cur.rowcount > 0

    def set_default(self, profile_id: str) -> Optional[LlmProfile]:
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM llm_profiles WHERE id = ?", (profile_id,)
            ).fetchone()
            if not existing:
                return None
            conn.execute("UPDATE llm_profiles SET is_default = 0")
            now = _now().isoformat()
            conn.execute(
                "UPDATE llm_profiles SET is_default = 1, updated_at = ? WHERE id = ?",
                (now, profile_id),
            )
        return self.get(profile_id)

    def reset_for_tests(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM llm_profiles")


_store_singleton = LlmProfilesStore()


def get_llm_profiles_store() -> LlmProfilesStore:
    return _store_singleton
