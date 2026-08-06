---
applyTo: "frontend/**/*.vue,frontend/**/*.ts,frontend/**/*.js"
---

# Frontend (Vue 3 + Vite + Pinia)

## Werkzeuge

- Paketmanager ist `bun`, nicht `npm` oder `yarn`.
- Arbeitsverzeichnis für alle Frontend-Kommandos ist `frontend/`.

## Verbindlich

- Keine hartkodierten UI-Texte. Jeder sichtbare String läuft über `vue-i18n`.
- Kein React-/Lovable-Rewrite und kein zweites paralleles Frontend.
- Keine neuen produktiven Legacy-Modell-Picker. Der Workflow `check-legacy-model-picker.yml` bricht sonst.
- API-Antworten gegen die `zod`-Schemas in `src/contracts/` validieren, nicht blind durchreichen.
- Fremdes HTML nur über `dompurify` rendern.
- State gehört in Pinia-Stores, nicht in globale Singletons neben dem Store.

## Vor dem Commit

```bash
cd frontend
bun run test
bun run check   # lint + typecheck + coverage + build
```

Vor dem Push zusätzlich `bash scripts/pre-push-gate.sh frontend`. Kein `--no-verify`.
