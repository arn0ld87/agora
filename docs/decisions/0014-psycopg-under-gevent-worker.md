# ADR-0014: psycopg 3 unter dem gunicorn-gevent-Worker

- Status: akzeptiert
- Datum: 2026-09-18
- Bezug: [`docs/plans/supabase.md`](../plans/supabase.md) §8 (PostgreSQL-Grundlage),
  Importreihenfolge aus [#529](https://github.com/arn0ld87/agora/issues/529)
- Beantwortet die in [`docs/STATUS.md`](../STATUS.md) offen geführte Frage aus PR 3

## Kontext

Der Migrationsplan führt die Metadaten-Stores schrittweise auf PostgreSQL. Der
Webprozess läuft dabei unverändert unter genau einem gunicorn-Worker mit
`worker_class = "gevent"` ([`backend/gunicorn.conf.py`](../../backend/gunicorn.conf.py)) —
gewählt, damit die SSE-Streams nicht blockieren. Treiber ist psycopg 3
(`psycopg[binary]>=3.2.0`, SQLAlchemy-Dialekt `postgresql+psycopg`).

Daraus entstand eine Frage, die vor dem ersten produktiven Store auf PostgreSQL
beantwortet sein musste: psycopg 3 ist async-first entworfen, der synchrone
Pfad wartet aber selbst auf den Socket. Wartet er in C, sieht der gevent-Hub
davon nichts. Eine einzige langsame Abfrage würde dann den gesamten Prozess
anhalten — mit `--workers 1` heißt das: die ganze Instanz, einschließlich der
Streams, für die der gevent-Worker überhaupt existiert. Ein solcher Treiber
serialisiert still; er wirft keinen Fehler, er wird nur langsam.

## Befund

Gemessen am 2026-09-18 gegen PostgreSQL 17, mit psycopg 3.3.5, gevent 26.4.0
und SQLAlchemy 2.0.54. Messprinzip: acht Greenlets führen gleichzeitig
`SELECT pg_sleep(1)` aus. Kooperiert der Treiber, dauert das ungefähr eine
Sekunde; blockiert er, acht.

| Aufbau | Gemessen |
|---|---|
| psycopg direkt, nach `patch_all()` | 1,08 s |
| über `build_engine()` (SQLAlchemy-Pool) | 1,04 s |
| Gegenprobe ohne `patch_all()` | 8,19 s |

Die Gegenprobe ist der Teil, der die Messung tragfähig macht: ohne Patch
serialisiert derselbe Code sichtbar. Die beiden Fälle liegen um eine
Größenordnung auseinander, nicht im Messrauschen.

Bei gepatchtem `select` wählt psycopg die Wartefunktion `wait_poll` auf
Python-Ebene statt der C-Implementierung aus dem Binärpaket. Genau das ist der
Mechanismus, den psycopg ab 3.1.14 als gevent-Unterstützung dokumentiert;
`psycogreen`, das psycopg2 dafür brauchte, entfällt.

## Entscheidung

1. **psycopg 3 bleibt der Treiber.** Kein `psycogreen`, kein Rückbau auf
   psycopg2, kein Umbau des Webprozesses auf asyncio.
2. **Die Importreihenfolge ist die Bedingung, unter der das gilt.**
   `gevent.monkey.patch_all()` muss vor dem ersten psycopg-Import laufen.
   Das ist bereits erzwungen und nicht neu: [`backend/wsgi.py`](../../backend/wsgi.py)
   patcht als allererstes Statement, das `Dockerfile` startet `wsgi:app`. Dieselbe
   Reihenfolge schützt seit #529 `requests`/`ssl`; PostgreSQL hängt sich hier an
   eine bestehende Garantie an, statt eine zweite einzuführen.
3. **Der Mindest-Pin bleibt `>=3.2.0`** und damit über der dokumentierten
   Grenze 3.1.14.
4. **Der Nachweis wird als Integrationstest gehalten**, nicht als Notiz:
   `backend/tests/integration/test_gevent_psycopg_cooperation.py`.

## Konsequenzen

- Die Frage blockiert Phase 4 und die folgenden Repository-Umstellungen nicht
  mehr. Am Betriebsmodell — ein Worker, gevent, `--preload` — ändert sich nichts.
- Bei falscher Importreihenfolge serialisiert psycopg nicht still, sondern
  scheitert beim Verbindungsaufbau: es bindet die Wartefunktion an einen
  Selektor, den das gepatchte `select`-Modul nicht mehr hat. Gemessen wurde das
  auf macOS (`select.kqueue` fehlt). Die Fehlerklasse ist plattformabhängig,
  der laute Abbruch ist es nicht — trotzdem hält der Test die Reihenfolge fest,
  statt sich auf diesen Nebeneffekt zu verlassen.
- **Nicht geprüft und weiterhin offen:** das Verhalten hinter Supavisor unter
  Last und das Zusammenspiel von SQLAlchemy-Pool und gevent bei mehr als einem
  Worker. Der HARDSTOP `--workers 1` bleibt aus den in `gunicorn.conf.py`
  genannten Gründen bestehen; diese Entscheidung verschiebt ihn nicht.
