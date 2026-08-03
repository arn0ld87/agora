"""Persona-Generierungsziel — der Nenner des Fortschrittszählers.

Issue #1034 (Teilpunkt 2) · 2026-08-03

Die Anzeige zeigte „Erzeugt 22 / 7 Personas…": der Zähler lief über
seinen eigenen Nenner. Der Nenner kam aus ``expected_entities_count``
(Entitätenzahl), der Zähler aus der Persona-Generierung, deren Menge erst
durch Quota-Plan oder Persona-Floor entsteht. Sieben Entitäten wurden zu
fünfzig Personas.

``compute_persona_target`` ist die eine Quelle für beide Pfade. Diese
Tests nageln die Rechenregeln fest und prüfen, dass Preview-Antwort und
Laufpfad nicht wieder auseinanderdriften können.
"""

from __future__ import annotations

import types
from unittest.mock import MagicMock

from app.contracts import PersonaQuotaPlan, PersonaTargetContract
from app.services.prepare_service import compute_persona_target
from app.services.report_agent import MIN_PERSONA_TABLE_ROWS


def test_small_entity_pool_targets_the_floor():
    """Der gemeldete Defekt: 7 Entitäten, 50 Personas, Nenner blieb 7."""
    target = compute_persona_target(7)

    assert target.persona_target_count == MIN_PERSONA_TABLE_ROWS
    assert target.entity_count == 7
    assert target.floor_applied is True
    assert target.floor == MIN_PERSONA_TABLE_ROWS


def test_large_entity_pool_targets_itself():
    target = compute_persona_target(80)

    assert target.persona_target_count == 80
    assert target.floor_applied is False


def test_max_agents_caps_floor_and_target():
    """Nutzer-Wunsch schlägt Contract — ein kleineres max_agents gewinnt."""
    target = compute_persona_target(3, max_agents=5)

    assert target.floor == 5
    assert target.persona_target_count == 5
    assert target.floor_applied is True


def test_quota_plan_total_wins_after_floor_lift():
    plan = PersonaQuotaPlan(targets={"Person": 4, "Company": 2}, total=6)

    target = compute_persona_target(6, quota_plan=plan)

    assert target.persona_target_count == MIN_PERSONA_TABLE_ROWS
    assert target.floor_applied is True


def test_quota_plan_above_floor_is_left_alone():
    plan = PersonaQuotaPlan(targets={"Person": 60}, total=60)

    target = compute_persona_target(60, quota_plan=plan)

    assert target.persona_target_count == 60
    assert target.floor_applied is False


def test_quota_plan_below_floor_reports_floor_applied_despite_large_pool():
    """Mit Plan zählt der Plan, nicht die Entitätenzahl.

    80 Entitäten mit einer Quota von 6 werden auf den Floor angehoben. Ein
    Vergleich `target > entity_count` läse das als „kein Floor" — und der
    Hinweis in Schritt 2, der genau diese Anhebung erklärt, bliebe aus.
    """
    plan = PersonaQuotaPlan(targets={"Person": 6}, total=6)

    target = compute_persona_target(80, quota_plan=plan)

    assert target.persona_target_count == MIN_PERSONA_TABLE_ROWS
    assert target.floor_applied is True


def test_valid_quota_above_floor_reports_no_floor_lift_on_small_pool():
    """Die Gegenrichtung: fünf Entitäten, gültige Quota von 60.

    Hier hebt der Floor nichts an — der Plan lag bereits darüber. Ein
    Vergleich gegen die Entitätenzahl meldete fälschlich einen Floor.
    """
    plan = PersonaQuotaPlan(targets={"Person": 60}, total=60)

    target = compute_persona_target(5, quota_plan=plan)

    assert target.persona_target_count == 60
    assert target.floor_applied is False


def test_empty_pool_with_quota_plan_stays_empty():
    """Der Guard steht vor dem Quota-Zweig, nicht dahinter.

    Sonst meldete ein leerer Pool mit Plan den floor-angehobenen
    Quota-Total — einen Nenner, den die Generierung nie erreichen kann,
    weil `_expand_entities_for_quota` bei leerem Pool wirft und der
    Orchestrator vorher bei `filtered_count == 0` abbricht.
    """
    plan = PersonaQuotaPlan(targets={"Person": 6}, total=6)

    target = compute_persona_target(0, quota_plan=plan)

    assert target.persona_target_count == 0
    assert target.floor_applied is False


def test_empty_pool_stays_empty():
    """Kein Ziel von 50 bei null Entitäten.

    ``_apply_persona_floor_to_entities`` skaliert einen leeren Pool nicht
    hoch — es gibt nichts zu wiederholen. Ein Nenner von 50 gegen einen
    Zähler, der bei 0 bleibt, wäre genau die Divergenz, die dieser
    Contract beseitigen soll.
    """
    target = compute_persona_target(0)

    assert target.persona_target_count == 0
    assert target.floor_applied is False


def test_resolved_floor_is_not_recomputed():
    """Wer den Floor schon aufgelöst hat, reicht ihn herein.

    Der Orchestrator berechnet ``persona_floor`` für die Generierung.
    Würde ``compute_persona_target`` ihn ein zweites Mal aus ``max_agents``
    ableiten, könnten beide Werte auseinanderlaufen, sobald ein Aufrufer
    einen abweichenden Floor setzt.
    """
    target = compute_persona_target(3, max_agents=5, floor=12)

    assert target.floor == 12
    assert target.persona_target_count == 12


def test_contract_rejects_unknown_fields():
    """``extra="forbid"`` — der Vertrag ist die Grenze, nicht ein Vorschlag."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PersonaTargetContract(
            entity_count=1,
            persona_target_count=1,
            floor_applied=False,
            floor=1,
            tippfehler=True,
        )


def test_phase_generate_profiles_denominator_matches_generated_count(monkeypatch, tmp_path):
    """Zähler und Nenner stammen aus derselben Quelle.

    Der Nenner geht als ``total`` in den Progress-Callback; der Zähler ist
    die Zahl der tatsächlich erzeugten Profile. Beide müssen bei
    gegriffenem Floor übereinstimmen — vorher kam der eine aus
    ``len(entities)`` und der andere aus der Entitätenzahl.
    """
    from app.services import prepare_service as ps_mod

    generated: dict = {}

    class FakeGenerator:
        def __init__(self, *_args, **_kwargs):
            pass

        def generate_profiles_from_entities(self, **kwargs):
            generated["count"] = len(kwargs["entities"])
            return [object()] * len(kwargs["entities"])

        def save_profiles(self, **_kwargs):
            return None

    monkeypatch.setattr(ps_mod, "OasisProfileGenerator", FakeGenerator)

    seen_totals: list[int] = []

    def progress_callback(_stage, _progress, _msg, **kwargs):
        if kwargs.get("total"):
            seen_totals.append(kwargs["total"])

    state = types.SimpleNamespace(
        graph_id="graph_1",
        enable_reddit=False,
        enable_twitter=False,
        profiles_count=0,
    )
    filtered = types.SimpleNamespace(
        entities=[types.SimpleNamespace(name=f"E{i}") for i in range(7)]
    )

    ps_mod._phase_generate_profiles(
        state,
        MagicMock(),
        filtered,
        str(tmp_path),
        llm_model=None,
        language="de",
        use_llm_for_profiles=False,
        parallel_profile_count=1,
        persona_floor=MIN_PERSONA_TABLE_ROWS,
        progress_callback=progress_callback,
    )

    assert generated["count"] == MIN_PERSONA_TABLE_ROWS
    assert seen_totals
    assert set(seen_totals) == {MIN_PERSONA_TABLE_ROWS}


def test_preview_and_run_path_share_one_target_function(monkeypatch):
    """Beide Pfade rufen dieselbe Funktion.

    Wird der Aufruf in einem der beiden entfernt oder durch eine eigene
    Rechnung ersetzt, fällt dieser Test. Bei #1029 saß ein vollständiger
    Fix im unbenutzten von zwei Pfaden — dagegen ist das hier die Sperre.
    """
    from app.api import simulation_prepare as sp_mod
    from app.services import prepare_service as ps_mod

    assert sp_mod.compute_persona_target is ps_mod.compute_persona_target

    import inspect

    run_path_source = inspect.getsource(ps_mod._phase_generate_profiles)
    assert "compute_persona_target(" in run_path_source

    preview_source = inspect.getsource(sp_mod.prepare_simulation)
    assert "compute_persona_target(" in preview_source
