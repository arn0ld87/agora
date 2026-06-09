# Design-v4 Dashboard — Workbench-Rebuild

- **Datum:** 2026-05-14
- **Branch:** `feat/design-v4-dashboard` (Worktree `/tmp/agora-design-v4-dashboard`)
- **Base:** `origin/main` @ `b981a54`
- **Slice-Kontext:** Folgeslice zu Design-v4 Slice F (Stub-Ersetzung), spielt zugleich Teile der für Slice H geplanten Home.vue-Migration früher ein.

## Discovery

Aktueller Stand vor dem Slice war ein 40-LOC-Stub mit einer einzigen Placeholder-Card. Ziel: vollständig überarbeitetes Dashboard als operative Workbench mit Live-Daten.

Discovery-Antworten (per AskUserQuestion):

- **Scope:** Full Rebuild mit Live-Daten.
- **Visuelle These:** Workbench — ruhig, dichte Information, Mono für IDs/Counts, ein Accent pro Region.
- **Primäraktion:** Neuer Run aus Quelle (Hero oben).
- **Worktree:** `/tmp/agora-design-v4-dashboard`.

## Visuelle Richtung

> "Operator-Workbench" — wenig Farbe, dichte aber gestaffelte Information, ID-Pillen monospace, exakt eine Accent-Aktion pro Region.

Prinzipien:

1. Accent nur auf Primäraktion (Start-CTA im Hero) — sonst Hairlines + Tone-Sätze.
2. Mono für Run-IDs, Project-Slugs, Counts; Sans für Headlines/Prosa.
3. Status zeigt sich durch Token-Tones (`status-green/orange/red/...`), nie durch Glow.
4. Hero dominiert above-the-fold; Stats, Grid, Reports, Quick-Actions staffeln sich darunter.
5. Empty/Loading/Error sind first-class pro Widget.

## Architektur

```
DashboardView
├─ PageHeader
├─ HeroNewRun                (Drop · Modell+Sprache · Start)
├─ StatsRow                  (4 Mikro-Kennzahlen)
├─ Grid 2/3 · 1/3
│  ├─ ActiveRunsCard
│  └─ SystemHealthCard
├─ RecentReportsCard
└─ QuickActionsRow           (Compare · History · Settings)
```

Datenfluss:

- `useRunsPolling(5000)` → Active Runs + Stats-Aggregation.
- `useSystemStatus(15000)` → Ollama / Neo4j / Disk-Telemetrie aus `/api/status`.
- `RecentReportsCard` pollt `listRuns({run_type:'report_generate', status:'completed', limit:8})` alle 30 s.
- `HeroNewRun` greift auf bestehenden `setPendingUpload()`-Pfad zu und routet zu `/process/new`.

## Geänderte / neue Dateien

### Neu (Code)

| Datei | LOC | Tests |
|---|---:|---:|
| `frontend/src/contracts/systemStatusContract.ts` | 72 | über Composable-Spec |
| `frontend/src/api/status.ts` | 22 | (Wrapper, gemockt) |
| `frontend/src/composables/useSystemStatus.ts` | 82 | 3 |
| `frontend/src/components/v4/dashboard/HeroNewRun.vue` | 469 | 2 |
| `frontend/src/components/v4/dashboard/StatsRow.vue` | 85 | 2 |
| `frontend/src/components/v4/dashboard/ActiveRunsCard.vue` | 224 | 4 |
| `frontend/src/components/v4/dashboard/SystemHealthCard.vue` | 226 | 4 |
| `frontend/src/components/v4/dashboard/RecentReportsCard.vue` | 230 | 2 |
| `frontend/src/components/v4/dashboard/QuickActionsRow.vue` | 96 | 2 |
| `frontend/src/components/v4/dashboard/__tests__/dashTestHelpers.ts` | 41 | — |

### Geändert

- `frontend/src/views/v4/DashboardView.vue` — Stub durch Orchestrator ersetzt.
- `frontend/src/i18n/locales/de.json` + `en.json` — neuer `dashboard.*`-Namespace + `common.tryAgain`.
- `frontend/src/views/__tests__/AppShellWrappers.spec.ts` — Dashboard-Block entfernt (durch eigenen Spec ersetzt).
- `frontend/src/views/v4/__tests__/DashboardView.spec.ts` — Orchestrator-Smoke mit gestubbten Sub-Components.

## Gates (lokal)

| Gate | Status |
|---|---|
| `npm run typecheck` | ✓ grün |
| `npm test -- --run` | ✓ 674/674 Tests, 80/80 Files |
| `npm run lint` | ✓ grün |
| `npm run build` | ✓ grün |

Test-Delta: 19 neue Tests in 8 neuen Spec-Dateien.

## Bundle-Delta gegen main

| Asset | main | neu | Δ |
|---|---:|---:|---:|
| `DashboardView` JS | 0.91 kB | 22.61 kB | +21.70 kB |
| `DashboardView` CSS | 0.10 kB | 12.58 kB | +12.48 kB |
| `index` JS | 677.46 kB | 681.19 kB | +3.73 kB |
| `index` CSS | 154.87 kB | 154.87 kB | 0 |

Im Lazy-Chunk steht der echte Dashboard-Inhalt — der monolithische `index`-Bundle wächst nur um 3.7 kB (gz +1.1 kB). Akzeptabel.

## Bekannte Gaps

- **OASIS-Health hat keinen Backend-Endpoint.** Die Zeile rendert als gedimmter `idle`-Pill mit Hinweis "Wird beim Start eines Runs aktiv". Sobald ein OASIS-Status verfügbar ist, einfach in `SystemHealthCard.rows.computed` ergänzen.
- **`metadata.confidence_score` ist nicht garantiert befüllt.** Wenn fehlt: `avgConfidence` bleibt `null`, RecentReportsCard zeigt em-dash.
- **Hero schreibt nur `STORAGE_MODEL` + `STORAGE_LANG`.** Custom-Model-Pfad (`STORAGE_CUSTOM_MODEL`) bleibt der Settings-Seite vorbehalten — bewusste Reduktion gegenüber Home.vue, um die Hero-UX schmal zu halten.

## Designentscheidungen (Stichpunkte)

- **Mono-IDs durch `shortId(id)` auf 12 Zeichen begrenzt** — verhindert das Aufquellen der Tabellenzeilen bei UUIDs.
- **Stats-Row als Grid mit `gap: 1px` + Hairline-Hintergrund** — erzeugt klare Trennlinien ohne dekorative Borders.
- **Drop-Zone als `role="button"` + Enter/Space-Handler** — Tastaturbedienbarkeit ohne zusätzliche Schaltfläche.
- **Stats berechnen sich aus dem ungefilterten `useRunsPolling`-Stream** — kein zweiter API-Call nötig, kein Drift-Risiko zwischen Stats und Active-Liste.
- **`prefers-reduced-motion` respektiert** — alle Transitions im Hero werden bei reduce-motion gestoppt.

## Visueller Akzeptanztest

Lokal `npm run dev` → `/dashboard`. Erwartet: Hero oben, dann StatsRow, dann ActiveRuns+SystemHealth nebeneinander, dann Recent Reports, dann Quick-Actions. Sidebar-Active-State `dashboard` bleibt korrekt (durch bestehendes AppShell-Mapping).
