"""Endpunkt-Tests fuer /api/simulation/create-from-personas (Block B4).

Der Weg soll einen Lauf allein aus gespeicherten Personas anlegen —
ohne Dokument, Ontologie oder Graph. Geprueft wird hier die HTTP-Ebene:
Eingabevalidierung, Aufloesung der Bibliotheks-Verweise und die
Verdrahtung mit dem Vorbereitungs-Service.
"""

import os
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
