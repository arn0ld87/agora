"""Tests für scripts/llm-secrets-doctor.py (Issue #450 P1.4).

Wir laden das Script als Modul aus dem Repo-Root (kein paket-fähiger Pfad),
weil es als CLI-Skript mit Dash im Dateinamen abgelegt ist.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCTOR_PATH = REPO_ROOT / "scripts" / "llm-secrets-doctor.py"


def _load_doctor():
    spec = importlib.util.spec_from_file_location("llm_secrets_doctor", DOCTOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["llm_secrets_doctor"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def doctor():
    return _load_doctor()


@pytest.fixture
def valid_key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def store_with_entry(tmp_path: Path, valid_key, monkeypatch):
    """Legt einen frisch verschlüsselten Provider-Eintrag im tmp_path an."""
    monkeypatch.setenv("AGORA_SECRET_KEY", valid_key)
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    from app.services.llm_provider_secrets_store import (
        LlmProviderSecretsStore,
        reset_singleton_for_tests,
    )

    reset_singleton_for_tests()
    store = LlmProviderSecretsStore(data_dir=tmp_path)
    store.upsert("openai", api_key="sk-testkey-abcdefghij")
    store.upsert("google", api_key="AIza-testkey-1234567")
    return tmp_path


# --- status ---------------------------------------------------------------


def test_status_lists_entries(doctor, store_with_entry, capsys):
    rc = doctor.main(["status", "--data-dir", str(store_with_entry)])
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "openai" in captured.out
    assert "google" in captured.out
    # Klartext darf nicht in stdout landen
    assert "sk-testkey-abcdefghij" not in captured.out
    assert "AIza-testkey-1234567" not in captured.out


def test_status_fails_when_key_missing(doctor, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("AGORA_SECRET_KEY", raising=False)
    rc = doctor.main(["status", "--data-dir", str(tmp_path)])
    assert rc == 1
    assert "AGORA_SECRET_KEY" in capsys.readouterr().err


def test_status_fails_when_key_invalid(doctor, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AGORA_SECRET_KEY", "not-a-valid-fernet-key")
    rc = doctor.main(["status", "--data-dir", str(tmp_path)])
    assert rc == 1
    assert "Fernet" in capsys.readouterr().err


def test_status_handles_missing_store_file(doctor, tmp_path, monkeypatch, capsys, valid_key):
    monkeypatch.setenv("AGORA_SECRET_KEY", valid_key)
    rc = doctor.main(["status", "--data-dir", str(tmp_path)])
    assert rc == 0
    assert "Kein Store-File" in capsys.readouterr().out


# --- verify ---------------------------------------------------------------


def test_verify_passes_with_correct_key(doctor, store_with_entry, capsys):
    rc = doctor.main(["verify", "--data-dir", str(store_with_entry)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "decrypt-roundtrip ok" in captured.out
    # Wieder: Klartext nicht in stdout
    assert "sk-testkey-abcdefghij" not in captured.out


def test_verify_fails_with_wrong_key(doctor, store_with_entry, monkeypatch, valid_key, capsys):
    # Anderen Key setzen → Decrypt schlägt fehl
    monkeypatch.setenv("AGORA_SECRET_KEY", Fernet.generate_key().decode())
    rc = doctor.main(["verify", "--data-dir", str(store_with_entry)])
    captured = capsys.readouterr()
    assert rc == 2
    assert "Fehlgeschlagene" in captured.err


# --- rotate ---------------------------------------------------------------


def test_rotate_re_encrypts_with_new_key(
    doctor, store_with_entry, monkeypatch, valid_key, capsys, tmp_path
):
    new_key = Fernet.generate_key().decode()
    monkeypatch.setenv("AGORA_SECRET_KEY", valid_key)
    monkeypatch.setenv("NEW_AGORA_SECRET_KEY", new_key)

    rc = doctor.main(
        [
            "rotate",
            "--data-dir",
            str(store_with_entry),
            "--old-key-env",
            "AGORA_SECRET_KEY",
            "--new-key-env",
            "NEW_AGORA_SECRET_KEY",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0, capsys.readouterr().err
    assert "erfolgreich re-encrypted" in out

    # Verify mit neuem Key
    monkeypatch.setenv("AGORA_SECRET_KEY", new_key)
    from app.services.llm_provider_secrets_store import (
        LlmProviderSecretsStore,
        reset_singleton_for_tests,
    )

    reset_singleton_for_tests()
    fresh_store = LlmProviderSecretsStore(data_dir=store_with_entry)
    assert fresh_store.get_plaintext("openai") == "sk-testkey-abcdefghij"
    assert fresh_store.get_plaintext("google") == "AIza-testkey-1234567"


def test_rotate_aborts_when_old_key_wrong(
    doctor, store_with_entry, monkeypatch, capsys
):
    wrong_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    monkeypatch.setenv("WRONG_KEY", wrong_key)
    monkeypatch.setenv("NEW_KEY", new_key)

    rc = doctor.main(
        [
            "rotate",
            "--data-dir",
            str(store_with_entry),
            "--old-key-env",
            "WRONG_KEY",
            "--new-key-env",
            "NEW_KEY",
        ]
    )
    err = capsys.readouterr().err
    assert rc == 2
    assert "old-key passt nicht" in err


def test_rotate_handles_missing_store_file(doctor, tmp_path, monkeypatch, valid_key, capsys):
    new_key = Fernet.generate_key().decode()
    monkeypatch.setenv("AGORA_SECRET_KEY", valid_key)
    monkeypatch.setenv("NEW_AGORA_SECRET_KEY", new_key)
    rc = doctor.main(
        [
            "rotate",
            "--data-dir",
            str(tmp_path),
            "--old-key-env",
            "AGORA_SECRET_KEY",
            "--new-key-env",
            "NEW_AGORA_SECRET_KEY",
        ]
    )
    assert rc == 0
    assert "nichts zu rotieren" in capsys.readouterr().out


def test_rotate_preserves_store_file_structure(
    doctor, store_with_entry, monkeypatch, valid_key
):
    new_key = Fernet.generate_key().decode()
    monkeypatch.setenv("AGORA_SECRET_KEY", valid_key)
    monkeypatch.setenv("NEW_AGORA_SECRET_KEY", new_key)
    doctor.main(
        [
            "rotate",
            "--data-dir",
            str(store_with_entry),
            "--old-key-env",
            "AGORA_SECRET_KEY",
            "--new-key-env",
            "NEW_AGORA_SECRET_KEY",
        ]
    )
    raw = json.loads(
        (store_with_entry / "llm_provider_secrets.json").read_text(encoding="utf-8")
    )
    # Strukturelle Invariante: version + entries.openai + ciphertext
    assert raw["version"] == 1
    assert set(raw["entries"].keys()) == {"openai", "google"}
    assert raw["entries"]["openai"]["masked_value"] == "sk-...ghij"
    assert raw["entries"]["openai"]["ciphertext"].startswith("gAAAAA")
