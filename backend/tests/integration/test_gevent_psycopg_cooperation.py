"""Nachweis, dass psycopg 3 unter gevent den Hub nicht blockiert.

Hintergrund: der Webprozess laeuft unter genau einem gunicorn-Worker mit
``worker_class = "gevent"`` (``backend/gunicorn.conf.py``). Blockierte ein
Datenbankaufruf den Hub, wuerde eine einzige langsame Abfrage den gesamten
Prozess anhalten — einschliesslich der SSE-Streams, fuer die der gevent-Worker
ueberhaupt gewaehlt wurde. Vor dem ersten produktiven Store auf PostgreSQL
muss deshalb belegt sein, dass psycopg kooperiert und nicht serialisiert.

Der Test laeuft in einem SUBPROZESS, weil ``gevent.monkey.patch_all()``
prozessweit wirkt und den restlichen pytest-Lauf veraendern wuerde.

Messprinzip: ``N`` Greenlets fuehren gleichzeitig ``SELECT pg_sleep(S)`` aus.
Kooperiert der Treiber, dauert das ungefaehr ``S``; blockiert er, ``N * S``.
Die Schwelle liegt bewusst bei der Haelfte der seriellen Zeit — sie trennt
die beiden Faelle um Groessenordnungen und nicht um Messrauschen.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

pytestmark = pytest.mark.integration

GREENLETS = 8
SLEEP_SECONDS = 1.0

# Laeuft im Subprozess. ``patch_all()`` steht vor jedem psycopg-Import, genau
# wie in ``backend/wsgi.py`` — diese Reihenfolge ist Teil dessen, was hier
# geprueft wird (siehe Dockerfile CMD: ``wsgi:app``, Issue #529).
_PROBE = '''
import gevent.monkey
gevent.monkey.patch_all()

import json
import sys
import time

import gevent
import psycopg
import psycopg.waiting

url, greenlets, sleep_seconds = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])


def worker():
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute("SELECT pg_sleep(%s), pg_backend_pid()", (sleep_seconds,))
        return cur.fetchone()[1]


start = time.monotonic()
jobs = [gevent.spawn(worker) for _ in range(greenlets)]
gevent.joinall(jobs, raise_error=True)
elapsed = time.monotonic() - start

print(json.dumps({
    "elapsed": elapsed,
    "backend_pids": sorted({job.value for job in jobs}),
    "wait_impl": psycopg.waiting.wait.__name__,
    "select_patched": gevent.monkey.is_module_patched("select"),
}))
'''


def test_psycopg_does_not_block_the_gevent_hub(postgres_database_url):
    raw_url = postgres_database_url.replace(
        'postgresql+psycopg://', 'postgresql://'
    )
    completed = subprocess.run(
        [
            sys.executable,
            '-c',
            _PROBE,
            raw_url,
            str(GREENLETS),
            str(SLEEP_SECONDS),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr

    result = json.loads(completed.stdout.strip().splitlines()[-1])
    serial_seconds = GREENLETS * SLEEP_SECONDS

    assert result['select_patched'] is True
    # Jede Abfrage hat einen eigenen Backend-Prozess gesehen: die Greenlets
    # liefen wirklich gleichzeitig und nicht nacheinander auf einer Verbindung.
    assert len(result['backend_pids']) == GREENLETS
    assert result['elapsed'] < serial_seconds / 2, (
        f"psycopg serialisiert unter gevent: {result['elapsed']:.2f}s fuer "
        f'{GREENLETS} gleichzeitige Abfragen von je {SLEEP_SECONDS}s '
        f"(Wartefunktion: {result['wait_impl']}). Ein blockierender Treiber "
        'haelt unter einem gunicorn-gevent-Worker den ganzen Prozess an.'
    )
