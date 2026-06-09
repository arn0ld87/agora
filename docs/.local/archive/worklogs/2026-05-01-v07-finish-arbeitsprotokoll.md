# Arbeitsprotokoll — v0.7.0 Finish (2026-05-01)

**Worktree:** `/mnt/brain/Projekte/Agora/.claude/worktrees/heuristic-hertz-2211a4`
**Branch:** `claude/heuristic-hertz-2211a4` (FF auf `origin/main`, Start: `ea2407f`)
**Plan:** `PLAN.md` (Worktree-Root, gitignored)
**Ziel:** Milestone v0.7.0 von 11/13 (85 %) auf 13/13 (100 %), Tag `v0.7.0` auf main.

---

## Sub-Slice A0 — `.gitignore`-Negativ-Pattern + `docu/api-contracts.md` + Release-Notes-Skelett

**Modell:** Sonnet
**Status:** ✅ committed (14ae25e)

### Was

- `.gitignore` Variante (γ): `/docu/*` plus zwei Negativ-Patterns für `api-contracts.md` und `2026-05-01-v0.7.0-release-notes.md`. Rest von `docu/` bleibt lokal/gitignored.
- `docu/api-contracts.md` — Single-Source-of-Truth für Response-Envelopes und alle 23 `ApiErrorCode`. Inhalte 1:1 aus `backend/app/utils/api_errors.py` und `frontend/src/api/errorMessages.ts` extrahiert. HTTP-Status pro Code: beobachtete Werte aus `grep`-Inventur (Code+nächste Zeile, status=… extrahiert), nicht-aktive Codes mit `(Konvention)` markiert und RFC-Standardstatus dokumentiert.
- `docu/2026-05-01-v0.7.0-release-notes.md` — Skelett mit Themen-Headern und Platzhalter-Sektionen. Inhalt wird in A3 finalisiert.

### Warum

Milestone-DoD verlangt `docu/api-contracts.md` als SSoT und `docu/2026-XX-XX-v07-release-notes.md` committed. `/docu/` war bisher komplett gitignored, was den DoD widersprüchlich machte. Variante (γ) löst das mit minimalem Eingriff: zwei Negativ-Pattern, `docu/`-Workflow für Arbeitsprotokolle bleibt unangetastet.

### Wie verifiziert

- [x] `git check-ignore -v` bestätigt: `api-contracts.md` und `2026-05-01-v0.7.0-release-notes.md` greifen Negativ-Pattern (line 65 + 66); arbeitsprotokoll-File bleibt durch `/docu/*` ignoriert.
- [x] `git status --untracked-files=all` zeigt nur die zwei beabsichtigten Files unversioniert.
- [x] `npm run check` grün: **Backend 419 passed, 2 skipped** (unverändert), Frontend Lint + Build sauber, Vite-Build 481.82 kB / gzip 160.79 kB.
- [x] Commit `14ae25e`: `docs(v0.7.0): track api-contracts SSoT and v0.7.0 release notes skeleton` — 3 files, +229/-1.

### Out-of-scope A0

- Inhaltliche Finalisierung der Release-Notes (kommt in A3, nachdem A1 und A2 finale Testanzahlen geliefert haben).
- HTTP-Status-Vergabe an die 13 noch nicht aktiv genutzten Codes (separates Issue, nicht Milestone-blocking).

### Test-Stand nach A0

- Backend: 419 passed, 2 skipped (unverändert).
- Frontend: kein Test-Runner installiert (kommt in A2).

---

## Sub-Slice A1 — Issue #59 EPIC-10-ST-04 — Tests für Simulation-State-Transitionen

**Modell:** Sonnet
**Status:** ✅ committed (`f0264c8`) → PR [#81](https://github.com/arn0ld87/agora/pull/81) → merged (`7c536d1`)
**Branch:** `claude/v07-a1-state-machine` (frischer Branch, da claude/heuristic-hertz-2211a4 nach A0-Rebase-Merge divergiert war)

### Was

- **`backend/app/services/simulation_state_machine.py`** — `ALLOWED_TRANSITIONS`-Tabelle (8 Status-Einträge), `is_valid_transition`, `get_allowed_next`, `is_terminal`. Rein deklarativ.
- **`backend/tests/test_simulation_state_machine.py`** — 46 Tests: 15 erlaubte + 18 verbotene Übergänge parametrisiert, terminal-state Asserts, Konsistenz-Checks (Tabelle ↔ TERMINAL_STATES, vollständige Enum-Coverage, defensive Lookup).
- **`backend/tests/services/test_simulation_manager_transitions.py`** — 23 Tests: 3 `create_simulation`-Behavior, 7 parametrisierte Persist/Reload pro Status, 13 Compliance-Tests gegen die real beobachteten Transition-Call-Sites in `simulation_manager.py`, `api/simulation_run.py`, `api/runs.py`.
- **`backend/tests/services/__init__.py`** — leeres Package-Marker.

### Sonderfall create_branch

Branch-Init `simulation_manager.py:603` setzt `CREATED → READY` direkt — Initialisierungs-Setter, kein regulärer Lifecycle. Tabelle erlaubt das absichtlich NICHT (würde Lifecycle bypassen). Compliance-Test markiert es explizit als Sonderfall für EPIC-06-ST-02.

### Test-Stand

- Backend: **488 passed, 2 skipped** (vorher 419, +46 Tabelle, +23 Behavior). Redis-Skips wie immer.
- Frontend: Lint + Build sauber, 728 modules, 481.82 kB / gzip 160.79 kB.
- `npm run check` grün.

### Verifikation

- [x] `Closes #59` im PR-Body → Issue auto-closed (gh issue view 59 → `CLOSED`).
- [x] PR-Merge via `gh pr merge 81 --rebase --delete-branch`.
- [x] Milestone-Counter nach Merge: **12/13 (92 %)**.

### Out-of-scope

- EPIC-06-ST-02 (State-Machine in Manager/API integrieren). Bewusst getrennt.
- Async-Edge-Cases (Pause während async `_prepare_async()`).

---

## Sub-Slice A2 — Issue #61 EPIC-10-ST-06 — Frontend Vitest Setup

**Modell:** Opus
**Status:** ✅ committed (`e706e87`) → PR [#82](https://github.com/arn0ld87/agora/pull/82) → merged (`f7a7f29`)
**Branch:** `claude/v07-a2-vitest`

### context7-Befund

`vitest/config` mit `defineConfig` aus Vite 7 ist kompatibel via Triple-Slash-Reference. Kein separates `vitest.config.ts` nötig — `test`-Block direkt in `vite.config.js`. Kein `tsconfig.json` notwendig: Vitest nutzt esbuild-Loader, der TS-Types transparent strippt.

### Was

- **`frontend/package.json`** — `vitest@4.1.5` als devDep, Scripts `test` (CI) + `test:watch` (DX).
- **`frontend/vite.config.js`** — Triple-Slash + `test`-Block (`environment: 'node'`, include-Pattern, `globals: false`). Node-Env ist für `envelope.ts` (pure-TS) ausreichend; jsdom kommt mit EPIC-10-ST-07.
- **`frontend/src/api/__tests__/envelope.spec.ts`** — 11 Tests in 3 describe-Blöcken: 6 für `unwrap`, 2 für `ApiError`-Konstruktor, 3 für `isApiError`-Type-Guard.
- **`package.json` (root)** — `test:frontend`-Script in `check`-Pipeline integriert (Stufe 4 von 5).

### Test-Stand

- Backend: **488 passed, 2 skipped** (unverändert).
- Frontend: **11 passed** in 277ms (vitest 4.1.5).
- `npm run check` grün über alle 5 Stufen.

### Verifikation

- [x] `Closes #61` im PR-Body → Issue auto-closed.
- [x] PR-Merge via `gh pr merge 82 --rebase`.
- [x] **Milestone v0.7.0: 13/13 (100 %), 0 offene Issues.**

### Out-of-scope

- EPIC-10-ST-07 (Composable-Tests `usePolling`, `useEventStream`, `useWorkspaceStatus`) → v0.8.0.
- Coverage-Reports im CI.
- Vue-Component-Tests.

---

## Sub-Slice A3 — Tag v0.7.0 + CHANGELOG-Bump + Release-Notes finalisieren

**Modell:** Haiku (mechanisch)
**Status:** ✅ committed (`dbcb5c6`) → direkt-push main → Tag `v0.7.0` → GitHub-Release → Milestone closed

### Was

- **CHANGELOG.md** — `[Unreleased]` aufgespalten: oben neuer leerer Block, darunter `[0.7.0] — 2026-05-01` mit Highlights-Absatz + 3 neuen "Hinzugefügt"-Einträgen (Simulation-State-Machine, Vitest-Setup, api-contracts.md). Bestehende EPIC-09-Einträge bleiben unter `[0.7.0]`.
- **`docu/2026-05-01-v0.7.0-release-notes.md`** — Skelett aus A0 mit echtem Inhalt gefüllt: Highlights, Frontend-Dev-Hinweise, Backend-Dev-Hinweise, Test-Stand (488+11=499 Tests), Migrations-Hinweise (keine Breaking-Changes), bekannte Limitierungen, PR-Verweise.

### Release-Operationen

- **Direkt-Push auf main:** `git push origin claude/v07-a3-tag:main` — `f7a7f29..dbcb5c6`.
- **Annotated Tag:** `git tag -a v0.7.0 dbcb5c6 -m "Release v0.7.0 — API Contracts & Quality Gate"` + `git push origin v0.7.0`.
- **GitHub-Release:** `gh release create v0.7.0 --notes-file docu/2026-05-01-v0.7.0-release-notes.md` → https://github.com/arn0ld87/agora/releases/tag/v0.7.0.
- **Milestone schließen:** `gh api -X PATCH /repos/arn0ld87/agora/milestones/1 -f state=closed` → `state: closed, closed_issues: 16` (13 Issues + 3 PRs).

### Verifikation

- [x] `npm run check` grün vor Tag: 488 Backend + 11 Frontend = **499 Tests passed**, 2 skipped.
- [x] Tag annotated und auf main referenziert.
- [x] GitHub-Release sichtbar mit korrekten Notes.
- [x] Milestone v0.7.0: state=closed, 0 offene Issues/PRs.

### Out-of-scope A3

- v0.7.1-Hotfix-Branch (nur bei Bedarf).
- Roadmap-Update für v0.8.0 (separater PR).
- Tweet/Blog-Post.

---

## Slice-Abschluss

**Milestone v0.7.0 — API Contracts & Quality Gate: 100 % geschlossen.**

| Metric | Wert |
|--------|------|
| Sub-Slices | 4 (A0/A1/A2/A3) |
| Commits | 4 (`a02cf3f`, `7c536d1`, `f7a7f29`, `dbcb5c6`) |
| PRs | 3 ([#80](https://github.com/arn0ld87/agora/pull/80), [#81](https://github.com/arn0ld87/agora/pull/81), [#82](https://github.com/arn0ld87/agora/pull/82)) — A3 direkt-push |
| Issues geschlossen | 2 ([#59](https://github.com/arn0ld87/agora/issues/59), [#61](https://github.com/arn0ld87/agora/issues/61)) |
| Backend-Tests | 419 → **488** (+69) |
| Frontend-Tests | 0 → **11** |
| Tag | `v0.7.0` auf `dbcb5c6` |
| Release | https://github.com/arn0ld87/agora/releases/tag/v0.7.0 |
