# Arbeitsprotokoll — M11 Phase 6: sync-status.sh Marker-basiert + CI-Gate

**Datum:** 2026-05-09
**Slice:** M11 Phase 6
**Branch:** `feat/m11-phase6-status-sync`

## Ziel

`scripts/sync-status.sh` darf `docs/status.md` nicht mehr komplett überschreiben.
Stattdessen ersetzt es nur die dynamischen Bereiche (Versions- und Test-Count-Tabellen)
über HTML-Comment-Marker. Alle manuell gepflegten Sektionen (Layer-Status,
Coverage-Sektion, Static-Analysis-Gates, Aktuelles Milestone, Aktualisierungs-Protokoll)
bleiben unangetastet.

## Architektur-Entscheidung

**Marker-Sektionen statt Datei-Overwrite.**

Begründung: `docs/status.md` enthält reichhaltigen manuellen Inhalt (Layer-Status,
Backend-/Frontend-Coverage-Roadmaps, Static-Analysis-Gates, ausführliches
Aktualisierungs-Protokoll), der beim alten Full-Overwrite-Ansatz bei jedem
`sync-status.sh`-Lauf auf den M9-Stand zurückgesetzt worden wäre.

Das Skript definiert genau zwei dynamische Blöcke:
- `<!-- BEGIN_AUTOGEN_VERSIONS -->` ... `<!-- END_AUTOGEN_VERSIONS -->` — Versionstabelle
- `<!-- BEGIN_AUTOGEN_TESTS -->` ... `<!-- END_AUTOGEN_TESTS -->` — Test-Count-Tabelle

Der Stand-Datum-Header (`Stand: YYYY-MM-DD`) bleibt absichtlich manuell, weil ein
automatisches Datum in CI bei jedem Tageswechsel drift erzeugen würde.

## Geänderte Dateien

| Datei | Art |
|---|---|
| `docs/status.md` | Marker eingefügt (BEGIN/END_AUTOGEN_VERSIONS + TESTS) |
| `scripts/sync-status.sh` | Kompletter Neubau: Marker-basierte Ersetzung, `--check`-Modus |
| `.github/workflows/contract-gates.yml` | Neuer Job `status-sync-drift` |
| `CHANGELOG.md` | `[Unreleased]` Tooling-Eintrag |
| `docs/2026-05-09-m11-phase6-status-sync-arbeitsprotokoll.md` | dieses Protokoll |

## Implementierungs-Details

### scripts/sync-status.sh

- Liest `docs/status.md` und ersetzt **nur** den Inhalt zwischen den Markern via
  eingebettetem Python3-Einzeiler (`re.sub` mit `re.DOTALL`).
- Marker-Tags selbst bleiben erhalten; nur der Inhalt dazwischen wird überschrieben.
- Fehlt ein Marker → `exit 1` mit klarer Fehlermeldung an stderr.
- `--check`-Modus: kopiert status.md in ein Tempfile, wendet die Ersetzungen an,
  vergleicht mit `diff -q`. Keine Schreiboperation auf die echte Datei.
  Exit 0 bei Sync, Exit 1 bei Drift (mit Diff in stderr).
- Idempotent: Doppellauf auf einer bereits aktualisierten Datei erzeugt keinen Diff.
- Backend-Tests via `pytest --collect-only -q` mit 180 s Timeout, Fallback `unknown`.
- Frontend-Spec-Files via `find` — stabil, kein `npm install` nötig.

### contract-gates.yml

Neuer Job `status-sync-drift` nach `schema-drift`:
- `actions/checkout@v6`, `actions/setup-python@v6` (gleiche Version wie Rest der Datei)
- `uv sync --group dev` für `pytest --collect-only`
- `bash scripts/sync-status.sh --check` → Exit 1 bei Drift

## Test-Schritte (lokal verifiziert)

1. `chmod +x scripts/sync-status.sh` — ausführbar
2. Erster Lauf: `bash scripts/sync-status.sh` — Marker-Bereiche werden befüllt
3. `git diff docs/status.md` — nur die neuen Marker-Zeilen betroffen (keine anderen Sektionen)
4. Doppellauf: `bash scripts/sync-status.sh` — kein neuer diff
5. `--check` bei sync: Exit 0
6. `--check` bei manuell korrumpiertem Inhalt: Exit 1
7. `git diff --exit-code schemas/` — kein Schema-Drift (kein Backend-Code geändert)
8. `cd backend && uv run pytest tests/contracts/ -x -v` — alle Contract-Tests grün

## Marker-Sanity

```
grep -c "BEGIN_AUTOGEN_VERSIONS" docs/status.md  # 1
grep -c "BEGIN_AUTOGEN_TESTS"    docs/status.md  # 1
grep -c "BEGIN_AUTOGEN_HEADER"   docs/status.md  # 0
```

## Out-of-Scope (absichtlich nicht erledigt)

- AGENTS.md / CLAUDE.md Sync (separater Doku-Slice)
- `sync-status.sh` als Pre-Commit-Hook verdrahten (Folge-Slice)
- HEADER-Marker in status.md (würde CI-Tageswechsel-Drift erzeugen → bewusst manuell)
