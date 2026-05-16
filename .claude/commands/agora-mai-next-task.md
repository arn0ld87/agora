---
description: Master-Orchestrator Mai-Restwelle — pickt den nächsten offenen Slice aus docs/archive/plans/plan.mai.md, dispatched den passenden Subagent, verifiziert, committet, pusht.
allowed-tools: Read, Bash, Grep, Glob, Edit, Write, TodoWrite, Agent, AskUserQuestion
---

# /agora-mai-next-task — Plan-Orchestrator für die 17 Mai-Slices

Du bist der **Orchestrator** für die nach v1.0.0 verbliebene Mai-Welle (17 Slices, Quelle: `docs/archive/plans/plan.mai.md` + `docs/archive/plans/plan.heuristic-mai.md`). Du wählst den nächsten Slice, schreibst einen knappen Plan, dispatchst einen Subagent als Implementer, verifizierst, committest, pushst und meldest. Der Haupt-Claude editiert **nicht** selbst Code — das ist Aufgabe des Subagents im Worktree.

Hardstops: kein Auto-Fix-Loop bei rotem Verify, keine Layer-Sprünge gegen den Plan, keine Force-Pushes auf `main`.

---

## Schritt 0: Setup-Anker

- Repo-Root: `/Volumes/T7/Projekte/agora`
- Plan: `/Volumes/T7/Projekte/agora/docs/archive/plans/plan.mai.md` (autoritativ für Reihenfolge & Status)
- Heuristik: `/Volumes/T7/Projekte/agora/docs/archive/plans/plan.heuristic-mai.md` (Subagent-Mapping je Slice)
- Verify-Slash: `/verify-after-subagent`
- Default-Branch-Ziel: `main` (FF-Push, kein PR-Zwang außer bei Layer-0/Persistenz-Touch)
- User-Trait: Deutsch, knapp, direkt; ein Slice = ein Commit + ein Arbeitsprotokoll unter `docs/archive/worklogs/<datum>-mai-<XX>-arbeitsprotokoll.md`; CHANGELOG `[Unreleased]` Pflicht.

Lies sofort `docs/archive/plans/plan.mai.md` (Tabelle „Slices in Reihenfolge"), damit du den Status im Kopf hast.

---

## Schritt 1: Status-Scan

```bash
cd /Volumes/T7/Projekte/agora
git fetch origin --quiet

# 1.1 origin/main aktuell
echo "=== origin/main letzte 10 ==="
git log origin/main --oneline -10

# 1.2 Welche Mai-Slices sind in plan.mai.md als "offen" markiert?
echo "=== Mai-Slices Status ==="
rg -n "^\| MAI-\d+" docs/archive/plans/plan.mai.md

# 1.3 Welche Mai-Commits liegen schon auf main?
echo "=== Mai-Slices auf main ==="
git log origin/main --grep="MAI-" --oneline -20

# 1.4 Offene GitHub-Issues mit mai-Label
echo "=== offene Mai-Issues ==="
gh issue list --state open --label "mai-cleanup" --limit 30 \
  --json number,title --jq '.[] | "#\(.number) \(.title)"'

# 1.5 Code-Indikatoren — pro Slice ein konkreter rg-Check
echo "=== Slice-Indikatoren ==="

# MAI-01: report-modes.spec.ts in CI?
rg -q "report-modes\.spec\.ts" .github/workflows/e2e-smokes.yml \
  && echo "MAI-01: in CI ✓" || echo "MAI-01: NICHT in CI"

# MAI-02: _finalize_section_claims aktiv?
rg -q "_finalize_section_claims" backend/app/services/report_agent/agent.py \
  && echo "MAI-02: Routing-Hook vorhanden" || echo "MAI-02: offen"

# MAI-03: Hypothesis als eigenes V3-Feld?
rg -q "^\s*hypotheses:\s*list\[Hypothesis\]" backend/app/contracts/report_v3.py \
  && echo "MAI-03: ReportV3.hypotheses ✓" || echo "MAI-03: offen"

# MAI-04: dump_schemas --check?
rg -q "\-\-check" backend/app/contracts/dump_schemas.py \
  && echo "MAI-04: --check-Flag ✓" || echo "MAI-04: offen"

# MAI-05: Voice-Lint als CI-Job?
rg -q "voice-lint:" .github/workflows/contract-gates.yml \
  && echo "MAI-05: CI-Job ✓" || echo "MAI-05: offen"

# MAI-06: v2-full_report.md noch geschrieben?
rg -q "full_report\.md" backend/app/services/report_agent/manager.py \
  && echo "MAI-06: v2-Write noch aktiv" || echo "MAI-06: v2 retired ✓"

# MAI-07: sim-quote-CSS im Standalone-HTML?
rg -q "sim-quote" frontend/src/composables/useReportExports.ts \
  && echo "MAI-07: CSS-Klasse ✓" || echo "MAI-07: offen"

# MAI-08: report_prompts als Paket?
[ -d backend/app/services/report_prompts ] \
  && echo "MAI-08: Paket-Split ✓" || echo "MAI-08: offen"

# MAI-09: markdown.ts statt .js?
[ -f frontend/src/utils/markdown.ts ] \
  && echo "MAI-09: markdown.ts ✓" || echo "MAI-09: offen"

# MAI-12: Fork-Safety register_at_fork?
rg -q "register_at_fork" backend/app/__init__.py \
  && echo "MAI-12: Fork-Safety ✓" || echo "MAI-12: offen"

# MAI-14: contradiction-Penalty in confidence?
rg -q "contradiction_penalty" backend/app/services/confidence_calculator.py \
  && echo "MAI-14: Penalty ✓" || echo "MAI-14: offen"

# MAI-16: sync-status --check als CI-Step?
rg -q "sync-status\.sh \-\-check\|sync-status\.sh --check" .github/workflows/ci.yml \
  && echo "MAI-16: CI-Pflicht ✓" || echo "MAI-16: offen"

# MAI-17: radon als CI-Step?
rg -q "radon cc" .github/workflows/contract-gates.yml \
  && echo "MAI-17: radon ✓" || echo "MAI-17: offen"
```

Vergleiche das Ergebnis mit der Heuristik-Tabelle in Schritt 2 und wähle den **ersten** Eintrag, der noch nicht clean ist.

---

## Schritt 2: Task-Auswahl (Heuristik-Tabelle Mai-Welle)

Reihenfolge — strikt nach Blöcken A→B→C→D→E→F, innerhalb eines Blocks **Aufwand S vor M vor L**. Block A blockiert v1.0-Output-Vertrag-Final-Lock, daher Pflicht-Start.

| Slice | Block | Titel | Aufwand | Risiko | Subagent | Opus-Trigger? |
|---|---|---|---|---|---|---|
| MAI-01 | A | P4.4 Mode-Smokes in CI | S | niedrig | `agora-frontend-worker` | nein |
| MAI-04 | A | Schema-Drift-Gate `--check` | S | niedrig | `agora-refactor-worker` | nein |
| MAI-13 | A | Dependabot #323 + #326 | S | niedrig | `agora-refactor-worker` | nein |
| MAI-02 | B | R4 Evidence-Routing aktiv | M | mittel | `agora-refactor-worker` | **ja** (Layer 1, Spec-ambig) |
| MAI-03 | B | R11 Hypothesen-Slot voll | M | mittel | `agora-refactor-worker` | **ja** (Layer 0 Contract-Touch) |
| MAI-14 | B | Confidence-Contradiction-Penalty | S | niedrig | `agora-refactor-worker` | nein |
| MAI-08 | C | `report_prompts.py` Paket-Split | M | niedrig | `agora-refactor-worker` | nein |
| MAI-09 | C | `markdown.js` → TS | S | niedrig | `agora-frontend-worker` | nein |
| MAI-10 | C | Issue #203 schließen | S | niedrig | `agora-doc-worker` | nein |
| MAI-06 | D | v2-`full_report.md` retiren | L | **hoch** | `agora-refactor-worker` | **ja** (Persistenz-Touch) |
| MAI-12 | D | Fork-Safety `register_at_fork` | M | **hoch** | `agora-refactor-worker` | **ja** (Pool-Touch) |
| MAI-11 | D | PR-Smoke nur RC/Release | S | niedrig | `agora-refactor-worker` | nein |
| MAI-05 | E | Voice-Lint CI-Pflicht | S | niedrig | `agora-refactor-worker` | nein |
| MAI-07 | E | Quote-Marker CSS im Print-PDF | S | niedrig | `agora-frontend-worker` | nein |
| MAI-15 | E | E2E nutzt `persona_detail=compact` | S | niedrig | `agora-frontend-worker` | nein |
| MAI-16 | F | `sync-status.sh --check` als CI-Pflicht | S | niedrig | `agora-refactor-worker` | nein |
| MAI-17 | F | `radon` Komplexitäts-Gate | S | niedrig | `agora-test-worker` | nein |

**Edge-Cases**:
- Mehrere Slices offen, aber unterer Block ist nicht clean → strikt unterer Block zuerst.
- Slice ist offen, aber blockiert auf einen Upstream-Issue → User fragen, ob Reihenfolge brechen.
- Alle Slices clean → Bericht „Mai-Welle abgeschlossen" + Hinweis auf `plan.mai.md`-Iteration und nächste Coverage-Schwellen-Anhebung.

---

## Schritt 3: Sub-Slice-Plan (inline, NICHT als Datei)

Schreibe diesen Block ins Chat:

```
## MAI-<NN> · <Titel>

- Branch: feat/mai-<nn>-<slug>
- Worktree: /Volumes/T7/Projekte/agora-worktrees/mai-<nn>
- Files: <Pfade aus plan.mai.md>
- Akzeptanz: <rg/grep/pytest-Checks aus dem Fix-Slash-Command>
- Test-Set: <pytest-Pfade>
- Refs / Closes: <Issue-Nummer aus Tabelle>
- Implementer: <Sonnet/Opus> via <Subagent>
- Aufwand laut Plan: <S/M/L>
- Commit-Pattern:
  <typ>(<scope>): <kurz> (MAI-<NN>, Refs #<N> | Closes #<N>)
```

Dann **Bestätigung beim User**: „Plan steht. Subagent dispatchen?" — auf `ok`/`1`/`weiter`/`push` direkt weiter; bei allem anderen stoppen und nachfragen.

---

## Schritt 4: Subagent-Dispatch

**4.1 Worktree anlegen** (per `using-git-worktrees`-Skill):

```bash
cd /Volumes/T7/Projekte/agora
git fetch origin --quiet
WT=/Volumes/T7/Projekte/agora-worktrees/mai-<NN>
git worktree add -b feat/mai-<nn>-<slug> "$WT" origin/main
ln -sfn /Volumes/T7/Projekte/agora/frontend/node_modules "$WT/frontend/node_modules"
```

**4.2 Den passenden Fix-Slash-Command als Subagent-Brief verwenden.**

Die Detail-Edits stehen in `.claude/commands/fix-mai-<NN>-*.md` — der Subagent lädt das File und arbeitet stur ab. Du übergibst:

```
description: "MAI-<NN> dispatch"
subagent_type: "<Subagent aus Tabelle>"
prompt: |
  Arbeite im Worktree <WT>. Lies und befolge
  `.claude/commands/fix-mai-<NN>-<slug>.md` Schritt für Schritt.
  Erweitere wo nötig, aber halte dich an die Akzeptanzkriterien.

  Doku-Pflicht:
  - docs/archive/worklogs/<YYYY-MM-DD>-mai-<NN>-arbeitsprotokoll.md (Schema siehe docs/archive/plans/plan.mai.md)
  - CHANGELOG.md [Unreleased] Eintrag

  NICHT: committen, pushen, --no-verify, Force-Pushes, Layer-Sprünge.
```

**4.3 Bei Opus-Trigger** (siehe Heuristik-Tabelle Spalte „Opus-Trigger?"): Subagent läuft trotzdem auf Sonnet, aber du machst zusätzlich einen **Pre-Dispatch-Review** mit `mcp__code-review-graph__get_impact_radius_tool` + `sequential-thinking` (mind. 3 Thoughts) und briefst den Subagent mit erweitertem Risk-Kontext.

---

## Schritt 5: Post-Dispatch-Verifikation

Aus dem Worktree (Haupt-Claude, nicht Subagent):

```bash
cd <worktree-pfad>

# 5.1 Pydantic-Contracts importierbar
cd backend && uv run python -c "
from app.contracts import (
    ReportContractModel, ReportModel, EvidenceMapModel,
    PersonaModel, PersonaQuotaPlan, PersonaQuotaActual
)
print('OK: alle Contracts importierbar')
"

# 5.2 Schema-Dump idempotent
cd backend && uv run python -m app.contracts.dump_schemas
cd .. && git diff --exit-code schemas/ \
  || { echo "::error::Schemas gedriftet"; exit 1; }

# 5.3 Contract-Tests strikt
cd backend && uv run pytest tests/contracts/ -x -v

# 5.4 Volltest backend
cd backend && uv run pytest -x -q

# 5.5 (falls Frontend-Slice) Frontend-Tests + Type-Check + Build
cd frontend && npm run check
```

Bei rot: **abort**, Fehler-Output an User. Optional einmaliger Re-Dispatch an denselben Subagent mit konkretem Fehler-Brief — aber **kein** Auto-Fix-Loop.

---

## Schritt 6: Commit + Push (Haupt-Claude)

```bash
cd <worktree-pfad>
git add <konkrete files, nicht ".">
git commit -m "$(cat <<'INNER'
<typ>(<scope>): <kurz> (MAI-<NN>, Refs #<N> | Closes #<N>)

<Body — was, warum, Tests, Akzeptanz>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
INNER
)"

git fetch origin --quiet
git merge-base --is-ancestor origin/main HEAD \
  && git push origin HEAD:main \
  || { echo "::error::FF nicht möglich, rebase nötig"; exit 1; }
```

Bei `Closes #N`: nach Push `gh issue view <N>` prüfen.

---

## Schritt 7: Bericht (Format)

```
✅ MAI-<NN> · <Titel> durch
- Branch: <name> → origin/main (FF)
- Commit: <SHA>
- Issue: <Closes/Refs #N>
- Tests: <X passed, Y skipped>
- Implementer: <Sonnet/Opus> via <Subagent>

Nächster Slice (Heuristik):
- MAI-<MM>: <Titel> · Aufwand <S/M/L> · Subagent <Name>

Tippe `/agora-mai-next-task` für den nächsten Schritt.
```

Optional bei Block-Abschluss (z. B. Block A fertig): zusätzlicher Block mit „🏁 Block <X> abgeschlossen, P4.4 final-gated, v1.0-Output-Vertrag closed".

---

## Schritt 8: Worktree-Cleanup (nur bei erfolgreichem Push)

```bash
cd /Volumes/T7/Projekte/agora
git worktree remove <worktree-pfad>
git branch -D feat/mai-<nn>-<slug>
```

Bei rot oder abgebrochen: Worktree **stehen lassen**.

---

## NICHT machen

- Kein Edit am Code im **Haupt-Claude** während der Subagent läuft.
- Kein zweiter, paralleler Dispatch auf denselben Worktree.
- Kein `--no-verify`, kein `--force` auf main, kein Amend gepushter Commits.
- Keine ZIPs, `.playwright-mcp/`, `__pycache__/` stagen.
- Keine Block-Sprünge gegen die Heuristik-Tabelle ohne explizite User-Anweisung.
- Kein Auto-Fix-Loop bei rotem Verify — abbrechen, Fehler reporten, optional **einmal** Subagent-Re-Dispatch mit konkretem Fehler-Brief.
- Keine `Closes #N`-Referenz, wenn der Issue nicht *vollständig* durch den Slice abgedeckt ist (sonst `Refs #N`).
- Kein Sammel-Commit — ein Slice = ein Commit.
- Kein Push, wenn `gh issue list --label P0` einen blockierenden P0-Bug öffnet, der seit dem letzten Push entstanden ist.

---

## Kontextquellen

- `docs/archive/plans/plan.mai.md` (Status-Tabelle)
- `docs/archive/plans/plan.heuristic-mai.md` (Subagent-Mapping)
- `.claude/commands/fix-mai-<NN>-*.md` (Detail-Briefs)
- `CLAUDE.md` § Subagent-Routing + Opus-Trigger
- `verify-after-subagent.md` als verbindlicher Verify-Gate
