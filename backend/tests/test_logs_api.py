"""Tests für den Backend-Log-Viewer-API (Issue #132).

Verträge:
  1. Auth: ohne Token (im Token-Modus) → 401.
  2. Path-Traversal-Schutz: kein ``?file=`` o.ä. wird akzeptiert; der Pfad
     wird hardcoded aus ``LOG_DIR`` plus heutigem Datum gebildet.
  3. Tail-Default 200, Cap 2000.
  4. Level-Filter klassifiziert via Heuristik (Levelname im Logger-Format).
  5. Bei nicht-existierender Logdatei → leere Liste, Status 200.
"""

from pathlib import Path

import pytest
from flask import Blueprint, Flask

from app.api.logs import get_logs, stream_logs
from app.utils.auth import install_blueprint_guard


@pytest.fixture(scope='module')
def app():
    # Frische Blueprint-Instanz pro Modul, damit `install_blueprint_guard`
    # nur einmal aufgerufen wird (Flask >=3 verbietet Setup-Aufrufe nach
    # `register_blueprint`).
    app = Flask(__name__)
    bp = Blueprint('logs_test', __name__)
    bp.add_url_rule('', view_func=get_logs, methods=['GET'])
    bp.add_url_rule('/', view_func=get_logs, methods=['GET'])
    bp.add_url_rule('/stream', view_func=stream_logs, methods=['GET'])
    install_blueprint_guard(bp)
    app.register_blueprint(bp, url_prefix='/api/logs')
    return app


@pytest.fixture
def client(app, tmp_path, monkeypatch):
    # LOG_DIR pro Test patchen — frischer tmp-Ordner, kein Bleed.
    monkeypatch.setattr('app.api.logs.LOG_DIR', str(tmp_path))
    return app.test_client()


def _write_today_log(tmp_path: Path, content: str) -> Path:
    from datetime import datetime
    name = datetime.now().strftime('%Y-%m-%d') + '.log'
    p = tmp_path / name
    p.write_text(content, encoding='utf-8')
    return p


def test_get_logs_returns_empty_when_no_file(client, monkeypatch):
    monkeypatch.delenv('AGORA_AUTH_TOKEN', raising=False)
    res = client.get('/api/logs')
    assert res.status_code == 200
    body = res.get_json()
    assert body['success'] is True
    assert body['data']['lines'] == []
    assert body['data']['file'] is None


def test_get_logs_tails_existing_file(client, tmp_path, monkeypatch):
    monkeypatch.delenv('AGORA_AUTH_TOKEN', raising=False)
    _write_today_log(tmp_path, '\n'.join(f'line-{i}' for i in range(10)))

    res = client.get('/api/logs?tail=3')
    assert res.status_code == 200
    body = res.get_json()
    lines = body['data']['lines']
    assert len(lines) == 3
    assert lines[0].strip() == 'line-7'
    assert lines[2].strip() == 'line-9'


def test_get_logs_caps_tail_at_max(client, tmp_path, monkeypatch):
    monkeypatch.delenv('AGORA_AUTH_TOKEN', raising=False)
    _write_today_log(tmp_path, '\n'.join(f'l{i}' for i in range(5000)))

    res = client.get('/api/logs?tail=10000')  # > _MAX_TAIL
    assert res.status_code == 200
    assert len(res.get_json()['data']['lines']) == 2000


def test_get_logs_default_tail_when_param_missing(client, tmp_path, monkeypatch):
    monkeypatch.delenv('AGORA_AUTH_TOKEN', raising=False)
    _write_today_log(tmp_path, '\n'.join(f'l{i}' for i in range(500)))

    res = client.get('/api/logs')
    assert len(res.get_json()['data']['lines']) == 200


def test_get_logs_level_filter_errors(client, tmp_path, monkeypatch):
    monkeypatch.delenv('AGORA_AUTH_TOKEN', raising=False)
    _write_today_log(
        tmp_path,
        '2026-05-01 - agora - INFO - hello\n'
        '2026-05-01 - agora - ERROR - boom\n'
        '2026-05-01 - agora - DEBUG - quiet\n'
        'Traceback (most recent call last):\n',
    )

    res = client.get('/api/logs?level=error')
    body = res.get_json()
    assert all('ERROR' in ln or 'Traceback' in ln for ln in body['data']['lines'])
    assert len(body['data']['lines']) == 2


def test_get_logs_requires_token_when_set(client, tmp_path, monkeypatch):
    monkeypatch.setenv('AGORA_AUTH_TOKEN', 'secret-token-xxxxxxxxxxxxxxxxxxxxxxxxxxxx')
    _write_today_log(tmp_path, 'l\n')

    res = client.get('/api/logs')
    assert res.status_code == 401
    body = res.get_json()
    assert body['success'] is False
    assert body['code'] == 'auth_required'


def test_get_logs_accepts_token_in_header(client, tmp_path, monkeypatch):
    monkeypatch.setenv('AGORA_AUTH_TOKEN', 'secret-token-xxxxxxxxxxxxxxxxxxxxxxxxxxxx')
    _write_today_log(tmp_path, 'one\ntwo\n')

    res = client.get(
        '/api/logs',
        headers={'Authorization': 'Bearer secret-token-xxxxxxxxxxxxxxxxxxxxxxxxxxxx'},
    )
    assert res.status_code == 200
    assert len(res.get_json()['data']['lines']) == 2


def test_get_logs_ignores_invalid_tail_value(client, tmp_path, monkeypatch):
    monkeypatch.delenv('AGORA_AUTH_TOKEN', raising=False)
    _write_today_log(tmp_path, '\n'.join(f'l{i}' for i in range(20)))

    # Negatives, Strings, 0 → default 200, also alle 20 Lines.
    res = client.get('/api/logs?tail=-5')
    assert len(res.get_json()['data']['lines']) == 20
    res = client.get('/api/logs?tail=abc')
    assert len(res.get_json()['data']['lines']) == 20
    res = client.get('/api/logs?tail=0')
    assert len(res.get_json()['data']['lines']) == 20


def test_get_logs_no_file_param_supported(client, tmp_path, monkeypatch):
    """Path-Traversal-Schutz: ``?file=…`` ist NICHT in der API.
    Setzen wir den Param trotzdem, muss er ignoriert werden — die heutige
    Logdatei bleibt die einzig gelesene Quelle.
    """
    monkeypatch.delenv('AGORA_AUTH_TOKEN', raising=False)
    _write_today_log(tmp_path, 'safe-line\n')

    res = client.get('/api/logs?file=../../etc/passwd')
    assert res.status_code == 200
    lines = res.get_json()['data']['lines']
    # Newlines werden serverseitig gestrippt (Konsistenz mit dem
    # Stream-Endpunkt, der splitlines() nutzt).
    assert lines == ['safe-line']


def test_get_logs_strips_trailing_newlines(client, tmp_path, monkeypatch):
    """PR #146-Review: Tail-Lines kommen ohne Trailing-Newline zurück,
    damit das Frontend (``white-space: pre-wrap`` + ``<div>``-pro-Zeile)
    keine doppelten Leerzeilen rendert. Stream-Endpunkt liefert das
    bereits via ``splitlines()``.
    """
    monkeypatch.delenv('AGORA_AUTH_TOKEN', raising=False)
    _write_today_log(tmp_path, 'one\r\ntwo\nthree\n')

    res = client.get('/api/logs')
    lines = res.get_json()['data']['lines']
    assert lines == ['one', 'two', 'three']
    # Niemand soll noch \r oder \n am Ende haben.
    assert all(not ln.endswith(('\n', '\r')) for ln in lines)


def test_get_logs_offset_matches_file_size(client, tmp_path, monkeypatch):
    """PR #146-Review: Der Offset im Tail-Response soll der echten
    Dateigröße entsprechen — Stream nutzt den Wert als Wiederaufsetzpunkt.
    ``fh.tell()`` nach Iteration über das Text-File-Objekt ist durch
    Pythons internes Buffering nicht zuverlässig.
    """
    monkeypatch.delenv('AGORA_AUTH_TOKEN', raising=False)
    payload = '\n'.join(f'l{i}' for i in range(20)) + '\n'
    p = _write_today_log(tmp_path, payload)

    res = client.get('/api/logs?tail=5')
    body = res.get_json()['data']
    assert body['offset'] == p.stat().st_size


def test_parse_offset_arg_rejects_negative_and_garbage():
    """PR #146-Review: Stream-``?offset=`` muss Garbage absorbieren und
    auf ``None`` fallen, damit die Default-Wahl (Datei-Ende) greift.
    """
    from app.api.logs import _parse_offset_arg

    app_ = Flask(__name__)
    cases = [
        ('5', 5),
        ('0', 0),
        ('-1', None),
        ('abc', None),
        ('', None),
    ]
    for raw, expected in cases:
        with app_.test_request_context(f'/?offset={raw}'):
            assert _parse_offset_arg() == expected, raw
    with app_.test_request_context('/'):
        assert _parse_offset_arg() is None
