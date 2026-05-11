# R0 — Dev-Tooling-Helper · Arbeitsprotokoll

**Datum:** 2026-05-01
**Slice:** R0 (Helper, kein Sub-Issue)

## Ziel

Container-Workflow für Agora vereinfachen, damit S1/S2-pre-Fixes ohne mentale Last live im Container verifiziert werden können.

## Implementierung

- `scripts/dev-rebuild.sh` (chmod +x): drei Modi `quick`/`deps`/`full` für Container-Restart, Frontend-Dependency-Install, Full-Rebuild.
- `scripts/verify-deploy.sh` (chmod +x): Health-Checks (Container, Backend `/health`), S1-Asserts (DOMPurify im node_modules + im markdown-Util), S2-pre-Asserts (name-Lookup im Service), und ein Diagnose-Run gegen die letzten 3 Sims.
- `package.json` um vier Aliases ergänzt: `dev:rebuild`, `dev:rebuild:deps`, `dev:rebuild:full`, `dev:verify`.
- `docs/2026-05-01-evidence-pipeline-plan.md` Slice-Tabelle um eine Zeile R0 ergänzt.

## Tests

`npm run check` grün (keine Code-Änderung an Tests, nur Helper-Skripte und Plan-Doku).
