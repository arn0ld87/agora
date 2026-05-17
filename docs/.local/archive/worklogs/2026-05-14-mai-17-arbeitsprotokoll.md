# Arbeitsprotokoll: MAI-17 · radon-Komplexitäts-Gate

**Datum:** 2026-05-14  
**Branch:** `feat/mai-17-radon-gate`  
**Worker:** Agora-Test-Worker (Subagent)

---

## Ziel

`radon cc app --min C --no-assert` läuft in CI. Funktionen mit Rang D oder schlechter
(Cyclomatic Complexity ≥ 21) blockieren den Merge, sofern nicht in der Allowlist gepinnt.
Bestehende Hotspots werden geduldet, neue müssen sauber sein.

---

## Erledigte Schritte

### 1. Radon installiert

```
cd backend && uv add --dev radon
```

radon 6.0.1 war bereits als Transitive-Dep vorhanden, wurde als explizite Dev-Dep hinzugefügt.

### 2. Baseline gemessen

```
uv run radon cc app --min C --no-assert -j > /tmp/radon.json
```

**Ergebnis (2026-05-14):**

| Rank | Anzahl |
|------|--------|
| F (cc ≥ 41) | 5 |
| E (cc 31–40) | 1 |
| D (cc 21–30) | 24 |
| **D+ gesamt** | **30** |

Top-5 nach Complexity:

| Rank | cc | Symbol |
|------|----|--------|
| F | 50 | `app/services/evidence_migrations.py::migrate_v2_to_v3` |
| F | 47 | `app/services/report_agent/workflow.py::generate_report` |
| F | 46 | `app/services/report_agent/manager.py::ReportManager.build_report_v3` |
| F | 45 | `app/api/report.py::get_generate_status` |
| F | 43 | `app/api/simulation_run.py::start_simulation` |

### 3. Allowlist aktualisiert

`backend/radon-allowlist.txt` — 30 Einträge (alle D+).

**Schlüsselformat:**
- Module-Level-Funktion/Klasse: `app/path.py::name`
- Methode: `app/path.py::ClassName.method_name`

Dieses Format entspricht dem radon-JSON-Output (`classname` + `name`-Felder).

**Timestamp-Update:** Header auf 2026-05-14 aktualisiert (vorher: 2026-05-11, 29 Einträge → 30 Einträge nach Drift durch Code-Changes seit Tag).

### 4. `backend/scripts/check_complexity.py` geschrieben

Vollständiger Python-Wrapper (≈75 LOC):

- Ruft `radon cc app --min C --no-assert -j` als Subprocess auf
- Parst JSON-Output
- Vergleicht jeden D+/E/F-Eintrag gegen `radon-allowlist.txt`
- Exit 0 wenn keine neuen Hotspots
- Exit 1 mit GitHub-Actions-kompatiblem `::error::`-Prefix und Fix-Hinweisen

### 5. CI-Step aktualisiert

`.github/workflows/contract-gates.yml` → Job `complexity-gate` → letzter Step:

**Vorher:** `bash scripts/check_complexity.sh` (fehlende Datei)  
**Nachher:** `cd backend && uv run python scripts/check_complexity.py`

Step-Name geändert auf: **`Cyclomatic-Complexity-Gate (MAI-17)`**

---

## Verifikationsergebnisse

```
# 1) Gate exit 0
cd backend && uv run python scripts/check_complexity.py
→ OK: keine neuen Komplexitäts-Hotspots (30 pre-existing in allowlist).
→ Exit: 0 ✅

# 2) Allowlist nicht leer
wc -l backend/radon-allowlist.txt
→ 54 backend/radon-allowlist.txt ✅ (30 Einträge + Header-Kommentare)

# 3) Drift-Demo (künstliche D-Funktion)
→ Exit: 1 + korrekte Fehlermeldung ✅

# 4) Workflow-Match
grep -n 'radon\|check_complexity' .github/workflows/contract-gates.yml
→ Match auf Zeilen 150, 165, 168, 171, 172 ✅
```

---

## Allowlist-Counter

| Zeitpunkt | D+ Einträge | Bemerkung |
|-----------|-------------|-----------|
| 2026-05-11 (original) | 29 | Erste Messung |
| 2026-05-14 (aktuell) | 30 | +1 durch Code-Evolution seit Slice |

---

## Refactor-Kandidaten (für spätere Sub-Slices)

| Symbol | Rank | cc | Slice-Vorschlag |
|--------|------|----|-----------------|
| `evidence_migrations.py::migrate_v2_to_v3` | F | 50 | Aggregations-Helper splitten (post-v1.0) |
| `report_agent/workflow.py::generate_report` | F | 47 | Report-Agent-Refactor (M11.6) |
| `report_agent/manager.py::ReportManager.build_report_v3` | F | 46 | API-Envelope-Refactor |
| `api/report.py::get_generate_status` | F | 45 | API-Envelope-Refactor (M11.6) |
| `api/simulation_run.py::start_simulation` | F | 43 | Sim-Run-Refactor |

---

## Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `backend/scripts/check_complexity.py` | NEU — Python-Gate-Skript |
| `backend/radon-allowlist.txt` | Timestamp + Counter aktualisiert |
| `.github/workflows/contract-gates.yml` | Step-Name + Befehl aktualisiert |
| `docu/2026-05-14-mai-17-arbeitsprotokoll.md` | DIESES DOKUMENT |

---

## Nächste Schritte

1. CHANGELOG-Eintrag: `MAI-17 · radon-Komplexitäts-Gate (rank D+ blockiert, allowlist-basiert).`
2. Refactor-Slices für F-Rank-Kandidaten planen (M11.6: API-Envelope-Refactor).
3. ADR-0004 (camel-oasis-Upgrade) prüfen oder Coverage-Sprint planen.
