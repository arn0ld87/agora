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

# Die Stores, die ihre Auflösung aus ``data_dir`` beziehen. ``api_keys_store``
# steht bewusst NICHT in dieser Liste: es führt ein gleichnamiges
# ``_resolve_data_dir`` mit abweichender Signatur (``Optional[Path]``) und
# eigener Semantik.
_STORE_MODULES = [
    "api_keys_persistence",
    "embedding_configuration_store",
    "llm_provider_secrets_store",
    "onboarding_state_store",
    "provider_connection_store",
    "user_profile_store",
    "workspace_routing_store",
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
    """Hält die sieben Stores an der gemeinsamen Auflösung."""

    @pytest.mark.parametrize("module_name", _STORE_MODULES)
    def test_store_uses_shared_resolver(self, module_name):
        module = importlib.import_module(f"app.services.{module_name}")
        assert module._resolve_data_dir is resolve_data_dir, (
            f"{module_name} löst das Datenverzeichnis wieder selbst auf — "
            "damit driften die Stores erneut auseinander."
        )

    def test_all_stores_agree_on_the_directory(self, monkeypatch, tmp_path):
        monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path))

        resolved = {
            name: importlib.import_module(f"app.services.{name}")._resolve_data_dir()
            for name in _STORE_MODULES
        }

        assert set(resolved.values()) == {tmp_path.resolve()}
