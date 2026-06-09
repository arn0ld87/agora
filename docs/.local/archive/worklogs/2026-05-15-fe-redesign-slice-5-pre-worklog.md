# Worklog: FE-Redesign Slice 5-pre — Backend PostCreatedEvent + OASIS-Emit

**Datum:** 2026-05-15
**Branch:** feat/fe-redesign-5-pre-post-event
**Worktree:** /private/tmp/agora-fe-redesign-5-pre

---

## Was die Pipeline jetzt kann

PostCreatedEvent geht von OASIS-Action → Redis → SSE → Frontend-Zod-Schema durch:

1. Nach jedem `CREATE_POST`-Action in `run_parallel_simulation.py` (Twitter + Reddit) wird `_emit_post_created_to_redis()` aufgerufen.
2. Die Funktion publisht einen `PostCreatedEvent`-Payload auf `agora:sim:{simulation_id}:post_created`.
3. `simulation_stream.py` subscribed auf diesen Channel (dritter Drainer-Thread) und emittiert `event: post_created`-SSE-Frames.
4. `stream.ts` parst den Frame via `PostCreatedEventSchema.safeParse()`, unwrappt den SimulationEvent-Envelope.
5. `useEventStream.ts` reicht den Handler durch; `lastEventAt`/`error`-Bookkeeping durch `wrap()`.

---

## Test-Delta

**Backend:**
- `backend/tests/contracts/test_post_event_contract.py` — neu, 12 Tests
- `backend/tests/services/test_event_bus_post_created.py` — neu, 4 Tests
- `backend/tests/api/test_simulation_stream_post_event.py` — neu, 2 Tests
- Gesamt neu: +18 Tests

**Frontend:**
- `frontend/src/contracts/__tests__/postEventContract.spec.ts` — neu, 12 Tests
- Gesamt neu: +12 Tests (819 Total, alle grün)

---

## Schema-Drift-Check

`git diff --exit-code schemas/` → EXIT 0 (clean)

Neue Datei: `schemas/post-created-event.schema.json` — committed in Task 2.

---

## Subprocess-Bridge-Pfad

**Pfad: A (direkt, asyncio-inline)**

Der OASIS-Subprozess läuft in einem asyncio-Loop. `_emit_post_created_to_redis()` ist
eine `async def` die innerhalb dieses Loops direkt `redis.asyncio` nutzt — kein
gevent-Boundary, kein Bridge-Marshal. Client wird pro-Call geöffnet/geschlossen
(non-fatal bei Ausfall, Simulation läuft weiter).

`subprocess_redis_bridge.py` erhält zusätzlich `publish_post_event()` für den Fall,
dass die Bridge bereits aktiv ist und der Caller es bevorzugt (nicht verwendet im
aktuellen Sim-Loop, offen für Optimierung).

Begründung: Der Plan nannte Pfad B (via Bridge), aber die Bridge wird erst nach dem
Simulations-Loop im `wait_for_commands`-Block aufgebaut — also ist sie für den Emit
im Sim-Loop nicht verfügbar. Pfad A ist korrekt und sicher.

---

## Tool-Pflicht-Skips

- `code-review-graph::get_minimal_context_tool` — Tool nicht verfügbar (MCP-Error). Fallback auf `rg`/`Read`.
- `mcp__MCP_DOCKER__sequentialthinking` — Tool nicht verfügbar (MCP-Error). Inline-Analyse dokumentiert.
- `context-mode` — Tool nicht verfügbar (MCP-Error). Direkte `Read`/`Bash`-Calls genutzt.

---

## Offene Punkte / Followups

1. **voice_register-Lücken:** `_emit_post_created_to_redis()` fällt auf `"casual"` zurück wenn `voice_register` in `action_args` fehlt. Wenn oasis_profile_generator das Feld nicht befüllt, kommt immer `"casual"`. Followup: oasis_profile_generator.py auf voice_register-Pflichtfeld prüfen (Sub-Slice 10 claim).
2. **post_id-Lücken:** Wenn OASIS-DB kein `post_id`-Feld in `action_args` zurückgibt (Twitter nutzt `new_post_id`, Reddit nutzt `post_id`), wird das Emit übersprungen. Smoke-Test mit echter Sim nötig.
3. **Bridge-Optimierung:** `publish_post_event()` in `RedisIPCBridge` könnte genutzt werden wenn Bridge aktiv ist — spart pro-Call-Connect-Overhead bei hohen Post-Frequenzen. Slice 5-post-opt offen.
4. **Mastodon/Threads:** Bewusst out-of-scope. ADR-Hint im Contract-Kommentar. Enum-Erweiterung braucht Slice + Schema-Migration.
5. **SSE-Replay:** Bus puffert keine vergangenen Events. Reconnect startet best-effort ab now. Volle Replay-Semantik braucht Persistenz (eigener Slice, im Kommentar in simulation_stream.py erwähnt).

---

## Verification-Gate-Ergebnis

```
Backend:
  pytest -x -q → 2281 passed, 9 skipped (davon 2 Redis-Skip, 7 Docker-Skip)
  ruff check app/ tests/ → All checks passed!
  mypy app → Success: no issues found in 173 source files

Schema-Drift:
  git diff --exit-code schemas/ → EXIT 0

Frontend:
  bun run typecheck → exit 0 (vue-tsc --noEmit clean)
  bun run test -- --run → 819 passed (103 test files)
  bun run build → exit 0 (535ms)
  bun run lint → exit 0 (eslint clean)
```
