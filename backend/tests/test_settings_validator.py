"""Tests für den Settings-Payload-Validator (Issue #133, SUB2).

Pinnt Type-Coercion, Range-Checks, Enum-Validierung, Cross-Field-
Konsistenz (``EMBEDDING_MODEL`` ↔ ``VECTOR_DIM``) und die Trennung
``allow_secrets``-Flag.
"""

from __future__ import annotations

import pytest

from app.services.settings_validator import (
    validate_payload,
    split_payload_by_secret,
)


# ---------------------------------------------------------------------------
# Happy Path
# ---------------------------------------------------------------------------


def test_validate_accepts_known_string_field():
    validated, errors = validate_payload({'LLM_MODEL_NAME': 'qwen2.5:14b'})
    assert errors == []
    assert validated == {'LLM_MODEL_NAME': 'qwen2.5:14b'}


def test_validate_coerces_int_from_string():
    validated, errors = validate_payload({'ONTOLOGY_MIN_ENTITY_TYPES': '12'})
    assert errors == []
    assert validated == {'ONTOLOGY_MIN_ENTITY_TYPES': 12}


def test_validate_accepts_native_int():
    validated, errors = validate_payload({'ONTOLOGY_MIN_ENTITY_TYPES': 5})
    assert errors == []
    assert validated == {'ONTOLOGY_MIN_ENTITY_TYPES': 5}


def test_validate_accepts_float_from_string():
    validated, errors = validate_payload({'HYBRID_SEARCH_VECTOR_WEIGHT': '0.55'})
    assert errors == []
    assert validated['HYBRID_SEARCH_VECTOR_WEIGHT'] == pytest.approx(0.55)


@pytest.mark.parametrize('raw,expected', [
    (True, True), (False, False),
    ('true', True), ('false', False),
    ('TRUE', True), ('Off', False),
    ('yes', True), ('no', False),
    (1, True), (0, False),
])
def test_validate_bool_coercion(raw, expected):
    validated, errors = validate_payload({'ENABLE_AGENT_TOOLS': raw})
    assert errors == []
    assert validated == {'ENABLE_AGENT_TOOLS': expected}


def test_validate_enum_value():
    validated, errors = validate_payload({'EVENT_BUS_BACKEND': 'redis'})
    assert errors == []
    assert validated == {'EVENT_BUS_BACKEND': 'redis'}


# ---------------------------------------------------------------------------
# Validation-Errors
# ---------------------------------------------------------------------------


def test_validate_rejects_unknown_field():
    validated, errors = validate_payload({'TOTALLY_BOGUS_KEY': 'x'})
    assert validated == {}
    assert len(errors) == 1
    assert errors[0].code == 'unknown_field'


def test_validate_rejects_invalid_int():
    _, errors = validate_payload({'ONTOLOGY_MIN_ENTITY_TYPES': 'not-a-number'})
    assert len(errors) == 1
    assert errors[0].code == 'type_error'


def test_validate_rejects_fractional_float_for_int():
    _, errors = validate_payload({'ONTOLOGY_MIN_ENTITY_TYPES': 1.5})
    assert len(errors) == 1
    assert errors[0].code == 'type_error'


def test_validate_rejects_int_below_min():
    _, errors = validate_payload({'ONTOLOGY_MIN_ENTITY_TYPES': 0})
    assert len(errors) == 1
    assert errors[0].code == 'out_of_range'


def test_validate_rejects_float_above_max():
    _, errors = validate_payload({'HYBRID_SEARCH_VECTOR_WEIGHT': 2.5})
    assert len(errors) == 1
    assert errors[0].code == 'out_of_range'


def test_validate_rejects_unknown_enum_value():
    _, errors = validate_payload({'EVENT_BUS_BACKEND': 'kafka'})
    assert len(errors) == 1
    assert errors[0].code == 'type_error'
    # Validator-Message muss alle gültigen Optionen nennen, sonst hat
    # die UI keine Chance, einen guten Hint zu rendern.
    assert 'auto' in errors[0].message and 'redis' in errors[0].message


def test_validate_rejects_bool_for_int_field():
    _, errors = validate_payload({'ONTOLOGY_MIN_ENTITY_TYPES': True})
    assert len(errors) == 1
    assert errors[0].code == 'type_error'


def test_validate_rejects_null_value():
    _, errors = validate_payload({'LLM_MODEL_NAME': None})
    assert len(errors) == 1
    assert errors[0].code == 'type_error'


def test_validate_rejects_non_dict_payload():
    validated, errors = validate_payload(['not', 'a', 'dict'])  # type: ignore[arg-type]
    assert validated == {}
    assert len(errors) == 1
    assert errors[0].code == 'invalid_payload'


# ---------------------------------------------------------------------------
# Cross-Field-Regel (EMBEDDING_MODEL ↔ VECTOR_DIM)
# ---------------------------------------------------------------------------


def test_validate_accepts_matching_embedding_pair():
    validated, errors = validate_payload({
        'EMBEDDING_MODEL': 'qwen3-embedding:4b',
        'VECTOR_DIM': 2560,
    })
    assert errors == []
    assert validated['VECTOR_DIM'] == 2560


def test_validate_rejects_vector_dim_mismatch():
    _, errors = validate_payload({
        'EMBEDDING_MODEL': 'qwen3-embedding:4b',
        'VECTOR_DIM': 1024,
    })
    assert any(e.code == 'vector_dim_mismatch' for e in errors)


def test_validate_rejects_partial_update_against_effective_state():
    """Gemini #155-High: vorher schloss der Validator nur die
    Both-in-Payload-Variante; ein Partial-Update mit nur
    ``EMBEDDING_MODEL`` (oder nur ``VECTOR_DIM``) ließ einen Mismatch
    gegen den persistierten Gegenpart durch.
    """
    effective = {'EMBEDDING_MODEL': 'qwen3-embedding:4b', 'VECTOR_DIM': 2560}
    _, errors = validate_payload(
        {'EMBEDDING_MODEL': 'nomic-embed-text'},
        effective_settings=effective,
    )
    assert any(e.code == 'vector_dim_mismatch' for e in errors)

    _, errors = validate_payload(
        {'VECTOR_DIM': 1024},
        effective_settings=effective,
    )
    assert any(e.code == 'vector_dim_mismatch' for e in errors)


def test_validate_partial_update_passes_with_matching_effective_state():
    effective = {'EMBEDDING_MODEL': 'qwen3-embedding:4b', 'VECTOR_DIM': 2560}
    _, errors = validate_payload(
        {'VECTOR_DIM': 2560},
        effective_settings=effective,
    )
    assert errors == []


def test_validate_skips_cross_field_when_pair_not_involved():
    """Wenn weder ``EMBEDDING_MODEL`` noch ``VECTOR_DIM`` im Payload
    sind, ist die Cross-Field-Regel kein Thema dieses PUTs — auch
    nicht, wenn der effective Stand selbst inkonsistent ist.
    """
    effective = {'EMBEDDING_MODEL': 'qwen3-embedding:4b', 'VECTOR_DIM': 1024}
    validated, errors = validate_payload(
        {'LLM_MODEL_NAME': 'qwen2.5:14b'},
        effective_settings=effective,
    )
    assert errors == []
    assert validated == {'LLM_MODEL_NAME': 'qwen2.5:14b'}


def test_validate_does_not_complain_when_model_unknown():
    """Wir kennen die Output-Dim nicht aller Modelle (z. B. custom
    cloud). In dem Fall greifen wir nicht ins Lenkrad — der Operator
    weiß es besser.
    """
    validated, errors = validate_payload({
        'EMBEDDING_MODEL': 'fancy-cloud-embedding:v1',
        'VECTOR_DIM': 1024,
    })
    assert errors == []
    assert validated['EMBEDDING_MODEL'] == 'fancy-cloud-embedding:v1'


# ---------------------------------------------------------------------------
# Secret-Trennung
# ---------------------------------------------------------------------------


def test_validate_rejects_secret_field_by_default():
    _, errors = validate_payload({'NEO4J_PASSWORD': 'new-pw'})
    assert len(errors) == 1
    assert errors[0].code == 'secret_not_allowed'


def test_validate_allows_secret_with_flag():
    validated, errors = validate_payload(
        {'NEO4J_PASSWORD': 'new-pw'}, allow_secrets=True
    )
    assert errors == []
    assert validated == {'NEO4J_PASSWORD': 'new-pw'}


def test_split_payload_by_secret():
    nonsecret, secrets = split_payload_by_secret({
        'LLM_MODEL_NAME': 'qwen2.5:14b',
        'NEO4J_PASSWORD': 'pw',
        'AGORA_AUTH_TOKEN': 'tok',
    })
    assert nonsecret == {'LLM_MODEL_NAME': 'qwen2.5:14b'}
    assert secrets == {'NEO4J_PASSWORD': 'pw', 'AGORA_AUTH_TOKEN': 'tok'}


# ---------------------------------------------------------------------------
# Edge-Cases: mehrere Errors auf einmal
# ---------------------------------------------------------------------------


def test_validator_collects_all_errors_in_one_pass():
    """All-or-Nothing-Vertrag: bei Validation-Failure soll das Frontend
    alle Probleme gleichzeitig sehen, nicht nur das erste.
    """
    _, errors = validate_payload({
        'TOTALLY_BOGUS': 'x',
        'ONTOLOGY_MIN_ENTITY_TYPES': 'na',
        'HYBRID_SEARCH_VECTOR_WEIGHT': 5.0,
    })
    assert len(errors) == 3
    codes = {e.code for e in errors}
    assert codes == {'unknown_field', 'type_error', 'out_of_range'}
