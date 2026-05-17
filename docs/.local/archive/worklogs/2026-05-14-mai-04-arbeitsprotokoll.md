# MAI-04 — Schema-Drift-Gate: Arbeitsprotokoll

**Slice-ID:** MAI-04
**Titel:** Schema-Drift-Gate `dump_schemas --check` hart in CI
**Implementer:** Sonnet 4.6 via agora-refactor-worker
**Datum:** 2026-05-14

## Kontext

R12 fordert ein CI-Gate, das Pydantic-Contracts und `schemas/`-Dateien byte-genau synchron haelt.
Der `schema-drift`-Job in `contract-gates.yml` rief `dump_schemas --check` bereits auf, aber:

1. `check_one` nutzte `all()`-Kurzschluss — bei einem Drift-Fund wurden nachfolgende Schemas nicht geprueft.
2. Ausgabe war `"drift: ..."` auf stderr ohne GitHub-Actions-`::error::`-Annotation — keine Merge-Blockierung.
3. Emojis (`checkmark`) in stdout — verboten laut Konventionen.
4. Step-Name war `Check generated schemas from Pydantic models`, nicht MAI-04-gekennzeichnet.

## Aenderungsliste

### `backend/app/contracts/dump_schemas.py`

- `check_one()` neu: gibt `::error::Schema-Drift (MAI-04): ...`-Zeilen auf stderr aus (GitHub-Actions-kompatibel).
- Kurzschluss-`all()` ersetzt durch vollstaendige List-Comprehension: alle 19 Schemas werden geprueft, auch wenn fruehe fehlschlagen.
- Zusammenfassung am Ende: `::error::Schema-Drift (MAI-04): N von 19 Schemas weichen ab.`
- Emojis entfernt, ersetzt durch `OK: schemas/<filename>` auf stdout.
- Docstring um `--check`-Modus-Beschreibung erweitert.
- `dump_one`/`main`-Dump-Pfad: `print` durch `sys.stdout.write` ersetzt.

**LOC-Delta:** +51 / -15 (netto +36)

### `.github/workflows/contract-gates.yml`

- Step-Name von `Check generated schemas from Pydantic models` zu `Schema-Drift-Check (MAI-04)` umbenannt.
- Kommentar `# exit 1 bei nicht-committeten Schema-Aenderungen -> blockiert Merge.` ergaenzt.

**LOC-Delta:** +2 / -1 (netto +1)

## Verify-Output

### Check 1: `--check` ohne Drift, exit 0

```
OK: schemas/branch-comparison.schema.json
...
OK: schemas/api-keys-list-response.schema.json
OK: alle 19 Schemas matchen schemas/
Exit: 0
```

### Check 2: `--check` mit kuenstlichem Drift an `schemas/persona.schema.json`, exit 1

```
::error::Schema-Drift (MAI-04): Inhalt weicht ab: schemas/persona.schema.json
  Fix: cd backend && uv run python -m app.contracts.dump_schemas && git add schemas/
::error::Schema-Drift (MAI-04): 1 von 19 Schemas weichen ab. ...
OK: schemas/branch-comparison.schema.json
...
OK: schemas/api-keys-list-response.schema.json
Exit: 1
```

(Revert: `git checkout -- schemas/persona.schema.json`)

### Check 3: Workflow-Syntax

```
npx @action-validator/cli@latest .github/workflows/contract-gates.yml
Exit: 0
```

### Check 4: Contract-Tests

```
146 passed in 1.02s
Exit: 0
```

### Check 5: Volltest

```
1 failed, 30 passed, 2 skipped, 7 deselected
```

`test_add_progress_callback_sets_progress_detail_on_task_manager` schlaegt fehl mit
`LLM_API_KEY not configured`. **Pre-existierender Fehler** — verifiziert: schlaegt auch auf
`origin/main` ohne MAI-04-Aenderungen fehl (lokale Umgebung ohne LLM_API_KEY). Nicht im Scope
von MAI-04.

## Schritt-Folge Block A

- MAI-01: Report-Mode-Smokes CI (done)
- MAI-04: Schema-Drift-Gate (done — dieser Slice)
- MAI-13: Dependabot mistune/pygments Bump (done, auf origin/main)
- Naechster: weitere offene MAI-Block-A-Eintraege
