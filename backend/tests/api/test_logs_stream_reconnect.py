"""Tests für SSE-Reconnect-Semantik: id:-Frames und Last-Event-ID-Header (Slice J.5.1, #233).

Verträge:
  A. Jede Datenzeile im Stream enthält ein vorangestelltes ``id: <int>``-Frame.
     Die id:-Werte sind monoton steigend; der letzte entspricht der Dateigröße.
  B. ``Last-Event-ID``-Header überstimmt ``?offset=``-Query — der Stream
     startet ab dem im Header genannten Byte-Offset.
  C. Reconnect mit dem letzten ``id:``-Wert liefert keine Duplikate und
     alle Zeilen ab dem Wiederaufsetzpunkt.
  D. Invalides ``Last-Event-ID`` fällt sauber auf URL-Offset zurück (200, korrekte Daten).
  E. simulation_stream loggt Last-Event-ID beim Reconnect (caplog).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from flask import Blueprint, Flask

from app.api.logs import get_logs, stream_logs
from app.utils.auth import install_blueprint_guard


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope='module')
def app():
    """Frische Flask-App mit logs-Blueprint — scope=module für Performance."""
    application = Flask(__name__)
    bp = Blueprint('logs_reconnect_test', __name__)
    bp.add_url_rule('', view_func=get_logs, methods=['GET'])
    bp.add_url_rule('/', view_func=get_logs, methods=['GET'])
    bp.add_url_rule('/stream', view_func=stream_logs, methods=['GET'])
    install_blueprint_guard(bp)
    application.register_blueprint(bp, url_prefix='/api/logs')
    return application


@pytest.fixture
def client(app, tmp_path, monkeypatch):
    monkeypatch.setattr('app.api.logs.LOG_DIR', str(tmp_path))
    monkeypatch.delenv('AGORA_AUTH_TOKEN', raising=False)
    # time.sleep im Generator überspringen — verhindert Test-Timeouts.
    monkeypatch.setattr('app.api.logs.time.sleep', lambda *_: None)
    return app.test_client()


def _write_today_log(tmp_path: Path, lines: list[str]) -> Path:
    """Schreibt ``lines`` (mit abschließendem \\n pro Zeile) in die heutige Logdatei."""
    from datetime import datetime
    name = datetime.now().strftime('%Y-%m-%d') + '.log'
    p = tmp_path / name
    p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return p


def _collect_sse_frames(
    response,
    *,
    max_data_frames: int,
    timeout_sec: float = 2.0,
) -> list[str]:
    """Liest bis zu ``max_data_frames`` data:-Frames aus dem SSE-Response und
    gibt alle rohen SSE-Chunks als Liste zurück.

    Stoppt sobald ``max_data_frames`` data:-Zeilen gesehen wurden oder die
    Deadline abläuft. Schließt den Response danach immer.
    """
    chunks: list[str] = []
    data_count = 0
    deadline = time.monotonic() + timeout_sec
    try:
        for raw in response.response:
            chunk = raw.decode('utf-8') if isinstance(raw, bytes) else raw
            chunks.append(chunk)
            data_count += chunk.count('\ndata:') + (1 if chunk.startswith('data:') else 0)
            if data_count >= max_data_frames:
                break
            if time.monotonic() >= deadline:
                break
    finally:
        response.close()
    return chunks


def _parse_sse_events(chunks: list[str]) -> list[dict[str, str]]:
    """Parst rohe SSE-Chunks in eine Liste von Dicts mit Keys ``id``, ``event``, ``data``."""
    blob = ''.join(chunks)
    events = []
    current: dict[str, str] = {}
    for line in blob.splitlines():
        if line.startswith('id:'):
            current['id'] = line[3:].strip()
        elif line.startswith('event:'):
            current['event'] = line[6:].strip()
        elif line.startswith('data:'):
            current['data'] = line[5:].strip()
        elif line == '' and current:
            if 'data' in current:
                events.append(current)
            current = {}
    if current and 'data' in current:
        events.append(current)
    return events


# ---------------------------------------------------------------------------
# Test A — id:-Frame pro Datenzeile
# ---------------------------------------------------------------------------


def test_stream_emits_id_frame_per_data_line(client, tmp_path, monkeypatch):
    """Jeder data:-Frame muss ein vorangestelltes id: <int>-Frame tragen.

    Verträge:
    - Alle data:-Events haben ein ``id``-Feld.
    - Die id-Werte sind monoton steigend (als Integer).
    - Der letzte id-Wert entspricht der Dateigröße in Bytes.
    """
    log_lines = ['alpha line', 'beta line', 'gamma line']
    log_file = _write_today_log(tmp_path, log_lines)
    file_size = log_file.stat().st_size

    response = client.get('/api/logs/stream?offset=0', buffered=False)
    assert response.status_code == 200
    assert response.mimetype == 'text/event-stream'

    chunks = _collect_sse_frames(response, max_data_frames=3)
    events = _parse_sse_events(chunks)

    # Nur data-Events filtern (kein retry-Frame, kein heartbeat).
    data_events = [e for e in events if 'data' in e]
    assert len(data_events) >= 3, (
        f"Erwartet mind. 3 data:-Events, erhalten: {len(data_events)}. "
        f"Chunks: {chunks!r}"
    )

    # Alle data-Events müssen ein id-Feld haben.
    for evt in data_events[:3]:
        assert 'id' in evt, f"data:-Event ohne id-Feld: {evt!r}"
        # id muss ein Integer sein.
        assert evt['id'].isdigit() or (
            evt['id'].lstrip('-').isdigit()
        ), f"id ist kein Integer: {evt['id']!r}"

    # id-Werte monoton steigend.
    ids = [int(e['id']) for e in data_events[:3]]
    for i in range(1, len(ids)):
        assert ids[i] > ids[i - 1], (
            f"id-Werte nicht monoton steigend: {ids}"
        )

    # Letzter id-Wert = Dateigröße.
    assert ids[-1] == file_size, (
        f"Letzter id-Wert {ids[-1]} != Dateigröße {file_size}"
    )


# ---------------------------------------------------------------------------
# Test B — Last-Event-ID überstimmt ?offset=
# ---------------------------------------------------------------------------


def test_last_event_id_overrides_url_offset(client, tmp_path, monkeypatch):
    """Last-Event-ID-Header hat höhere Priorität als ?offset= in der URL.

    Setup: 5 Zeilen schreiben, Byte-Offset nach Zeile 3 ermitteln.
    Request: ?offset=0 + Header Last-Event-ID=<offset-nach-zeile-3>.
    Erwartung: erster data:-Frame enthält Zeile 4, nicht Zeile 1.
    """
    lines = ['line-one', 'line-two', 'line-three', 'line-four', 'line-five']
    _write_today_log(tmp_path, lines)

    # Byte-Offset nach den ersten 3 Zeilen ermitteln.
    first_three = '\n'.join(lines[:3]) + '\n'
    offset_after_line3 = len(first_three.encode('utf-8'))

    response = client.get(
        '/api/logs/stream?offset=0',
        buffered=False,
        headers={'Last-Event-ID': str(offset_after_line3)},
    )
    assert response.status_code == 200

    chunks = _collect_sse_frames(response, max_data_frames=1)
    events = _parse_sse_events(chunks)
    data_events = [e for e in events if 'data' in e]

    assert len(data_events) >= 1, (
        f"Kein data:-Event empfangen. Chunks: {chunks!r}"
    )

    first_payload = json.loads(data_events[0]['data'])
    first_line = first_payload['line']

    assert first_line == 'line-four', (
        f"Erwartet 'line-four' (Last-Event-ID überstimmt ?offset=0), "
        f"erhalten: {first_line!r}"
    )


# ---------------------------------------------------------------------------
# Test C — Kein Duplikat beim Reconnect
# ---------------------------------------------------------------------------


def test_no_duplicates_on_reconnect(client, tmp_path, monkeypatch):
    """Reconnect mit dem id:-Wert des letzten Events liefert keine Duplikate.

    Ablauf:
    1. Logdatei mit 4 Zeilen schreiben.
    2. Erste Verbindung: alle 4 data:-Frames lesen, letzten id:-Wert merken.
    3. Datei um 2 weitere Zeilen erweitern.
    4. Zweite Verbindung mit Last-Event-ID=<letzter-id>.
    5. Assert: keine Zeile aus dem ersten Stream, alle neuen Zeilen da.
    """
    lines_first = ['first-a', 'first-b', 'first-c', 'first-d']
    log_file = _write_today_log(tmp_path, lines_first)

    # Erste Verbindung.
    response1 = client.get('/api/logs/stream?offset=0', buffered=False)
    assert response1.status_code == 200
    chunks1 = _collect_sse_frames(response1, max_data_frames=4)
    events1 = _parse_sse_events(chunks1)
    data_events1 = [e for e in events1 if 'data' in e]
    assert len(data_events1) >= 4, (
        f"Erwartet mind. 4 data:-Events in erster Verbindung, "
        f"erhalten: {len(data_events1)}"
    )
    last_id = data_events1[-1]['id']

    # Datei wächst um 2 weitere Zeilen.
    existing = log_file.read_text(encoding='utf-8')
    log_file.write_text(existing + 'second-e\nsecond-f\n', encoding='utf-8')

    # Zweite Verbindung mit Last-Event-ID.
    response2 = client.get(
        '/api/logs/stream',
        buffered=False,
        headers={'Last-Event-ID': last_id},
    )
    assert response2.status_code == 200
    chunks2 = _collect_sse_frames(response2, max_data_frames=2)
    events2 = _parse_sse_events(chunks2)
    data_events2 = [e for e in events2 if 'data' in e]

    received_lines = [json.loads(e['data'])['line'] for e in data_events2]

    # Keine Zeile aus dem ersten Stream.
    for old_line in lines_first:
        assert old_line not in received_lines, (
            f"Duplikat entdeckt: '{old_line}' im zweiten Stream. "
            f"Empfangen: {received_lines!r}"
        )

    # Neue Zeilen vorhanden.
    assert 'second-e' in received_lines, (
        f"'second-e' fehlt im Reconnect-Stream. Empfangen: {received_lines!r}"
    )
    assert 'second-f' in received_lines, (
        f"'second-f' fehlt im Reconnect-Stream. Empfangen: {received_lines!r}"
    )


# ---------------------------------------------------------------------------
# Test D — Invalides Last-Event-ID fällt sauber auf URL-Offset zurück
# ---------------------------------------------------------------------------


def test_invalid_last_event_id_falls_back_to_url_offset(client, tmp_path, monkeypatch):
    """Garbage-Last-Event-ID: Server antwortet 200 und startet ab ?offset=0.

    Ein invalider Header-Wert darf den Stream nicht crashen — stattdessen
    greift der URL-Offset als Fallback.
    """
    lines = ['fallback-line-one', 'fallback-line-two']
    _write_today_log(tmp_path, lines)

    response = client.get(
        '/api/logs/stream?offset=0',
        buffered=False,
        headers={'Last-Event-ID': 'garbage-not-an-int'},
    )
    assert response.status_code == 200
    assert response.mimetype == 'text/event-stream'

    chunks = _collect_sse_frames(response, max_data_frames=2)
    events = _parse_sse_events(chunks)
    data_events = [e for e in events if 'data' in e]

    assert len(data_events) >= 2, (
        f"Erwartet mind. 2 data:-Events nach Garbage-Header, "
        f"erhalten: {len(data_events)}. Chunks: {chunks!r}"
    )

    first_line = json.loads(data_events[0]['data'])['line']
    assert first_line == 'fallback-line-one', (
        f"Erwartet 'fallback-line-one' (URL-Offset=0 als Fallback), "
        f"erhalten: {first_line!r}"
    )


# ---------------------------------------------------------------------------
# Test E — simulation_stream loggt Last-Event-ID (caplog)
# ---------------------------------------------------------------------------


def test_simulation_stream_logs_last_event_id():
    """GET /api/simulation/<id>/stream mit Last-Event-ID-Header → Log-Eintrag.

    Der Bus hat keine Replay-API; das Logging ist der einzige sichtbare
    Effekt des Headers auf simulation_stream.

    Hinweis: agora.simulation_stream nutzt ``propagate=False``, daher muss
    der caplog-Handler direkt an den Logger gehängt werden.
    """
    import logging

    from flask import Flask

    from app.api import simulation_bp
    from app.services.event_bus import InMemoryEventBus

    sim_app = Flask(__name__)
    sim_app.extensions = {}
    sim_app.extensions['event_bus'] = InMemoryEventBus()
    sim_app.register_blueprint(simulation_bp, url_prefix='/api/simulation')

    sim_id = 'sim_abcdef012345'

    # Da propagate=False gesetzt ist, hängen wir einen eigenen Handler
    # direkt an den Agora-Logger, um Records zu capturen.
    captured: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    target_logger = logging.getLogger('agora.simulation_stream')
    handler = _Capture(level=logging.INFO)
    target_logger.addHandler(handler)
    try:
        client = sim_app.test_client()
        response = client.get(
            f'/api/simulation/{sim_id}/stream',
            buffered=False,
            headers={'Last-Event-ID': '42'},
        )
        # Genug lesen, damit der Request-Handler durchläuft.
        try:
            next(iter(response.response))
        except StopIteration:
            pass
        response.close()
    finally:
        target_logger.removeHandler(handler)

    matching = [
        r for r in captured
        if 'Last-Event-ID' in r.getMessage() and sim_id in r.getMessage()
    ]
    assert matching, (
        f"Kein Log-Eintrag mit 'Last-Event-ID' und sim_id={sim_id!r} gefunden. "
        f"Records: {[r.getMessage() for r in captured]!r}"
    )


# ---------------------------------------------------------------------------
# Test F — Multi-Byte-UTF-8: id:-Werte entsprechen Byte-Offsets
# ---------------------------------------------------------------------------


def test_id_frames_correct_for_multibyte_utf8_lines(client, tmp_path, monkeypatch):
    """Bei UTF-8-Multi-Byte-Zeilen muss id == Byte-Offset in der Datei sein.

    Im alten Textmodus war tell() ein opakes Cookie, das beim Reconnect
    nicht zuverlässig mit st_size verglichen werden konnte. Mit 'rb' ist
    tell() garantiert ein Byte-Offset.

    Zwei Zeilen mit Umlauten und Emoji — bewusst Multi-Byte pro Zeichen.
    """
    line1 = "Müller-Maße: 42 €"
    line2 = "Test 🚀 läuft"
    content = (line1 + "\n" + line2 + "\n").encode("utf-8")

    from datetime import datetime as _dt
    log_name = _dt.now().strftime('%Y-%m-%d') + '.log'
    log_file = tmp_path / log_name
    log_file.write_bytes(content)

    # Erwartete Byte-Offsets: jeweils nach dem abschließenden \n jeder Zeile.
    expected_id_after_line1 = len(line1.encode("utf-8")) + 1  # +1 für \n
    expected_id_after_line2 = len(content)

    response = client.get('/api/logs/stream?offset=0', buffered=False)
    assert response.status_code == 200
    assert response.mimetype == 'text/event-stream'

    chunks = _collect_sse_frames(response, max_data_frames=2)
    events = _parse_sse_events(chunks)
    data_events = [e for e in events if 'data' in e]

    assert len(data_events) >= 2, (
        f"Erwartet mind. 2 data:-Events für Multi-Byte-Zeilen, "
        f"erhalten: {len(data_events)}. Chunks: {chunks!r}"
    )

    ids = [int(e['id']) for e in data_events[:2]]

    assert ids[0] == expected_id_after_line1, (
        f"id nach Zeile 1: erwartet {expected_id_after_line1} (Byte-Offset), "
        f"erhalten: {ids[0]}. Zeile enthält Multi-Byte-Zeichen."
    )
    assert ids[1] == expected_id_after_line2, (
        f"id nach Zeile 2: erwartet {expected_id_after_line2} (Byte-Offset = Dateigröße), "
        f"erhalten: {ids[1]}."
    )

    # Zeileninhalte müssen korrekt dekodiert ankommen.
    decoded_lines = [json.loads(e['data'])['line'] for e in data_events[:2]]
    assert decoded_lines[0] == line1, (
        f"Zeile 1 falsch dekodiert: erwartet {line1!r}, erhalten: {decoded_lines[0]!r}"
    )
    assert decoded_lines[1] == line2, (
        f"Zeile 2 falsch dekodiert: erwartet {line2!r}, erhalten: {decoded_lines[1]!r}"
    )
