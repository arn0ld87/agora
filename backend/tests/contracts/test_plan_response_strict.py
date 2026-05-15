"""
Pflicht-Tests für OpenAI strict structured outputs Kompatibilität.

Smoke-Report 2026-05-15, Befund #1:
OpenAI gibt HTTP 400 zurück wenn required[] nicht alle Properties enthält.
Pydantic lässt Felder mit default= aus required heraus — das bricht OpenAI strict mode.

Tests prüfen:
a) PlanSection.model_json_schema() hat required == set(properties)
b) PlanResponse.model_json_schema() hat required == set(properties)
c) SectionMetadata.model_json_schema() hat required == set(properties)
d) _harden_schema_for_openai_strict() setzt required=all + additionalProperties=false
e) Verschachtelte Schemas werden rekursiv gehärtet
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.report_agent.schemas import (
    PlanResponse,
    PlanSection,
    SectionMetadata,
)
from app.utils.llm_client import _harden_schema_for_openai_strict


# ---------------------------------------------------------------------------
# a) PlanSection
# ---------------------------------------------------------------------------

def test_plan_section_required_includes_all_properties() -> None:
    """PlanSection.model_json_schema() muss required == set(properties) haben."""
    schema = PlanSection.model_json_schema()
    props = set(schema.get("properties", {}).keys())
    required = set(schema.get("required", []))
    assert props, "PlanSection muss Properties haben"
    assert required == props, (
        f"PlanSection: required={required} != properties={props}. "
        "OpenAI strict mode benötigt alle Properties in required."
    )


# ---------------------------------------------------------------------------
# b) PlanResponse
# ---------------------------------------------------------------------------

def test_plan_response_required_includes_all_properties() -> None:
    """PlanResponse.model_json_schema() muss required == set(properties) haben."""
    schema = PlanResponse.model_json_schema()
    props = set(schema.get("properties", {}).keys())
    required = set(schema.get("required", []))
    assert props, "PlanResponse muss Properties haben"
    assert required == props, (
        f"PlanResponse: required={required} != properties={props}. "
        "OpenAI strict mode benötigt alle Properties in required."
    )


# ---------------------------------------------------------------------------
# c) SectionMetadata
# ---------------------------------------------------------------------------

def test_section_metadata_required_includes_all_properties() -> None:
    """SectionMetadata.model_json_schema() muss required == set(properties) haben."""
    schema = SectionMetadata.model_json_schema()
    props = set(schema.get("properties", {}).keys())
    required = set(schema.get("required", []))
    assert props, "SectionMetadata muss Properties haben"
    assert required == props, (
        f"SectionMetadata: required={required} != properties={props}. "
        "OpenAI strict mode benötigt alle Properties in required."
    )


# ---------------------------------------------------------------------------
# d) _harden_schema_for_openai_strict — Basis-Repro
# ---------------------------------------------------------------------------

def test_llm_client_hardens_schema_for_strict() -> None:
    """Pydantic-Schema mit default (required fehlt) wird durch Helper gehärtet."""

    class _WithDefault(BaseModel):
        name: str
        value: str = Field(default="fallback")

    raw = _WithDefault.model_json_schema()

    # Pydantic lässt 'value' (mit default) aus required heraus
    raw_required = set(raw.get("required", []))
    raw_props = set(raw.get("properties", {}).keys())
    # Vorab-Assertion: Schema ist tatsächlich "unhärtet"
    assert raw_props - raw_required, (
        "Test-Voraussetzung: Pydantic muss 'value' aus required herauslassen"
    )

    hardened = _harden_schema_for_openai_strict(raw)

    h_props = set(hardened.get("properties", {}).keys())
    h_required = set(hardened.get("required", []))
    assert h_required == h_props, (
        f"Nach Hardening: required={h_required} != properties={h_props}"
    )
    assert hardened.get("additionalProperties") is False, (
        "additionalProperties muss nach Hardening False sein"
    )

    # Original darf nicht mutiert worden sein (deep copy) — nach Hardening
    # darf raw kein additionalProperties: False tragen (es hatte keins).
    assert "additionalProperties" not in raw, (
        "Original-Schema darf durch Hardening nicht mutiert werden"
    )


# ---------------------------------------------------------------------------
# e) Rekursive Härtung verschachtelter Schemas
# ---------------------------------------------------------------------------

def test_strict_schema_recursion_handles_nested_objects() -> None:
    """PlanResponse (enthält list[PlanSection]) muss auf beiden Ebenen gehärtet sein."""
    raw = PlanResponse.model_json_schema()
    hardened = _harden_schema_for_openai_strict(raw)

    # Top-Level (PlanResponse)
    top_props = set(hardened.get("properties", {}).keys())
    top_required = set(hardened.get("required", []))
    assert top_required == top_props, (
        f"PlanResponse top-level: required={top_required} != props={top_props}"
    )
    assert hardened.get("additionalProperties") is False

    # $defs enthält PlanSection — prüfe dass es ebenfalls gehärtet ist
    defs = hardened.get("$defs", {})
    assert defs, "PlanResponse.model_json_schema() sollte $defs mit PlanSection enthalten"

    for def_name, def_schema in defs.items():
        if def_schema.get("type") == "object" or "properties" in def_schema:
            def_props = set(def_schema.get("properties", {}).keys())
            def_required = set(def_schema.get("required", []))
            assert def_required == def_props, (
                f"$defs[{def_name!r}]: required={def_required} != props={def_props}. "
                "Rekursive Härtung hat nicht gegriffen."
            )
            assert def_schema.get("additionalProperties") is False, (
                f"$defs[{def_name!r}]: additionalProperties muss False sein"
            )
