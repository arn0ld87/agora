"""Sub-Slice B — Manuell hinzugefügte Personas: Schema-Parity mit generierten Profilen.

Regression-Test für Issue #210:
Manuell über POST /<sim_id>/profiles hinzugefügte Personas haben bisher kein
``karma``, kein ``created_at`` und evtl. leere ``bio``/``persona``.
OASIS ignoriert oder bricht bei solchen Profilen — daher erscheinen sie in der
Simulation nicht.

Nach dem Fix muss read-after-write beweisen, dass persistierte manuelle Profile
die gleichen Pflichtfelder haben wie via ``_save_reddit_json`` generierte.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from flask import Flask

from app.api import simulation_bp
from app.services.artifact_store import InMemoryArtifactStore


SIM_ID = "sim_aabbccddeeff"
SIM_ID_EMPTY = "sim_00112233aabb"

# Bereits generierte Profile (wie _save_reddit_json sie schreibt)
GENERATED_PROFILES = [
    {
        "user_id": 0,
        "username": "gen_user_0",
        "name": "Generated User 0",
        "bio": "A generated participant in social discussion.",
        "persona": "gen_user_0 is a participant in social discussions who engages regularly.",
        "karma": 1000,
        "created_at": "2024-01-01T00:00:00",
        "age": 30,
        "gender": "other",
        "mbti": "ISTJ",
        "country": "DE",
        "profession": "Engineer",
        "interested_topics": ["Tech"],
        "source_entity_uuid": "ent-0001",
        "source_entity_type": "graph",
    }
]


@pytest.fixture()
def store() -> InMemoryArtifactStore:
    s = InMemoryArtifactStore()
    s.write_json(SIM_ID, "reddit_profiles", list(GENERATED_PROFILES))
    return s


@pytest.fixture()
def client(store, tmp_path, monkeypatch):
    """Flask-Testclient mit InMemoryArtifactStore + gemocktem sim_dir-Check."""
    app = Flask(__name__)
    app.extensions["artifact_store"] = store
    app.extensions["neo4j_storage"] = MagicMock(name="Neo4jStorage")

    # Beide Sim-Verzeichnisse anlegen, damit der os.path.exists-Check greift
    (tmp_path / SIM_ID).mkdir()
    (tmp_path / SIM_ID_EMPTY).mkdir()

    # Patch Config.OASIS_SIMULATION_DATA_DIR via monkeypatch — auto-reverts after test
    import app.api.simulation_profiles as mod
    monkeypatch.setattr(mod.Config, "OASIS_SIMULATION_DATA_DIR", str(tmp_path))

    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")

    with app.test_client() as c:
        yield c


def _get_profiles(store: InMemoryArtifactStore, sim_id: str = SIM_ID) -> list[dict]:
    return store.read_json(sim_id, "reddit_profiles", default=[])


# ---------------------------------------------------------------------------
# RED tests — diese Tests schlagen FEHL, solange der Bug besteht
# ---------------------------------------------------------------------------


def test_manual_profile_has_karma(client, store):
    """Persistiertes manuelles Profil muss ein ``karma``-Feld >= 0 besitzen."""
    resp = client.post(
        f"/api/simulation/{SIM_ID}/profiles",
        json={"username": "manual_max", "name": "Max Muster"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    profiles = _get_profiles(store)
    manual = next(p for p in profiles if p.get("username") == "manual_max")
    assert "karma" in manual, "Fehlendes Feld: karma"
    assert isinstance(manual["karma"], int), "karma muss ein Integer sein"
    assert manual["karma"] >= 0


def test_manual_profile_has_created_at(client, store):
    """Persistiertes manuelles Profil muss ``created_at`` besitzen."""
    resp = client.post(
        f"/api/simulation/{SIM_ID}/profiles",
        json={"username": "manual_anna", "name": "Anna Beispiel"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    profiles = _get_profiles(store)
    manual = next(p for p in profiles if p.get("username") == "manual_anna")
    assert "created_at" in manual, "Fehlendes Feld: created_at"
    assert manual["created_at"], "created_at darf nicht leer sein"


def test_manual_profile_bio_nonempty_when_not_provided(client, store):
    """Wenn kein ``bio`` mitgegeben wird, muss ein Fallback-Wert gesetzt werden."""
    resp = client.post(
        f"/api/simulation/{SIM_ID}/profiles",
        json={"username": "nobio_user", "name": "No Bio"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    profiles = _get_profiles(store)
    manual = next(p for p in profiles if p.get("username") == "nobio_user")
    assert manual.get("bio"), "bio darf nicht leer sein, wenn kein bio angegeben"


def test_manual_profile_persona_nonempty_when_not_provided(client, store):
    """Wenn kein ``persona`` mitgegeben wird, muss ein Fallback-Wert gesetzt werden."""
    resp = client.post(
        f"/api/simulation/{SIM_ID}/profiles",
        json={"username": "nopersona_user", "name": "No Persona"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    profiles = _get_profiles(store)
    manual = next(p for p in profiles if p.get("username") == "nopersona_user")
    assert manual.get("persona"), "persona darf nicht leer sein, wenn kein persona angegeben"


def test_manual_profile_user_id_unique_and_nonzero_when_profiles_exist(client, store):
    """next_id darf nicht auf einer existierenden user_id kollidieren."""
    resp = client.post(
        f"/api/simulation/{SIM_ID}/profiles",
        json={"username": "uniqueid_user", "name": "Unique ID"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    profiles = _get_profiles(store)
    ids = [p["user_id"] for p in profiles]
    # Alle IDs müssen eindeutig sein
    assert len(ids) == len(set(ids)), f"Doppelte user_ids: {ids}"
    manual = next(p for p in profiles if p.get("username") == "uniqueid_user")
    # Muss > 0 sein, weil user_id=0 bereits dem generierten Profil gehört
    assert manual["user_id"] > 0, f"user_id kollidiert: {manual['user_id']}"


def test_manual_profile_user_id_starts_at_1_when_no_profiles_exist(client, store):
    """Wenn noch keine Profile vorhanden sind, beginnt user_id bei 1 (nicht 0).

    Defensive Absicherung: Falls prepare_service bei einem Neustart mit user_id=0
    anfängt und danach manuell jemand hinzukommt, soll keine Kollision entstehen.
    """
    # SIM_ID_EMPTY hat keine Profile im Store
    resp = client.post(
        f"/api/simulation/{SIM_ID_EMPTY}/profiles",
        json={"username": "first_manual", "name": "First Manual"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    profiles = _get_profiles(store, SIM_ID_EMPTY)
    assert len(profiles) == 1
    assert profiles[0]["user_id"] == 1, (
        f"Erster manueller user_id sollte 1 sein, nicht {profiles[0]['user_id']}"
    )


def test_provided_bio_and_persona_are_kept(client, store):
    """Explizit gelieferte bio/persona dürfen nicht vom Fallback überschrieben werden."""
    resp = client.post(
        f"/api/simulation/{SIM_ID}/profiles",
        json={
            "username": "full_user",
            "name": "Full User",
            "bio": "Ein ausführlicher Steckbrief.",
            "persona": "Full User nimmt aktiv an sozialen Diskussionen teil und vertritt liberale Werte.",
        },
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    profiles = _get_profiles(store)
    manual = next(p for p in profiles if p.get("username") == "full_user")
    assert manual["bio"] == "Ein ausführlicher Steckbrief."
    assert "Full User nimmt aktiv" in manual["persona"]
