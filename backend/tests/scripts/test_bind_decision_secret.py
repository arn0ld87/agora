"""Tests für scripts/bind_decision_secret.py (f001, Slice `jev-key-cli`).

``scripts/`` ist kein importierbares Paket — das Skript wird wie in
``test_jev_benchmark_report.py`` per Dateipfad als Modul geladen.

Jeder Test, der einen Store braucht, konstruiert
``LlmProviderSecretsStore(data_dir=tmp_path)`` direkt und injiziert ihn über
``main(..., store=...)`` — der echte Store unter ``backend/data`` wird dadurch
nie angefasst. Eine Ausnahme ist
``test_resolve_jev_api_key_sees_the_bound_secret``: der prüft bewusst den
Default-Pfad über den Prozess-Singleton (``AGORA_DATA_DIR`` + Reset), weil
genau der im Betrieb tatsächlich läuft.
"""

from __future__ import annotations

import importlib.util
import io
import logging
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.services.decisions.jev_provider import resolve_jev_api_key
from app.services.llm_provider_secrets_store import (
    LlmProviderSecretsStore,
    reset_singleton_for_tests,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SCRIPT = _REPO_ROOT / "backend" / "scripts" / "bind_decision_secret.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("bind_decision_secret", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[spec.name] = mod  # type: ignore[union-attr]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_BIND = _load_script()

# Markanter Stand-in für einen echten Key — lang genug, um an upsert()s
# Mindestlänge vorbeizukommen, und auffällig genug, um ihn zuverlässig in
# capsys/caplog zu suchen.
_MARKER = "sk-super-secret-test-value-0123456789"


@pytest.fixture(autouse=True)
def _capture_bind_logger(caplog: pytest.LogCaptureFixture):
    """``_configure_logging`` setzt ``propagate = False`` auf den Skript-
    Logger — der Root-Handler von ``caplog`` erreicht ihn sonst nie (gleiches
    Muster wie ``test_jev_benchmark_report.py::_capture_bench_logger``)."""
    bind_logger = logging.getLogger("agora.scripts.bind_decision_secret")
    bind_logger.addHandler(caplog.handler)
    yield
    bind_logger.removeHandler(caplog.handler)


@pytest.fixture(autouse=True)
def _reset_llm_secrets_singleton():
    """Isoliert den Prozess-Singleton je Test — ohne das würde ein Test, der
    den Default-Pfad (kein ``store=``-Override) nimmt, den Singleton eines
    vorherigen Tests mit dessen (ggf. bereits gelöschtem) tmp_path erben."""
    reset_singleton_for_tests()
    yield
    reset_singleton_for_tests()


@pytest.fixture
def secret_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("AGORA_SECRET_KEY", key)
    return key


@pytest.fixture
def store(tmp_path: Path, secret_key: str) -> LlmProviderSecretsStore:
    return LlmProviderSecretsStore(data_dir=tmp_path)


def _set_stdin(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    """``io.StringIO`` meldet ``isatty() == False`` — das Skript nimmt damit
    den Pipe-Zweig (``sys.stdin.read()``), nicht den ``getpass``-Zweig."""
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


class TestBindRoundtrip:
    def test_roundtrip_binds_key_and_store_decrypts_it(self, store, monkeypatch, capsys):
        _set_stdin(monkeypatch, _MARKER)

        rc = _BIND.main(["jev"], store=store)

        assert rc == 0
        assert store.get_plaintext("jev") == _MARKER
        assert _MARKER not in capsys.readouterr().out

    def test_resolve_jev_api_key_sees_the_bound_secret(
        self, tmp_path, secret_key, monkeypatch
    ):
        """Ende-zu-Ende über den echten Singleton-Pfad: bind_decision_secret.py
        und resolve_jev_api_key() müssen auf demselben Store landen."""
        monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
        _set_stdin(monkeypatch, _MARKER)

        rc = _BIND.main(["jev"])

        assert rc == 0
        assert resolve_jev_api_key() == _MARKER

    def test_trailing_newline_and_whitespace_are_stripped(self, store, monkeypatch):
        _set_stdin(monkeypatch, f"  {_MARKER}\n")

        rc = _BIND.main(["jev"], store=store)

        assert rc == 0
        assert store.get_plaintext("jev") == _MARKER


class TestBindRejections:
    def test_empty_stdin_is_rejected_and_nothing_is_saved(self, store, monkeypatch, caplog):
        caplog.set_level(logging.INFO, logger="agora.scripts.bind_decision_secret")
        _set_stdin(monkeypatch, "   \n")

        rc = _BIND.main(["jev"], store=store)

        assert rc == 2
        assert store.get_entry("jev") is None

    def test_unknown_secret_ref_is_rejected(self, store, monkeypatch):
        _set_stdin(monkeypatch, _MARKER)

        rc = _BIND.main(["openai"], store=store)

        assert rc == 2
        assert store.get_entry("openai") is None

    def test_missing_secret_key_env_is_a_clear_config_error(
        self, tmp_path, monkeypatch, caplog
    ):
        monkeypatch.delenv("AGORA_SECRET_KEY", raising=False)
        store_without_key = LlmProviderSecretsStore(data_dir=tmp_path)
        caplog.set_level(logging.ERROR, logger="agora.scripts.bind_decision_secret")
        _set_stdin(monkeypatch, _MARKER)

        rc = _BIND.main(["jev"], store=store_without_key)

        assert rc == 2
        assert "AGORA_SECRET_KEY" in caplog.text

    def test_wrong_master_key_against_existing_store_is_rejected_before_writing(
        self, tmp_path, monkeypatch, caplog
    ):
        """Codex-Review (PR #1741): ein syntaktisch gültiger, aber FALSCHER
        Master-Key darf einen bereits bestehenden Store-Eintrag nicht
        überschreiben — sonst bestätigt der Roundtrip (derselbe falsche Key)
        fälschlich Erfolg, und der zuvor korrekt verschlüsselte Ciphertext ist
        verloren, sobald die Umgebung später korrigiert wird."""
        correct_key = Fernet.generate_key().decode("utf-8")
        monkeypatch.setenv("AGORA_SECRET_KEY", correct_key)
        seeded_store = LlmProviderSecretsStore(data_dir=tmp_path)
        seeded_store.upsert("openai", api_key="sk-original-openai-value-0123")

        wrong_key = Fernet.generate_key().decode("utf-8")
        monkeypatch.setenv("AGORA_SECRET_KEY", wrong_key)
        store_with_wrong_key = LlmProviderSecretsStore(data_dir=tmp_path)
        caplog.set_level(logging.ERROR, logger="agora.scripts.bind_decision_secret")
        _set_stdin(monkeypatch, _MARKER)

        rc = _BIND.main(["jev"], store=store_with_wrong_key)

        assert rc == 2
        assert "AGORA_SECRET_KEY" in caplog.text
        assert store_with_wrong_key.get_entry("jev") is None

        # Mit dem korrekten Key wiederhergestellt: weder der vorhandene
        # ``openai``-Eintrag noch das Fehlen von ``jev`` wurden beschädigt.
        monkeypatch.setenv("AGORA_SECRET_KEY", correct_key)
        store_with_correct_key = LlmProviderSecretsStore(data_dir=tmp_path)
        assert store_with_correct_key.get_plaintext("openai") == "sk-original-openai-value-0123"
        assert store_with_correct_key.get_entry("jev") is None

    def test_matching_master_key_still_allows_binding_a_new_ref(
        self, store, monkeypatch
    ):
        """Gegenprobe: ein zum Store passender Master-Key darf weiterhin eine
        neue Ref binden, auch wenn der Store bereits andere Einträge hat."""
        store.upsert("openai", api_key="sk-original-openai-value-0123")
        _set_stdin(monkeypatch, _MARKER)

        rc = _BIND.main(["jev"], store=store)

        assert rc == 0
        assert store.get_plaintext("jev") == _MARKER


class TestBindDelete:
    def test_delete_removes_a_bound_secret(self, store, caplog):
        store.upsert("jev", api_key=_MARKER)
        caplog.set_level(logging.INFO, logger="agora.scripts.bind_decision_secret")

        rc = _BIND.main(["jev", "--delete"], store=store)

        assert rc == 0
        assert store.get_entry("jev") is None

    def test_delete_when_nothing_bound_still_succeeds(self, store):
        rc = _BIND.main(["jev", "--delete"], store=store)

        assert rc == 0
        assert store.get_entry("jev") is None


class TestBindNeverLeaksTheKey:
    def test_key_never_appears_in_stdout_or_logs(self, store, monkeypatch, capsys, caplog):
        caplog.set_level(logging.INFO, logger="agora.scripts.bind_decision_secret")
        _set_stdin(monkeypatch, _MARKER)

        rc = _BIND.main(["jev"], store=store)

        assert rc == 0
        assert _MARKER not in capsys.readouterr().out
        assert _MARKER not in caplog.text

    def test_key_never_appears_even_when_binding_fails(self, tmp_path, monkeypatch, caplog):
        """Fehlender AGORA_SECRET_KEY darf den Key trotzdem nicht in die
        Fehlermeldung durchreichen."""
        monkeypatch.delenv("AGORA_SECRET_KEY", raising=False)
        store_without_key = LlmProviderSecretsStore(data_dir=tmp_path)
        caplog.set_level(logging.ERROR, logger="agora.scripts.bind_decision_secret")
        _set_stdin(monkeypatch, _MARKER)

        rc = _BIND.main(["jev"], store=store_without_key)

        assert rc == 2
        assert _MARKER not in caplog.text
