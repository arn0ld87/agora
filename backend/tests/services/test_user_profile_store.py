"""Service-Tests für UserProfileStore (Onboarding Slice 2).

Instanzen werden direkt mit ``data_dir=tmp_path`` konstruiert — kein
Singleton-Zugriff nötig. Prüft Persistenz, Merge-Semantik, Dateirechte.
"""
from __future__ import annotations

import json
import stat

import pytest

from app.contracts.user_profile_contract import UserProfileUpdateRequest
from app.services.user_profile_store import UserProfileStore


@pytest.fixture
def store(tmp_path) -> UserProfileStore:
    return UserProfileStore(data_dir=tmp_path)


class TestLoadWithoutProfile:
    def test_load_returns_none_without_file(self, store: UserProfileStore) -> None:
        assert store.load() is None

    def test_load_returns_none_for_corrupt_file(self, tmp_path, store: UserProfileStore) -> None:
        (tmp_path / "user_profile.json").write_text("{not valid json", encoding="utf-8")
        assert store.load() is None

    def test_load_returns_none_for_structurally_invalid_json(
        self, tmp_path, store: UserProfileStore
    ) -> None:
        # Valides JSON, aber verletzt den Contract (display_name fehlt).
        (tmp_path / "user_profile.json").write_text(
            json.dumps({"language": "de"}), encoding="utf-8"
        )
        assert store.load() is None


class TestSaveLoadRoundtrip:
    def test_roundtrip(self, store: UserProfileStore) -> None:
        created = store.update(UserProfileUpdateRequest(display_name="Alex Schneider"))
        loaded = store.load()
        assert loaded is not None
        assert loaded.display_name == "Alex Schneider"
        assert loaded.avatar_ref == created.avatar_ref


class TestUpdate:
    def test_update_creates_profile_with_display_name(
        self, store: UserProfileStore
    ) -> None:
        profile = store.update(UserProfileUpdateRequest(display_name="Neu"))
        assert profile.display_name == "Neu"

    def test_update_without_display_name_and_no_existing_profile_raises(
        self, store: UserProfileStore
    ) -> None:
        with pytest.raises(ValueError):
            store.update(UserProfileUpdateRequest(role="Redakteurin"))

    def test_update_merges_only_set_fields(self, store: UserProfileStore) -> None:
        store.update(UserProfileUpdateRequest(display_name="Alex", role="Redakteur"))
        updated = store.update(UserProfileUpdateRequest(role="Lead"))
        assert updated.display_name == "Alex"
        assert updated.role == "Lead"

    def test_updated_at_increases_monotonically(self, store: UserProfileStore) -> None:
        first = store.update(UserProfileUpdateRequest(display_name="Alex"))
        second = store.update(UserProfileUpdateRequest(role="Lead"))
        assert second.updated_at >= first.updated_at


class TestFilePermissions:
    def test_file_is_0600_after_save(self, tmp_path, store: UserProfileStore) -> None:
        store.update(UserProfileUpdateRequest(display_name="Alex"))
        path = tmp_path / "user_profile.json"
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600


class TestAvatarRef:
    _HEX32 = "0123456789abcdef0123456789abcdef"[:32]

    def test_set_avatar_ref_without_profile_raises(self, store: UserProfileStore) -> None:
        with pytest.raises(ValueError):
            store.set_avatar_ref(f"avatar-{self._HEX32}.png")

    def test_set_avatar_ref_with_profile(self, store: UserProfileStore) -> None:
        store.update(UserProfileUpdateRequest(display_name="Alex"))
        updated = store.set_avatar_ref(f"avatar-{self._HEX32}.png")
        assert updated.avatar_ref == f"avatar-{self._HEX32}.png"

    def test_clear_avatar_ref_without_profile_returns_none(
        self, store: UserProfileStore
    ) -> None:
        assert store.clear_avatar_ref() is None

    def test_clear_avatar_ref_removes_reference(self, store: UserProfileStore) -> None:
        store.update(UserProfileUpdateRequest(display_name="Alex"))
        store.set_avatar_ref(f"avatar-{self._HEX32}.png")
        cleared = store.clear_avatar_ref()
        assert cleared is not None
        assert cleared.avatar_ref is None


class TestAvatarDir:
    def test_avatar_dir_is_created_under_data_dir(
        self, tmp_path, store: UserProfileStore
    ) -> None:
        directory = store.avatar_dir
        assert directory.exists()
        assert directory.parent == tmp_path


class TestPersistenceAcrossInstances:
    def test_second_instance_reads_state_written_by_first(self, tmp_path) -> None:
        first = UserProfileStore(data_dir=tmp_path)
        first.update(UserProfileUpdateRequest(display_name="Alex Schneider"))

        second = UserProfileStore(data_dir=tmp_path)
        loaded = second.load()
        assert loaded is not None
        assert loaded.display_name == "Alex Schneider"
