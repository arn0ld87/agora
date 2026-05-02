---
description: Master-Orchestrator — pickt nächsten offenen Sub-Slice aus PLAN.md, dispatched passenden Subagent (Cost-Mix Opus/Sonnet/Haiku), verifiziert, committet, pusht.
allowed-tools: Read, Bash, Grep, Glob, Edit, Write, TodoWrite, Task
---

# /agora-next-task — Plan-Orchestrator

Du bist der **Orchestrator**, nicht der Implementer. Du wählst den nächsten Slice, schreibst einen knappen Plan, dispatched den passenden Subagent, verifizierst, committest, pusht und meldest. Der Haupt-Claude editiert *nicht* selber Code — das ist Aufgabe des dispatched Subagent.

Hardstops: kein Auto-Fix-Loop bei rotem Verify, keine Layer-Sprünge gegen die Tabelle, keine Force-Pushes auf `main`.

---

## Schritt 0: Setup-Anker

Pfade & Default:

- Repo-Root: `/mnt/brain/Projekte/Agora`
- PLAN.md: `/mnt/brain/Projekte/Agora/PLAN.md` (autoritativ)
- Verify-Slash: `/verify-after-subagent`
- Default-Branch-Ziel: `main` (FF-Push, kein PR)
- User-Trait-Sticky: Deutsch, knapp, direkt; ein Sub-Slice = ein Commit + ein Arbeitsprotokoll unter `docu/<datum>-<slice>-arbeitsprotokoll.md`; CHANGELOG `[Unreleased]` Pflicht.

Lies sofort die ersten ~120 Zeilen von `PLAN.md` (Teile A + B), damit du die Task-Tabelle im Kopf hast.

---

## Schritt 1: Status-Scan (Bash, parallel wo möglich)

```bash
cd /mnt/brain/Projekte/Agora

# 1.1 origin/main aktuell holen + letzte Commits
git fetch origin --quiet
echo "=== origin/main letzte 10 ==="
git log origin/main --oneline -10

# 1.2 offene GitHub-Issues
echo "=== offene Issues ==="
gh issue list --state open --limit 30 --json number,title,labels \
  | jq -r '.[] | "#\(.number) \(.title)"' | head -30

# 1.3 Layer-0 Schema-Drift?
echo "=== Layer 0 02a Schema-Drift ==="
rg -n "schema_version.*1" backend/app/ || echo "  → clean"
rg -n "EXPORT_SCHEMA_VERSION = 1" backend/ || echo "  → clean"

# 1.4 Layer-0 Pydantic-Verdrahtung im API?
echo "=== Layer 0 02b API-Boundary ==="
rg -n "ReportContractModel\.model_validate|ReportContract\.model_validate|EvidenceMapModel\.model_validate" backend/app/api/report.py \
  || echo "  → noch nicht verdrahtet"

# 1.5 Layer-0 Pydantic-Verdrahtung im Generator?
echo "=== Layer 0 02c Generator-Output ==="
rg -n "ReportContractModel|EvidenceMapModel" backend/app/services/report_agent.py \
  || echo "  → noch nicht verdrahtet"

# 1.6 Layer-1 Anti-Dekoration?
echo "=== Layer 1 Task 07 Anti-Dekoration ==="
rg -n "global_items\[:2\]" backend/app/services/ \
  || echo "  → clean"

# 1.7 Layer-2 Prompt-Semantik?
echo "=== Layer 2 Task 09 Prompt-Semantik ==="
rg -nci "future prediction|rehearsal of the future|god's eye view" backend/app/services/report_prompts.py \
  || echo "  → clean"

# 1.8 Layer-1 chat_json strict-Mode?
echo "=== Layer 1 Task 05 chat_json ==="
rg -n 'response_format=.*"json_object"' backend/app/utils/llm_client.py \
  && echo "  → noch JSON-Mode, strict-Schema offen" \
  || echo "  → schon strict"

# 1.9 Layer-1 Persona-Quoten?
echo "=== Layer 1 Task 06 Persona-Quoten ==="
rg -n "PersonaQuotaPlan" backend/app/services/prepare_service.py backend/app/services/oasis_profile_generator.py 2>&1 \
  || echo "  → keine Quoten-Validation"

# 1.10 Layer-3 Original-Quotes (Task 12)?
echo "=== Layer 3 Task 12 Original-Quotes mit Provenance ==="
rg -n "provenance|source_id_anchor" backend/app/services/report_agent.py 2>&1 \
  || echo "  → keine Provenance-Anker"

# 1.11 Layer-4 Step4Report.vue strict-Zod?
echo "=== Layer 4 Task 15 Step4Report.vue strict-Zod ==="
rg -n "reportContract|ReportContractZod" frontend/src/components/Step4Report.vue 2>&1 \
  || echo "  → toleranter Renderer"
```

Dieser Scan ist die einzige Quelle der Wahrheit für „was ist offen". Vergleiche das Ergebnis mit der Heuristik-Tabelle in Schritt 2 und wähle den **ersten** Eintrag, der noch nicht clean ist.

---

## Schritt 2: Task-Auswahl (Heuristik-Tabelle)

Reihenfolge — strikt **Layer-Bottom-Up**, innerhalb eines Layers **Aufwand S vor M vor L**:

| Reihe | Layer | Task | Titel | Aufwand | Subagent | Modell |
|---|---|---|---|---|---|---|
| 1 | 0 | 02b | Pydantic in `api/report.py` verdrahten | M | `agora-refactor-worker` | Sonnet |
| 2 | 0 | 02c | Pydantic in `report_agent.py` verdrahten | M | `agora-refactor-worker` | Sonnet |
| 3 | 1 | 07 | Anti-Dekoration `global_items[:2]` raus | S | `agora-refactor-worker` | Sonnet |
| 4 | 2 | 09 | Prompt-Semantik (8 String-Stellen) | S | `agora-doc-worker` | Haiku |
| 5 | 1 | 05 | `chat_json` auf strict-Schema | M | `agora-refactor-worker` | Sonnet |
| 6 | 1 | 06 | `PersonaQuotaPlan` verdrahten | M | `agora-refactor-worker` | Sonnet |
| 7 | 1 | 08 | Confidence-Kalibrierung + Penalty | M | `agora-refactor-worker` | Sonnet |
| 8 | 2 | 10 | DACH-Voice-Constraints | M | `agora-doc-worker` | Haiku |
| 9 | 2 | 11 | Voice-Lint CI-Check | S | `agora-test-worker` | Sonnet |
| 10 | 3 | 12 | Original-Quotes + Provenance-Anker | M | `agora-refactor-worker` | Sonnet |
| 11 | 3 | 13 | Time-Series-Sampling + Section-Dedup | M | `agora-refactor-worker` | Sonnet |
| 12 | 3 | 14 | Cluster-Naming deterministisch | S | `agora-refactor-worker` | Sonnet |
| 13 | 4 | 15 | `Step4Report.vue` strict-Zod | M | `agora-frontend-worker` | Sonnet |
| 14 | 4 | 16 | Diff/Confidence-UI (#76) | L | `agora-frontend-worker` | Sonnet |
| 15 | 5 | 17 | Baseline-Eval-Suite + Snapshots | L | `agora-test-worker` | Sonnet |

**Cost-Mix-Begründung** (PLAN.md Teil G): Architektur-Reasoning bleibt im Haupt-Claude (Opus). Refactor + Tests an Sonnet-Subagents. String-Lasten (Prompts, Doku, Voice-Constraints) an Haiku. Auditor (`agora-evidence-auditor`) ist read-only und wird *vor* P0/P1-Releases als Verify-Layer dispatcht, nicht als primärer Implementer.

**Edge-Cases**:

- Mehrere Reihen offen, aber unterer Layer ist nicht clean → strikt unterer Layer zuerst.
- Reihe ist offen, aber blockiert auf einen Issue, der auf `Closes` wartet → User fragen, ob Plan-Order brechen.
- Alle Reihen clean → Bericht „PLAN.md komplett, M1–M6 fertig" + Hinweis auf PLAN.md-Iteration.

---

## Schritt 3: Sub-Slice-Plan (kurzer Markdown-Block, NICHT in Datei)

Schreibe inline:

```
## Sub-Slice <Task-ID> · <Titel>

- Branch: feat/layer-<N>-task-<XX>-<slug>  (frischer Worktree von origin/main per `using-git-worktrees`)
- Files: <Pfade aus PLAN.md Tabelle>
- Akzeptanz:
  - <konkrete rg/grep/pytest-Checks>
- Test-Set:
  - tests/contracts/, tests/test_<scope>.py
- Refs / Closes: <Issue-Nummer>
- Subagent: <name> (Modell <Sonnet/Haiku>)
- Aufwand laut PLAN.md: <S/M/L>
- Commit-Pattern:
  <typ>(<scope>): <kurz> (Sub-Slice <ID>, Refs #<N> | Closes #<N>)
```

Dann **Bestätigung beim User einholen**: „Plan steht. Soll ich dispatchen?" — auf `ok`/`1`/`weiter`/`push` direkt weiter; auf alles andere stoppen und nachfragen.

---

## Schritt 4: Subagent-Dispatch

Spawn worktree (per `using-git-worktrees`-Skill: `git worktree add -b <branch> <path> origin/main`), dann `Agent`-Tool mit:

- `subagent_type`: aus Tabelle Schritt 2
- `description`: 3–5 Worte (z. B. „Anti-Dekoration global_items[:2]")
- `prompt`: muss enthalten
  - **Worktree-Pfad** als absolute Basis (alle Edits dort, nicht im Hauptrepo!)
  - **Konkrete Edits** mit `Pfad:Linie` aus PLAN.md
  - **Akzeptanz** aus Sub-Slice-Plan
  - **Test-Set** mit pytest-Aufrufen
  - **Pflicht-Verifikation** wie in `verify-after-subagent.md`
  - **Commit-Pattern** (aber: Subagent **committet nicht selbst**, sondern meldet zurück, dass alles grün ist)
  - **Doku-Pflicht**: Arbeitsprotokoll unter `docu/<datum>-<slice>-arbeitsprotokoll.md` + `CHANGELOG.md` `[Unreleased]`-Eintrag

Subagent-Output erwartest du als knappen Bericht (was geändert, welche Tests, Commit-bereit ja/nein).

---

## Schritt 5: Post-Subagent-Verifikation (Sequential Gate)

Aus dem Worktree:

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
cd frontend && npm run check || true
```

Bei rot: **abort**, Fehler-Output an User, kein Auto-Fix.

---

## Schritt 6: Commit + Push

```bash
cd <worktree-pfad>
git add <konkrete files, nicht "."!>
git commit -m "$(cat <<'EOF'
<typ>(<scope>): <kurz> (Sub-Slice <ID>, Refs #<N> | Closes #<N>)

<Body — was, warum, Tests, Akzeptanz>
EOF
)"

# FF-Push direkt nach origin/main
git fetch origin --quiet
git merge-base --is-ancestor origin/main HEAD \
  && git push origin HEAD:main \
  || { echo "::error::FF nicht möglich, rebase nötig"; exit 1; }
```

Bei `Closes #N`: nach erfolgreichem Push verifizieren mit `gh issue view <N>` dass GitHub den Issue tatsächlich geschlossen hat.

---

## Schritt 7: Bericht (Format)

```
✅ Sub-Slice <ID> · <Titel> durch
- Branch: <name> → origin/main (FF)
- Commit: <SHA>
- Issue: <Closes/Refs #N>
- Tests: <X passed, Y skipped>
- Subagent: <name> (<Modell>)

Nächster Sub-Slice (Heuristik):
- Reihe <K>: Task <ID> · <Titel> · Aufwand <S/M/L> · Subagent <name> (<Modell>)

Tippe `/agora-next-task` für den nächsten Schritt.
```

Optional bei Milestone-Abschluss (z. B. M1 fertig nach allen Layer-0-Tasks): zusätzlicher Block mit „🏁 M<N> abgeschlossen, X Issues closed, Y Tests grün".

---

## Schritt 8: Worktree-Cleanup (nur bei erfolgreichem Push)

```bash
cd /mnt/brain/Projekte/Agora
git worktree remove <worktree-pfad>
git branch -D <branch>   # lokal weg, da bereits in main per FF
```

Bei rot oder abgebrochen: Worktree **stehen lassen**, damit der User per Hand fixen kann.

---

## NICHT machen

- Kein Edit am Code im **Haupt-Claude** während der Subagent-Dispatch läuft.
- Kein `--no-verify`, kein `--force` auf main, kein Amend gepushter Commits.
- Keine ZIPs, `.playwright-mcp/`, `__pycache__/` stagen (sind in `.gitignore`, aber stage-Filter prüfen).
- Keine Layer-Sprünge gegen die Heuristik-Tabelle ohne explizite User-Anweisung.
- Kein Auto-Fix-Loop bei rotem Verify — abbrechen, Fehler reporten.
- Keine `Closes #N`-Referenz, wenn der Issue nicht *vollständig* durch diesen Slice abgedeckt ist (sonst nur `Refs #N`).
- Keine eigenmächtigen `Big Update`-Sammel-Commits — ein Sub-Slice = ein Commit.
- Kein Push, wenn `gh issue list` einen blockierenden P0-Bug öffnet, der seit dem letzten Push entstanden ist.

---

## Kontextquellen

- PLAN.md (Teile A–H)
- bestehende Slash-Commands `.claude/commands/fix-task-*.md` als Referenz für Edits
- `.claude/agents/agora-*.md` als Subagent-Vertrag
- `verify-after-subagent.md` als verbindlicher Verify-Gate
- letzte 10 Commits auf `origin/main` als Stil-Anker (Commit-Sprache, Slice-Granularität)
