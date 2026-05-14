# Mai-Welle — Subagent-Heuristik

**Stand:** 2026-05-14
**Bezug:** [`docu/plan.mai.md`](plan.mai.md) (Plan), [`CLAUDE.md`](../CLAUDE.md) § Subagent-Routing (Vertrags-Grundlagen).
**Zweck:** Pro Mai-Slice die optimale Subagent-Wahl, das Opus-Trigger-Signal und das Akzeptanzkriterium auf einen Blick. Diese Datei wird vom `/agora-mai-next-task`-Orchestrator gelesen — Änderungen wirken ohne Code-Touch.

---

## Routing-Logik (Kurzfassung)

| Signal | Routing |
|---|---|
| Workflow-yml + Doku | `agora-frontend-worker` (CI-Files leben am Frontend-Build-Pfad) ODER `agora-refactor-worker` |
| Backend-Refactor mit Layer-0-Contract-Touch | `agora-refactor-worker` (Sonnet) + **Opus-Pre-Review** |
| Backend-Refactor ohne Layer-0-Touch | `agora-refactor-worker` (Sonnet) |
| Persistenz-Touch (Files unter `uploads/`) | `agora-refactor-worker` (Sonnet) + **Opus-Pre-Review** |
| Pool-/Fork-/Thread-Touch | `agora-refactor-worker` (Sonnet) + **Opus-Pre-Review** |
| Vue/Pinia/Zod | `agora-frontend-worker` (Sonnet) |
| Reine Doku, CHANGELOG, Issue-Comments | `agora-doc-worker` (Haiku) |
| Test-/Coverage-Erweiterung | `agora-test-worker` (Sonnet) |
| Read-only Audit (Evidence, Wording-Glossar) | `agora-evidence-auditor` (Sonnet) |

**Opus-Trigger** (überstimmen das Default-Routing):

1. Layer-0 (Pydantic-Contracts) wird angefasst.
2. Mehrere Layer gleichzeitig betroffen.
3. Persistenz-Format ändert sich (Files unter `uploads/` werden anders geschrieben).
4. Pool-/Thread-/Fork-Logik wird angefasst.
5. Spec ist ambig oder Tests fehlen.
6. Pre-PR-Self-Review **vor** `gh pr create` (fängt Drift bevor Gemini sie sieht).

Bei Opus-Trigger: Subagent läuft trotzdem auf Sonnet, aber der Lead macht **zusätzlich** einen Pre-Dispatch-Review mit `mcp__code-review-graph__get_impact_radius_tool` + `sequential-thinking` (mind. 3 Thoughts) und briefst den Subagent mit erweitertem Risk-Kontext.

---

## Slice-Mapping

### Block A — Output-Vertrag final dichtmachen

| Slice | Subagent | Aufwand | Opus-Trigger | Slash-Command |
|---|---|---|---|---|
| MAI-01 | `agora-frontend-worker` | S | nein | `/fix-mai-01-mode-smokes-ci` |
| MAI-04 | `agora-refactor-worker` | S | nein | `/fix-mai-04-schema-drift-gate` |
| MAI-13 | `agora-refactor-worker` | S | nein | `/fix-mai-13-dependabot-cleanup` |

**Akzeptanz Block A:** Alle drei Slices grün auf `main`, P4.4 Mode-Banner in CI sichtbar, `git diff --exit-code schemas/` läuft als CI-Step, `uv.lock` ohne mistune/pygments-Drift.

### Block B — Bewertungs-Score-Hebel (R4 + R11 + Confidence)

| Slice | Subagent | Aufwand | Opus-Trigger | Slash-Command |
|---|---|---|---|---|
| MAI-02 | `agora-refactor-worker` | M | **ja** | `/fix-mai-02-evidence-routing` |
| MAI-03 | `agora-refactor-worker` | M | **ja** | `/fix-mai-03-hypotheses-slot` |
| MAI-14 | `agora-refactor-worker` | S | nein | `/fix-mai-14-contradiction-penalty` |

**Akzeptanz Block B:** Snapshot-Diff in `tests/eval/snapshots/` mit-committet, `data_gaps[]` enthält nur noch echte Datenlücken (keine Hypothesen mehr), ReportV3 hat `hypotheses[]`-Slot, Confidence-Calculator senkt Score bei Widerspruch.

### Block C — Hygiene parallel zu B

| Slice | Subagent | Aufwand | Opus-Trigger | Slash-Command |
|---|---|---|---|---|
| MAI-08 | `agora-refactor-worker` | M | nein | `/fix-mai-08-prompts-split` |
| MAI-09 | `agora-frontend-worker` | S | nein | `/fix-mai-09-markdown-ts` |
| MAI-10 | `agora-doc-worker` | S | nein | `/fix-mai-10-close-issue-203` |

**Akzeptanz Block C:** `backend/app/services/report_prompts/` ist ein Paket mit 4 Modulen, `frontend/src/utils/markdown.ts` ist die einzige Markdown-Util, Issue #203 ist `state=CLOSED`.

### Block D — Production-Cleanup

| Slice | Subagent | Aufwand | Opus-Trigger | Slash-Command |
|---|---|---|---|---|
| MAI-06 | `agora-refactor-worker` | L | **ja** | `/fix-mai-06-retire-v2-md` |
| MAI-12 | `agora-refactor-worker` | M | **ja** | `/fix-mai-12-fork-safety` |
| MAI-11 | `agora-refactor-worker` | S | nein | `/fix-mai-11-pr-smoke-rc-only` |

**Akzeptanz Block D:** Keine neuen `full_report.md` mehr unter `uploads/reports/`, `docker logs agora 2>&1 | grep -c "Neo4j storage initialized"` liefert `1` (war `2`), PR-Smoke läuft nicht mehr auf Feature-PRs.

### Block E — Bewertungs-Polish

| Slice | Subagent | Aufwand | Opus-Trigger | Slash-Command |
|---|---|---|---|---|
| MAI-05 | `agora-refactor-worker` | S | nein | `/fix-mai-05-voice-lint-ci` |
| MAI-07 | `agora-frontend-worker` | S | nein | `/fix-mai-07-quote-marker-css` |
| MAI-15 | `agora-frontend-worker` | S | nein | `/fix-mai-15-e2e-persona-compact` |

**Akzeptanz Block E:** `check_voice.py` läuft im CI-Pflichtschritt, exportiertes Print-PDF zeigt SIM-Badge an Persona-Quotes, E2E-Laufzeit reduziert.

### Block F — Optional / Nice-to-have

| Slice | Subagent | Aufwand | Opus-Trigger | Slash-Command |
|---|---|---|---|---|
| MAI-16 | `agora-refactor-worker` | S | nein | `/fix-mai-16-status-sync-ci` |
| MAI-17 | `agora-test-worker` | S | nein | `/fix-mai-17-radon-gate` |

**Akzeptanz Block F:** STATUS.md kann nicht mehr per Hand driften, neue Funktionen mit `cyclomatic complexity > 15` werden in CI blockiert.

---

## Test-Set je Subagent-Profil

| Subagent | Pflicht-Tests |
|---|---|
| `agora-refactor-worker` | `cd backend && uv run pytest -x -q && uv run ruff check . && uv run mypy app` + Slice-spezifische Contract-Tests |
| `agora-frontend-worker` | `cd frontend && npm run check` (= typecheck + test + build + lint) |
| `agora-test-worker` | `cd backend && uv run pytest -x -q` + neue Fixture/Snapshot, `tests/eval/` falls Snapshot-Touch |
| `agora-evidence-auditor` | Read-only, kein Write — Ausgabe als Audit-Markdown-Datei |
| `agora-doc-worker` | Markdown-Lint, kein Code-Touch |

---

## Worktree-Pfad-Konvention

```
/Volumes/T7/Projekte/agora-worktrees/mai-<NN>/
```

`<NN>` ist die zweistellige Slice-Nummer (`01`, `02`, … `17`).

Symlink für `node_modules` ist Pflicht — sonst kostet jeder Subagent-Run 60-90 s `npm ci`:

```bash
ln -sfn /Volumes/T7/Projekte/agora/frontend/node_modules \
        /Volumes/T7/Projekte/agora-worktrees/mai-<NN>/frontend/node_modules
```

---

## Eskalationspfad

Wenn ein Slice nach **zwei** Subagent-Runs nicht grün ist:

1. Worktree stehen lassen (`/private/tmp/agora-worktrees/mai-<NN>/`).
2. Status in `docu/<datum>-mai-<NN>-blockiert.md` dokumentieren — was rot, welche Annahme war falsch.
3. User entscheidet:
   - **Spec-Bug** → `plan.mai.md` Slice-Definition anpassen, neuer Slice-ID.
   - **Tooling-Bug** → Slice pausieren, Issue im Repo öffnen.
   - **Größere Architektur-Frage** → Slice splitten, ADR anlegen.

Niemals einen halb-grünen Slice mergen, niemals `--force-with-lease` auf `main`.

---

## Doku-Pflicht je Slice

Jeder Subagent-Run schreibt zwei Files **bevor er fertig meldet**:

1. **Arbeitsprotokoll** `docu/<YYYY-MM-DD>-mai-<NN>-arbeitsprotokoll.md`:

```markdown
# MAI-<NN> · <Titel> — Arbeitsprotokoll

**Datum:** YYYY-MM-DD
**Subagent:** <name>
**Branch:** feat/mai-<nn>-<slug>
**Commit:** <SHA>

## Befund
<was war kaputt, was hat der Slice geändert>

## Edits
- <pfad>:<linie> — <was>

## Tests
- <pytest/npm-Aufruf> — <Ergebnis>

## Akzeptanz erfüllt?
- [x] <Kriterium 1>
- [x] <Kriterium 2>

## Folge-Slices
<Issues/Slices die durch diesen Slice entblockt sind>
```

2. **CHANGELOG.md** unter `[Unreleased]`:

```markdown
### Changed
- MAI-<NN> · <kurz>: <was geändert>, <referenz>.
```

---

## Referenzen

- [`docu/plan.mai.md`](plan.mai.md) — Plan + Status
- [`docu/plan.heuristic.md`](plan.heuristic.md) — Schwester-Heuristik für Layer-0–10 (Pre-v1.0)
- [`CLAUDE.md`](../CLAUDE.md) § Subagent-Routing — Vertrags-Grundlagen
- [`.claude/commands/agora-mai-next-task.md`](../.claude/commands/agora-mai-next-task.md) — Orchestrator
- [`.claude/commands/fix-mai-*.md`](../.claude/commands/) — Slice-Detail-Briefs
