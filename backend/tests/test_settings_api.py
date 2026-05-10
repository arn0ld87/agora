"""Tests für die Settings-API (Issue #133, SUB1 + SUB2).

Pinnt die HTTP-Verträge der vier Routen, inklusive Auth-Guard,
Sektions-Gruppierung, Secret-Maske im GET-Response und
All-or-Nothing-Verhalten der PUT-Validierung.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from flask import Blueprint, Flask

from app.api.settings import (
    get_settings,
    get_settings_schema,
    put_settings,
    put_settings_secrets,
)
from app.services.settings_layer import SettingsService
from app.services.settings_schema import SECTIONS, SETTINGS_FIELDS
from app.utils.api_responses import install_api_error_handlers
from app.utils.auth import install_blueprint_guard


@pytest.fixture
def app(monkeypatch, tmp_path: Path):
    # Frische Service-Instanz pro Test gegen einen tmp instance-Pfad —
    # das verhindert, dass Test-Overrides aus dem Modul-Singleton in
    # andere Tests bleeden.
    service = SettingsService(instance_path=tmp_path / 'settings.json')
    monkeypatch.setattr(
        'app.api.settings.get_default_service', lambda: service
    )
    changed_events = []
    monkeypatch.setattr(
        'app.api.settings.publish_settings_changed',
        lambda keys, *, source: changed_events.append((sorted(keys), source)),
    )

    app = Flask(__name__)
    install_api_error_handlers(app)
    bp = Blueprint('settings_test', __name__)
    bp.add_url_rule('', view_func=get_settings, methods=['GET'])
    bp.add_url_rule('/', view_func=get_settings, methods=['GET'])
    bp.add_url_rule('/schema', view_func=get_settings_schema, methods=['GET'])
    bp.add_url_rule('', view_func=put_settings, methods=['PUT'])
    bp.add_url_rule('/', view_func=put_settings, methods=['PUT'])
    bp.add_url_rule('/secrets', view_func=put_settings_secrets, methods=['PUT'])
    install_blueprint_guard(bp)
    app.register_blueprint(bp, url_prefix='/api/settings')
    app.config['service'] = service
    app.config['changed_events'] = changed_events
    return app


@pytest.fixture
def client(app, monkeypatch):
    monkeypatch.delenv('AGORA_AUTH_TOKEN', raising=False)
    return app.test_client()


# ---------------------------------------------------------------------------
# GET /api/settings
# ---------------------------------------------------------------------------


def test_get_settings_returns_all_sections(client):
    res = client.get('/api/settings')
    assert res.status_code == 200
    body = res.get_json()
    assert body['success'] is True
    data = body['data']
    assert data['sections'] == list(SECTIONS)
    assert set(data['fields'].keys()) == set(SECTIONS)
    total = sum(len(v) for v in data['fields'].values())
    assert total == len(SETTINGS_FIELDS)


def test_get_settings_field_payload_shape(client):
    res = client.get('/api/settings')
    fields = res.get_json()['data']['fields']
    sample = next(item for item in fields['llm'] if item['key'] == 'LLM_MODEL_NAME')
    assert sample['type'] == 'string'
    assert sample['secret'] is False
    assert sample['source'] in ('default', 'env', 'file', 'override')
    assert 'value' in sample
    assert 'default' in sample
    # reload_required muss als bool dabei sein, damit das Frontend das
    # Badge unbedingt rendern kann.
    assert isinstance(sample['reload_required'], bool)


def test_get_settings_masks_secret_values(client, monkeypatch):
    monkeypatch.setenv('NEO4J_PASSWORD', 'secret-actual-password')
    res = client.get('/api/settings')
    fields = res.get_json()['data']['fields']
    pw = next(item for item in fields['neo4j'] if item['key'] == 'NEO4J_PASSWORD')
    assert pw['secret'] is True
    assert pw['value'] is None
    assert pw['is_set'] is True
    # Ein Plaintext-Leak im Response-Body wäre der schlimmste Fall —
    # wir suchen das Secret als Substring im gesamten Response-JSON.
    assert b'secret-actual-password' not in res.data


def test_get_settings_secret_unset_is_marked(client, monkeypatch):
    monkeypatch.delenv('NEO4J_PASSWORD', raising=False)
    res = client.get('/api/settings')
    fields = res.get_json()['data']['fields']
    pw = next(item for item in fields['neo4j'] if item['key'] == 'NEO4J_PASSWORD')
    assert pw['is_set'] is False
    assert pw['value'] is None


def test_get_settings_reflects_override(client, app, monkeypatch):
    monkeypatch.delenv('LLM_MODEL_NAME', raising=False)
    app.config['service'].set_override('LLM_MODEL_NAME', 'llama3.1:8b')
    res = client.get('/api/settings')
    fields = res.get_json()['data']['fields']
    item = next(i for i in fields['llm'] if i['key'] == 'LLM_MODEL_NAME')
    assert item['source'] == 'override'
    assert item['value'] == 'llama3.1:8b'


# ---------------------------------------------------------------------------
# GET /api/settings/schema
# ---------------------------------------------------------------------------


def test_get_schema_payload(client):
    res = client.get('/api/settings/schema')
    assert res.status_code == 200
    body = res.get_json()
    assert body['success'] is True
    fields = body['data']['fields']
    assert len(fields) == len(SETTINGS_FIELDS)
    # Schema enthält keine ``value``- und keine ``source``-Felder, das
    # bleibt der GET-Endpoint für die Werte. So bleibt der Schema-Cache
    # im Frontend stabil, auch wenn sich die Werte ändern.
    for entry in fields:
        assert 'value' not in entry
        assert 'source' not in entry


def test_get_schema_does_not_leak_secret_defaults(client, monkeypatch):
    monkeypatch.setenv('NEO4J_PASSWORD', 'leak-me-not')
    res = client.get('/api/settings/schema')
    fields = res.get_json()['data']['fields']
    pw = next(e for e in fields if e['key'] == 'NEO4J_PASSWORD')
    assert pw['default'] is None
    assert pw['secret'] is True
    assert b'leak-me-not' not in res.data


# ---------------------------------------------------------------------------
# Auth-Guard
# ---------------------------------------------------------------------------


def test_auth_required_when_token_set(app, monkeypatch):
    monkeypatch.setenv('AGORA_AUTH_TOKEN', 'tok-xyz')
    client = app.test_client()
    # Ohne Token → 401
    res = client.get('/api/settings')
    assert res.status_code == 401
    # Mit korrektem Header → 200
    res2 = client.get('/api/settings', headers={'X-Agora-Token': 'tok-xyz'})
    assert res2.status_code == 200


# ---------------------------------------------------------------------------
# PUT /api/settings — Happy Path
# ---------------------------------------------------------------------------


def test_put_settings_persists_and_returns_updated_state(client, app):
    res = client.put('/api/settings', json={'LLM_MODEL_NAME': 'qwen2.5:14b'})
    assert res.status_code == 200
    body = res.get_json()
    assert body['success'] is True
    assert body['data']['updated_keys'] == ['LLM_MODEL_NAME']
    # Datei wurde geschrieben
    instance_path = app.config['service'].instance_path
    assert instance_path.exists()
    data = json.loads(instance_path.read_text(encoding='utf-8'))
    assert data == {'LLM_MODEL_NAME': 'qwen2.5:14b'}


def test_put_settings_broadcasts_settings_changed_event(client, app):
    res = client.put('/api/settings', json={'LLM_MODEL_NAME': 'qwen2.5:14b'})
    assert res.status_code == 200
    assert app.config['changed_events'] == [
        (['LLM_MODEL_NAME'], 'settings')
    ]


def test_put_settings_response_reflects_new_source(client):
    res = client.put('/api/settings', json={'LLM_MODEL_NAME': 'qwen2.5:14b'})
    fields = res.get_json()['data']['fields']
    item = next(i for i in fields['llm'] if i['key'] == 'LLM_MODEL_NAME')
    assert item['value'] == 'qwen2.5:14b'
    assert item['source'] == 'file'


def test_put_settings_round_trip_with_get(client):
    client.put('/api/settings', json={'REPORT_LANGUAGE': 'English'})
    res = client.get('/api/settings')
    fields = res.get_json()['data']['fields']
    item = next(i for i in fields['locale'] if i['key'] == 'REPORT_LANGUAGE')
    assert item['value'] == 'English'
    assert item['source'] == 'file'


# ---------------------------------------------------------------------------
# PUT /api/settings — Validation
# ---------------------------------------------------------------------------


def test_put_settings_returns_400_on_validation_error(client):
    res = client.put('/api/settings', json={
        'ONTOLOGY_MIN_ENTITY_TYPES': 'nope',
    })
    assert res.status_code == 400
    body = res.get_json()
    assert body['success'] is False
    assert body['code'] == 'validation_failed'
    assert any(err['key'] == 'ONTOLOGY_MIN_ENTITY_TYPES' for err in body['errors'])


def test_put_settings_collects_multiple_errors(client):
    res = client.put('/api/settings', json={
        'ONTOLOGY_MIN_ENTITY_TYPES': 'nope',
        'EVENT_BUS_BACKEND': 'kafka',
        'BOGUS_KEY': 'x',
    })
    assert res.status_code == 400
    body = res.get_json()
    keys = [err['key'] for err in body['errors']]
    assert 'ONTOLOGY_MIN_ENTITY_TYPES' in keys
    assert 'EVENT_BUS_BACKEND' in keys
    assert 'BOGUS_KEY' in keys


def test_put_settings_all_or_nothing_no_partial_persist(client, app):
    res = client.put('/api/settings', json={
        'REPORT_LANGUAGE': 'English',  # gültig
        'ONTOLOGY_MIN_ENTITY_TYPES': 'broken',  # ungültig
    })
    assert res.status_code == 400
    # File darf nicht angelegt worden sein
    assert not app.config['service'].instance_path.exists()
    assert app.config['changed_events'] == []


def test_put_settings_rejects_secrets_on_regular_endpoint(client):
    res = client.put('/api/settings', json={'NEO4J_PASSWORD': 'pw'})
    assert res.status_code == 400
    body = res.get_json()
    assert any(
        err['code'] == 'secret_not_allowed' for err in body['errors']
    )


def test_put_settings_rejects_vector_dim_mismatch(client):
    res = client.put('/api/settings', json={
        'EMBEDDING_MODEL': 'qwen3-embedding:4b',
        'VECTOR_DIM': 1024,
    })
    assert res.status_code == 400
    body = res.get_json()
    assert any(
        err['code'] == 'vector_dim_mismatch' for err in body['errors']
    )


def test_put_settings_rejects_partial_update_against_persisted_state(
    client, app, monkeypatch
):
    """Gemini #155-High: PUT mit nur einer Hälfte des
    EMBEDDING_MODEL/VECTOR_DIM-Paares muss gegen den persistierten
    Gegenpart geprüft werden — sonst landet eine inkonsistente
    Konfiguration in der Datei.
    """
    # Persisted Stand ist explizit gesetzt
    app.config['service'].apply_payload(
        {'EMBEDDING_MODEL': 'qwen3-embedding:4b', 'VECTOR_DIM': 2560},
        persist=True,
    )
    # Jetzt nur EMBEDDING_MODEL wechseln, VECTOR_DIM nicht mit
    res = client.put(
        '/api/settings', json={'EMBEDDING_MODEL': 'nomic-embed-text'},
    )
    assert res.status_code == 400
    body = res.get_json()
    assert any(err['code'] == 'vector_dim_mismatch' for err in body['errors'])

    # Persisted-Stand ist unverändert geblieben (All-or-Nothing).
    data = json.loads(app.config['service'].instance_path.read_text(encoding='utf-8'))
    assert data['EMBEDDING_MODEL'] == 'qwen3-embedding:4b'
    assert data['VECTOR_DIM'] == 2560


def test_put_settings_rejects_non_dict_body(client):
    res = client.put('/api/settings', json=['not', 'a', 'dict'])
    assert res.status_code == 400
    assert res.get_json()['code'] == 'invalid_payload'


# ---------------------------------------------------------------------------
# PUT /api/settings/secrets
# ---------------------------------------------------------------------------


def test_put_secrets_requires_confirm_flag(client):
    res = client.put('/api/settings/secrets', json={
        'fields': {'NEO4J_PASSWORD': 'new-pw'},
    })
    assert res.status_code == 400
    assert res.get_json()['code'] == 'confirm_required'


def test_put_secrets_persists_with_confirm(client, app):
    res = client.put('/api/settings/secrets', json={
        'confirm': True,
        'fields': {'NEO4J_PASSWORD': 'new-pw'},
    })
    assert res.status_code == 200
    body = res.get_json()
    assert body['success'] is True
    # GET liefert NIE den Klartext zurück
    pw_field = next(
        i for i in body['data']['fields']['neo4j']
        if i['key'] == 'NEO4J_PASSWORD'
    )
    assert pw_field['value'] is None
    assert pw_field['is_set'] is True
    # Aber das File enthält den Klartext (Issue-Akzeptanz)
    data = json.loads(app.config['service'].instance_path.read_text(encoding='utf-8'))
    assert data['NEO4J_PASSWORD'] == 'new-pw'


def test_put_secrets_broadcasts_settings_changed_event_without_values(client, app):
    res = client.put('/api/settings/secrets', json={
        'confirm': True,
        'fields': {'NEO4J_PASSWORD': 'new-pw'},
    })
    assert res.status_code == 200
    assert app.config['changed_events'] == [
        (['NEO4J_PASSWORD'], 'settings.secrets')
    ]
    assert b'new-pw' not in res.data


def test_put_secrets_rejects_non_secret_field(client):
    res = client.put('/api/settings/secrets', json={
        'confirm': True,
        'fields': {'LLM_MODEL_NAME': 'sneaky'},
    })
    assert res.status_code == 400
    assert res.get_json()['code'] == 'non_secret_field'


def test_put_secrets_rejects_unknown_field(client):
    res = client.put('/api/settings/secrets', json={
        'confirm': True,
        'fields': {'TOTALLY_BOGUS': 'x'},
    })
    assert res.status_code == 400
    # ``non_secret_field`` triggert vor ``unknown_field`` — beides
    # signalisiert dem Operator: Feld gehört nicht hierher.
    assert res.get_json()['code'] == 'non_secret_field'


def test_put_secrets_response_does_not_leak_plaintext(client):
    res = client.put('/api/settings/secrets', json={
        'confirm': True,
        'fields': {'NEO4J_PASSWORD': 'super-secret-leak-canary'},
    })
    assert b'super-secret-leak-canary' not in res.data


def test_put_settings_auth_required(app, monkeypatch):
    monkeypatch.setenv('AGORA_AUTH_TOKEN', 'tok-xyz')
    client = app.test_client()
    res = client.put('/api/settings', json={'LLM_MODEL_NAME': 'a'})
    assert res.status_code == 401
    res2 = client.put(
        '/api/settings',
        json={'LLM_MODEL_NAME': 'a'},
        headers={'X-Agora-Token': 'tok-xyz'},
    )
    assert res2.status_code == 200
