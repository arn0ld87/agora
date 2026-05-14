# Arbeitsprotokoll — Design v3 Rollout Phase 2–6

**Datum:** 2026-05-11
**Branch:** `feat/design-v3-epic-complete`
**Draft-PR:** #401
**Plan:** [2026-05-09-design-v3-epic.md](2026-05-09-design-v3-epic.md)

## Ablauf

Auf Wunsch laufen Phase 2–6 nicht als einzelne PRs, sondern als ein Draft-PR,
der mit separaten Commits erweitert wird. GitHub-CI und Gemini werden erst nach
Abschluss aller Phasen als finales Gate bewertet.

## Umgesetzt

1. Shell/Layout:
   - `WorkspaceLayout`, `WorkspaceHeader`, `WorkspaceSplit`,
     `WorkspaceModeSwitch`, `WorkspaceStepStatus`, `WorkspaceBrandLink`
   - v3-native Token-Fallbacks, Glass-Header, Apple-Segmented-Control,
     kompakte Status-Pills
2. UI Kit:
   - `Btn`, `Badge`, `Field`, `Card`, `Select`, `SectionHead`
   - Apple-Enterprise Pills, System-Badges, sanftere Inputs, sans-only Headings
3. Pipeline Step 1–3:
   - `Step1GraphBuild`, `Step2EnvSetup`, `Step3Simulation`, `step2/*`
   - grouped surfaces, sans-only Labels, v3 Focus-Rings und kompaktere Controls
4. Pipeline Step 4–5 + Graph + Compare:
   - `Step4Report`, `Step5Interaction`, `GraphPanel`, `graph/*`,
     `compare/BranchComparePanel`
   - v3 Report-, Graph-, Diff- und Compare-Chrome
5. Cleanup:
   - v3 ist Default; `VITE_DESIGN_V3`-Schalter aus `main.ts` entfernt
   - `frontend/src/assets/styles/tokens.css` entfernt
   - Theme-Toggle entfernt
   - `data-theme="dark"`-Pfade entfernt
   - Google-Fonts-Link aus `frontend/index.html` entfernt

## Bewusste Abweichung

Der v2-Kompatibilitaets-Layer in `tokens-v3.css` bleibt erhalten. Nach Phase 6
fand `rg` noch 2402 Legacy-Tokenverwendungen in `frontend/src`; ein sofortiges
Entfernen des Layers wuerde nicht vollstaendig migrierte Komponenten visuell
brechen. Der alte v2-Default ist dennoch entfernt: `main.ts` importiert nur noch
`tokens-v3.css`.

Das finale GitHub-Gate machte ausserdem drei vorbestehende Wartungsdrifts
sichtbar, die im selben PR eng behoben wurden:

- `backend/app/api/llm_routing.py`: mypy-kompatible StageId-Validierung und
  ValidationError-Envelope
- `docu/STATUS.md`: Backend-Testcount per `scripts/sync-status.sh`
  aktualisiert
- `backend/radon-allowlist.txt`: `app/api/graph.py::build_graph` als
  vorbestehenden Class-D-Orchestrator-Hotspot mit Refactor-Hinweis aufgenommen

## Lokale Gates

Bislang lokal gruen:

```bash
cd frontend && npm run typecheck
cd frontend && npm run build
```

Final ausstehend:

```bash
cd frontend && npm run check
```

Danach: Draft-PR #401 aktualisieren, GitHub-CI/Gemini-Findings sichten und erst
dann ready/merge-faehig machen.
