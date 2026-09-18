Die vor PR 4 offen geführte Frage, ob psycopg 3 unter dem gunicorn-gevent-Worker
den Hub blockiert, ist beantwortet: der Treiber kooperiert, sobald
`gevent.monkey.patch_all()` vor dem ersten psycopg-Import gelaufen ist — was
`backend/wsgi.py` bereits sicherstellt. Acht gleichzeitige Abfragen von je einer
Sekunde brauchen 1,08 s statt 8. Der Nachweis liegt als Integrationstest vor
(`backend/tests/integration/test_gevent_psycopg_cooperation.py`), die
Entscheidung samt ihrer Grenzen in ADR-0014.
