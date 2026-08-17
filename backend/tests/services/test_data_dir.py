"""Tests für ``app/services/data_dir.py``.

Die sieben dateibasierten JSON-Stores trugen bis zum 17.08.2026 je eine eigene,
zeichengleiche Kopie der Datenverzeichnis-Auflösung. Diese Tests pinnen das
zusammengeführte Verhalten und halten die Stores daran.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from app.services.data_dir import DATA_DIR_ENV, resolve_data_dir
from app.services.json_file_store import JsonFileStore

# Stores, die ``resolve_data_dir`` direkt als Modulfunktion beziehen.
# ``api_keys_store`` steht bewusst NICHT in dieser Liste: es führt ein
# gleichnamiges ``_resolve_data_dir`` mit abweichender Signatur
# (``Optional[Path]``) und eigener Semantik.
_MODULE_LEVEL_STORES = [
    "api_keys_persistence",
    "embedding_configuration_store",
    "llm_provider_secrets_store",
    "provider_connection_store",
]

# Stores, die die Auflösung über ``JsonFileStore`` erben.
_JSON_FILE_STORES = [
    ("onboarding_state_store", "OnboardingStateStore", "onboarding_state.json"),
    ("user_profile_store", "UserProfileStore", "user_profile.json"),
    ("workspace_routing_store", "WorkspaceRoutingStore", "workspace_llm_routing.json"),
]


class TestResolveDataDir:
    def test_env_override_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path))
        assert resolve_data_dir() == tmp_path.resolve()

    def test_env_value_is_expanded_and_resolved(self, monkeypatch):
        monkeypatch.setenv(DATA_DIR_ENV, "~")
        assert resolve_data_dir() == Path("~").expanduser().resolve()

    def test_fallback_is_backend_data(self, monkeypatch):
        """Der Fallback hängt an der Modulposition — hier festgenagelt."""
        monkeypatch.delenv(DATA_DIR_ENV, raising=False)

        resolved = resolve_data_dir()

        assert resolved.name == "data"
        assert resolved.parent.name == "backend"

    def test_empty_env_value_falls_back(self, monkeypatch):
        """Leerstring ist kein Pfad — sonst landeten die Daten im cwd."""
        monkeypatch.setenv(DATA_DIR_ENV, "")

        resolved = resolve_data_dir()

        assert resolved.name == "data"
        assert resolved.parent.name == "backend"

    def test_evaluated_per_call_not_at_import_time(self, monkeypatch, tmp_path):
        """``tests/conftest.py`` setzt die Variable je Test — das muss greifen."""
        first = tmp_path / "one"
        second = tmp_path / "two"

        monkeypatch.setenv(DATA_DIR_ENV, str(first))
        assert resolve_data_dir() == first.resolve()

        monkeypatch.setenv(DATA_DIR_ENV, str(second))
        assert resolve_data_dir() == second.resolve()


class TestStoresShareOneResolution:
    """Hält die sieben Stores an der gemeinsamen Auflösung.

    Es gibt zwei Wege dorthin, und beide werden geprüft: vier Stores rufen
    ``resolve_data_dir`` als Modulfunktion auf, drei erben sie über
    ``JsonFileStore``. Geprüft wird deshalb das *Ergebnis* — welches
    Verzeichnis am Ende benutzt wird — und nicht die Objektidentität der
    Funktion: Letztere bricht bei jedem legitimen Umbau, ohne dass sich am
    Verhalten etwas ändert.
    """

    @pytest.mark.parametrize("module_name", _MODULE_LEVEL_STORES)
    def test_module_level_store_uses_shared_resolver(self, module_name, monkeypatch, tmp_path):
        monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path))
        module = importlib.import_module(f"app.services.{module_name}")

        assert module._resolve_data_dir() == tmp_path.resolve(), (
            f"{module_name} löst das Datenverzeichnis wieder selbst auf — "
            "damit driften die Stores erneut auseinander."
        )

    @pytest.mark.parametrize("module_name,class_name,filename", _JSON_FILE_STORES)
    def test_json_file_store_inherits_resolution(
        self, module_name, class_name, filename, monkeypatch, tmp_path
    ):
        monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path))
        store_cls = getattr(importlib.import_module(f"app.services.{module_name}"), class_name)

        assert issubclass(store_cls, JsonFileStore), (
            f"{class_name} erbt die Datei- und Sperrmechanik nicht mehr — "
            "prüfen, ob dabei wieder eigene Kopien entstanden sind."
        )
        store = store_cls()
        assert store._data_dir == tmp_path.resolve()
        assert store._path == tmp_path.resolve() / filename

    def test_all_seven_stores_agree_on_the_directory(self, monkeypatch, tmp_path):
        monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path))

        resolved = {
            name: importlib.import_module(f"app.services.{name}")._resolve_data_dir()
            for name in _MODULE_LEVEL_STORES
        }
        for module_name, class_name, _ in _JSON_FILE_STORES:
            store_cls = getattr(
                importlib.import_module(f"app.services.{module_name}"), class_name
            )
            resolved[module_name] = store_cls()._data_dir

        assert len(resolved) == 7
        assert set(resolved.values()) == {tmp_path.resolve()}
