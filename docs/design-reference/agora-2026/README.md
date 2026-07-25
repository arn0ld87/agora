# Agora 2026 — eingefrorene Designexploration

Dieses Verzeichnis enthält den archivierten Quellcode der "Agora 2026"-Designexploration
(editorial Data-Room-Ästhetik). Der Code ist eine **eingefrorene Designreferenz**, kein
lauffähiges Produkt.

Bezug: [Issue #832](https://github.com/arn0ld87/agora/issues/832) — `chore(0.9): /agora-2026 aus dem produktiven
Router entfernen und archivieren`.

## Herkunft

- Ursprünglicher Pfad: `frontend/src/views/agora2026/`
- Ursprüngliche Route: `/agora-2026` (Name `Agora2026`) in `frontend/src/router/index.ts`
- Zugehöriges Stylesheet: `frontend/src/assets/styles/tokens-2026.css`, global importiert in
  `frontend/src/main.ts`

Vor Issue #832 war `/agora-2026` produktiv über den Router erreichbar und
`tokens-2026.css` landete im globalen Produktionsbundle, obwohl es sich ausschließlich um
eine Designexploration ohne produktive Consumer handelte (ROADMAP-Kriterium für Agora
0.9.0 Stability Beta: "`/agora-2026` ist kein produktiv gerouteter Parallelentwurf").

## Status

- **Nicht gebaut.** Der Code ist aus dem Vite-Build-Graph entfernt (kein Import mehr aus
  `frontend/src/`) und erzeugt keinen Chunk mehr im Produktionsbundle.
- **Nicht gewartet.** Es werden keine Bugfixes, Dependency-Updates oder Feature-Arbeit an
  diesem Code mehr vorgenommen. Er dient ausschließlich als visuelle/strukturelle
  Referenz für zukünftige Designentscheidungen.
- **Nicht getestet.** Es existiert keine Testabdeckung; keine wird nachgerüstet.

## Inhalt

- `Agora2026View.vue` — Top-Level-View
- `icons.ts` — Icon-Set
- `components/` — `Icon.vue`, `ModelPill.vue`, `ProvMark.vue`, `Shell.vue`
- `screens/` — `DashboardScreen.vue`, `RunsScreen.vue`
- `tokens-2026.css` — zugehöriges Design-Token-Stylesheet (gescopet auf
  `[data-theme="agora-2026"]`)

Der Code wurde per `git mv` verschoben, nicht neu geschrieben — die Git-History bleibt
erhalten.
