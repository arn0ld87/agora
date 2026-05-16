# 2026-05-04 · Slice E (#213) Verify-and-Close — Active-Model-Badge

## Ziel

Verifizieren, dass Issue #213 („Slice E · Live-Anzeige des aktiven LLM-Modells im Frontend-Header") **vollständig im Code** umgesetzt ist, und den Issue per `Closes #213` schließen.

## Befund

Audit durch `agora-evidence-auditor` (read-only). Alle 8 Akzeptanzpunkte erfüllt, kein Code-Change nötig. Tabelle:

| # | Akzeptanzpunkt | Beleg | Status |
|---|---|---|---|
| 1 | llm_client.chat() publiziert model.active-Event vor Modell-Call | backend/app/utils/llm_client.py:195 (Aufruf), :135–170 (_publish_model_active) | ✅ |
| 2 | SSE-Channel mit Auth via Signed Ticket | backend/app/api/llm.py:53 (@allow_ticket_auth(... single_use=False)), auth.py:71–87 + :109 (signed_ticket.verify()) — kein ?token=-Fallback | ✅ |
| 3 | Pinia-Store useActiveModelStore | frontend/src/store/useActiveModelStore.ts:51 | ✅ |
| 4 | ActiveModelBadge.vue im Header | frontend/src/components/ActiveModelBadge.vue + frontend/src/layouts/WorkspaceHeader.vue:3,15 | ✅ |
| 5 | Modell + Kontext-Icon, Idle-Fallback nach STALE_AFTER_MS | Store: STALE_AFTER_MS = 30_000 (:23), isStale (:61–64); Badge: v-else-if=
| 8a | Backend-Tests (Event-Schema, Bus, Publish) | `tests/services/test_model_event_bus.py` (16 Tests), `tests/utils/test_llm_client_publishes_model_active.py` (10 Tests) — 26 grün | ✅ |
| 8b | Vitest (Store-Wechsel, Idle, Badge-Render) | `frontend/src/store/__tests__/useActiveModelStore.spec.ts` (4), `frontend/src/components/__tests__/ActiveModelBadge.spec.ts` (3) — 7 grün | ✅ |

## Test-Belege

```
backend:  pytest tests/services/test_model_event_bus.py tests/utils/test_llm_client_publishes_model_active.py tests/api/test_llm_model_stream.py
          → 26 passed

frontend: npm test -- --run -- src/store/__tests__/useActiveModelStore.spec.ts src/components/__tests__/ActiveModelBadge.spec.ts
          → 7 passed (2 test files)
```

## Wo ist die Implementation entstanden?

Der Slice wurde inkrementell über mehrere Vorgänger-Commits aufgebaut (Backend ModelEventBus + LLM-Publish + SSE-Endpoint + Frontend-Store + Badge-Component + i18n + Header-Wiring). Issue #213 ist damit Doku-/Tracking-Schuld, kein Implementation-Backlog.

## Risiken / Folge-Slices

- **Keine Hardening-Lücken** im Audit gefunden. SSE-Endpoint nutzt Signed-Ticket-Auth (kein Bundle-Token, kein `?token=`-Fallback in Prod).
- **Persona-Latenz** (#217) bleibt eigenständig offen, ist nicht blockiert durch #213.
- **Settings-UI** für Modell-Wechsel (#212) bleibt eigenständig — der Badge zeigt nur an, was der Server tatsächlich nutzt; Modell-Wechsel ist UX-Feature.

## Folgemaßnahme

Reiner Doku-Commit mit `Closes #213`, ein-Zeiler im CHANGELOG `[Unreleased]` `### Documentation`-Block.
