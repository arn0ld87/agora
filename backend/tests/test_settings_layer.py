"""Tests für den Settings-Layer (Issue #133, SUB1).

Pinnt die Lade-Reihenfolge ``Defaults → env → file → override`` und das
Source-Tracking. Der Pin-Test gegen ``Config`` fängt Drift zwischen
Schema-Defaults und Code-Defaults ab — das war ausdrücklich Akzeptanz-
Kriterium des Issues („gleiche Validatoren wie Startup").
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.settings_layer import (
    SOURCE_DEFAULT,
    SOURCE_ENV,
    SOURCE_FILE,
    SOURCE_OVERRIDE,
    SettingsService,
)
from app.services.settings_schema import (
    SECTIONS,
    SETTINGS_FIELDS,
    field_by_key,
    fields_by_section,
)


@pytest.fixture
def isolated_service(tmp_path: Path) -> SettingsService:
    return SettingsService(instance_path=tmp_path / 'settings.json')


@pytest.fixture
def clean_env(monkeypatch):
    """Strip alle Settings-Env-Vars, damit Source ``default`` reproduzierbar
    nachweisbar ist. Tests, die env brauchen, setzen sie explizit.
    """
    for spec in SETTINGS_FIELDS:
        monkeypatch.delenv(spec.key, raising=False)
    return monkeypatch


# ---------------------------------------------------------------------------
# Schema-Konsistenz
# ---------------------------------------------------------------------------


def test_schema_sections_are_unique_and_ordered():
    # SECTIONS ist die Tab-Reihenfolge der UI; Duplikate würden zu
    # mehrfach gerenderten Tabs führen.
    assert len(SECTIONS) == len(set(SECTIONS))


def test_every_field_section_is_declared():
    for spec in SETTINGS_FIELDS:
        assert spec.section in SECTIONS, (
            f'Field {spec.key} verweist auf unbekannte Sektion {spec.section!r}'
        )


def test_every_section_has_at_least_one_field():
    for section in SECTIONS:
        assert fields_by_section(section), (
            f'Sektion {section!r} hat keine Felder — UI würde leeren Tab rendern.'
        )


def test_field_by_key_lookup():
    assert field_by_key('LLM_MODEL_NAME').default == 'qwen2.5:32b'
    assert field_by_key('does-not-exist') is None


@pytest.mark.parametrize(
    'key,expected_default',
    [
        # Strings/Enums — 1:1 aus dem Default-Argument von
        # ``os.environ.get(...)`` in ``backend/app/config.py``.
        ('LLM_MODEL_NAME', 'qwen2.5:32b'),
        ('LLM_BASE_URL', 'http://localhost:11434/v1'),
        ('LLM_MAX_OUTPUT_TOKENS', 8192),
        ('LLM_CONTEXT_LIMIT', 262144),
        ('NEO4J_URI', 'bolt://localhost:7687'),
        ('NEO4J_USER', 'neo4j'),
        ('ONTOLOGY_MIN_ENTITY_TYPES', 8),
        ('ONTOLOGY_MAX_ENTITY_TYPES', 16),
        ('ONTOLOGY_MAX_EDGE_TYPES', 12),
        ('HYBRID_SEARCH_VECTOR_WEIGHT', 0.7),
        ('HYBRID_SEARCH_KEYWORD_WEIGHT', 0.3),
        ('AGORA_LOG_FORMAT', 'text'),
        ('TIME_PROFILE', 'dach_default'),
        ('REPORT_LANGUAGE', 'German'),
        ('AGENT_LANGUAGE', 'de'),
        ('REDIS_URL', 'redis://redis:6379/0'),
        ('EVENT_BUS_BACKEND', 'auto'),
        ('ENABLE_AGENT_TOOLS', False),
        ('MAX_TOOL_CALLS_PER_ACTION', 2),
        ('ONTOLOGY_MUTATION_MODE', 'disabled'),
        ('ONTOLOGY_MUTATION_MIN_CONFIDENCE', 0.6),
    ],
)
def test_schema_defaults_match_config_defaults(key: str, expected_default):
    """Pin: Schema-Defaults müssen 1:1 mit den Code-Defaults in
    ``backend/app/config.py`` übereinstimmen.

    Wir vergleichen gegen literal Werte statt gegen ``Config.X``: das
    Class-Attribut wird zum Import-Zeitpunkt aus ``os.environ`` belegt
    und ist daher kein zuverlässiger Default-Anker, sobald die
    Test-Umgebung eine env-Variable setzt (z. B. wenn der Operator vor
    dem Test-Run ``LLM_MODEL_NAME`` in der Shell gesetzt hat).

    Wenn dieser Test rot wird, entweder den Schema-Default
    nachziehen oder den Code-Default in ``config.py`` prüfen — das
    ist die gewollte Sichtbarkeit gegen Drift.
    """
    spec = field_by_key(key)
    assert spec is not None
    assert spec.default == expected_default


# ---------------------------------------------------------------------------
# Lade-Reihenfolge
# ---------------------------------------------------------------------------


def test_default_source_when_nothing_is_set(isolated_service, clean_env):
    state = isolated_service.get_field_state('LLM_MODEL_NAME')
    assert state['source'] == SOURCE_DEFAULT
    assert state['value'] == 'qwen2.5:32b'
    assert state['is_set'] is False


def test_env_source_beats_default(isolated_service, clean_env):
    clean_env.setenv('LLM_MODEL_NAME', 'qwen2.5:14b')
    state = isolated_service.get_field_state('LLM_MODEL_NAME')
    assert state['source'] == SOURCE_ENV
    assert state['value'] == 'qwen2.5:14b'
    assert state['is_set'] is True


def test_file_source_beats_env(isolated_service, clean_env):
    clean_env.setenv('LLM_MODEL_NAME', 'qwen2.5:14b')
    isolated_service.instance_path.parent.mkdir(parents=True, exist_ok=True)
    isolated_service.instance_path.write_text(
        json.dumps({'LLM_MODEL_NAME': 'gpt-oss:20b'}), encoding='utf-8'
    )
    state = isolated_service.get_field_state('LLM_MODEL_NAME')
    assert state['source'] == SOURCE_FILE
    assert state['value'] == 'gpt-oss:20b'


def test_override_source_beats_file(isolated_service, clean_env):
    isolated_service.instance_path.parent.mkdir(parents=True, exist_ok=True)
    isolated_service.instance_path.write_text(
        json.dumps({'LLM_MODEL_NAME': 'gpt-oss:20b'}), encoding='utf-8'
    )
    isolated_service.set_override('LLM_MODEL_NAME', 'llama3.1:8b')
    state = isolated_service.get_field_state('LLM_MODEL_NAME')
    assert state['source'] == SOURCE_OVERRIDE
    assert state['value'] == 'llama3.1:8b'


def test_unknown_field_returns_none(isolated_service):
    assert isolated_service.get_field_state('does-not-exist') is None


def test_set_override_rejects_unknown_key(isolated_service):
    with pytest.raises(KeyError):
        isolated_service.set_override('DOES_NOT_EXIST', 'x')


def test_clear_override_single_key_then_all(isolated_service, clean_env):
    isolated_service.set_override('LLM_MODEL_NAME', 'a')
    isolated_service.set_override('REPORT_LANGUAGE', 'b')
    isolated_service.clear_override('LLM_MODEL_NAME')
    assert isolated_service.get_field_state('LLM_MODEL_NAME')['source'] == SOURCE_DEFAULT
    assert isolated_service.get_field_state('REPORT_LANGUAGE')['source'] == SOURCE_OVERRIDE
    isolated_service.clear_override()
    assert isolated_service.get_field_state('REPORT_LANGUAGE')['source'] == SOURCE_DEFAULT


# ---------------------------------------------------------------------------
# Coercion
# ---------------------------------------------------------------------------


def test_int_field_coerces_env_string(isolated_service, clean_env):
    clean_env.setenv('ONTOLOGY_MIN_ENTITY_TYPES', '12')
    state = isolated_service.get_field_state('ONTOLOGY_MIN_ENTITY_TYPES')
    assert state['value'] == 12
    assert isinstance(state['value'], int)


def test_float_field_coerces_env_string(isolated_service, clean_env):
    clean_env.setenv('HYBRID_SEARCH_VECTOR_WEIGHT', '0.45')
    state = isolated_service.get_field_state('HYBRID_SEARCH_VECTOR_WEIGHT')
    assert state['value'] == pytest.approx(0.45)


def test_bool_field_coerces_env_truthy(isolated_service, clean_env):
    clean_env.setenv('ENABLE_AGENT_TOOLS', 'true')
    assert isolated_service.get_field_state('ENABLE_AGENT_TOOLS')['value'] is True
    clean_env.setenv('ENABLE_AGENT_TOOLS', 'false')
    assert isolated_service.get_field_state('ENABLE_AGENT_TOOLS')['value'] is False
    clean_env.setenv('ENABLE_AGENT_TOOLS', 'yes')
    assert isolated_service.get_field_state('ENABLE_AGENT_TOOLS')['value'] is True


def test_invalid_int_falls_back_to_default(isolated_service, clean_env):
    clean_env.setenv('ONTOLOGY_MIN_ENTITY_TYPES', 'not-a-number')
    state = isolated_service.get_field_state('ONTOLOGY_MIN_ENTITY_TYPES')
    # Ungültiger Env-Wert wird coerced auf Default; der ``source``
    # bleibt ``env``, weil die Variable explizit gesetzt war —
    # Operator soll die Inkonsistenz im UI sehen.
    assert state['value'] == 8
    assert state['source'] == SOURCE_ENV


# ---------------------------------------------------------------------------
# Secret-Maske
# ---------------------------------------------------------------------------


def test_secret_field_value_is_always_null(isolated_service, clean_env):
    clean_env.setenv('NEO4J_PASSWORD', 'super-secret-actual-password')
    state = isolated_service.get_field_state('NEO4J_PASSWORD')
    assert state['value'] is None
    assert state['is_set'] is True
    # Auch ``default`` darf nicht durchsickern
    assert 'default' not in state


def test_secret_field_marks_unset_when_blank_and_no_override(isolated_service, clean_env):
    state = isolated_service.get_field_state('NEO4J_PASSWORD')
    assert state['value'] is None
    assert state['is_set'] is False


def test_secret_override_is_masked_in_get(isolated_service, clean_env):
    isolated_service.set_override('NEO4J_PASSWORD', 'temp-rotation-pw')
    state = isolated_service.get_field_state('NEO4J_PASSWORD')
    assert state['value'] is None
    assert state['is_set'] is True
    assert state['source'] == SOURCE_OVERRIDE


# ---------------------------------------------------------------------------
# Schema- und Group-Endpoints
# ---------------------------------------------------------------------------


def test_get_all_grouped_returns_every_section(isolated_service, clean_env):
    grouped = isolated_service.get_all_grouped()
    for section in SECTIONS:
        assert section in grouped
    total = sum(len(items) for items in grouped.values())
    assert total == len(SETTINGS_FIELDS)


def test_get_all_grouped_preserves_field_order(isolated_service, clean_env):
    grouped = isolated_service.get_all_grouped()
    declared_per_section = {
        sec: [s.key for s in fields_by_section(sec)] for sec in SECTIONS
    }
    actual_per_section = {
        sec: [item['key'] for item in grouped[sec]] for sec in SECTIONS
    }
    assert declared_per_section == actual_per_section


def test_get_schema_does_not_leak_secret_defaults(isolated_service):
    schema = isolated_service.get_schema()
    by_key = {entry['key']: entry for entry in schema}
    assert by_key['NEO4J_PASSWORD']['default'] is None
    assert by_key['LLM_MODEL_NAME']['default'] == 'qwen2.5:32b'


def test_get_schema_includes_enum_values_and_bounds(isolated_service):
    schema = isolated_service.get_schema()
    by_key = {entry['key']: entry for entry in schema}
    assert by_key['EVENT_BUS_BACKEND']['enum_values'] == ['auto', 'redis', 'file']
    assert by_key['HYBRID_SEARCH_VECTOR_WEIGHT']['min'] == 0.0
    assert by_key['HYBRID_SEARCH_VECTOR_WEIGHT']['max'] == 1.0
    assert by_key['EMBEDDING_MODEL']['cross_validates_with'] == ['VECTOR_DIM']


# ---------------------------------------------------------------------------
# instance/settings.json — Edge-Cases
# ---------------------------------------------------------------------------


def test_corrupt_instance_file_is_treated_as_empty(isolated_service, clean_env):
    isolated_service.instance_path.parent.mkdir(parents=True, exist_ok=True)
    isolated_service.instance_path.write_text('not-json', encoding='utf-8')
    state = isolated_service.get_field_state('LLM_MODEL_NAME')
    assert state['source'] == SOURCE_DEFAULT


def test_non_dict_instance_file_is_treated_as_empty(isolated_service, clean_env):
    isolated_service.instance_path.parent.mkdir(parents=True, exist_ok=True)
    isolated_service.instance_path.write_text('[1, 2, 3]', encoding='utf-8')
    state = isolated_service.get_field_state('LLM_MODEL_NAME')
    assert state['source'] == SOURCE_DEFAULT


def test_missing_instance_file_is_no_error(isolated_service, clean_env):
    # Datei existiert nicht — Service muss trotzdem auflösen
    assert not isolated_service.instance_path.exists()
    state = isolated_service.get_field_state('LLM_MODEL_NAME')
    assert state['source'] == SOURCE_DEFAULT


# ---------------------------------------------------------------------------
# effective_snapshot (Cross-Field-Kontext für den Validator)
# ---------------------------------------------------------------------------


def test_effective_snapshot_excludes_secrets(isolated_service, clean_env):
    snapshot = isolated_service.effective_snapshot()
    for spec in SETTINGS_FIELDS:
        if spec.secret:
            assert spec.key not in snapshot


def test_effective_snapshot_includes_defaults_for_unset_fields(
    isolated_service, clean_env
):
    snapshot = isolated_service.effective_snapshot()
    # EMBEDDING_MODEL und VECTOR_DIM haben Defaults im Schema — sie
    # müssen im Snapshot stehen, damit der Validator den Cross-Field-
    # Check auch bei Partial-Updates fahren kann.
    assert 'EMBEDDING_MODEL' in snapshot
    assert 'VECTOR_DIM' in snapshot


def test_effective_snapshot_reflects_persisted_overrides(
    isolated_service, clean_env
):
    isolated_service.apply_payload(
        {'EMBEDDING_MODEL': 'qwen3-embedding:4b', 'VECTOR_DIM': 2560},
        persist=True,
    )
    snapshot = isolated_service.effective_snapshot()
    assert snapshot['EMBEDDING_MODEL'] == 'qwen3-embedding:4b'
    assert snapshot['VECTOR_DIM'] == 2560


# ---------------------------------------------------------------------------
# Issue #212: neu registrierte Keys (AGORA_PARALLEL_PERSONA_COUNT,
# AGORA_PERSONA_DETAIL_LEVEL, ONTOLOGY_MAX_TOKENS)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'key,expected_default',
    [
        ('AGORA_PARALLEL_PERSONA_COUNT', 10),
        ('ONTOLOGY_MAX_TOKENS', 12288),
        ('AGORA_PERSONA_DETAIL_LEVEL', 'standard'),
    ],
)
def test_new_keys_schema_defaults(key, expected_default, isolated_service, clean_env):
    """Pin-Test: Schema-Defaults der Issue-#212-Migration."""
    spec = field_by_key(key)
    assert spec is not None, f'{key} fehlt im Schema'
    assert spec.default == expected_default


def test_agora_parallel_persona_count_get_default(isolated_service, clean_env):
    state = isolated_service.get_field_state('AGORA_PARALLEL_PERSONA_COUNT')
    assert state['value'] == 10
    assert state['source'] == SOURCE_DEFAULT


def test_agora_parallel_persona_count_env_override(isolated_service, clean_env):
    clean_env.setenv('AGORA_PARALLEL_PERSONA_COUNT', '20')
    state = isolated_service.get_field_state('AGORA_PARALLEL_PERSONA_COUNT')
    assert state['value'] == 20
    assert state['source'] == SOURCE_ENV


def test_agora_parallel_persona_count_live_put(isolated_service, clean_env):
    """Live-Effekt: PUT via apply_payload — effective_value sieht den neuen Wert."""
    isolated_service.apply_payload({'AGORA_PARALLEL_PERSONA_COUNT': 5}, persist=False)
    assert isolated_service.effective_value('AGORA_PARALLEL_PERSONA_COUNT') == 5


def test_agora_persona_detail_level_get_default(isolated_service, clean_env):
    state = isolated_service.get_field_state('AGORA_PERSONA_DETAIL_LEVEL')
    assert state['value'] == 'standard'
    assert state['source'] == SOURCE_DEFAULT


def test_agora_persona_detail_level_env_override(isolated_service, clean_env):
    clean_env.setenv('AGORA_PERSONA_DETAIL_LEVEL', 'compact')
    state = isolated_service.get_field_state('AGORA_PERSONA_DETAIL_LEVEL')
    assert state['value'] == 'compact'
    assert state['source'] == SOURCE_ENV


def test_agora_persona_detail_level_live_put(isolated_service, clean_env):
    """Live-Effekt: PUT via apply_payload — effective_value sieht den neuen Wert."""
    isolated_service.apply_payload({'AGORA_PERSONA_DETAIL_LEVEL': 'rich'}, persist=False)
    assert isolated_service.effective_value('AGORA_PERSONA_DETAIL_LEVEL') == 'rich'


def test_ontology_max_tokens_get_default(isolated_service, clean_env):
    state = isolated_service.get_field_state('ONTOLOGY_MAX_TOKENS')
    assert state['value'] == 12288
    assert state['source'] == SOURCE_DEFAULT


def test_ontology_max_tokens_env_override(isolated_service, clean_env):
    clean_env.setenv('ONTOLOGY_MAX_TOKENS', '8192')
    state = isolated_service.get_field_state('ONTOLOGY_MAX_TOKENS')
    assert state['value'] == 8192
    assert state['source'] == SOURCE_ENV


def test_ontology_max_tokens_live_put(isolated_service, clean_env):
    """Live-Effekt: PUT via apply_payload — effective_value sieht den neuen Wert."""
    isolated_service.apply_payload({'ONTOLOGY_MAX_TOKENS': 16384}, persist=False)
    assert isolated_service.effective_value('ONTOLOGY_MAX_TOKENS') == 16384
