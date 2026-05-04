# Slice E.2 — Active-Model-Badge Frontend

**Datum:** 2026-05-04
**Issue:** #213
**Branch:** feat/task-e2-active-model-badge
**Backend-Basis:** E.1 / PR #259 (d808c25 auf main)

## Ziel

Das aktive LLM-Modell in Echtzeit im `WorkspaceHeader` anzeigen. Backend liefert `ModelActiveEvent`-Frames via SSE (`GET /api/llm/model-stream`, Signed-Ticket-Auth). Frontend subscribed via Pinia-Store, parsed strikt mit Zod, rendert Badge mit Provider-Icon.

## Angefasste / neue Dateien

| Datei | Art | Beschreibung |
|---|---|---|
| `frontend/src/contracts/modelActiveContract.ts` | neu | Zod-Spiegel zu `ModelActiveEvent` (Pydantic v2, extra="forbid"). `.strict()`, Enum-Schemata für `context` und `provider`. |
| `frontend/src/store/useActiveModelStore.ts` | neu | Pinia `defineStore`. State: `lastEvent`, `isStale`, `connectionStatus`, `reconnectAttempts`. Actions: `connect`, `disconnect`, `reconnect`. Ticket-Fetch analog `fetchStreamTicket` in `api/stream.ts`, aber scope=`llm-stream` ohne sim-Suffix. |
| `frontend/src/components/ActiveModelBadge.vue` | neu | `<script setup lang="ts">`, alle Strings via `t('activeModel.*')`. Provider-Icons via vier kleine SVG-Komponenten. `aria-live="polite"`, `role="status"`. Mobile: `display:none` unter 720px. |
| `frontend/src/components/icons/OllamaIcon.vue` | neu | Minimales SVG (Kreis + Punkt). |
| `frontend/src/components/icons/CloudIcon.vue` | neu | Minimales Cloud-SVG. |
| `frontend/src/components/icons/OpenAiIcon.vue` | neu | Vier-Zacken-Stern-SVG. |
| `frontend/src/components/icons/UnknownModelIcon.vue` | neu | Fragezeichen-Kreis-SVG. |
| `frontend/src/layouts/WorkspaceHeader.vue` | geändert | `<ActiveModelBadge>` in `.workspace-status` vor dem `status`-Slot eingebaut. Script auf `lang="ts"` hochgestuft. |
| `frontend/src/main.js` | geändert | `createPinia()` eingebunden (Pflicht für Pinia-Stores). |
| `frontend/src/i18n/locales/de.json` | geändert | `activeModel.*`-Keys ergänzt (label, idle, connecting, failed, reload, provider.*, context.*). |
| `frontend/src/i18n/locales/en.json` | geändert | Analoge EN-Keys. |
| `frontend/src/store/__tests__/useActiveModelStore.spec.ts` | neu | 4 Tests: Modell-Wechsel, Idle-Fallback (Fake-Timer), Reconnect-Cap, Auth-Fehler. |
| `frontend/src/components/__tests__/ActiveModelBadge.spec.ts` | neu | 3 Tests via createTestingPinia: Model-Render + aria-live, Stale-Idle, Failed-Reload-Button. |
| `CHANGELOG.md` | geändert | `[Unreleased] Added` um E.2-Eintrag ergänzt. |
| `package.json` (frontend) | geändert | `pinia` + `@pinia/testing` als Abhängigkeiten hinzugefügt (pinia war bisher nicht im Repo). |

## Architektur-Entscheidungen

### Pinia statt reactive-Singleton

Die bestehenden Stores (`pendingUpload.ts`, `settings.ts`) nutzen plain `reactive`. Der Spec fordert explizit Pinia mit `createTestingPinia` für die Komponenten-Tests. Da `@pinia/testing` ohne Pinia-Store nicht funktioniert, wurde Pinia eingeführt. Pinia ist Vue-3-Standard und erlaubt saubere Test-Isolation via `setActivePinia(createPinia())` in Store-Tests bzw. `createTestingPinia` in Component-Tests.

### Provider-Icons: Inline SVG-Komponenten

Optionen waren: lucide-vue-next (nicht installiert, neue Dep), Emoji-Fallback (schlechte Accessibility), inline SVG in Badge (dichte Codebasis). Entschied: vier Mini-SVG-Komponenten (`OllamaIcon`, `CloudIcon`, `OpenAiIcon`, `UnknownModelIcon`) in `components/icons/`. Jede ist ~10 Zeilen, keine externe Dep nötig, TypeScript-safe.

### isStale-Reaktivität via _now Ref + setInterval

`Date.now()` innerhalb eines `computed` wird nicht reaktiv neu evaluiert, wenn sich keine Dependency ändert. Lösung: `_now = ref(Date.now())`, das `setInterval` (5 s) aktualisiert `_now.value`, der `computed isStale` liest `_now.value` und löst damit re-evaluierung aus. Das Interval wird in `connect()` gestartet und in `disconnect()` / bei Auth-Fehler gecleared.

### Ticket-Fetch ohne Token = sofort URL ohne `?ticket=`

Analog zu `buildSimulationStreamUrl` in `api/stream.ts`: wenn `getAgoraToken()` keinen Wert liefert, wird kein POST `/api/auth/ticket` gemacht und die SSE-URL ohne Ticket geöffnet. Das erlaubt den unauthentifizierten Dev-Mode ohne Fehler.

### Badge im WorkspaceHeader direkt, nicht via Slot

Der Spec sagt "Badge einbauen". Statt einem neuen Slot (der in allen Views befüllt werden müsste) wurde die Komponente fest in `WorkspaceHeader.vue` eingebaut. Alle Views, die `<WorkspaceHeader>` nutzen, bekommen die Badge gratis. Der Badge-Lifecycle wird komplett von `onMounted`/`onUnmounted` in `ActiveModelBadge.vue` gesteuert — keine externe Koordination nötig.

### Mobile: display:none

Unter 720px wird der Badge ausgeblendet (space ist zu eng). Der `role="status"` bleibt im DOM aber unsichtbar — Screen-Reader lesen `aria-live`-Änderungen auch dann.

## Akzeptanz-Output

```
 Test Files  23 passed (23)
      Tests  165 passed (165)   (+7 neue)
   Start at  10:59:24
   Duration  6.47s

vue-tsc --noEmit: 0 Fehler
vite build: grün (1.85s)
```

Vorher: 158 Tests in 22 Dateien. Nachher: 165 Tests in 23 Dateien.

## Bekannte Einschränkungen / Out-of-Scope

- Die Icon-SVGs sind Platzhalter (geometrische Formen). Offizielle Logos (Ollama-Llama, OpenAI-Stern) können später durch exakte SVGs ersetzt werden ohne Interface-Änderung.
- `ActiveModelBadge` ist unter 720px ausgeblendet. Ob ein kompakter Tooltip-Only-Mode sinnvoll ist, bleibt späterer UX-Review (Issue #69/70 Persona-Diff-Bereich).
