"""Endpunkt-Tests fuer ``/api/persona-sets`` (Issue #1807, Slice 7b).

Dateiadapter in ``tmp_path``; die alte Persona-Bibliothek und ihr Marker laufen
ueber eine In-Memory-Ablage, damit kein Test die echte Ablage beruehrt.
"""

from __future__ import annotations

import os

import pytest
from flask import Flask

from app.api import persona_sets_bp
from app.config import Config
from app.services.artifact_store import InMemoryArtifactStore
from app.services.persona_library import PersonaLibrary


@pytest.fixture(autouse=True)
def _clear_auth_token():
    prev = os.environ.pop("AGORA_AUTH_TOKEN", None)
    try:
        yield
    finally:
        if prev is not None:
            os.environ["AGORA_AUTH_TOKEN"] = prev


@pytest.fixture
def legacy_store(monkeypatch) -> InMemoryArtifactStore:
    store = InMemoryArtifactStore()
    monkeypatch.setattr(
        "app.services.persona_set_service.PersonaLibrary",
        lambda: PersonaLibrary(store=store),
    )
    monkeypatch.setattr(
        "app.services.persona_set_service.LocalFilesystemArtifactStore",
        lambda: store,
    )
    return store


@pytest.fixture
def client(tmp_path, monkeypatch, legacy_store):
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(Config, "PERSONA_SET_BACKEND", "file")
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    app.extensions = {}
    app.register_blueprint(persona_sets_bp, url_prefix="/api/persona-sets")
    return app.test_client()


def _create(client, name="Betroffene") -> str:
    res = client.post("/api/persona-sets", json={"name": name})
    assert res.status_code == 201
    return res.get_json()["data"]["id"]


def _add(client, set_id, username="anna", origin="manual", **profile):
    return client.post(
        f"/api/persona-sets/{set_id}/entries",
        json={
            "origin": origin,
            "profile": {"username": username, "name": username.title(), **profile},
        },
    )


def _lock(set_id: str, simulation_id: str = "sim_1"):
    from app.services.persona_set_service import PersonaSetService

    PersonaSetService().record_run(set_id, simulation_id)


# --- Saetze ---------------------------------------------------------------


def test_create_und_get_roundtrip(client):
    res = client.post(
        "/api/persona-sets", json={"name": "Pflege", "description": "Gutachten"}
    )

    assert res.status_code == 201
    created = res.get_json()["data"]
    assert created["id"].startswith("pset_")
    assert created["entries"] == []
    assert created["locked_at"] is None

    fetched = client.get(f"/api/persona-sets/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.get_json()["data"] == created


def test_create_ohne_name_ist_400_validation_failed(client):
    res = client.post("/api/persona-sets", json={"description": "x"})

    assert res.status_code == 400
    body = res.get_json()
    assert body["success"] is False
    assert body["code"] == "validation_failed"


def test_create_mit_unbekanntem_feld_ist_400(client):
    res = client.post("/api/persona-sets", json={"name": "A", "locked_at": "x"})

    assert res.status_code == 400
    assert res.get_json()["code"] == "validation_failed"


def test_get_unbekannt_ist_404_not_found(client):
    res = client.get("/api/persona-sets/pset_nein")

    assert res.status_code == 404
    assert res.get_json()["code"] == "not_found"


def test_list_liefert_kacheln_mit_zaehlern(client):
    set_id = _create(client)
    _add(client, set_id)

    res = client.get("/api/persona-sets")

    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["count"] == 1
    summary = data["sets"][0]
    assert summary["id"] == set_id
    assert summary["entry_count"] == 1
    assert summary["locked"] is False
    assert "entries" not in summary


def test_patch_aendert_name_auch_wenn_gesperrt(client):
    set_id = _create(client)
    _add(client, set_id)
    _lock(set_id)

    res = client.patch(f"/api/persona-sets/{set_id}", json={"name": "Neu"})

    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["name"] == "Neu"
    assert data["locked_at"] is not None


def test_patch_ohne_feld_ist_400(client):
    set_id = _create(client)

    res = client.patch(f"/api/persona-sets/{set_id}", json={})

    assert res.status_code == 400


def test_delete_ungesperrt_ok_gesperrt_409(client):
    free = _create(client, "Frei")
    locked = _create(client, "Gesperrt")
    _add(client, locked)
    _lock(locked)

    ok = client.delete(f"/api/persona-sets/{free}")
    assert ok.status_code == 200
    assert ok.get_json()["data"] == {"removed": free}
    assert client.get(f"/api/persona-sets/{free}").status_code == 404

    refused = client.delete(f"/api/persona-sets/{locked}")
    assert refused.status_code == 409
    assert refused.get_json()["code"] == "persona_set_locked"
    assert client.get(f"/api/persona-sets/{locked}").status_code == 200


def test_delete_unbekannt_ist_404(client):
    assert client.delete("/api/persona-sets/pset_nein").status_code == 404


def test_duplicate_liefert_bearbeitbare_kopie_eines_gesperrten_satzes(client):
    set_id = _create(client)
    _add(client, set_id, origin="fallback")
    _lock(set_id)

    res = client.post(f"/api/persona-sets/{set_id}/duplicate", json={"name": "Kopie"})

    assert res.status_code == 201
    copy = res.get_json()["data"]
    assert copy["id"] != set_id
    assert copy["name"] == "Kopie"
    assert copy["locked_at"] is None
    assert copy["used_by_simulation_ids"] == []
    assert [e["origin"] for e in copy["entries"]] == ["fallback"]
    assert _add(client, copy["id"], username="bernd").status_code == 201


def test_duplicate_ohne_name_ist_400(client):
    set_id = _create(client)

    assert client.post(f"/api/persona-sets/{set_id}/duplicate", json={}).status_code == 400


# --- Eintraege ------------------------------------------------------------


def test_add_entry_201_mit_serverkennung_und_herkunft(client):
    set_id = _create(client)

    res = _add(client, set_id, origin="ai_draft", age=41)

    assert res.status_code == 201
    entry = res.get_json()["data"]
    assert entry["entry_id"].startswith("pent_")
    assert entry["origin"] == "ai_draft"
    assert entry["profile"]["age"] == 41


def test_add_entry_doppelter_username_ist_409_conflict(client):
    set_id = _create(client)
    _add(client, set_id, username="anna")

    res = _add(client, set_id, username="ANNA")

    assert res.status_code == 409
    assert res.get_json()["code"] == "conflict"


def test_add_entry_vertragsverletzung_ist_400(client):
    set_id = _create(client)

    res = client.post(
        f"/api/persona-sets/{set_id}/entries",
        json={"origin": "unbekannt", "profile": {"username": "a", "name": "A"}},
    )

    assert res.status_code == 400
    assert res.get_json()["code"] == "validation_failed"


def test_entry_aendern_und_loeschen_im_gesperrten_satz_ist_409(client):
    set_id = _create(client)
    entry_id = _add(client, set_id).get_json()["data"]["entry_id"]
    _lock(set_id)

    assert _add(client, set_id, username="bernd").status_code == 409
    patched = client.patch(
        f"/api/persona-sets/{set_id}/entries/{entry_id}", json={"origin": "fallback"}
    )
    assert patched.status_code == 409
    assert patched.get_json()["code"] == "persona_set_locked"
    deleted = client.delete(f"/api/persona-sets/{set_id}/entries/{entry_id}")
    assert deleted.status_code == 409
    bulk = client.post(
        f"/api/persona-sets/{set_id}/entries/delete", json={"entry_ids": [entry_id]}
    )
    assert bulk.status_code == 409

    entries = client.get(f"/api/persona-sets/{set_id}").get_json()["data"]["entries"]
    assert [e["entry_id"] for e in entries] == [entry_id]


def test_entry_patch_ersetzt_profil(client):
    set_id = _create(client)
    entry_id = _add(client, set_id).get_json()["data"]["entry_id"]

    res = client.patch(
        f"/api/persona-sets/{set_id}/entries/{entry_id}",
        json={"profile": {"username": "anna", "name": "Anna Neu", "bio": "neu"}},
    )

    assert res.status_code == 200
    assert res.get_json()["data"]["profile"]["name"] == "Anna Neu"


def test_entry_patch_unbekannter_eintrag_ist_404(client):
    set_id = _create(client)

    res = client.patch(
        f"/api/persona-sets/{set_id}/entries/pent_nein", json={"origin": "manual"}
    )

    assert res.status_code == 404
    assert res.get_json()["code"] == "not_found"


def test_entry_delete_antwortet_mit_kennung_und_neuem_stand(client):
    set_id = _create(client)
    first = _add(client, set_id, username="anna").get_json()["data"]["entry_id"]
    _add(client, set_id, username="bernd")

    res = client.delete(f"/api/persona-sets/{set_id}/entries/{first}")

    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["removed_entry_ids"] == [first]
    assert data["set"]["entry_count"] == 1


def test_entries_delete_mehrfach_alles_oder_nichts(client):
    set_id = _create(client)
    ids = [
        _add(client, set_id, username=name).get_json()["data"]["entry_id"]
        for name in ("anna", "bernd", "carla")
    ]

    unknown = client.post(
        f"/api/persona-sets/{set_id}/entries/delete",
        json={"entry_ids": [ids[0], "pent_nein"]},
    )
    assert unknown.status_code == 404
    unchanged = client.get(f"/api/persona-sets/{set_id}").get_json()["data"]["entries"]
    assert len(unchanged) == 3

    ok = client.post(
        f"/api/persona-sets/{set_id}/entries/delete",
        json={"entry_ids": [ids[0], ids[0], ids[2]]},
    )
    assert ok.status_code == 200
    data = ok.get_json()["data"]
    assert data["removed_entry_ids"] == [ids[0], ids[2]]
    assert data["set"]["entry_count"] == 1


def test_entries_delete_leere_auswahl_ist_400(client):
    set_id = _create(client)

    res = client.post(f"/api/persona-sets/{set_id}/entries/delete", json={"entry_ids": []})

    assert res.status_code == 400


# --- Qualitaet ------------------------------------------------------------


def test_quality_liefert_hinweise_je_eintrag(client):
    set_id = _create(client)
    _add(client, set_id, username="leer", origin="ai_draft")

    res = client.get(f"/api/persona-sets/{set_id}/quality")

    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["set_id"] == set_id
    assert data["summary"]["total"] == 1
    assert data["personas"][0]["username"] == "leer"
    codes = {i["code"] for i in data["personas"][0]["issues"]}
    assert "missing_core_fields" in codes


def test_quality_unbekannter_satz_ist_404(client):
    assert client.get("/api/persona-sets/pset_nein/quality").status_code == 404


# --- Altbestand beim ersten Lesen -----------------------------------------


def test_erste_liste_uebernimmt_den_altbestand_einmalig(client, legacy_store):
    library = PersonaLibrary(store=legacy_store)
    library.save_template({"username": "anna", "name": "Anna", "persona": "Skeptisch."})

    first = client.get("/api/persona-sets").get_json()["data"]
    assert first["count"] == 1
    assert first["sets"][0]["name"] == "Importiert"
    assert first["sets"][0]["entry_count"] == 1

    again = client.get("/api/persona-sets").get_json()["data"]
    assert again["count"] == 1
    assert again["sets"][0]["entry_count"] == 1

    # Die alten Endpunkte-Daten bleiben unberuehrt.
    assert len(library.list_templates()) == 1


def test_liste_ohne_altbestand_bleibt_leer(client):
    data = client.get("/api/persona-sets").get_json()["data"]

    assert data == {"count": 0, "sets": []}
