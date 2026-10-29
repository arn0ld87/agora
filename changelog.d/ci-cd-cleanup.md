### Geändert

- **CI/CD-Konsolidierung & Entmistung**:
  - Drei redundante Einzel-Workflows (`contract-gates.yml`, `version-drift.yml`, `check-legacy-model-picker.yml`), die bei jedem PR bis zu 8 zusätzliche Python-Runner hochfuhren und dieselben Checks doppelt zu `ci.yml` ausführten, in `ci.yml` (`backend-pr-gate`, `backend`, `frontend-pr-gate`, `frontend`) integriert und entfernt.
  - `e2e-smokes.yml` von 8 parallelen Docker-Compose-Stack-Jobs (jeweils vollständiger Image-Bake + Stack-Boot + Browser-Setup) auf einen konsolidierten `e2e-smoke`-Job (`Playwright E2E-Smokes`) zusammengeführt, der alle 10 Playwright-Specs seriell (`workers: 1`) gegen einen einmalig gebooteten Stack ausführt.
  - Tote `--deselect`-Einträge (7 bereits gelöschte Testdateien, 2 gefixte Tests) aus `ci.yml` und `scripts/pre-push-gate.sh` entfernt.
  - `labeled`/`unlabeled`-Trigger-Rauschen in `ci.yml` entfernt, `cve-monitor.yml` auf den wöchentlichen Schedule + `workflow_dispatch` beschränkt (PR-Lockfile-Prüfung erfolgt bereits durch `dependency-review.yml` und `ci.yml::security`), und abgelaufene `GHSA-p4gq-832x-fm9v`-Ausnahme aus `dependency-review.yml` bereinigt.
