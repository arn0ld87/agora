"""Vertragstests fuer ``CreateFromPersonasResponse`` (Issue #1807, E7-B1).

Die 201-Antwort von ``POST /api/simulation/create-from-personas`` war ein
handgebautes Dict. Der Vertrag haelt ihre Form fest: ohne Satz drei Schluessel
wie bisher, mit Satz zusaetzlich ``persona_set_id`` und ``degradations``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.persona_set_contract import CreateFromPersonasResponse
from app.contracts.pipeline_degradation_contract import (
    DegradationKind,
    DegradationSeverity,
    PipelineDegradationReport,
)
from app.services.degradation_collector import DegradationCollector


def test_ohne_satz_bleiben_genau_die_drei_bisherigen_schluessel():
    dumped = CreateFromPersonasResponse(
        simulation_id="sim_neu", project_id="proj_neu", persona_count=2
    ).model_dump(mode="json")

    assert dumped == {
        "simulation_id": "sim_neu",
        "project_id": "proj_neu",
        "persona_count": 2,
    }


def test_mit_satz_traegt_persona_set_id_und_befundbericht():
    collector = DegradationCollector()
    collector.record(
        kind=DegradationKind.PERSONA_RULE_BASED_FALLBACK,
        severity=DegradationSeverity.WARNING,
        detail="1 von 2 Personas sind regelbasierte Platzhalter.",
        context={"fallback_personas": 1, "total_personas": 2},
    )
    report = collector.report()

    dumped = CreateFromPersonasResponse(
        simulation_id="sim_neu",
        project_id="proj_neu",
        persona_count=2,
        persona_set_id="pset_000000000001",
        degradations=report,
    ).model_dump(mode="json")

    assert set(dumped) == {
        "simulation_id",
        "project_id",
        "persona_count",
        "persona_set_id",
        "degradations",
    }
    assert dumped["persona_set_id"] == "pset_000000000001"
    # Genau die Form, die der Endpunkt bisher als ``report().model_dump`` lieferte.
    assert dumped["degradations"] == report.model_dump(mode="json")
    assert dumped["degradations"]["events"][0]["kind"] == "persona_rule_based_fallback"


def test_leerer_befundbericht_bleibt_sichtbar():
    """Leere Liste heisst: nichts ist still ausgefallen. Sie darf nicht verschwinden."""
    dumped = CreateFromPersonasResponse(
        simulation_id="sim_neu",
        project_id="proj_neu",
        persona_count=1,
        persona_set_id="pset_000000000001",
        degradations=PipelineDegradationReport(),
    ).model_dump(mode="json")

    assert dumped["degradations"]["events"] == []


def test_unbekanntes_feld_wird_abgelehnt():
    with pytest.raises(ValidationError):
        CreateFromPersonasResponse(
            simulation_id="sim_neu",
            project_id="proj_neu",
            persona_count=1,
            graph_id="",
        )


def test_negative_personazahl_wird_abgelehnt():
    with pytest.raises(ValidationError):
        CreateFromPersonasResponse(
            simulation_id="sim_neu", project_id="proj_neu", persona_count=-1
        )
