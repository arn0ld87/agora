# PR-Workflow

Datei: `docs/runbooks/pr-workflow.md` · Stand: 2026-05-17

## Kernregel

**Nie direkt auf `main` pushen.** Jede Änderung geht durch einen Pull Request.

---

## Workflow-Schritte

### 1. Branch anlegen

```bash
git checkout -b feat/<slice-id>-<kurzbeschreibung>
```

Branch-Naming: `feat/`, `fix/`, `chore/`, `docs/` — gefolgt von Slice-ID und Stichwort.

### 2. Sub-Slice = ein Commit

Jeder Sub-Slice (eine abgeschlossene funktionale Einheit) ist EIN Commit mit
aussagekräftiger Message:

```
feat(P1.1): Pflichtabschnitt-Validator mit cross_stakeholder-Gate

- ReportSectionValidator prüft required_sections gegen ReportV3
- cross_stakeholder_for_high: mindestens 2 Stakeholder bei high confidence
- reject_inferred_in_high_confidence: inferred sources abgelehnt
```

### 3. Quality-Gate VOR Push

```bash
# Pflicht — bricht bei Fehler ab
# Single source of truth: scripts/pre-push-gate.sh (Slice 4.3.3 Maintenance)
# spiegelt 1:1 die CI PR-Smoke-Gates. Lokal + CI laufen identisch.
bash scripts/pre-push-gate.sh          # alles
bash scripts/pre-push-gate.sh backend  # nur Backend (ruff, mypy, contracts, schemas)
bash scripts/pre-push-gate.sh frontend # nur Frontend (lint, typecheck, test, build)
bash scripts/pre-push-gate.sh schemas  # nur Schema-Drift + STATUS.md-Drift
```

> ℹ️ Der einzelne `npm run check`-Aufruf (Root) entfällt — der neue
> `pre-push-gate.sh` deckt Backend + Frontend ab und ist CI-gespiegelt.

### 4. PR erstellen

```bash
git push -u origin feat/<slice-id>-<name>
gh pr create --title "<Typ>(<Slice>): <Titel>" --body "<Beschreibung>"
```

PR-Body muss enthalten:
- **Was** wurde geändert (1 Satz)
- **Warum** (Referenz auf Issue/PLAN.md)
- **Test-Delta** (+N Tests, alle grün)
- **Risk** (niedrig/mittel/hoch + Begründung)

### 5. Gemini-Sichtung (Pflicht)

Vor dem Merge MUSS ein Gemini-basierter Review stattfinden:

- Code-Review-Graph `detect_changes` gegen den PR-Diff
- Gemini analysiert Findings auf: Security, Evidence-Gating-Verletzung,
  Wording-Glossar-Verstoß, Layer-Reihenfolge-Bruch
- Alle HIGH-Findings müssen resolved sein
- MEDIUM-Findings: dokumentierte Akzeptanz oder Fix

### 6. Merge

Erst wenn:
- Alle Quality-Gates grün
- Gemini-Sichtung: 0 HIGH-Findings offen
- Mindestens 1 Human-Review (bei Layer 0–2: 2 Reviews)

```bash
gh pr merge --squash
```

### 7. Cleanup

```bash
git branch -d feat/<slice-id>-<name>
git push origin --delete feat/<slice-id>-<name>
```

---

## Anti-Pattern

- "Ist nur ein kleiner Fix, direkt auf main" → Nein. PR-Pflicht gilt immer.
- Gemini-Sichtung überspringen weil „hatte ich schon manuell geprüft" → Nein. Gemini
  findet strukturelle Muster, die manuelles Review übersieht.
- Merge ohne grüne CI → Nur mit explizitem Admin-Override + dokumentiertem Grund.
