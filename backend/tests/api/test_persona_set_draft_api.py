"""Tests fuer den KI-Entwurf im Personasatz (Issue #1807, Slice 7c).

Der Entwurf ist der einzige LLM-Aufruf der Etappe 7. Er laeuft ueber einen
eigenen Job (``run_type="persona_draft"``), damit der Aufruf im Budget-Ledger
landet und in der Aktivitaet sichtbar wird — sonst waere ein Entwurf ein
Aufruf ohne Spur.

Hier wird das LLM durch einen Fake ersetzt; getestet wird die HTTP-Kante:
Vertrag, Herkunft, Sperrregel und Fehlerbild. Das Verhalten des LLM-Aufrufs
selbst (Prompt, Schema, Retries) steht in
``backend/tests/services/test_persona_set_draft_service.py``.
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


@pytest.fixture
def draft(monkeypatch):
    """Ersetzt den LLM-Aufruf. Gibt die Aufrufe fuer die Assertions zurueck."""
    calls: list[dict] = []

    def fake_draft(*, set_id, brief, language="de"):
        calls.append({"set_id": set_id, "brief": brief, "language": language})
        return {
            "profile": {
                "username": "KarlaBrandt",
                "name": "Karla Brandt",
                "bio": "Betriebsratin aus Bremen, seit zwei Jahren im Konflikt.",
                "persona": "Spricht sachlich, stellt Rueckfragen, nennt Zahlen.",
                "age": 41,
                "gender": "female",
                "mbti": "INTJ",
                "country": "DE",
                "profession": "Betriebsratin",
                "interested_topics": ["Arbeitsrecht", "Schichtmodelle"],
                "language": "de",
                "activity_level": 0.6,
                "time_zone": "Europe/Berlin",
                "location": "Bremen",
            },
            "example_post": {
                "content": "Die Schichtplanung muss vor dem Quartalsende "
                "mit dem Betriebsrat abgestimmt sein.",
                "network": "twitter",
            },
        }

    monkeypatch.setattr(
        "app.api.persona_sets.draft_persona_entry", fake_draft, raising=True
    )
    return calls


def _create(client, name="Betroffene") -> str:
    res = client.post("/api/persona-sets", json={"name": name})
    assert res.status_code == 201
    return res.get_json()["data"]["id"]


def test_draft_requires_a_brief(client, draft):
    set_id = _create(client)
    res = client.post(f"/api/persona-sets/{set_id}/draft", json={"brief": ""})
    assert res.status_code == 400
    assert res.get_json()["code"] == "validation_failed"
    assert draft == [], "ohne Brief darf das LLM nicht laufen"


def test_draft_adds_entry_with_ai_origin(client, draft):
    set_id = _create(client)
    res = client.post(
        f"/api/persona-sets/{set_id}/draft",
        json={"brief": "Betriebsratin aus Bremen", "language": "de"},
    )
    assert res.status_code == 201
    data = res.get_json()["data"]
    assert data["origin"] == "ai_draft"
    assert data["profile"]["username"] == "KarlaBrandt"
    assert data["example_post"]["network"] == "twitter"
    assert len(draft) == 1
    assert draft[0]["brief"] == "Betriebsratin aus Bremen"


def test_draft_entry_is_persisted_in_the_set(client, draft):
    set_id = _create(client)
    client.post(f"/api/persona-sets/{set_id}/draft", json={"brief": "Bremen"})

    record = client.get(f"/api/persona-sets/{set_id}").get_json()["data"]
    assert [e["origin"] for e in record["entries"]] == ["ai_draft"]

    summary = client.get("/api/persona-sets").get_json()["data"]
    assert summary["sets"][0]["entry_count"] == 1


def test_draft_reports_a_duplicate_username(client, draft):
    """Der Entwurf darf keinen zweiten Eintrag mit gleichem ``username`` anlegen."""
    set_id = _create(client)
    first = client.post(f"/api/persona-sets/{set_id}/draft", json={"brief": "Bremen"})
    assert first.status_code == 201

    second = client.post(f"/api/persona-sets/{set_id}/draft", json={"brief": "Bremen"})
    assert second.status_code == 409
    assert second.get_json()["code"] == "conflict"


def test_draft_is_refused_on_a_locked_set(client, draft):
    """Ein gesperrter Satz bleibt unveraenderlich — auch durch einen Entwurf."""
    set_id = _create(client)
    added = client.post(
        f"/api/persona-sets/{set_id}/entries",
        json={
            "origin": "manual",
            "profile": {"username": "Hand", "name": "Von Hand"},
        },
    )
    assert added.status_code == 201

    from app.services.persona_set_service import PersonaSetService

    PersonaSetService().record_run(set_id, "sim_test")

    res = client.post(f"/api/persona-sets/{set_id}/draft", json={"brief": "Bremen"})
    assert res.status_code == 409
    assert res.get_json()["code"] == "persona_set_locked"
    assert draft == [], "der Sperrfehler muss vor dem LLM greifen"


def test_draft_on_unknown_set_is_404(client, draft):
    res = client.post("/api/persona-sets/pset_gibtsnicht/draft", json={"brief": "x"})
    assert res.status_code == 404
    assert draft == []


def test_draft_reports_a_provider_failure(client, monkeypatch):
    """Ein Anbieterfehler ist ein 502 mit Grund, kein 500 und kein leerer Eintrag."""
    from app.services.persona_set_draft_service import PersonaDraftError

    def boom(**_kwargs):
        raise PersonaDraftError("provider returned 503")

    monkeypatch.setattr("app.api.persona_sets.draft_persona_entry", boom)

    set_id = _create(client)
    res = client.post(f"/api/persona-sets/{set_id}/draft", json={"brief": "Bremen"})
    assert res.status_code == 502
    assert "503" in res.get_json()["error"]

    record = client.get(f"/api/persona-sets/{set_id}").get_json()["data"]
    assert record["entries"] == [], "ein Fehlschlag legt keinen Eintrag an"
