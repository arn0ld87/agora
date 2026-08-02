"""Issue #901 — ``AiModelRef.source`` überlebt den Route-Snapshot.

``seed_run_stage_routing`` baute aus einer ``AiModelRef`` eine
``StageLLMRoute`` mit ``provider_id``/``model``/``provider_options``.
``AiModelRef.source`` fiel dabei weg, weil ``StageLLMRoute`` kein Feld dafür
hatte — und ``ai_route_from_stage_route`` schrieb beim Zurückprojizieren hart
``source="legacy"``. Ergebnis: jede explizite UI-Modellwahl erschien im
Snapshot und im ``AiRouteAudit`` als ``legacy``; bewusste Nutzerwahl und
Provider-Fallback waren nicht mehr unterscheidbar.

Zwei Vokabulare, bewusst getrennt gehalten (Entscheidung zu #901):

* ``AiModelRefSource`` — was das UI geschickt hat (``stage-override``,
  ``explicit``, ``fallback``, …). Wird **wörtlich** auf der ``StageLLMRoute``
  persistiert, damit die Herkunft rekonstruierbar bleibt.
* ``RouteSource`` — das Vokabular von ``AiRoute`` (``stage_override``,
  ``runtime``, ``provider_fallback``, ``legacy``, …). Die Abbildung passiert
  erst bei der Projektion.

Bestandssnapshots ohne das Feld bleiben lesbar und projizieren weiterhin auf
``legacy``.
"""

from __future__ import annotations

import pytest

from app.contracts.ai_provider_contract import (
    AiModelRef,
    ai_route_from_stage_route,
    stage_route_from_ai_route,
)
from app.contracts.llm_routing_contract import StageLLMRoute
from app.contracts.provider_types import AiModelRefSource


# Vollständige Abbildung beider Vokabulare. Der Test zählt die Einträge gegen
# das Literal — ein neuer AiModelRefSource-Wert ohne Abbildung fällt auf.
EXPECTED_MAPPING = {
    "stage-override": "stage_override",
    "run-override": "run_override",
    "project-default": "project",
    "workspace-default": "workspace",
    "explicit": "runtime",
    "fallback": "provider_fallback",
}


def _all_ref_sources() -> tuple[str, ...]:
    return tuple(AiModelRefSource.__args__)  # type: ignore[attr-defined]


def test_mapping_deckt_jeden_ai_model_ref_source_wert_ab():
    """Wächter: ein neuer AiModelRefSource-Wert braucht eine Abbildung.

    Ohne diesen Test bliebe ein neuer Wert stillschweigend auf ``legacy``
    stehen — genau der Defekt, den #901 behebt, nur eine Ebene später.
    """
    assert set(_all_ref_sources()) == set(EXPECTED_MAPPING), (
        "AiModelRefSource und die Abbildung nach RouteSource sind auseinandergelaufen"
    )


@pytest.mark.parametrize("ref_source", _all_ref_sources())
def test_stage_route_traegt_ai_model_ref_source(ref_source: str):
    """Das Feld existiert und nimmt jeden AiModelRefSource-Wert an."""
    route = StageLLMRoute(
        stage="report_generation",
        provider_id="conn-1",
        model="qwen2.5:32b",
        ai_model_ref_source=ref_source,
        fallback_reason="Primaermodell nicht erreichbar" if ref_source == "fallback" else None,
    )
    assert route.ai_model_ref_source == ref_source


@pytest.mark.parametrize("ref_source,expected_route_source", sorted(EXPECTED_MAPPING.items()))
def test_projektion_bildet_auf_route_source_ab(ref_source: str, expected_route_source: str):
    """AiModelRef → StageLLMRoute → AiRoute behält die Herkunft."""
    route = StageLLMRoute(
        stage="report_generation",
        provider_id="conn-1",
        model="qwen2.5:32b",
        ai_model_ref_source=ref_source,
        fallback_reason="Primaermodell nicht erreichbar" if ref_source == "fallback" else None,
    )
    ai_route = ai_route_from_stage_route(route)
    assert ai_route.source == expected_route_source, (
        f"{ref_source!r} muss auf {expected_route_source!r} abbilden, "
        f"nicht auf {ai_route.source!r}"
    )


def test_bestandsroute_ohne_feld_bleibt_legacy():
    """AK: Bestandssnapshots ohne das Feld lesen sauber und gelten als legacy."""
    route = StageLLMRoute(
        stage="report_generation",
        provider_id="conn-1",
        model="qwen2.5:32b",
    )
    assert route.ai_model_ref_source is None
    assert ai_route_from_stage_route(route).source == "legacy"


def test_bestandssnapshot_dict_ohne_feld_validiert():
    """StageLLMRoute ist extra=forbid — ein persistierter Bestands-Dict ohne
    das neue Feld muss trotzdem durchgehen (kein Migrationszwang)."""
    route = StageLLMRoute.model_validate(
        {
            "stage": "report_generation",
            "provider_id": "conn-1",
            "model": "qwen2.5:32b",
            "provider_options": {},
        }
    )
    assert route.ai_model_ref_source is None


@pytest.mark.parametrize("ref_source", _all_ref_sources())
def test_roundtrip_ist_verlustfrei(ref_source: str):
    """StageLLMRoute → AiRoute → StageLLMRoute erhält Herkunft und Grund.

    Die Rueckabbildung darf nicht ueber RouteSource raten — ``runtime`` liesse
    sich nicht eindeutig auf ``explicit`` zuruecknehmen. Der Wert reist
    deshalb im ``__legacy_stage_route__``-Kanal mit, in dem schon
    temperature/max_tokens/reasoning_effort transportiert werden.
    """
    reason = "Primaermodell nicht erreichbar" if ref_source == "fallback" else None
    original = StageLLMRoute(
        stage="report_generation",
        provider_id="conn-1",
        model="qwen2.5:32b",
        temperature=0.4,
        max_tokens=2048,
        ai_model_ref_source=ref_source,
        fallback_reason=reason,
    )
    restored = stage_route_from_ai_route(ai_route_from_stage_route(original))

    assert restored.ai_model_ref_source == ref_source
    assert restored.fallback_reason == reason
    # Die bereits vorher transportierten Felder duerfen nicht verloren gehen.
    assert restored.temperature == 0.4
    assert restored.max_tokens == 2048


def test_fallback_ohne_grund_wird_abgelehnt():
    """``provider_fallback`` verlangt laut AiRoute-Validator einen Grund.

    Der Fehler muss beim Bauen der Route auftreten, nicht erst spaeter beim
    Projizieren — sonst bricht ein Run an einer Stelle, die mit der Ursache
    nichts zu tun hat.
    """
    with pytest.raises(ValueError, match="fallback_reason"):
        StageLLMRoute(
            stage="report_generation",
            provider_id="conn-1",
            model="qwen2.5:32b",
            ai_model_ref_source="fallback",
        )


def test_ai_model_ref_quelle_und_stage_route_teilen_das_vokabular():
    """``AiModelRef.source`` und das neue Feld sind typgleich — kein zweites,
    still divergierendes Literal."""
    ref = AiModelRef(
        provider_connection_id="conn-1",
        model_id="qwen2.5:32b",
        source="run-override",
    )
    route = StageLLMRoute(
        stage="report_generation",
        provider_id=ref.provider_connection_id,
        model=ref.model_id,
        ai_model_ref_source=ref.source,
    )
    assert route.ai_model_ref_source == ref.source
