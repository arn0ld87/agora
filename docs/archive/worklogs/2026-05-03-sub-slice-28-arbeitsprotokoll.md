# Sub-Slice 28 — Pinia-Stores .js → .ts Migration (Layer 6, Refs #71 #73)

Datum: 2026-05-03
Branch: `feat/layer-6-task-21-stores-ts`

## Ziel

Migration der 2 verbleibenden JavaScript-Stores in `frontend/src/store/` auf TypeScript
sowie Umbenennung der zugehörigen Test-Datei auf `.spec.ts`.

## Migrierte Dateien

| Datei (vorher) | Datei (nachher) | LOC vorher | LOC nachher |
|---|---|---|---|
| `frontend/src/store/pendingUpload.js` | `frontend/src/store/pendingUpload.ts` | 33 | 43 |
| `frontend/src/store/settings.js` | `frontend/src/store/settings.ts` | 210 | 242 |
| `frontend/src/store/__tests__/settings.spec.js` | `frontend/src/store/__tests__/settings.spec.ts` | 242 | 259 |

## Neue Interfaces / Types (pendingUpload.ts)

Keine Imports aus api/*. Eigene Interface-Definition:

- `PendingUploadState` — `{ files: File[], simulationRequirement: string, isPending: boolean }`

Funktions-Signaturen typisiert:
- `setPendingUpload(files: File[], requirement: string): void`
- `getPendingUpload(): PendingUploadState`
- `clearPendingUpload(): void`

## Neue Interfaces / Types (settings.ts)

Aus `frontend/src/api/settings.ts` importiert:
- `SecretsPayload` — für `_splitDirtyByKind()` Rückgabe-Typing

Lokal definierte Interfaces (spiegeln Backend-Envelope-Shape):
- `FieldSpec` — Schema-Beschreibung eines Feldes (key, section, type, secret, ...)
- `FieldMeta` — Laufzeit-Wert-Metadaten (key, value, source, is_set, ...)
- `ValidationError` — Backend-Validierungsfehler `{ key, code, message }`
- `SettingsState` — vollständiger State-Shape des reaktiven Singletons
- `SettingsApiError` (intern) — Error + code + originalResponse
- `SettingsApiResponse` (intern) — Axios-ähnliche Envelope-Doppeltiefe `.data.data.*`
- `SchemaApiResponse` (intern) — analog für Schema-Endpunkt

### Hinweis zur `.data.data`-Doppeltiefe

Der Axios-Interceptor in `api/index.ts` gibt `response.data` (den Envelope-Body)
direkt zurück. In Tests mocken die Test-Fixtures jedoch die axios-ähnliche Struktur
`{ data: { success: true, data: {...} } }`, wie sie vor dem Interceptor existiert.
Die bestehende Zugriffslogik `valuesRes.data.data.sections` entspricht diesem
Verhalten — kein funktionaler Umbau, nur Typ-Annotation.

## settings.spec.ts — Anpassungen

`vi.fn()`-Mocks werden nach dem Import auf `MockInstance` gecastet:
```ts
// reason: vi.mock() ersetzt Funktionen durch Mock-Instanzen; TS kennt nur
// den deklarierten Typ aus api/settings.ts. Cast auf MockInstance nötig,
// damit .mockResolvedValueOnce / .mockRejectedValueOnce verfügbar sind.
const _fetchSettings = fetchSettings as unknown as MockInstance
```
Alle `fetchSettingsSchema.mockResolvedValueOnce(...)` etc. durch die `_`-prefixed
Cast-Variablen ersetzt. Testlogik unverändert.

## Verifikation

```
npm run check  →  vue-tsc OK, 16 Test-Files, 137 Tests grün, vite build OK
rg ".js"-Imports auf store/  →  OK (keine .js-Endungen mehr)
uv run pytest -x -q  →  1282 passed, 9 skipped
```
