"""Log-Viewer API (Issue #132).

Stellt die aktuellen Backend-Logs schreibgeschützt zur Verfügung — sowohl als
einmaliger Tail (`GET /api/logs`) als auch als SSE-Stream
(`GET /api/logs/stream`). Auth läuft über den Standard-Blueprint-Guard
(``AGORA_AUTH_TOKEN``); ein Path-Traversal ist ausgeschlossen, weil das
Composable hardcodet die heutige Logdatei aus ``LOG_DIR`` wählt und keinen
``?file=``-Parameter akzeptiert.

Begründung: Die Backend-Logs liegen heute datiert (``YYYY-MM-DD.log``) in
``backend/logs/`` und werden vom RotatingFileHandler verwaltet. Die
``error.log``/``app.log`` aus dem ursprünglichen Issue-Wording sind im
aktuellen Repo nicht stabil belegt — wir orientieren uns am tatsächlichen
Logger-Setup statt an einem theoretischen Pfad.
"""

import json
import re
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from flask import Response, request, stream_with_context

from . import logs_bp
from ..utils.api_responses import handle_api_errors, json_success
from ..utils.logger import LOG_DIR, get_logger

logger = get_logger('agora.api.logs')

# Default- und Hard-Caps. Issue-Akzeptanz: Default 200, max 2000.
_DEFAULT_TAIL = 200
_MAX_TAIL = 2000

# Heuristisches Pattern, mit dem ``level=…`` clientseitig vorab gefiltert wird.
# Logger-Format ``%(asctime)s - %(name)s - %(levelname)s - %(message)s`` macht
# den Levelname mit Bindestrich-Padding gut greifbar.
_LEVEL_PATTERNS = {
    'error': re.compile(r'\b(ERROR|CRITICAL|FATAL|Traceback|Exception)\b', re.IGNORECASE),
    'warn': re.compile(r'\b(WARNING|WARN)\b', re.IGNORECASE),
    'info': re.compile(r'\bINFO\b'),
    'debug': re.compile(r'\bDEBUG\b'),
}

# SSE-Heartbeat-Intervall — verhindert idle-Disconnects hinter Reverse-Proxies.
_STREAM_HEARTBEAT_SEC = 15.0
_STREAM_POLL_SEC = 0.5

# Reconnect-Intervall in ms, das dem Browser via 'retry:'-Frame mitgeteilt
# wird. Ohne dieses Feld nutzt der Browser seinen internen Default (~3 s,
# nicht vom Backend steuerbar).
# TODO: über settings_layer konfigurierbar machen sobald Sub-Slice D durch ist.
_SSE_RETRY_MS = 5000


def _resolve_log_path() -> Path | None:
    """Liefert den absoluten Pfad zur heutigen Logdatei oder ``None``,
    wenn das Verzeichnis fehlt bzw. noch nichts geschrieben wurde.

    Path-Traversal-Schutz: Wir konstruieren den Pfad ausschließlich aus
    ``LOG_DIR`` und einem hardcoded Datumsmuster — kein Param-Input.
    """
    log_dir = Path(LOG_DIR).resolve()
    if not log_dir.is_dir():
        return None
    today_name = datetime.now().strftime('%Y-%m-%d') + '.log'
    candidate = (log_dir / today_name).resolve()
    # Defense-in-depth: candidate muss in LOG_DIR liegen.
    try:
        candidate.relative_to(log_dir)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


def _parse_tail_arg() -> int:
    raw = request.args.get('tail')
    if raw is None:
        return _DEFAULT_TAIL
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_TAIL
    if n <= 0:
        return _DEFAULT_TAIL
    return min(n, _MAX_TAIL)


def _parse_offset_arg() -> int | None:
    """Liest ``?offset=…`` aus der Query und gibt einen non-negativen
    Integer zurück oder ``None``, wenn der Param fehlt bzw. invalide ist.
    """
    raw = request.args.get('offset')
    if raw is None:
        return None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def _filter_lines(lines: list[str], level: str | None) -> list[str]:
    if not level:
        return lines
    pat = _LEVEL_PATTERNS.get(level.lower())
    if not pat:
        return lines
    return [ln for ln in lines if pat.search(ln)]


def _read_tail(path: Path, n: int) -> tuple[list[str], int]:
    """Liefert die letzten ``n`` Zeilen plus den Datei-Offset (in Bytes) am Ende.

    Wir lesen die ganze Datei einmal — bei einer 50 MB-Logdatei wäre das
    teuer, aber unser Rotation-Limit liegt deutlich darunter (10 MB / 5
    Backups, siehe `RotatingFileHandler`-Config). Für die Akzeptanz reicht
    das, ohne `seek`-Akrobatik.

    Newlines werden gestrippt: der Stream-Endpunkt nutzt
    ``str.splitlines()`` und liefert daher Lines ohne Trailing-``\\n``;
    konsistente Form verhindert doppelte Leerzeilen im Frontend
    (``white-space: pre-wrap`` plus ``<div>``-pro-Zeile).

    Der Datei-Offset wird via ``path.stat().st_size`` ermittelt, weil
    ``fh.tell()`` nach einer Iteration über das Text-File-Objekt durch
    Pythons internes Buffering nicht zuverlässig ist.
    """
    try:
        with path.open('r', encoding='utf-8', errors='replace') as fh:
            buf = deque((ln.rstrip('\r\n') for ln in fh), maxlen=n)
        return list(buf), path.stat().st_size
    except FileNotFoundError:
        return [], 0


@logs_bp.route('', methods=['GET'])
@logs_bp.route('/', methods=['GET'])
@handle_api_errors
def get_logs():
    """Tail der aktuellen Backend-Logdatei. Default 200 Zeilen, max 2000.

    Query-Parameter:
      - ``tail`` (int, optional): wie viele Zeilen zurückgegeben werden.
      - ``level`` (str, optional): clientseitiger Vorfilter (``error``/
        ``warn``/``info``/``debug``).
    """
    path = _resolve_log_path()
    n = _parse_tail_arg()
    level = request.args.get('level')
    if path is None:
        return json_success({'lines': [], 'offset': 0, 'file': None})
    lines, offset = _read_tail(path, n)
    filtered = _filter_lines(lines, level)
    return json_success({
        'lines': filtered,
        'offset': offset,
        'file': path.name,
        'total_returned': len(filtered),
    })


@logs_bp.route('/stream', methods=['GET'])
def stream_logs():
    """SSE-Stream auf neue Zeilen ab dem aktuellen Datei-Offset.

    Auth-Sonderregel: Der Standard-Blueprint-Guard prüft den Header bzw.
    den ``?token=`` Param schon vor dieser View. Da Browsers bei
    ``EventSource`` keine Custom-Header setzen können, wird der Token via
    ``?token=`` mitgegeben (analog zu :mod:`api.simulation_stream`).
    """
    path = _resolve_log_path()
    level = request.args.get('level')
    requested_offset = _parse_offset_arg()
    # Level-Pattern einmal pro Stream-Lebenszeit auflösen — die Iteration
    # über jede neue Zeile darf nicht jedes Mal das Dictionary neu treffen.
    level_pat = _LEVEL_PATTERNS.get(level.lower()) if level else None

    @stream_with_context
    def gen():
        # retry-Frame zuerst: teilt dem Browser mit, nach wie vielen ms er bei
        # einem Verbindungsabbruch neu verbinden soll (SSE-Spec, RFC 8895 §9.2).
        yield f'retry: {_SSE_RETRY_MS}\n\n'
        # FOLLOWUP J.5.1 (Issue #233): Browser-Reconnect nutzt dieselbe URL
        # ohne aktualisierten ?offset= — bei Reconnect droht entweder Datenverlust
        # (kein Offset → file_size) oder Duplikate (statischer Offset). Sauber via
        # ``id: <offset>``-Frames + Last-Event-ID-Header-Auswertung. Out-of-Scope
        # für Sub-Slice J.5 (das nur retry: setzt + LogDrawer.onerror fixt).
        # Default: am Datei-Ende ansetzen, alte Lines holt der Tail-Endpunkt.
        # Wenn der Client einen ``?offset=…`` aus dem Tail-Response durchreicht,
        # starten wir genau dort — sonst gehen Logs verloren, die zwischen
        # Tail-Antwort und Stream-Verbindung geschrieben wurden.
        offset = 0
        if path is not None:
            try:
                file_size = path.stat().st_size
            except OSError:
                file_size = 0
            if requested_offset is not None and requested_offset <= file_size:
                offset = requested_offset
            else:
                offset = file_size
        last_heartbeat = time.monotonic()
        while True:
            now = time.monotonic()
            current_path = _resolve_log_path()
            if current_path is None:
                # Noch keine Logdatei geschrieben — Heartbeat schicken.
                if now - last_heartbeat >= _STREAM_HEARTBEAT_SEC:
                    yield ': heartbeat\n\n'
                    last_heartbeat = now
                time.sleep(_STREAM_POLL_SEC)
                continue
            try:
                size = current_path.stat().st_size
            except OSError:
                time.sleep(_STREAM_POLL_SEC)
                continue
            if size < offset:
                # Logfile wurde rotiert oder gekürzt; wieder von vorn.
                offset = 0
            if size > offset:
                try:
                    with current_path.open('r', encoding='utf-8', errors='replace') as fh:
                        fh.seek(offset)
                        chunk = fh.read()
                        offset = fh.tell()
                except OSError:
                    chunk = ''
                for line in chunk.splitlines():
                    if level_pat is not None and not level_pat.search(line):
                        continue
                    payload = json.dumps({
                        'line': line,
                        'ts': datetime.now(timezone.utc).isoformat(),
                    })
                    yield f'data: {payload}\n\n'
                last_heartbeat = now
            else:
                if now - last_heartbeat >= _STREAM_HEARTBEAT_SEC:
                    yield ': heartbeat\n\n'
                    last_heartbeat = now
                time.sleep(_STREAM_POLL_SEC)

    headers = {
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',  # Nginx soll nicht puffern.
    }
    return Response(gen(), mimetype='text/event-stream', headers=headers)
