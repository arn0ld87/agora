"""Tests für die Settings-API (Issue #133, SUB1).

Pinnt die GET-Routen ``/api/settings`` und ``/api/settings/schema`` —
inklusive Auth-Guard, Sektions-Gruppierung und der Secret-Maske im
GET-Response. Schreib-Tests folgen in SUB2.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from flask import Blueprint, Flask

from app.api.settings import get_settings, get_settings_schema
from app.services.settings_layer import SettingsService
from app.services.settings_schema import SECTIONS, SETTINGS_FIELDS
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

    app = Flask(__name__)
    bp = Blueprint('settings_test', __name__)
    bp.add_url_rule('', view_func=get_settings, methods=['GET'])
    bp.add_url_rule('/', view_func=get_settings, methods=['GET'])
    bp.add_url_rule('/schema', view_func=get_settings_schema, methods=['GET'])
    install_blueprint_guard(bp)
    app.register_blueprint(bp, url_prefix='/api/settings')
    app.config['service'] = service
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
