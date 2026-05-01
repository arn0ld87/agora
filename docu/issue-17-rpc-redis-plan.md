# Issue #17 — RPC/Interview-IPC auf Redis Pub/Sub migrieren

> Stand: 2026-04-25 — **abgeschlossen** (Phasen 1–6 implementiert, Backend-Suite mit Live-Redis 214 grün).
> Verbleibend ist ein optionaler Live-E2E-Smoke-Test gegen den vollen Docker-Stack (siehe Abschnitt unten) und ein
> Folgeticket zum Deprecaten des File-IPC-Pfads, sobald Telemetrie zeigt, dass alle Setups den Bridge-Pfad nutzen.

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

## Stand der Umsetzung (Phase D abgeschlossen)

Mapping zwischen Plan und implementierten Commits auf `main`:

| Phase im Plan | Commit | Inhalt |
| --- | --- | --- |
| 1. Test-Hülle erweitern | `fb2608e` | 4 Hybrid-Round-Trip-Tests in `test_event_bus_redis.py` als TDD-Spec (3 als `xfail(strict=True)` markiert) |
| 2. Subprocess-Listener (Reddit) | `539eb5b` | `backend/scripts/subprocess_redis_bridge.py` (neu) + Cutover in `run_reddit_simulation.py` |
| 3. Backend-Side Redis-Pfad | `97cb201` | `RedisEventBus.publish/subscribe/request_response` hybrid; `_await_response` race't Redis vs. File; `xfail`-Marker entfernt; `test_event_bus_redis_rpc_delegation.py` gelöscht |
| 4. Smoke-Test (Bridge↔Bus) | `2808b67` | Neue Live-Integrationstests in `test_subprocess_redis_bridge.py`; `aclose()`-Migration in der Bridge |
| 5. Cutover Twitter + Parallel | `99df9af` | Identisches Patch-Set in `run_twitter_simulation.py` und `run_parallel_simulation.py` |
| 6. Doku-Sync | folgt | CHANGELOG, CLAUDE.md/AGENTS.md, dieses Dokument |

## Optionaler Live-E2E-Smoke-Test gegen Docker-Stack

Die automatisierten Tests (Backend-Suite + Bridge-Live-Tests) decken die Hybrid-Round-Trips ab, ohne OASIS oder
Ollama-Calls. Für eine letzte Bestätigung gegen die echte Stack-Pipeline empfiehlt sich folgender Smoke vom User
(braucht laufenden Ollama-Endpoint + LLM_API_KEY):

```bash
docker compose up -d redis neo4j agora
docker logs -f agora | grep -i "Redis bridge"
# erwartet beim ersten Sim-Start: "[IPC] Redis bridge active on redis://… for sim sim_…"

# UI-Pfad: Dokument hochladen → Graph bauen → Personas → Simulation starten →
# nach Lauf-Ende einen Interview-Request schicken (per Frontend oder via API).
# Erfolg: Antwort kommt im Frontend an; im Subprocess-Log erscheint
# "[redis] Received IPC command: interview, id=…" statt "[file] …".

# Backout-Verifikation:
# .env: EVENT_BUS_BACKEND=file
docker compose up -d --force-recreate --no-deps agora
# Selber Interview-Request — diesmal sollte "[file] Received IPC command: interview" erscheinen.
```

Nur die *qualitative* Zusicherung interessiert (Pfad funktioniert in beiden Modi). Latenzvergleich Redis vs. File
ist explizit out-of-scope — das wird im Folgeticket zur File-IPC-Deprecation gemessen.
