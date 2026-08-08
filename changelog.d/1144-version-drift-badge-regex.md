### Fixed (Drift-Fixer erkennt den README-Version-Badge wieder — 2026-08-08)

- **`check_version_drift.py` meldete „No version badge found in README.md", obwohl Zeile 11 einen Badge trägt:** Die Regex matchte nur `badge/Version-` (großes V), das README nutzt seit dem Redesign `badge/version-<semver>-<hexfarbe>`. Lese- und Schreib-Regex matchen jetzt case-insensitiv; beim Release-Cut 0.9.3 musste der Badge deshalb manuell nachgezogen werden. Regressionstests decken das aktuelle Kleinschreibungs-Format mit Hex-Farbe für Read- und Write-Pfad ab.
