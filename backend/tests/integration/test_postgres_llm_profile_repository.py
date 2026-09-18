"""Der PostgreSQL-Adapter und die Datenmigration gegen eine echte Datenbank.

Diese Tests laufen nur mit ``-m integration`` und einer erreichbaren Instanz
(``AGORA_TEST_POSTGRES_URL``). Sie gegen SQLite zu fahren waere sinnlos: was
hier geprueft wird — der partielle Unique-Index, das UUID-Spaltenformat, das
Verhalten ueber eine Transaktionsgrenze hinweg — gibt es dort nicht.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Iterator

import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet

from app.contracts import LlmProfileCreateRequest
from app.infrastructure.postgres.repositories import PostgresLlmProfileRepository
from app.infrastructure.postgres.session import Database
from app.services.llm_profile_secrets_store import LlmProfileSecretsStore

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = BACKEND_DIR / "migrations"

#: IDs im Format des SQLite-Stores: uuid4().hex, 32 Zeichen ohne Bindestriche.
_BESTAND = (
    ("a1b2c3d4e5f60718293a4b5c6d7e8f90", "Alt-Ollama", "ollama", "KEY-OLLAMA", 1),
    ("00112233445566778899aabbccddeeff", "Alt-OpenAI", "openai", "KEY-OPENAI", 0),
    ("ffeeddccbbaa99887766554433221100", "Ohne-Key", "custom", "", 0),
)


@pytest.fixture
def migrated_db(postgres_database_url: str, monkeypatch) -> Iterator[Database]:
    """Eine Wegwerf-Datenbank mit ``alembic upgrade head``."""
    monkeypatch.setenv("DATABASE_URL", postgres_database_url)
    config = Config(str(MIGRATIONS_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    command.upgrade(config, "head")
    database = Database(postgres_database_url)
    try:
        yield database
    finally:
        database.dispose()


@pytest.fixture
def secret_key(monkeypatch) -> str:
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("AGORA_SECRET_KEY", key)
    return key


@pytest.fixture
def repo(migrated_db, tmp_path, secret_key) -> PostgresLlmProfileRepository:
    return PostgresLlmProfileRepository(
        database=migrated_db,
        secrets=LlmProfileSecretsStore(data_dir=tmp_path / "data"),
    )


def _req(**overrides) -> LlmProfileCreateRequest:
    values = {
        "name": "Testprofil",
        "provider": "ollama",
        "base_url": "http://host:11434",
        "model_name": "qwen3",
        "api_key": "",
        "is_default": False,
    }
    values.update(overrides)
    return LlmProfileCreateRequest(**values)


class TestAdapter:
    def test_ids_keep_the_sqlite_shape(self, repo) -> None:
        """Gaebe der Adapter str(UUID) zurueck, zeigte jede gespeicherte
        Referenz wie ``llm_model: "profile:<id>"`` nach der Migration ins
        Leere."""
        created = repo.create(_req())

        assert len(created.id) == 32
        assert "-" not in created.id
        assert repo.get(created.id) is not None

    def test_two_profiles_of_one_provider_keep_separate_keys(self, repo) -> None:
        """Der Grund, warum der Schluessel nicht aus dem providerweiten Store
        kommt: sonst teilten sich diese beiden stillschweigend einen."""
        a = repo.create(_req(name="A", provider="openai", api_key="SCHLUESSEL-A"))
        b = repo.create(_req(name="B", provider="openai", api_key="SCHLUESSEL-B"))

        assert repo.get(a.id, include_api_key=True).api_key == "SCHLUESSEL-A"
        assert repo.get(b.id, include_api_key=True).api_key == "SCHLUESSEL-B"

    def test_key_is_absent_unless_requested(self, repo) -> None:
        created = repo.create(_req(api_key="NIEMALS-IN-EINER-ANTWORT"))

        assert repo.get(created.id).api_key == ""
        assert all(p.api_key == "" for p in repo.list())
        assert "NIEMALS-IN-EINER-ANTWORT" not in repr(repo.list())

    def test_key_is_not_stored_in_the_table(self, repo, migrated_db) -> None:
        """Das Datenmodell haelt Secrets aus der Tabelle heraus (§10); ein
        Adapter, der sie doch hineinschriebe, faellt hier auf."""
        from sqlalchemy import text

        repo.create(_req(api_key="NICHT-IN-DIE-TABELLE"))

        with migrated_db.session() as session:
            dump = str(
                session.execute(text("SELECT * FROM agora.llm_profiles")).fetchall()
            )
        assert "NICHT-IN-DIE-TABELLE" not in dump

    def test_only_one_profile_stays_default(self, repo) -> None:
        """Der partielle Unique-Index laesst nur einen zu — die Reihenfolge der
        Statements innerhalb der Transaktion muss das beachten."""
        repo.create(_req(name="A", is_default=True))
        repo.create(_req(name="B", is_default=True))

        assert sum(1 for p in repo.list() if p.is_default) == 1

    def test_set_default_moves_the_flag(self, repo) -> None:
        a = repo.create(_req(name="A", is_default=True))
        b = repo.create(_req(name="B"))

        repo.set_default(b.id)

        assert repo.get(a.id).is_default is False
        assert repo.get(b.id).is_default is True

    @pytest.mark.parametrize(
        ("sent", "expected"),
        [(None, "URSPRUNG"), ("", ""), ("NEU", "NEU")],
        ids=["none-laesst-stehen", "leer-loescht", "wert-ersetzt"],
    )
    def test_update_handles_the_three_api_key_cases(self, repo, sent, expected) -> None:
        """Die Invariante, an der ein zweiter Adapter am ehesten scheitert."""
        created = repo.create(_req(api_key="URSPRUNG"))

        repo.update(created.id, _req(api_key=sent))

        assert repo.get(created.id, include_api_key=True).api_key == expected

    def test_unknown_and_malformed_ids_answer_with_none(self, repo) -> None:
        """Eine ID, die keine UUID ist, darf keinen Datenbankfehler ausloesen."""
        assert repo.get(uuid.uuid4().hex) is None
        assert repo.get("das-ist-keine-uuid") is None
        assert repo.update("das-ist-keine-uuid", _req()) is None
        assert repo.delete("das-ist-keine-uuid") is False
        assert repo.set_default("das-ist-keine-uuid") is None

    def test_delete_removes_row_and_key(self, repo, tmp_path) -> None:
        created = repo.create(_req(api_key="WEG-DAMIT"))
        secrets = LlmProfileSecretsStore(data_dir=tmp_path / "data")

        assert repo.delete(created.id) is True
        assert repo.get(created.id) is None
        assert secrets.has(created.id) is False

    def test_list_does_not_bootstrap(self, repo, monkeypatch) -> None:
        """Wer auf PostgreSQL umschaltet, hat migriert — ein zusaetzliches
        Profil aus den LLM_*-Variablen haette niemand angelegt."""
        monkeypatch.setenv("LLM_MODEL_NAME", "aus-der-umgebung")

        assert repo.list() == []


class TestMigration:
    @pytest.fixture
    def sqlite_bestand(self, tmp_path) -> Path:
        db = tmp_path / "llm_profiles.db"
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE llm_profiles (id TEXT PRIMARY KEY, name TEXT, "
            "provider TEXT, base_url TEXT, model_name TEXT, api_key TEXT, "
            "is_default INTEGER, created_at TEXT, updated_at TEXT)"
        )
        for pid, name, provider, key, is_default in _BESTAND:
            conn.execute(
                "INSERT INTO llm_profiles VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    pid,
                    name,
                    provider,
                    "http://host:11434",
                    "modell",
                    key,
                    is_default,
                    "2026-03-01T08:00:00+00:00",
                    "2026-03-02T09:00:00+00:00",
                ),
            )
        conn.commit()
        conn.close()
        return db

    def test_migration_keeps_ids_timestamps_and_keys(
        self, sqlite_bestand, migrated_db, tmp_path, secret_key, monkeypatch
    ) -> None:
        """§6 verlangt: Anzahl, IDs, Zeitstempel, Statuswerte identisch."""
        import scripts.migrate_llm_profiles_to_postgres as mig

        monkeypatch.setattr(mig, "get_database", lambda: migrated_db)
        secrets = LlmProfileSecretsStore(data_dir=tmp_path / "data")

        count = mig.migrate(sqlite_bestand, secrets)

        assert count == len(_BESTAND)
        assert mig.verify(sqlite_bestand, secrets) == []

        repo = PostgresLlmProfileRepository(database=migrated_db, secrets=secrets)
        assert {p.id for p in repo.list()} == {row[0] for row in _BESTAND}
        for profile in repo.list():
            assert profile.created_at.isoformat() == "2026-03-01T08:00:00+00:00"

    def test_verify_fails_before_the_migration(
        self, sqlite_bestand, migrated_db, tmp_path, secret_key, monkeypatch
    ) -> None:
        """Ein Vergleich, der schon vorher gruen ist, prueft nichts."""
        import scripts.migrate_llm_profiles_to_postgres as mig

        monkeypatch.setattr(mig, "get_database", lambda: migrated_db)

        findings = mig.verify(
            sqlite_bestand, LlmProfileSecretsStore(data_dir=tmp_path / "data")
        )

        assert findings
        assert any("fehlt in PostgreSQL" in f for f in findings)

    def test_migration_is_repeatable(
        self, sqlite_bestand, migrated_db, tmp_path, secret_key, monkeypatch
    ) -> None:
        """Ein zweiter Lauf darf nicht an der Primaerschluessel-Kollision
        scheitern — sonst ist jede Wiederholung nach einem Teilabbruch blockiert."""
        import scripts.migrate_llm_profiles_to_postgres as mig

        monkeypatch.setattr(mig, "get_database", lambda: migrated_db)
        secrets = LlmProfileSecretsStore(data_dir=tmp_path / "data")

        mig.migrate(sqlite_bestand, secrets)
        mig.migrate(sqlite_bestand, secrets)

        assert mig.verify(sqlite_bestand, secrets) == []

    def test_sqlite_is_untouched(
        self, sqlite_bestand, migrated_db, tmp_path, secret_key, monkeypatch
    ) -> None:
        """§10 Schritt 9: die SQLite bleibt als Rueckweg liegen."""
        import scripts.migrate_llm_profiles_to_postgres as mig

        monkeypatch.setattr(mig, "get_database", lambda: migrated_db)
        before = sqlite_bestand.read_bytes()

        mig.migrate(sqlite_bestand, LlmProfileSecretsStore(data_dir=tmp_path / "data"))

        assert sqlite_bestand.read_bytes() == before
