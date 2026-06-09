# M11.5a — Backend Komplexitäts-Gate (radon) — Arbeitsprotokoll

**Datum:** 2026-05-10
**Branch:** feat/m11-5a-backend-radon-gate
**Basis:** origin/main (f117b7b, Phase 7 + Coverage-Step1 komplett)
**Scope:** Layer 9 Tooling (kein Code-Refactor)

---

## Ziel

Cyclomatic-Complexity-Gate einführen, das neue Funktionen mit Class D+ (cc >= 21)
in `backend/app/` per CI blockiert. Bestands-Hot-Spots werden in einer Allow-List
geduldet, bis eigene Refactor-Slices sie beseitigen.

---

## Schwellen-Entscheidung: Class D (cc >= 21) statt "cc > 15"

PLAN.md nennt zwei Schwellen, die sich widersprechen:
- "cc > 15" — das wäre innerhalb Class C (radon: cc 11–20)
- "> C-Klasse" — das bedeutet Class D+, also cc >= 21

**Gewählte Schwelle: cc >= 21 (Class D+)**

Begründung: "cc > 15" bei Klasse C zu fangen würde mit `radon cc -n C` laufen
und bei 15+ Funktionen im Bestand sofort fehlschlagen — das ist keine nützliche
Gate-Schwelle. Der Autor meinte offensichtlich Class D als neue verbotene Zone.
Da radon `D` bei cc = 21 beginnt, ist `-n D` die korrekte Implementierung von
"> Class C". Damit ist die Allow-List granular und besteht nur aus echten
Hot-Spots, nicht aus normalem Code.

---

## Bestands-Messung

**Messung:** 2026-05-10, radon 6.0.1, `radon cc -n D --show-complexity app/`

**Ergebnis: 27 Funktionen mit cc >= 21**

| Klasse | Anzahl |
|--------|--------|
| F (cc >= 41) | 1 |
| E (cc 21–40) | 4 (davon 2 bei cc=33, 1 bei cc=38) |
| D (cc 21–20) | 22 |

**Top 5 nach cc-Wert:**

| Rang | Klasse | cc | Datei | Funktion |
|------|--------|----|-------|----------|
| 1 | F | 44 | `app/api/report.py` | `get_generate_status` |
| 2 | E | 38 | `app/services/report_agent/workflow.py` | `generate_report` |
| 3 | E | 33 | `app/api/simulation_run.py` | `start_simulation` |
| 3 | E | 33 | `app/services/oasis_profile_generator.py` | `OasisProfileGenerator.generate_profiles_from_entities` |
| 5 | D | 30 | `app/services/report_agent/workflow.py` | `generate_section_react` |

**Refactor-Kandidaten für spätere Slices:**
- `app/api/report.py` (F/44): API-Envelope-Refactor passt in M11.6
- `app/services/report_agent/workflow.py` (E/38 + D/30): Report-Agent-Refactor
- `app/api/simulation_run.py` (E/33): Sim-Run-Decomposition
- `app/services/oasis_profile_generator.py` (E/33): OASIS-Profil-Generator-Schnitt

---

## Allow-List

**Datei:** `backend/radon-allowlist.txt`
**Größe:** 27 Einträge

Alle Bestands-Hot-Spots aus der Messung sind eingetragen. Die Allow-List nutzt
Format `<rel-path>::<func>` (relativ zu `backend/`), was exakt dem radon-Output-
Format entspricht (Klassen als `Config`, Methoden als `Class.method`,
Funktionen als `func_name`).

---

## Skript-Implementierung

**Datei:** `scripts/check_complexity.sh`

Das Skript:
1. Wechselt in `REPO_ROOT/backend/`
2. Läuft `uv run radon cc -n D --no-assert app/` in eine Temp-Datei
3. Parst den Output mit einem Python-Inline-Skript (ebenfalls Temp-Datei)
4. Gleicht jeden Eintrag `<file>::<func>` gegen die Allow-List ab
5. Exit 1 wenn unbekannte D/E/F-Funktionen gefunden werden

**Warum Variante B (Funktion-granular) statt Variante A (File-Exclude):**
- File-Excludes würden ganze Files aus dem Gate nehmen — neue D+-Funktionen in
  denselben Files blieben unentdeckt
- Funktion-granulare Allowlist zwingt zu bewusstem Eintrag pro Hot-Spot
- Künftige Refactors können einzelne Einträge aus der List entfernen, ohne den
  ganzen File ausschließen zu müssen

**macOS/Linux-Kompatibilität:** `mktemp -t complexity_filter.XXXXXX` statt
`mktemp --suffix=.py` (GNU-Only). Das Skript läuft auf macOS (lokal) und
Ubuntu (CI).

---

## CI-Job

**Datei:** `.github/workflows/contract-gates.yml`, Job `complexity-gate`

Orientiert am bestehenden `voice-lint`-Job-Pattern:
- `actions/checkout@v6` + `actions/setup-python@v6` (kein SHA-Pin, analog Bestand)
- `timeout-minutes: 5`
- `uv sync --group dev` installiert radon als Dev-Dep
- `bash scripts/check_complexity.sh` führt das Gate aus

---

## Verifikation

### Positiv-Test (Bestand bleibt grün)
```
OK: Keine neuen D/E/F-Klassen-Funktionen ausserhalb der Allow-List.
```

### Negativ-Test (neue D-Funktion ohne Allow-List-Eintrag)
Demo-Funktion mit cc=21 in temporärem `app/`-Unterverzeichnis:
```
::error:: Neue High-Complexity-Funktionen (Cyclomatic Class D+) gefunden:
  D  app/_test_complexity_tmp/__init__.py::new_complex_function

Wenn dies beabsichtigt ist, Zeile in backend/radon-allowlist.txt eintragen:
  app/_test_complexity_tmp/__init__.py::new_complex_function

Jeder neue Allow-List-Eintrag braucht eine Slice-Begruendung im Arbeitsprotokoll.
Exit code: 1
```

### Demo-Funktion erreicht cc=21 (radon-Schwellen-Verifikation)
```
/tmp/cc_demo.py
    F 1:0 f - D (21)
```
Schwelle stimmt: 20 Bedingungen + 1 Basis = cc 21 = Class D.

### Volltest
- `pytest -x -q -m "not llm"`: 1692 passed, 9 skipped
- `ruff check app/ tests/`: All checks passed!
- `mypy app`: Success: no issues found in 132 source files
- `dump_schemas` + `git diff --exit-code schemas/`: schemas: no drift
- `sync-status.sh --check`: OK: docu/STATUS.md in sync

---

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `backend/pyproject.toml` | `radon>=6.0.1` in `[project.optional-dependencies] dev` + `[dependency-groups] dev` |
| `backend/uv.lock` | Lockfile-Update (radon + mando als Dependency) |
| `backend/radon-allowlist.txt` | Neu: 27 Bestands-Einträge + Kommentar-Header |
| `scripts/check_complexity.sh` | Neu: Gate-Skript (Funktion-granularer Allow-List-Filter) |
| `.github/workflows/contract-gates.yml` | Neuer Job `complexity-gate` |
| `CHANGELOG.md` | `[Unreleased] ### Tooling` Bullet |
| `docu/2026-05-10-m11-5a-backend-radon-gate-arbeitsprotokoll.md` | Dieses Dokument |

---

## Bedienungsanleitung für künftige Slices

**Szenario: Neue Funktion landet in Class D+**

1. `bash scripts/check_complexity.sh` failt mit der Funktion im Error-Output.
2. Entscheidung treffen:
   - **Besser:** Funktion sofort refactoren (Loops/Conditions extrahieren), bis cc < 21.
   - **Wenn unvermeidbar:** Eintrag in `backend/radon-allowlist.txt` im Format `<rel-path>::<func>`, plus Begründung im Arbeitsprotokoll des jeweiligen Sub-Slices.
3. Jeder Allow-List-Eintrag braucht eine Slice-Begründung — kein stilles Hinzufügen.

**Szenario: Bestands-Hot-Spot refactort**

1. Eintrag aus `backend/radon-allowlist.txt` entfernen.
2. `bash scripts/check_complexity.sh` muss weiterhin grün bleiben (kein neuer D+-Anteil).
3. Kommentar im Arbeitsprotokoll: welcher Hot-Spot entfernt, neuer cc-Wert.

**Allow-List wächst unkontrolliert?**

Das ist ein Signal: Hot-Spot-Refactor-Slices priorisieren. Die Allow-List ist
kein Dauerlösung, sondern ein temporärer Bestandsschutz.
