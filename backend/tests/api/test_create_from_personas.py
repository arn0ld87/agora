"""Endpunkt-Tests fuer /api/simulation/create-from-personas (Block B4).

Der Weg soll einen Lauf allein aus gespeicherten Personas anlegen —
ohne Dokument, Ontologie oder Graph. Geprueft wird hier die HTTP-Ebene:
Eingabevalidierung, Aufloesung der Bibliotheks-Verweise und die
Verdrahtung mit dem Vorbereitungs-Service.
"""

import os
import pathlib
from unittest.mock import patch

import pytest
from flask import Flask

from app.api import simulation_bp


@pytest.fixture(autouse=True)
def _clear_auth_token():
    prev = os.environ.pop("AGORA_AUTH_TOKEN", None)
    try:
        yield
    finally:
        if prev is not None:
            os.environ["AGORA_AUTH_TOKEN"] = prev


def _client():
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    app.extensions = {}
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app.test_client()


PERSONA = {
    "template_id": "tpl_1",
    "username": "sachbearbeiterin",
    "name": "Sachbearbeiterin",
    "persona": "Skeptisch gegenueber Reformen.",
}


def test_verlangt_eine_fragestellung():
    res = _client().post("/api/simulation/create-from-personas", json={"personas": [PERSONA]})

    assert res.status_code == 400
    assert res.get_json()["success"] is False


def test_verlangt_personas_oder_template_ids():
    res = _client().post(
        "/api/simulation/create-from-personas",
        json={"simulation_requirement": "Wie reagiert die Belegschaft?"},
    )

    assert res.status_code == 400


def test_meldet_unbekannte_template_ids_statt_leer_zu_starten():
    # Ein Lauf ohne Personas waere sinnlos — hier muss 404 kommen,
    # nicht ein leerer, scheinbar erfolgreicher Lauf.
    with patch("app.api.simulation_lifecycle.PersonaLibrary") as lib:
        lib.return_value.list_templates.return_value = [PERSONA]
        res = _client().post(
            "/api/simulation/create-from-personas",
            json={"simulation_requirement": "Frage", "template_ids": ["gibt_es_nicht"]},
        )

    assert res.status_code == 404


def test_legt_projekt_und_simulation_an_und_bereitet_vor():
    with patch("app.api.simulation_lifecycle.PersonaLibrary") as lib, \
         patch("app.api.simulation_lifecycle.ProjectManager") as pm, \
         patch("app.api.simulation_lifecycle.SimulationManager") as sm, \
         patch("app.api.simulation_lifecycle.prepare_from_personas") as prep:
        lib.return_value.list_templates.return_value = [PERSONA]
        pm.create_project.return_value.project_id = "proj_neu"
        sm.return_value.create_simulation.return_value.simulation_id = "sim_neu"

        res = _client().post(
            "/api/simulation/create-from-personas",
            json={"simulation_requirement": "Wie reagiert die Belegschaft?", "template_ids": ["tpl_1"]},
        )

    assert res.status_code == 201
    payload = res.get_json()
    assert payload["success"] is True
    assert payload["data"]["simulation_id"] == "sim_neu"
    assert payload["data"]["project_id"] == "proj_neu"
    assert payload["data"]["persona_count"] == 1

    # Kern der Sache: die Simulation entsteht OHNE graph_id.
    sm.return_value.create_simulation.assert_called_once_with(project_id="proj_neu", graph_id="")
    prep.assert_called_once()
    assert prep.call_args[0][2] == [PERSONA]


def test_nimmt_auch_inline_personas_ohne_bibliothek():
    with patch("app.api.simulation_lifecycle.ProjectManager") as pm, \
         patch("app.api.simulation_lifecycle.SimulationManager") as sm, \
         patch("app.api.simulation_lifecycle.prepare_from_personas") as prep:
        pm.create_project.return_value.project_id = "proj_neu"
        sm.return_value.create_simulation.return_value.simulation_id = "sim_neu"

        res = _client().post(
            "/api/simulation/create-from-personas",
            json={"simulation_requirement": "Frage", "personas": [PERSONA]},
        )

    assert res.status_code == 201
    assert prep.call_args[0][2] == [PERSONA]


# --- Lauf aus Personasatz (#1807, Slice 7b) ---------------------------------


@pytest.fixture
def set_env(tmp_path, monkeypatch):
    """Echter Dienst und Dateiablage, echte Vorbereitung, kein Graph, kein Netz.

    ``ProjectManager`` ist ersetzt (es braucht nur eine Kennung); der
    ``SimulationManager`` ist ein echter mit In-Memory-Ablage, damit die
    geschriebenen Profile lesbar bleiben.
    """
    from app.config import Config
    from app.services.artifact_store import InMemoryArtifactStore
    from app.services.run_registry import RunRegistry
    from app.services.simulation_manager import SimulationManager

    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(Config, "PERSONA_SET_BACKEND", "file")
    monkeypatch.setattr(
        SimulationManager, "SIMULATION_DATA_DIR", str(tmp_path / "simulations")
    )
    registry_dir = str(tmp_path / "run_registry")
    monkeypatch.setattr(RunRegistry, "REGISTRY_DIR", registry_dir)
    RunRegistry._instance = None
    os.makedirs(registry_dir, exist_ok=True)

    manager = SimulationManager(store=InMemoryArtifactStore())
    with patch("app.api.simulation_lifecycle.ProjectManager") as pm, \
         patch("app.api.simulation_lifecycle.SimulationManager", lambda: manager):
        pm.create_project.return_value.project_id = "proj_neu"
        yield manager
    RunRegistry._instance = None


def _set_client():
    from app.api import persona_sets_bp

    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    app.extensions = {}
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    app.register_blueprint(persona_sets_bp, url_prefix="/api/persona-sets")
    return app.test_client()


def _make_set(client, usernames=("anna", "bernd")) -> str:
    set_id = client.post("/api/persona-sets", json={"name": "Betroffene"}).get_json()["data"]["id"]
    for username in usernames:
        res = client.post(
            f"/api/persona-sets/{set_id}/entries",
            json={
                "origin": "manual",
                "profile": {
                    "username": username,
                    "name": username.title(),
                    "persona": f"Persona von {username}.",
                },
            },
        )
        assert res.status_code == 201
    return set_id


def _run_from_set(client, set_id):
    return client.post(
        "/api/simulation/create-from-personas",
        json={"simulation_requirement": "Wie reagiert die Belegschaft?", "persona_set_id": set_id},
    )


def _usernames(manager, simulation_id):
    profiles = manager._store.read_json(simulation_id, "reddit_profiles", default=None)
    return [p["username"] for p in profiles]


def test_lauf_aus_satz_kopiert_personas_und_sperrt_den_satz(set_env):
    client = _set_client()
    set_id = _make_set(client)

    res = _run_from_set(client, set_id)

    assert res.status_code == 201
    data = res.get_json()["data"]
    assert data["persona_count"] == 2
    assert data["persona_set_id"] == set_id
    assert _usernames(set_env, data["simulation_id"]) == ["anna", "bernd"]

    locked = client.get(f"/api/persona-sets/{set_id}").get_json()["data"]
    assert locked["locked_at"] is not None
    assert locked["used_by_simulation_ids"] == [data["simulation_id"]]


def test_zwei_laeufe_aus_demselben_satz_erhalten_je_eine_kopie(set_env):
    client = _set_client()
    set_id = _make_set(client)

    first = _run_from_set(client, set_id).get_json()["data"]["simulation_id"]
    second = _run_from_set(client, set_id).get_json()["data"]["simulation_id"]

    assert first != second
    assert _usernames(set_env, first) == _usernames(set_env, second) == ["anna", "bernd"]
    used = client.get(f"/api/persona-sets/{set_id}").get_json()["data"]["used_by_simulation_ids"]
    assert used == [first, second]


def test_lauf_haelt_persona_set_id_in_den_metadaten_des_prepare_runs(set_env):
    from app.services.run_registry import RunRegistry

    client = _set_client()
    set_id = _make_set(client)

    simulation_id = _run_from_set(client, set_id).get_json()["data"]["simulation_id"]

    run = RunRegistry().get_latest_by_linked_id(
        "simulation_id", simulation_id, run_type="simulation_prepare"
    )
    assert run is not None
    assert run["metadata"]["persona_source"] == "set"
    assert run["metadata"]["persona_set_id"] == set_id
    assert run["metadata"]["persona_count"] == 2


def test_aendern_einer_persona_nach_dem_ersten_lauf_ist_409(set_env):
    client = _set_client()
    set_id = _make_set(client)
    entry_id = client.get(f"/api/persona-sets/{set_id}").get_json()["data"]["entries"][0]["entry_id"]
    _run_from_set(client, set_id)

    res = client.patch(
        f"/api/persona-sets/{set_id}/entries/{entry_id}",
        json={"profile": {"username": "anna", "name": "Anna Neu"}},
    )

    assert res.status_code == 409
    assert res.get_json()["code"] == "persona_set_locked"


def test_erster_lauf_behaelt_profile_wenn_die_kopie_des_satzes_geaendert_wird(set_env):
    client = _set_client()
    set_id = _make_set(client)
    first = _run_from_set(client, set_id).get_json()["data"]["simulation_id"]
    before = set_env._store.read_json(first, "reddit_profiles", default=None)

    copy = client.post(f"/api/persona-sets/{set_id}/duplicate", json={"name": "Kopie"}).get_json()["data"]
    victim = copy["entries"][0]["entry_id"]
    changed = client.patch(
        f"/api/persona-sets/{copy['id']}/entries/{victim}",
        json={"profile": {"username": "anna", "name": "Anna Veraendert", "persona": "Neu."}},
    )
    assert changed.status_code == 200
    deleted = client.delete(f"/api/persona-sets/{copy['id']}/entries/{copy['entries'][1]['entry_id']}")
    assert deleted.status_code == 200

    assert set_env._store.read_json(first, "reddit_profiles", default=None) == before
    original = client.get(f"/api/persona-sets/{set_id}").get_json()["data"]
    assert [e["profile"]["name"] for e in original["entries"]] == ["Anna", "Bernd"]
    # Auch ein Lauf aus der Kopie ist moeglich und traegt die neuen Werte.
    second = _run_from_set(client, copy["id"]).get_json()["data"]["simulation_id"]
    names = [p["name"] for p in set_env._store.read_json(second, "reddit_profiles", default=None)]
    assert names == ["Anna Veraendert"]


def test_unbekannter_satz_ist_404_und_legt_nichts_an(set_env):
    res = _run_from_set(_set_client(), "pset_nein")

    assert res.status_code == 404
    assert set_env.list_simulations() == []


def test_leerer_satz_ist_validierungsfehler_und_bleibt_ungesperrt(set_env):
    client = _set_client()
    set_id = _make_set(client, usernames=())

    res = _run_from_set(client, set_id)

    assert res.status_code == 400
    assert res.get_json()["code"] == "validation_failed"
    assert set_env.list_simulations() == []
    assert client.get(f"/api/persona-sets/{set_id}").get_json()["data"]["locked_at"] is None


@pytest.mark.parametrize("extra", [{"template_ids": ["tpl_1"]}, {"personas": [PERSONA]}])
def test_persona_set_id_zusammen_mit_anderer_quelle_ist_validierungsfehler(set_env, extra):
    client = _set_client()
    set_id = _make_set(client)

    res = client.post(
        "/api/simulation/create-from-personas",
        json={"simulation_requirement": "Frage", "persona_set_id": set_id, **extra},
    )

    assert res.status_code == 400
    assert res.get_json()["code"] == "validation_failed"
    assert client.get(f"/api/persona-sets/{set_id}").get_json()["data"]["locked_at"] is None


@pytest.mark.parametrize("bad", ["", "   ", 7, ["pset_x"]])
def test_persona_set_id_muss_nichtleerer_text_sein(set_env, bad):
    res = _set_client().post(
        "/api/simulation/create-from-personas",
        json={"simulation_requirement": "Frage", "persona_set_id": bad},
    )

    assert res.status_code == 400


def _add_entry(client, set_id, username, origin):
    res = client.post(
        f"/api/persona-sets/{set_id}/entries",
        json={
            "origin": origin,
            "profile": {
                "username": username,
                "name": username.title(),
                "persona": f"Persona von {username}.",
            },
        },
    )
    assert res.status_code == 201


def test_lauf_aus_satz_mit_fallback_meldet_die_degradation(set_env):
    from app.services.run_registry import RunRegistry

    client = _set_client()
    set_id = _make_set(client, usernames=("anna",))
    _add_entry(client, set_id, "bernd", "fallback")

    res = _run_from_set(client, set_id)

    assert res.status_code == 201
    data = res.get_json()["data"]
    # Marke im Laufprofil: dieselbe wie im normalen Prepare-Pfad.
    profiles = set_env._store.read_json(data["simulation_id"], "reddit_profiles", default=None)
    assert [(p["username"], p["generation_source"]) for p in profiles] == [
        ("anna", "llm"),
        ("bernd", "rule_based"),
    ]
    # Degradation in der Antwort ...
    events = data["degradations"]["events"]
    assert [e["kind"] for e in events] == ["persona_rule_based_fallback"]
    assert events[0]["severity"] == "warning"
    assert events[0]["context"]["fallback_personas"] == 1
    assert events[0]["context"]["total_personas"] == 2
    # ... und in den Metadaten des Prepare-Runs.
    run = RunRegistry().get_latest_by_linked_id(
        "simulation_id", data["simulation_id"], run_type="simulation_prepare"
    )
    assert run["metadata"]["degradations"]["events"][0]["kind"] == "persona_rule_based_fallback"


def test_lauf_aus_satz_nur_mit_fallback_ist_blocking(set_env):
    client = _set_client()
    set_id = _make_set(client, usernames=())
    _add_entry(client, set_id, "anna", "fallback")

    data = _run_from_set(client, set_id).get_json()["data"]

    assert data["degradations"]["events"][0]["severity"] == "blocking"


def test_lauf_aus_satz_ohne_fallback_meldet_keine_degradation(set_env):
    from app.services.run_registry import RunRegistry

    client = _set_client()
    set_id = _make_set(client)

    data = _run_from_set(client, set_id).get_json()["data"]

    assert data["degradations"]["events"] == []
    profiles = set_env._store.read_json(data["simulation_id"], "reddit_profiles", default=None)
    assert {p["generation_source"] for p in profiles} == {"llm"}
    run = RunRegistry().get_latest_by_linked_id(
        "simulation_id", data["simulation_id"], run_type="simulation_prepare"
    )
    assert "degradations" not in run["metadata"]


def test_scheitert_das_anlegen_wird_der_satz_nicht_gesperrt(set_env):
    client = _set_client()
    set_id = _make_set(client)

    with patch(
        "app.api.simulation_lifecycle.prepare_from_personas",
        side_effect=ValueError("Vorbereitung fehlgeschlagen"),
    ):
        res = _run_from_set(client, set_id)

    assert res.status_code == 400
    after = client.get(f"/api/persona-sets/{set_id}").get_json()["data"]
    assert after["locked_at"] is None
    assert after["used_by_simulation_ids"] == []


def test_persona_lauf_sagt_beim_bericht_klar_was_fehlt():
    """Ein Lauf ohne Graphen kann keinen Bericht erzeugen — das muss er sagen.

    Vorher stand dort „Missing graph ID“, was einem Nutzer nichts sagt,
    der nie einen Graphen bauen wollte. Ein Bericht ohne Graph-Belege
    waere die schlechtere Alternative: er saehe aus wie ein normaler.
    """
    from app.services import report_generation

    src = pathlib.Path(report_generation.__file__).read_text(encoding="utf-8")
    assert "Berichte stuetzen sich auf" in src
    assert "Missing graph ID, please ensure graph is built" not in src
