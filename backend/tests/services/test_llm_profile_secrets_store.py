"""Tests fuer den Fernet-Store der Profil-Schluessel und seine Befuellung.

Der Store ist die Ablage, die der PostgreSQL-Adapter aus PR 4 vorfinden wird.
Was hier geprueft wird, ist deshalb nicht 'funktioniert das Schreiben', sondern
die drei Eigenschaften, an denen ein Secret-Store scheitert: dass kein Klartext
auf der Platte landet, dass ein nicht entschluesselbarer Eintrag nicht als
'kein Schluessel' durchgeht, und dass die Befuellung die Quelle nicht anfasst.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.services.llm_profile_secrets_store import (
    LlmProfileSecretsStore,
    ProfileSecretDecryptionError,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND_DIR / "scripts" / "migrate_profile_secrets.py"


@pytest.fixture()
def secret_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("AGORA_SECRET_KEY", key)
    return key


@pytest.fixture()
def store(tmp_path: Path, secret_key: str) -> LlmProfileSecretsStore:
    return LlmProfileSecretsStore(data_dir=tmp_path / "data")


@pytest.fixture()
def sqlite_db(tmp_path: Path) -> Path:
    """Eine llm_profiles.db im Format des heutigen Stores."""
    db = tmp_path / "llm_profiles.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE llm_profiles (id TEXT PRIMARY KEY, name TEXT, provider TEXT, "
        "base_url TEXT, model_name TEXT, api_key TEXT, is_default INTEGER, "
        "created_at TEXT, updated_at TEXT)"
    )
    for pid, key in (("p1", "KEY-EINS"), ("p2", "KEY-ZWEI"), ("p3", "")):
        conn.execute(
            "INSERT INTO llm_profiles VALUES (?,?,?,?,?,?,?,?,?)",
            (pid, pid, "openai", "http://x", "m", key, 0, "2026-01-01", "2026-01-01"),
        )
    conn.commit()
    conn.close()
    return db


class TestStore:
    def test_roundtrip(self, store) -> None:
        """Ohne das hier ist alles andere gegenstandslos."""
        store.set("prof_a", "GEHEIM-A")
        assert store.get_plaintext("prof_a") == "GEHEIM-A"

    def test_unknown_profile_returns_none(self, store) -> None:
        """Ein Profil ohne Schluessel ist ein normaler Zustand, kein Fehler."""
        assert store.get_plaintext("gibt-es-nicht") is None

    def test_empty_value_deletes_the_entry(self, store) -> None:
        """Ein verschluesselter Leerstring waere ein Eintrag, der vorgibt einen
        Schluessel zu haben — dieselbe Bedeutung wie ein leeres api_key-Feld."""
        store.set("prof_a", "GEHEIM-A")
        store.set("prof_a", "")

        assert store.get_plaintext("prof_a") is None
        assert store.has("prof_a") is False

    def test_plaintext_never_reaches_the_file(self, store, tmp_path) -> None:
        """Der eine Fehler, der den ganzen Store sinnlos machen wuerde."""
        store.set("prof_a", "NIEMALS-IM-KLARTEXT")

        raw = (tmp_path / "data" / "llm_profile_secrets.json").read_text(
            encoding="utf-8"
        )
        assert "NIEMALS-IM-KLARTEXT" not in raw

    def test_file_is_not_world_readable(self, store, tmp_path) -> None:
        """Der Ciphertext gehoert keinem anderen Nutzer auf dem Host."""
        store.set("prof_a", "GEHEIM-A")

        path = tmp_path / "data" / "llm_profile_secrets.json"
        assert path.stat().st_mode & 0o777 == 0o600

    def test_rotated_master_key_raises_instead_of_reporting_no_key(
        self, store, monkeypatch
    ) -> None:
        """Wuerde hier None zurueckkommen, liefe ein Profil nach einer Rotation
        stillschweigend ohne Authentifizierung weiter."""
        store.set("prof_a", "GEHEIM-A")
        monkeypatch.setenv("AGORA_SECRET_KEY", Fernet.generate_key().decode())

        with pytest.raises(ProfileSecretDecryptionError):
            store.get_plaintext("prof_a")

    def test_missing_master_key_fails_loudly(self, tmp_path, monkeypatch) -> None:
        """Ohne Master-Key darf nichts geschrieben werden, das spaeter niemand
        mehr lesen kann."""
        monkeypatch.delenv("AGORA_SECRET_KEY", raising=False)
        store = LlmProfileSecretsStore(data_dir=tmp_path / "data")

        with pytest.raises(RuntimeError, match="AGORA_SECRET_KEY"):
            store.set("prof_a", "GEHEIM-A")

    def test_listing_and_existence_do_not_need_the_key(
        self, store, monkeypatch
    ) -> None:
        """Eine Bestandspruefung nach einer Migration soll ohne Master-Key
        moeglich sein."""
        store.set("prof_a", "GEHEIM-A")
        store.set("prof_b", "GEHEIM-B")
        monkeypatch.delenv("AGORA_SECRET_KEY", raising=False)

        assert store.list_profile_ids() == ["prof_a", "prof_b"]
        assert store.has("prof_a") is True
        assert store.has("prof_x") is False

    def test_delete_reports_whether_something_was_removed(self, store) -> None:
        store.set("prof_a", "GEHEIM-A")

        assert store.delete("prof_a") is True
        assert store.delete("prof_a") is False


class TestMigrationScript:
    def _run(self, db: Path, data_dir: Path, *args: str, key: str):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--db",
                str(db),
                "--data-dir",
                str(data_dir),
                *args,
            ],
            capture_output=True,
            text=True,
            cwd=str(BACKEND_DIR),
            env={"AGORA_SECRET_KEY": key, "PATH": "/usr/bin:/bin"},
        )

    def test_dry_run_writes_nothing(self, sqlite_db, tmp_path, secret_key) -> None:
        """Ein Vorschau-Lauf, der schon schreibt, ist keine Vorschau."""
        data_dir = tmp_path / "data"

        result = self._run(sqlite_db, data_dir, "--dry-run", key=secret_key)

        assert result.returncode == 0
        assert not (data_dir / "llm_profile_secrets.json").exists()

    def test_migration_transfers_only_profiles_with_a_key(
        self, sqlite_db, tmp_path, secret_key
    ) -> None:
        """Ein Profil ohne Schluessel darf keinen leeren Eintrag erzeugen."""
        data_dir = tmp_path / "data"

        assert self._run(sqlite_db, data_dir, key=secret_key).returncode == 0

        store = LlmProfileSecretsStore(data_dir=data_dir)
        assert store.list_profile_ids() == ["p1", "p2"]

    def test_verify_fails_before_and_passes_after(
        self, sqlite_db, tmp_path, secret_key
    ) -> None:
        """Ein Vergleich, der vorher schon gruen ist, prueft nichts."""
        data_dir = tmp_path / "data"

        before = self._run(sqlite_db, data_dir, "--verify", key=secret_key)
        self._run(sqlite_db, data_dir, key=secret_key)
        after = self._run(sqlite_db, data_dir, "--verify", key=secret_key)

        assert before.returncode == 1
        assert "im Store nicht" in before.stdout
        assert after.returncode == 0

    def test_verify_notices_a_diverging_value(
        self, sqlite_db, tmp_path, secret_key
    ) -> None:
        """Eine reine Existenzpruefung wuerde einen Eintrag aus einem frueheren
        Lauf mit anderem Wert durchgehen lassen."""
        data_dir = tmp_path / "data"
        self._run(sqlite_db, data_dir, key=secret_key)
        LlmProfileSecretsStore(data_dir=data_dir).set("p1", "ETWAS-ANDERES")

        result = self._run(sqlite_db, data_dir, "--verify", key=secret_key)

        assert result.returncode == 1
        assert "Klartext weicht ab" in result.stdout

    def test_verify_names_orphans(self, sqlite_db, tmp_path, secret_key) -> None:
        """Ein Schluessel, dessen Profil verschwunden ist, bleibt sonst
        unbemerkt liegen."""
        data_dir = tmp_path / "data"
        self._run(sqlite_db, data_dir, key=secret_key)
        LlmProfileSecretsStore(data_dir=data_dir).set("verwaist", "ALT")

        result = self._run(sqlite_db, data_dir, "--verify", key=secret_key)

        assert result.returncode == 1
        assert "verwaist" in result.stdout

    def test_sqlite_is_left_untouched(self, sqlite_db, tmp_path, secret_key) -> None:
        """Solange das Flag auf sqlite steht, ist die Datenbank die Wahrheit —
        die Migration legt eine Kopie an, sie raeumt nicht auf."""
        before = sqlite_db.read_bytes()

        self._run(sqlite_db, tmp_path / "data", key=secret_key)

        conn = sqlite3.connect(sqlite_db)
        stored = conn.execute(
            "SELECT api_key FROM llm_profiles WHERE id = 'p1'"
        ).fetchone()[0]
        conn.close()
        assert stored == "KEY-EINS"
        assert sqlite_db.read_bytes() == before
