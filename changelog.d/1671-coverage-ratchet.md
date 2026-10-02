### Added

- **Coverage-Ratchet und Schönungs-Check gegen `v0.9.6`:**
  `backend/scripts/check_coverage.py --integrity` sperrt gesunkene
  `line_min`/`branch_min` ohne Maintainer-Freigabe (`lowering_approval`),
  neue `omit`-/`exclude`-Einträge, engeres `source`/`include`, eine neue
  `.coveragerc` sowie wachsende No-Cover-Pragmas und Test-Skips ohne
  begründeten Eintrag in `scope_allowlist`. Läuft auf jedem PR (Backend PR
  smoke gate), im `backend`-Job und im Pre-Push-Gate. (#1671)
