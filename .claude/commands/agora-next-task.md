---
description: Master-Orchestrator — pickt nächsten offenen Sub-Slice aus PLAN.md, dispatched Sonnet (via sonnet:sonnet-rescue) als Implementer, verifiziert, committet, pusht.
allowed-tools: Read, Bash, Grep, Glob, Edit, Write, TodoWrite, Agent, AskUserQuestion
---

# /agora-next-task — Plan-Orchestrator (Codex-Dispatch)

Du bist der **Orchestrator**, nicht der Implementer. Du wählst den nächsten Slice, schreibst einen knappen Plan, dispatched **Sonnet** (via `sonnet:sonnet-rescue` Subagent) als Implementer, verifizierst, committest, pusht und meldest. Der Haupt-Claude editiert *nicht* selber Code — das ist Aufgabe von Sonnet im Worktree.

Hardstops: kein Auto-Fix-Loop bei rotem Verify, keine Layer-Sprünge gegen die Tabelle, keine Force-Pushes auf `main`.

---

## Schritt 0: Setup-Anker

Pfade & Default:

- Repo-Root: `/Volumes/T7/Projekte/agora`
- PLAN.md: `/Volumes/T7/Projekte/agora/PLAN.md` (autoritativ)
- Verify-Slash: `/verify-after-subagent`
- Default-Branch-Ziel: `main` (FF-Push, kein PR)
- Implementer: **Sonnet** via `sonnet:sonnet-rescue` Subagent (siehe Schritt 4)
- User-Trait-Sticky: Deutsch, knapp, direkt; ein Sub-Slice = ein Commit + ein Arbeitsprotokoll unter `docu/<datum>-<slice>-arbeitsprotokoll.md`; CHANGELOG `[Unreleased]` Pflicht.

Lies sofort die ersten ~120 Zeilen von `PLAN.md` (Teile A + B), damit du die Task-Tabelle im Kopf hast.

---

## Schritt 1: Status-Scan (Bash, parallel wo möglich)

```bash
cd /Volumes/T7/Projekte/agora

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

| Reihe | Layer | Task | Titel | Aufwand | Codex-Effort | Codex-Modell |
|---|---|---|---|---|---|---|
| 1 | 0 | 02b | Pydantic in `api/report.py` verdrahten | M | medium | default |
| 2 | 0 | 02c | Pydantic in `report_agent.py` verdrahten | M | medium | default |
| 3 | 1 | 07 | Anti-Dekoration `global_items[:2]` raus | S | low | spark |
| 4 | 2 | 09 | Prompt-Semantik (8 String-Stellen) | S | low | spark |
| 5 | 1 | 05 | `chat_json` auf strict-Schema | M | medium | default |
| 6 | 1 | 06 | `PersonaQuotaPlan` verdrahten | M | medium | default |
| 7 | 1 | 08 | Confidence-Kalibrierung + Penalty | M | medium | default |
| 8 | 2 | 10 | DACH-Voice-Constraints | M | low | spark |
| 9 | 2 | 11 | Voice-Lint CI-Check | S | medium | default |
| 10 | 3 | 12 | Original-Quotes + Provenance-Anker | M | medium | default |
| 11 | 3 | 13 | Time-Series-Sampling + Section-Dedup | M | medium | default |
| 12 | 3 | 14 | Cluster-Naming deterministisch | S | low | default |
| 13 | 4 | 15 | `Step4Report.vue` strict-Zod | M | medium | default |
| 14 | 4 | 16 | Diff/Confidence-UI (#76) | L | high | default |
| 15 | 5 | 17 | Baseline-Eval-Suite + Snapshots | L | high | default |

**Cost-Mix-Begründung**: Architektur-Reasoning bleibt im Haupt-Claude (Opus). Implementierung an Sonnet (claude-sonnet-4). Refactor- und Test-Tasks → `--effort medium`. String-/Prompt-/Voice-Tasks → `--effort low` + ggf. `--model claude-sonnet-4` (das ist `sonnet`). Größere, mehrschrittige Tasks → `--effort high`. Verify bleibt Bash-only und läuft im Haupt-Claude.

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
- Implementer: Sonnet (Effort <low/medium/high>, Modell <default/sonnet>)
- Aufwand laut PLAN.md: <S/M/L>
- Commit-Pattern:
  <typ>(<scope>): <kurz> (Sub-Slice <ID>, Refs #<N> | Closes #<N>)
```

Dann **Bestätigung beim User einholen**: „Plan steht. Soll ich Codex dispatchen?" — auf `ok`/`1`/`weiter`/`push` direkt weiter; auf alles andere stoppen und nachfragen.

---

## Schritt 4: Codex-Dispatch (via `codex:codex-rescue`)

**4.1 Worktree anlegen** (per `using-git-worktrees`-Skill):

```bash
cd /Volumes/T7/Projekte/agora
git fetch origin --quiet
WT=/Volumes/T7/Projekte/agora-worktrees/<branch>
git worktree add -b <branch> "$WT" origin/main
```

**4.2 Sonnet via Agent-Tool dispatchen** mit `subagent_type: "sonnet:sonnet-rescue"`.

Der `prompt` ist ein vollständig selbstständiger Codex-Brief und enthält:

- **Worktree-Pfad** als absolute Basis (alle Edits dort, nicht im Hauptrepo!) — `cd <WT>` als erste Anweisung im Brief
- **Konkrete Edits** mit `Pfad:Linie` aus PLAN.md
- **Akzeptanz** aus Sub-Slice-Plan (rg/grep-Patterns, die nach dem Run erfüllt sein müssen)
- **Test-Set** mit pytest-Aufrufen (Codex muss diese selbst grün laufen lassen)
- **Doku-Pflicht**: Arbeitsprotokoll unter `docu/<datum>-<slice>-arbeitsprotokoll.md` + `CHANGELOG.md` `[Unreleased]`-Eintrag
- **Commit-Pattern als Vorgabe**, aber: Codex **committet nicht selbst**. Stage-Status sauber lassen, alle Edits unstaged oder staged liegen lassen, damit der Haupt-Claude in Schritt 6 committet.
- **Routing-Flags** im Aufruf-Text: `--write` (default; Codex darf editieren), `--effort <low|medium|high>` und ggf. `--model gpt-5.3-codex-spark` aus Tabelle Schritt 2. `--background` nur bei L-Tasks oder wenn explizit gewünscht; sonst Foreground.

**4.3 Beispiel-Aufruf** (innerhalb des Agent-Tools):

```
description: "Sonnet dispatch <task-id>"
subagent_type: "sonnet:sonnet-rescue"
prompt: |
  --write --effort medium
  Arbeite im Worktree <WT>. Ziel: Sub-Slice <ID> · <Titel>.

  Edits:
  - <Pfad:Linie>: <konkret>
  - …

  Akzeptanz nach Run:
  - rg -n '"schema_version".*1' backend/app/  → leer
  - cd backend && uv run pytest tests/contracts/ -x -v  → grün
  - …

  Doku:
  - docu/<datum>-<slice>-arbeitsprotokoll.md anlegen (knapp: was/warum/Tests)
  - CHANGELOG.md [Unreleased] Eintrag

  NICHT: committen, pushen, --no-verify, Force-Pushes, Layer-Sprünge.
```

Sonnet-Output erwartest du als knappen Bericht (was geändert, welche Tests gelaufen, sind alle grün, Stage-Status). Wird `verbatim` durchgereicht — keine Paraphrasierung.

---

## Schritt 5: Post-Codex-Verifikation (Sequential Gate)

Aus dem Worktree (Haupt-Claude, nicht Codex):

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

Bei rot: **abort**, Fehler-Output an User. Optional einmaliger Re-Dispatch an Codex mit `--resume` und konkretem Fehler-Brief — aber **kein** Auto-Fix-Loop.

---

## Schritt 6: Commit + Push (Haupt-Claude, nicht Codex)

```bash
cd <worktree-pfad>
git add <konkrete files, nicht "."!>
git commit -m "$(cat <<'EOF'
<typ>(<scope>): <kurz> (Sub-Slice <ID>, Refs #<N> | Closes #<N>)

<Body — was, warum, Tests, Akzeptanz>

Co-Authored-By: Sonnet (claude-sonnet-4) <noreply@anthropic.com>
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
- Implementer: Sonnet (Effort <low/medium/high>, Modell <default/sonnet>)

Nächster Sub-Slice (Heuristik):
- Reihe <K>: Task <ID> · <Titel> · Aufwand <S/M/L> · Codex-Effort <low/medium/high>

Tippe `/agora-next-task` für den nächsten Schritt.
```

Optional bei Milestone-Abschluss (z. B. M1 fertig nach allen Layer-0-Tasks): zusätzlicher Block mit „🏁 M<N> abgeschlossen, X Issues closed, Y Tests grün".

---

## Schritt 8: Worktree-Cleanup (nur bei erfolgreichem Push)

```bash
cd /Volumes/T7/Projekte/agora
git worktree remove <worktree-pfad>
git branch -D <branch>   # lokal weg, da bereits in main per FF
```

Bei rot oder abgebrochen: Worktree **stehen lassen**, damit der User per Hand fixen kann oder Codex via `/codex:rescue --resume` nachlegen kann.

---

## NICHT machen

- Kein Edit am Code im **Haupt-Claude** während Sonnet läuft. Edits nur durch Sonnet im Worktree.
- Kein zweiter, paralleler Sonnet-Dispatch auf denselben Worktree.
- Kein `--no-verify`, kein `--force` auf main, kein Amend gepushter Commits.
- Keine ZIPs, `.playwright-mcp/`, `__pycache__/` stagen (sind in `.gitignore`, aber stage-Filter prüfen).
- Keine Layer-Sprünge gegen die Heuristik-Tabelle ohne explizite User-Anweisung.
- Kein Auto-Fix-Loop bei rotem Verify — abbrechen, Fehler reporten, optional **einmal** Codex `--resume` mit konkretem Fehler-Brief.
- Keine `Closes #N`-Referenz, wenn der Issue nicht *vollständig* durch diesen Slice abgedeckt ist (sonst nur `Refs #N`).
- Keine eigenmächtigen `Big Update`-Sammel-Commits — ein Sub-Slice = ein Commit.
- Kein Push, wenn `gh issue list` einen blockierenden P0-Bug öffnet, der seit dem letzten Push entstanden ist.
- Kein Codex-Dispatch ohne explizite `--write`-Flag, wenn Edits nötig sind (sonst läuft Codex read-only).
- Kein Aufruf von `codex:rescue` direkt als Slash-Command aus diesem Orchestrator — immer `Agent(subagent_type: "codex:codex-rescue")`, sonst hängt sich die Session auf.

---

## Kontextquellen

- PLAN.md (Teile A–H)
- bestehende Slash-Commands `.claude/commands/fix-task-*.md` als Codex-Brief-Vorlage
- `sonnet:sonnet-rescue` Subagent-Vertrag (`plugins/sonnet/agents/sonnet-rescue.md`)
- `anthropic-cli-runtime` und `claude-sonnet-4-prompting` Skills für Brief-Qualität
- `verify-after-subagent.md` als verbindlicher Verify-Gate
- letzte 10 Commits auf `origin/main` als Stil-Anker (Commit-Sprache, Slice-Granularität)
