# Issue #17 — RPC/Interview-IPC auf Redis Pub/Sub migrieren

> Stand: 2026-04-25. Ergänzung zu `docu/refactoring-backlog-priorisiert.md`.
> Nicht gelöst: Vollmigration ist Mehrkomponenten-Arbeit + braucht Live-Test gegen den Docker-Stack.

## Heute (Phase B)

- `RedisEventBus.publish` / `subscribe` für `CHANNEL_CONTROL` und `CHANNEL_STATE` läuft über Redis Pub/Sub; Backend-zu-UI-Pfad ist live.
- `RedisEventBus.request_response` und `publish/subscribe` für `CHANNEL_RPC_COMMAND` / `rpc.response.*` delegieren bewusst an `FilePollingEventBus`. Grund: die OASIS-Subprocess-Scripts (`backend/scripts/run_{reddit,twitter,parallel}_simulation.py`) haben einen eigenen `IPCHandler`, der `commands_dir` per `os.listdir` pollt und Antworten als File-Drops zurückschreibt. Backend-Side Migration allein würde das Backend-↔-Subprocess-Protokoll brechen.

## Was Phase D (Issue #17) tatsächlich anpassen muss

### Subprocess (`backend/scripts/run_*_simulation.py` × 3)

Der `IPCHandler` muss optional (`if REDIS_URL set`) zusätzlich zur File-Polling einen Redis-Pub/Sub-Listener öffnen. Komplikation: Der Subprocess läuft `asyncio` (OASIS), Redis-py `pubsub` ist sync. Optionen:

- **redis-py 5.x async client** — `redis.asyncio.Redis.pubsub()` läuft im selben Event-Loop. Bevorzugt.
- **Threading-Bridge** — sync Redis in Worker-Thread, Queue zur Async-Loop. Mehr Code, aber kompatibel mit aktuellem CAMEL/OASIS-Stack falls deren Async-Version stört.

Antwort-Pfad: Das Subprocess schreibt die Response-File (Backward-Compat) **und** publiziert sie auf `agora:sim:<id>:rpc.response.<cid>`. Doppelschreiben, bis File-Polling deprecated wird.

### Backend (`RedisEventBus`)

- `publish(CHANNEL_RPC_COMMAND, …)` → echte Redis-Pub/Sub statt `_file_bus.publish` (aber File parallel schreiben, solange Subprocesse alte Versionen sind, damit Rolling-Upgrade möglich ist).
- `subscribe(rpc_response_channel(cid), …)` → Redis-Pub/Sub konsumieren mit File-Fallback (timeout-basiert: erst Redis, bei Timeout File prüfen).
- `request_response` orchestriert beides.

### Tests

- `test_event_bus_redis.py` braucht zwei neue Szenarien:
  1. Real-Redis Round-Trip (Backend published, Mock-Subprocess subscribed via Redis, antwortet via Redis).
  2. Hybrid: Backend published Redis+File, Subprocess antwortet nur File (Legacy-Case) — Backend muss File noch sehen.
- Stop-Test: Backend published, Subprocess antwortet auf Redis und File — Backend nimmt das erstkommende, ignoriert das andere.

### Quality-Gate

- Live gegen `docker compose up -d redis` plus voll laufende Simulation. Ohne diesen End-to-End-Test ist die Migration nicht freigabefähig.
- Smoke-Test-Skript: `interview_agent` Round-Trip mit eingeschaltetem Redis vs. ausgeschaltetem Redis. Beide Modi müssen identische Latenzen liefern (Polling-Intervall gleich).

## Migrations-Sequenz

1. **Test-Hülle erweitern** (test_event_bus_redis): Erwartete Hybrid-Pfade als Spec festschreiben. Tests laufen rot.
2. **Subprocess-Listener (additiv)** in einem Script (z. B. `run_reddit_simulation.py` zuerst). Redis-async-pubsub im Event-Loop. File-Polling bleibt parallel aktiv.
3. **Backend-Side Redis-Pfad** (`RedisEventBus.request_response` + `publish`/`subscribe` für RPC-Channels). File bleibt als Fallback.
4. **Smoke-Test** mit `docker compose up redis agora` + komplettem Run-Through Graph→Simulation→Report→Interview.
5. **Cutover**: Wenn Smoke-Test grün, andere zwei Subprocess-Scripts nachziehen.
6. **File-Pfad deprecaten** in einem Folge-Issue, sobald Telemetrie zeigt dass alle Live-Setups Redis nutzen.

## Backout-Plan

Wenn Phase D nach Cutover fehlschlägt: `Config.EVENT_BUS_BACKEND=file` setzen → Container baut `FilePollingEventBus`, der Subprocess-Listener detektiert keinen Redis und bleibt File-only. Kein Code-Revert nötig.

## Aufwand-Schätzung

- Subprocess-Scripts × 3: 1 Tag (gemeinsamer Helper-Modul + Apply auf alle drei).
- Backend `RedisEventBus`: 0.5 Tag.
- Tests + Smoke-Test: 0.5–1 Tag.
- Live-Verifikation + Bug-Fixes: 0.5–1 Tag.

**Gesamt: 2–3 Tage.** Empfehlung: zusammen mit User in einer Session mit laufender `docker compose`-Umgebung machen.
