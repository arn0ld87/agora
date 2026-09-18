"""Contract-Tests für ``app.repositories.llm_profile_repository`` (PR 3).

Prüft die Invarianten, die der Port in seinen Docstrings festschreibt, gegen
``SqliteLlmProfileRepository`` — den einen heutigen Adapter. Ein zweiter
Adapter (PostgreSQL, PR 4) muss dieselben Zusagen einhalten; diese Datei ist
die Referenz dafür.

Jede Instanz bekommt eine eigene, per ``monkeypatch`` auf ``tmp_path``
umgelenkte ``_instance_dir()`` — ``_db_path()`` wird bei jedem ``_connect()``
frisch berechnet, also greift das Monkeypatch schon im Konstruktor, bevor
die Instanz eine Zeile in eine Datei schreibt. Ohne das würde jeder Testlauf
in die echte ``backend/instance/llm_profiles.db`` schreiben.
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from app.config import Config
from app.contracts import LlmProfileCreateRequest
from app.repositories.llm_profile_repository import (
    LlmProfileBackendUnavailable,
    LlmProfileRepository,
    get_llm_profile_repository,
)
from app.services import llm_profiles_store as store_module


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> store_module.SqliteLlmProfileRepository:
    """Isolierter Adapter — jeder Test schreibt in sein eigenes ``tmp_path``."""
    monkeypatch.setattr(store_module, "_instance_dir", lambda: tmp_path)
    return store_module.SqliteLlmProfileRepository()


def _req(**overrides) -> LlmProfileCreateRequest:
    base = dict(
        name="Test-Profil",
        provider="ollama",
        base_url="http://localhost:11434/v1",
        model_name="qwen2.5:32b",
        api_key=None,
        is_default=False,
    )
    base.update(overrides)
    return LlmProfileCreateRequest(**base)


# ---------------------------------------------------------------------------
# 1. CRUD-Rückgabesemantik
# ---------------------------------------------------------------------------


def test_get_unknown_id_returns_none_instead_of_raising(repo):
    """Ein fehlendes Profil ist bei der Routenauflösung ein erwarteter Fall — kein Fehler."""
    assert repo.get("does-not-exist") is None


def test_delete_unknown_id_returns_false(repo):
    """Ein stiller Erfolg auf eine unbekannte ID würde einen echten Löschfehler verdecken."""
    assert repo.delete("does-not-exist") is False


def test_update_unknown_id_returns_none(repo):
    """Ein Update auf eine unbekannte ID darf kein Phantom-Profil anlegen."""
    assert repo.update("does-not-exist", _req()) is None


def test_create_get_update_delete_roundtrip(repo):
    """Der Grundvertrag: was angelegt wird, lässt sich lesen, ändern und entfernen."""
    created = repo.create(_req(name="Ursprung"))
    assert repo.get(created.id).name == "Ursprung"

    updated = repo.update(created.id, _req(name="Geändert"))
    assert updated is not None
    assert updated.name == "Geändert"

    assert repo.delete(created.id) is True
    assert repo.get(created.id) is None


# ---------------------------------------------------------------------------
# 2. Default-Wechsel
# ---------------------------------------------------------------------------


def test_second_default_create_unsets_the_first(repo):
    """Zwei Default-Profile gleichzeitig würden die Routenauflösung raten lassen."""
    first = repo.create(_req(name="A", is_default=True))
    second = repo.create(_req(name="B", is_default=True))

    defaults = [p for p in repo.list() if p.is_default]
    assert [p.id for p in defaults] == [second.id]
    assert repo.get(first.id).is_default is False


def test_set_default_on_unknown_id_returns_none_and_keeps_current_default(repo):
    """Ein Tippfehler in der ID darf den bestehenden Default nicht kommentarlos wegnehmen."""
    current = repo.create(_req(name="Bestand", is_default=True))

    assert repo.set_default("does-not-exist") is None
    assert repo.get(current.id).is_default is True


# ---------------------------------------------------------------------------
# 3. Bootstrap aus LLM_*-Env-Variablen
# ---------------------------------------------------------------------------


def test_list_bootstraps_profile_from_env_when_model_name_set(repo, monkeypatch):
    """Ohne Bootstrap steht eine frische Installation ohne jede Route da."""
    monkeypatch.setenv("LLM_MODEL_NAME", "qwen2.5:32b")
    monkeypatch.setenv("LLM_BASE_URL", "http://host.docker.internal:11434/v1")
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    profiles = repo.list()

    assert len(profiles) == 1
    assert profiles[0].model_name == "qwen2.5:32b"
    assert profiles[0].is_default is True


def test_list_stays_empty_without_model_name_env(repo, monkeypatch):
    """Ein totes Auto-Profil ohne LLM_MODEL_NAME führte in Cloud-Setups zu 404."""
    monkeypatch.delenv("LLM_MODEL_NAME", raising=False)

    assert repo.list() == []


# ---------------------------------------------------------------------------
# 4. api_key-Redaktion
# ---------------------------------------------------------------------------


_SECRET = "sk-super-secret-value-should-never-leak"


def test_list_never_returns_api_key(repo):
    """Jede API-Antwort nimmt den Default und darf den Schlüssel nie sehen."""
    repo.create(_req(api_key=_SECRET))

    profiles = repo.list()

    assert _SECRET not in repr(profiles)
    assert all(p.api_key == "" for p in profiles)


def test_get_without_include_api_key_redacts(repo):
    """Der Laufzeit-Resolver ist der einzig vorgesehene Weg zum Schlüssel — nicht ``get()`` per Default."""
    created = repo.create(_req(api_key=_SECRET))

    fetched = repo.get(created.id)

    assert fetched is not None
    assert _SECRET not in repr(fetched)
    assert fetched.api_key == ""


def test_get_with_include_api_key_returns_it(repo):
    """Ohne diesen Pfad könnte kein Provider mehr erreicht werden, der einen Key braucht."""
    created = repo.create(_req(api_key=_SECRET))

    fetched = repo.get(created.id, include_api_key=True)

    assert fetched is not None
    assert fetched.api_key == _SECRET


# ---------------------------------------------------------------------------
# 5. Die Dreiteilung von api_key in update()
# ---------------------------------------------------------------------------


def test_update_with_api_key_none_leaves_stored_key_untouched(repo):
    """Eine Oberfläche, die den Key nie zu sehen bekommt, darf ihn beim Speichern nicht löschen."""
    created = repo.create(_req(api_key=_SECRET))

    repo.update(created.id, _req(name="Umbenannt", api_key=None))

    assert repo.get(created.id, include_api_key=True).api_key == _SECRET


def test_update_with_empty_string_clears_stored_key(repo):
    """Ein ausdrücklich geleertes Feld muss den Key wirklich entfernen, nicht nur die Anzeige."""
    created = repo.create(_req(api_key=_SECRET))

    repo.update(created.id, _req(name="Umbenannt", api_key=""))

    assert repo.get(created.id, include_api_key=True).api_key == ""


def test_update_with_new_value_replaces_stored_key(repo):
    """Ein rotierter Schlüssel darf nicht neben dem alten liegen bleiben."""
    created = repo.create(_req(api_key=_SECRET))

    repo.update(created.id, _req(name="Umbenannt", api_key="rotated-key"))

    assert repo.get(created.id, include_api_key=True).api_key == "rotated-key"


# ---------------------------------------------------------------------------
# 6. Parallele Zugriffe
# ---------------------------------------------------------------------------


def test_concurrent_create_and_list_lose_no_record_and_keep_one_default(repo):
    """Ein Data Race dürfte hier weder Profile verschlucken noch zwei Defaults hinterlassen."""
    n = 20
    errors: list[BaseException] = []

    def _create(i: int) -> None:
        try:
            repo.create(_req(name=f"Profil-{i}", is_default=True))
        except BaseException as exc:  # pragma: no cover - Diagnose bei Fehlschlag
            errors.append(exc)

    def _list() -> None:
        try:
            repo.list()
        except BaseException as exc:  # pragma: no cover - Diagnose bei Fehlschlag
            errors.append(exc)

    threads = [threading.Thread(target=_create, args=(i,)) for i in range(n)]
    threads += [threading.Thread(target=_list) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    profiles = repo.list()
    assert len(profiles) == n
    assert sum(1 for p in profiles if p.is_default) == 1


# ---------------------------------------------------------------------------
# 7. Factory
# ---------------------------------------------------------------------------


def test_factory_returns_something_satisfying_the_port_protocol():
    """Ein Consumer, der sich auf den Port verlässt, darf keinen Adapter ohne dessen Methoden bekommen."""
    assert isinstance(get_llm_profile_repository(), LlmProfileRepository)


def test_factory_raises_for_backend_without_adapter(monkeypatch):
    """Ein stiller Fallback auf sqlite sähe nach einer bewussten Entscheidung aus, die keine war."""
    monkeypatch.setattr(Config, "LLM_PROFILE_BACKEND", "postgres")

    with pytest.raises(LlmProfileBackendUnavailable, match="PR 4"):
        get_llm_profile_repository()
