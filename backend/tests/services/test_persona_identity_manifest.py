"""Issue #1833 — Laufartefakt ``persona_identity_bindings.json``.

Jede generierte Persona hat einen vertragsgeprüften Eintrag; unprüfbare
Bindungen tragen einen Grund. Alle Fixtures sind synthetisch und frei erfunden.
Kein Test liest Laufartefakte oder greift auf einen Remote-Host zu; das Modell
wird gestubbt, geschrieben wird nur in ein temporäres Verzeichnis.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from app.contracts.persona_identity_contract import PersonaIdentityBindingManifest
from app.services.entity_reader import EntityNode
from app.services.oasis_profile_generator import (
    OasisAgentProfile,
    OasisProfileGenerator,
    PersonaDemographicSlot,
)
from app.services.persona_identity_binding import (
    IDENTITY_BINDING_MANIFEST_FILENAME,
    build_identity_binding_manifest,
    write_identity_binding_manifest,
)
from app.services.prepare_service import _persist_identity_bindings


@pytest.fixture()
def generator():
    return OasisProfileGenerator(api_key="test", base_url="http://localhost", language="de")


def _entity(name: str, entity_type: str, attributes: dict[str, Any] | None = None) -> EntityNode:
    return EntityNode(
        uuid=f"uuid-{name}",
        name=name,
        labels=[entity_type, "Entity"],
        summary=f"{name} im Kontext der Klinikschließung.",
        attributes=attributes or {},
    )


def _profiles(generator) -> list[OasisAgentProfile | None]:
    slot = PersonaDemographicSlot(age=33, gender="female", mbti="ISFJ")
    source = generator.generate_profile_from_entity(
        _entity("Dr. Frank Oltmann", "Person", {"role": "Chefarzt der Klinik"}),
        user_id=0,
        use_llm=False,
        demographic_slot=slot,
    )
    collective = generator.generate_profile_from_entity(
        _entity("Klinikum Hollerau-Nord", "Hospital"),
        user_id=1,
        use_llm=False,
        demographic_slot=slot,
    )
    unbound = OasisAgentProfile(
        user_id=2, user_name="alt_profil", name="Altbestand", bio="b", persona="p"
    )
    return [source, collective, unbound, None]


def test_manifest_lists_one_validated_entry_per_bound_profile(generator):
    manifest = build_identity_binding_manifest("sim_test", _profiles(generator))

    assert [(e.user_id, e.persona_kind, e.binding.origin) for e in manifest.entries] == [
        (0, "individual", "source_person"),
        (1, "collective", "source_collective"),
    ], "Profile ohne Bindung und leere Slots fehlen"
    assert manifest.entries[0].user_name.startswith("dr_frank_oltmann")
    assert manifest.entries[0].binding.unverifiable_reasons == ["gender_not_documented"]

    dumped = manifest.model_dump(mode="json")
    assert PersonaIdentityBindingManifest.model_validate(dumped) == manifest
    assert dumped["schema_version"] == 1
    with pytest.raises(ValidationError):
        PersonaIdentityBindingManifest.model_validate({**dumped, "unexpected": 1})
    with pytest.raises(ValidationError):
        PersonaIdentityBindingManifest.model_validate(
            {**dumped, "entries": [{**dumped["entries"][0], "unexpected": 1}]}
        )


def test_manifest_is_written_atomically_and_errors_surface(generator, tmp_path):
    profiles = _profiles(generator)

    written = write_identity_binding_manifest(str(tmp_path), "sim_test", profiles)

    path = tmp_path / IDENTITY_BINDING_MANIFEST_FILENAME
    assert IDENTITY_BINDING_MANIFEST_FILENAME == "persona_identity_bindings.json"
    on_disk = PersonaIdentityBindingManifest.model_validate(json.loads(path.read_text("utf-8")))
    assert on_disk == written
    assert [p.name for p in tmp_path.iterdir()] == [IDENTITY_BINDING_MANIFEST_FILENAME], (
        "atomarer Schreibvorgang hinterlässt keine temporäre Datei"
    )

    blocked = tmp_path / "ist_eine_datei"
    blocked.write_text("x", encoding="utf-8")
    with pytest.raises(OSError):
        write_identity_binding_manifest(str(blocked), "sim_test", profiles)


def test_prepare_phase_writes_manifest_only_with_a_simulation_id(generator, tmp_path):
    profiles = [p for p in _profiles(generator) if p is not None]

    _persist_identity_bindings(SimpleNamespace(simulation_id="sim_test"), str(tmp_path), profiles)
    assert (tmp_path / IDENTITY_BINDING_MANIFEST_FILENAME).is_file()

    other = tmp_path / "ohne_id"
    other.mkdir()
    _persist_identity_bindings(SimpleNamespace(), str(other), profiles)
    assert list(other.iterdir()) == []
