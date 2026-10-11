"""Vertragstest ``PersonaIdentityBinding`` (Issue #1833).

Alle Fixtures sind synthetisch und frei erfunden. Kein Test liest Laufartefakte
oder greift auf einen Remote-Host zu.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.persona_identity_contract import PersonaIdentityBinding


def _binding(**overrides):
    base = {"origin": "source_person", "source_name": "Erika Beispiel"}
    base.update(overrides)
    return PersonaIdentityBinding(**base)


def test_binding_contract_rejects_unknown_fields_and_enforces_invariants():
    with pytest.raises(ValidationError):
        _binding(unknown_field=1)
    with pytest.raises(ValidationError):
        _binding(origin="made_up_origin")
    with pytest.raises(ValidationError):
        _binding(source_name="")
    with pytest.raises(ValidationError):
        _binding(unverifiable_reasons=["not_a_reason"])

    # documented_function genau dann gesetzt, wenn function_evidence nicht 'none'.
    with pytest.raises(ValidationError):
        _binding(documented_function="Chefarzt", function_evidence="none")
    with pytest.raises(ValidationError):
        _binding(documented_function=None, function_evidence="attribute")
    with pytest.raises(ValidationError):
        _binding(documented_function="x" * 201, function_evidence="attribute")

    # Funktion, Geschlechtsevidenz und Rollenabweichung nur bei source_person.
    for origin in ("source_collective", "synthetic_representative", "synthetic_supplement"):
        with pytest.raises(ValidationError):
            _binding(origin=origin, documented_function="Chefarzt", function_evidence="attribute")
        with pytest.raises(ValidationError):
            _binding(origin=origin, gender_evidence="attribute")
        with pytest.raises(ValidationError):
            _binding(origin=origin, role_deviation="abweichend")

    ok = _binding(documented_function="Chefarzt", function_evidence="attribute")
    assert ok.name_is_locked is True
    assert ok.is_verifiable is True
    assert _binding(origin="source_collective").name_is_locked is True
    assert _binding(origin="synthetic_representative").name_is_locked is False
    assert _binding(origin="synthetic_supplement").name_is_locked is False
    open_binding = _binding(unverifiable_reasons=["gender_not_documented"])
    assert open_binding.is_verifiable is False
    with pytest.raises(ValidationError):
        ok.origin = "synthetic_supplement"  # type: ignore[misc]  # frozen
