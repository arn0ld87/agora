### Geändert

- **CI/CD-Konsolidierung & Entmistung**:
  - Drei redundante Einzel-Workflows (`contract-gates.yml`, `version-drift.yml`, `check-legacy-model-picker.yml`), die bei jedem PR bis zu 8 zusätzliche Python-Runner hochfuhren und dieselben Checks doppelt zu `ci.yml` ausführten, in `ci.yml` (`backend-pr-gate`, `backend`, `frontend-pr-gate`, `frontend`) integriert und entfernt.
  - `e2e-smokes.yml` von 8 parallelen Docker-Compose-Stack-Jobs (jeweils vollständiger Image-Bake + Stack-Boot + Browser-Setup) auf einen konsolidierten `e2e-smoke`-Job (`Playwright E2E-Smokes`) zusammengeführt, der alle 10 Playwright-Specs seriell (`workers: 1`) gegen einen einmalig gebooteten Stack ausführt.
  - Tote `--deselect`-Einträge (7 bereits gelöschte Testdateien, 2 gefixte Tests) aus `ci.yml` und `scripts/pre-push-gate.sh` entfernt.
  - `unlabeled`-Trigger-Rauschen in `ci.yml` entfernt, `labeled`-Trigger gezielt auf die Opt-in-Labels `needs-backend-ci` und `needs-frontend-ci` gefiltert (ohne Re-Run der PR-Smoke-Gates), `cve-monitor.yml` auf PRs auf das Supabase-Image- und Risk-Register-Gate (`supabase-images`) beschränkt (`audit`-Job läuft nur außerhalb von PRs, da Python-Lockfiles bereits durch `ci.yml::security` und `dependency-review.yml` geprüft werden), und abgelaufene `GHSA-p4gq-832x-fm9v`-Ausnahme aus `dependency-review.yml` bereinigt.
