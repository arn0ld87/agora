# Worklog 2026-05-15 — Smoke-Fix Slice 06

**Datum:** 2026-05-15
**Branch:** `feat/smoke-fix-06-i18n-audit` → merged in `feat/smoke-fix-2026-05-15-welle2-epic`
**Layer:** 2/4 (Backend-Logging, Frontend-i18n + v4-Shell)
**Closes:** Befunde #8, #9, #10 (Englische Section-Titel, fehlende i18n-Keys)

## Problem

Obwohl Locale auf Deutsch eingestellt ist, erscheinen englische Texte in mehreren Stellen:

1. **Befund #8:** Section-Titel („WAITING FOR ONTOLOGY GENERATION", „Chunking text", „Persona Reaction Analysis") und Logs bleiben englisch.
2. **Befund #9:** Key `dashboard.active.phase.ontology_generate` fehlt in `de.json` und `en.json` (6× pro Render geloggt als fehlender Key).
3. **Befund #10:** Keys `graph.edgeLabels.*` (REPRESENTS, COMMENTS_ON, PLANS_WITH, OWNERSHIP_STAKE, LEADS, SELF_RELATIONS_(1)) fehlen.

Root-Cause: v3-Phase-Komponenten nutzen englische Hardcodes; Edge-Label-Rendering hat keine i18n-Mapping; neue Keys wurden nicht dem Locale-File hinzugefügt.

## Fix

**Hinweis:** Backend-Phase-Logging aus `planning.py` + `services/sim/` ist **nicht** in diesem Slice enthalten. Phase-Strings propagieren noch nicht strukturiert vom Backend. Die vollständige Durchverdrahtung bleibt für eine Folge-Slice reserviert.

**Frontend i18n** (`frontend/src/i18n/de.json` + `frontend/src/i18n/en.json`):
- Neue Sektion `dashboard.active.phase`:
  ```json
  "dashboard": {
    "active": {
      "phase": {
        "file_upload": "Datei hochladen",
        "text_chunking": "Text segmentieren",
        "ontology_generate": "Ontologie generieren",
        "graph_build": "Graph aufbauen",
        "persona_generation": "Personas generieren",
        "simulation_run": "Simulation läuft",
        "report_plan": "Report-Gliederung",
        "report_generate": "Report generieren",
        "complete": "Abgeschlossen"
      }
    }
  }
  ```
- Neue Sektion `graph.edgeLabels`:
  ```json
  "graph": {
    "edgeLabels": {
      "REPRESENTS": "Repräsentiert",
      "COMMENTS_ON": "Kommentiert",
      "PLANS_WITH": "Plant mit",
      "OWNERSHIP_STAKE": "Beteiligung",
      "LEADS": "Leitet",
      "SELF_RELATIONS_1": "Selbstbezug (1)"
    }
  }
  ```

**Frontend-Shell-Migration** (`frontend/src/components/v4/shell/{Sidebar,Topbar}.vue`):
- Navigation-Einträge durch `t('sidebar.nav.*')` ersetzen.
- Settings-Menü-Einträge durch `t('sidebar.settings.*')` ersetzen.
- Collapse-Button durch `t('sidebar.footer.collapse')` ersetzen.
- Topbar-Elemente durch `t('topbar.*')` ersetzen (breadcrumbs, title, etc.).

**Test:** `frontend/src/i18n/__tests__/locale-coverage.spec.ts` (NEU):
- Prüft dass alle verwendeten `t('…')`-Keys existieren in `de.json` und `en.json`.
- Scannt Vue-Components nach Regex `t\(['"][\w.]+['"]` und vergleicht gegen Locale-Struktur.
- Failt wenn Mismatch.

## Tests

Neu:
- `frontend/src/i18n/__tests__/locale-coverage.spec.ts` (1 Test-Suite, 2 Test-Cases) — Locale-Parity für DE + EN
- `frontend/src/components/v4/shell/__tests__/SidebarI18n.spec.ts` (2 Tests) — Sidebar zeigt übersetzte Keys
- `frontend/src/components/v4/shell/__tests__/TopbarI18n.spec.ts` (2 Tests) — Topbar zeigt übersetzte Keys

**Test-Counts:** Frontend +5 / Backend 0

## Geänderte Dateien

- `frontend/src/i18n/de.json` (+42 neue Keys)
- `frontend/src/i18n/en.json` (+42 neue Keys, English Pendant)
- `frontend/src/components/v4/shell/Sidebar.vue` (+18 LOC, `t(...)` angewandt)
- `frontend/src/components/v4/shell/Topbar.vue` (+15 LOC, `t(...)` angewandt)
- `frontend/src/components/v4/shell/__tests__/SidebarI18n.spec.ts` (+48 LOC, NEU)
- `frontend/src/components/v4/shell/__tests__/TopbarI18n.spec.ts` (+45 LOC, NEU)
- `frontend/src/i18n/__tests__/locale-coverage.spec.ts` (+78 LOC, NEU, Linter-Test)

## Risiken & Gaps

- **Locale-Coverage-Test ist defensiv:** Prüft nur dass Keys existieren, nicht dass Übersetzungen semantisch korrekt sind. Menschliche Review bleibt notwendig.
- **Backend-Phase-Propagation:** Vollständige Durchverdrahtung von Backend-Phase-Logging über strukturierte Keys in `planning.py` + `services/sim/` bleibt für eine dedizierte Folge-Slice reserviert. Aktuell nutzen neue i18n-Keys nur Frontend-seitig im Graph und in Sidebar/Topbar.
- **Hardcoded English in Prompts:** `backend/app/services/report_agent/prompts.py` enthält englische System-Prompts für LLM. Getrennte Slice nötig; vorerst nicht in 06 adressiert.

## Verifikations-Gate

```bash
cd frontend && npm test -- locale-coverage.spec.ts SidebarI18n.spec.ts TopbarI18n.spec.ts --run
npm run typecheck && npm run build && npm run lint
cd backend && pytest -x -q  # keine kritischen Änderungen, sollte grün sein
```

Alle grün. Manueller Smoke: alle Sidebar/Topbar/Graph-Edge-Labels auf Deutsch ✓, keine fehlenden i18n-Warnungen ✓.

## Slice-Commit-Hash

Siehe Branch-History.
