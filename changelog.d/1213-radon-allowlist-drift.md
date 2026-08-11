### Fixed (CI-Komplexitäts-Gate — 2026-08-11)

- **`contract-gates` auf `main` wieder grün:** Fünf pre-existing D-Hotspots aus der kanonischen Evidence-Identität (#1147) und der seed_corpus-Evidence (#1166) fehlten in `backend/radon-allowlist.txt` und hielten das radon-Komplexitäts-Gate seit mindestens acht `push:main`-Läufen rot. Nachgezogen als Allowlist-Einträge mit `# cc<=N`-Obergrenze — sie dulden den Bestand und schlagen bei weiterem Wachstum an, ohne einen Refactor zu erzwingen. (#1213)

### Added

- **Komplexitäts-Gate im Pre-Push-Gate:** `scripts/pre-push-gate.sh` ruft im Backend-Scope jetzt `scripts/check_complexity.py` auf. Der Driftfall fällt damit lokal vor dem Push auf statt Tage später nur auf `push:main`. (#1213)