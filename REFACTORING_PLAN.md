# Refactoring Plan

## Current Problems

- Security-relevante Defaults sind teilweise zu permissiv (Auth optional, historischer Passwort-Default).
- API-Auth ist technisch zentralisiert, aber Policy (wann zwingend?) ist nicht als klarer Betriebsmodus codiert.
- Security-Checks sind nicht fest im Standard-Check-Flow verankert.
- Einige Risiko-Themen sind dokumentiert, aber nicht in klare, kleine Umsetzungspakete zerlegt.

## Recommended Target Structure

- **Config Policy Layer**: explizite Sicherheitsmodi (`development`, `hardened`, `production`) mit Fail-Fast-Regeln.
- **Auth Surface**: zentraler Guard bleibt, aber URL-Token nur noch über signierte Kurzzeit-Tickets.
- **CI Security Stage**: reproduzierbare, cachbare Dependency- und Secret-Scans als eigener Pipeline-Abschnitt.
- **Dokumentation**: Security-Baseline als lebende Checkliste (`SECURITY_REVIEW.md` + issue-getriebene Umsetzung).

## Refactoring Tasks

| Priority | Task | Reason | Risk | Suggested PR |
|---|---|---|---|---|
| P0 | Auth in Non-Debug standardmäßig erzwingen oder explizites Allow-Flag einführen | verhindert offene API-Deployments | Mittel (Deployment-Anpassung nötig) | `security/repo-hardening` |
| P0 | SSE/Download Auth von Query-Token auf kurzlebige signed tickets migrieren | reduziert Token-Leakage in URLs/Logs | Mittel | `security/repo-hardening` |
| P1 | Security-Scans in CI integrieren (`npm audit`, Python-Audit, Secret Scan) | frühzeitige Erkennung neuer Risiken | Niedrig | `ci/add-security-checks` — umgesetzt 2026-04-29 |
| P1 | Einheitliche Error-Envelope inkl. Security-safe Fehlermeldungen prüfen/erzwingen | konsistente API + weniger Info-Leaks | Niedrig-Mittel | `refactor/code-quality-pass` — umgesetzt 2026-04-29 |
| P2 | Logging-Review auf Secret-Redaction und Token-Schutz | verhindert versehentliche Secret-Exposition | Niedrig | `refactor/code-quality-pass` — umgesetzt 2026-04-29 |

## Safe First Steps

1. Insecure Defaults entfernen (umgesetzt: `NEO4J_PASSWORD` ohne statischen Fallback).
2. Security-Review und priorisierte Tasks dokumentieren.
3. Kleine, nicht-breaking Härtungsänderungen in getrennten PRs durchführen.

## Larger Follow-Up Work

- Signed URL/Ticket-System für SSE und Artefakt-Downloads.
- Harte Auth-Policy in Prod inklusive klarer Migrationshinweise.
- Security-Regression-Tests (z. B. Auth required, CORS policy, token leakage checks).

## Umsetzung P1 — 2026-04-29

- CI: separater `security`-Job mit Frontend-`npm audit --audit-level=high`, Python-`pip-audit` gegen einen aus `uv.lock` exportierten Runtime-Requirements-Snapshot und Gitleaks Secret Scan über die volle Git-Historie.
- Python-Audit: 39 bestehende Advisories per kompatiblem `uv.lock`-Upgrade beseitigt; 6 verbleibende Advisories sind wegen fester `camel-oasis`-/`camel-ai`-/`sentence-transformers`-Pins temporär gebaselined.
- API: `handle_api_errors()` liefert bei ungefangenen 5xx-Fehlern im Nicht-Debug-Modus nur noch sichere Standardmeldungen (`internal server error`, `request timed out`) plus maschinenlesbare Codes.
- Flask-Framework-Fehler: generische `/api/*`-`HTTPException`- und ungefangene Exception-Handler erzwingen die zentrale JSON-Envelope auch außerhalb dekorierter Views.
- Dokumentation: Details und Rollback in `docu/p1-security-ci-error-envelope-protokoll.md`.
