"""Tests für ``app/services/json_file_store.py``.

Die Sperrmechanik lag bis zum 17.08.2026 in drei zeichengleichen Kopien vor
(``OnboardingStateStore``, ``UserProfileStore``, ``WorkspaceRoutingStore``).
Ein Fehler darin — ein vergessenes ``LOCK_UN``, ein falsch gesetztes
``finally`` — fällt beim Lesen nicht auf, sondern erst als hängender Prozess
unter Last. Diese Tests nageln die Zusage fest, jetzt an einer Stelle.
"""

from __future__ import annotations

import fcntl

import pytest

from app.services.json_file_store import JsonFileStore


@pytest.fixture
def store(tmp_path):
    return JsonFileStore("thing.json", data_dir=tmp_path)


class TestPaths:
    def test_derives_path_and_lock_path(self, store, tmp_path):
        assert store._path == tmp_path / "thing.json"
        assert store._lock_path == tmp_path / "thing.lock"

    def test_falls_back_to_shared_resolution_without_data_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))

        assert JsonFileStore("thing.json")._data_dir == tmp_path.resolve()

    def test_creates_missing_data_dir_on_lock(self, tmp_path):
        nested = tmp_path / "does" / "not" / "exist"
        store = JsonFileStore("thing.json", data_dir=nested)
        assert not nested.exists()

        with store._file_lock():
            pass

        assert nested.is_dir()


class TestFileLock:
    def _is_lockable(self, path) -> bool:
        """Versucht den Lock nicht-blockierend zu nehmen (aus demselben Prozess).

        ``fcntl.flock`` ist per open file description gebunden, nicht per
        Prozess — ein zweites ``open()`` derselben Datei bekommt daher eine
        eigene Beschreibung und läuft in ``BlockingIOError``, solange der
        erste Lock gehalten wird.
        """
        with open(path, "w", encoding="utf-8") as probe:
            try:
                fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return False
            fcntl.flock(probe, fcntl.LOCK_UN)
            return True

    def test_lock_is_exclusive_while_held(self, store):
        with store._file_lock():
            assert self._is_lockable(store._lock_path) is False

    def test_lock_is_released_after_the_block(self, store):
        with store._file_lock():
            pass

        assert self._is_lockable(store._lock_path) is True

    def test_lock_is_released_even_when_the_block_raises(self, store):
        with pytest.raises(RuntimeError):
            with store._file_lock():
                raise RuntimeError("boom")

        assert self._is_lockable(store._lock_path) is True

    def test_yields_a_writable_handle(self, store):
        with store._file_lock() as handle:
            assert handle.writable()


class TestResetForTests:
    def test_removes_payload_and_lock_file(self, store):
        store._path.write_text("{}", encoding="utf-8")
        with store._file_lock():
            pass
        assert store._path.exists() and store._lock_path.exists()

        store.reset_for_tests()

        assert not store._path.exists()
        assert not store._lock_path.exists()

    def test_is_a_noop_when_nothing_exists(self, store):
        store.reset_for_tests()  # darf nicht werfen

        assert not store._path.exists()
