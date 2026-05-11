# Sub-Slice 19 — Gunicorn-Timeout für LLM-Streaming-Calls

**Datum:** 2026-05-03
**Branch:** `feat/task-18-prod-bootfix` (Folge auf Sub-Slice 18)
**Layer:** Deployment
**Refs:** Folge zu Sub-Slice 18 ([`docs/2026-05-03-task-18-prod-bootfix-arbeitsprotokoll.md`](2026-05-03-task-18-prod-bootfix-arbeitsprotokoll.md)).

## Symptom

Nach Sub-Slice 18 startet der Prod-Stack sauber, aber jeder
LLM-Streaming-Call kollabiert nach exakt 30 s mit:

```
[CRITICAL] WORKER TIMEOUT (pid:73)
Error handling request POST /api/graph/ontology/generate
File "/app/backend/app/utils/llm_client.py", line 177, in chat
    for event in stream:
File "httpcore/_sync/http11.py", line 217, in _receive_event
    data = self._network_stream.read(...)
File "gunicorn/workers/base.py", line 198, in handle_abort
    sys.exit(1)
SystemExit: 1
```

Worker exited, neuer Worker bootet, Init-Sequenz läuft erneut durch
(`Embedding configuration validated`, `Neo4jStorage initialized`,
`SimulationEventBus … connected`, `Agora Backend startup complete`).

## Root Cause

Gunicorns sync-Worker-Default-Timeout ist **30 s**. Im Dockerfile-CMD
aus Sub-Slice 18 war kein `--timeout` explizit gesetzt. Praktisch jeder
LLM-Call gegen Ollama/Cloud-Provider mit 15 k+ Tokens Input überschreitet
das. `llm_client.chat()` blockiert während `for event in stream:` im
`httpcore`-`recv()` — Worker tut nichts „falsch", er wartet legitim auf
Stream-Chunks, aber gunicorn-Master schlägt zu.

## Fix

[`Dockerfile`](Dockerfile) prod-Stage CMD um zwei Flags erweitert:

```dockerfile
CMD ["/app/backend/.venv/bin/gunicorn", \
     "--workers", "2", \
     "--timeout", "600", \
     "--graceful-timeout", "30", \
     "--bind", "0.0.0.0:5001", \
     "--chdir", "/app/backend", \
     "--pid", "/home/agora/.gunicorn/gunicorn.pid", \
     "app:create_app()"]
```

- `--timeout 600`: 10 min Worker-Timeout, deckt Ontology-Generation,
  Report-Agent, Persona-Generation, Long-Running-LLM-Calls ab.
- `--graceful-timeout 30`: bei SIGTERM (Compose-Restart) bekommen
  laufende Worker 30 s zum sauberen Beenden, danach SIGKILL.

## Verifikation

```
$ docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build agora
 Container agora Started

$ docker exec agora ps -ef | grep gunicorn
agora  1  0  /app/backend/.venv/bin/python3 /app/backend/.venv/bin/gunicorn
       --workers 2 --timeout 600 --graceful-timeout 30
       --bind 0.0.0.0:5001 --chdir /app/backend
       --pid /home/agora/.gunicorn/gunicorn.pid app:create_app()
agora  7  1  ... (Worker)
agora  8  1  ... (Worker)

$ docker exec agora curl -fsS http://localhost:5001/health
{"service":"Agora Backend","status":"ok"}
```

End-to-End-Verifikation `POST /api/graph/ontology/generate` ist
nutzerseitig — Backend killt den Stream nicht mehr nach 30 s.

## Out of Scope (Folge-Slice 20)

**Echte Lösung: gevent-Worker.** Der Original-Plan
[`docs/2026-04-29-prod-slice2-gunicorn.md`](2026-04-29-prod-slice2-gunicorn.md)
sah `-k gevent --workers 1 --worker-connections 100` vor — Streams sind
non-blocking, ein Worker kann viele parallele LLM-Calls multiplexen.
Caveats aus dem damaligen Plan, in Slice 20 zu verifizieren:

- gevent-monkey-patching auf stdlib-Sockets — `SimulationRunner` startet
  OASIS bewusst als getrennter `subprocess.Popen`, also gevent-frei,
  muss nochmal verifiziert werden.
- Neo4j-Driver + httpx + Redis-Client gevent-kompatibel? httpx ja,
  redis-py ja, neo4j-Bolt-Driver mit eigenem Pool — Smoke nötig.
- gevent-Cython-Wheels vs. read-only rootfs (Plan-Slice 3/4-Thema, sollte
  passen).

Bis dahin: 600 s Timeout ist ein praktikabler Kompromiss, kein Kill mehr
mitten im Stream, max 2 parallele Calls (was für lokale Single-User-Loads
reicht).

## Geänderte Dateien

- `Dockerfile` — `--timeout 600 --graceful-timeout 30` im prod-Stage CMD
- `CHANGELOG.md` — `[Unreleased]` / Fixed-Block
- `docs/2026-05-03-task-19-gunicorn-timeout-arbeitsprotokoll.md` (neu)
