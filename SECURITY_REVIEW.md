# Security Review

> **Stand 2026-04-29:** Dieser Review ist ein **historischer Snapshot** (Erstfassung 2026-04-22).
> Aktueller Status der Findings siehe
> [`docu/2026-04-29-security-followup-plan.md`](./docu/2026-04-29-security-followup-plan.md)
> und [`docu/security-hardening.md`](./docu/security-hardening.md).
>
> Kurzstatus:
>
> - **F1** (API offen ohne Token) — erledigt (`Config.validate()` fail-fast in Non-Debug, `AGORA_ALLOW_ANONYMOUS` als Opt-out).
> - **F2** (Query-Token-Leakage) — Signed Tickets live; `?token=`-Fallback noch im Deprecation-Pfad.
> - **F3** (Neo4j-Default-Passwort) — erledigt (Default entfernt, Compose erzwingt Env).
> - **Low** (CI-Security-Scans) — erledigt (`npm audit`, `pip-audit`, gitleaks im CI).
> - **Info** (Container-Hardening) — read-only rootfs + `cap_drop` offen.

## Summary

Das Repository hat bereits gute Baseline-Härtung (nicht-root Container-User, zentrale Token-Guard-Option, restriktive CORS-Defaults, Upload-Größenlimit, Healthchecks). Die wichtigsten Risiken liegen aktuell in **unsicheren Dev-Defaults** (API offen ohne Token) und in der **Query-Token-Nutzung für SSE/Downloads** (Leakage-Risiko in URL-basierten Logs/Proxies). Zusätzlich fehlt ein automatisierter Security-Scan in der Standard-Quality-Gate-Pipeline.

## Risk Table

| Severity | Area                | Finding                                                                    | Impact                                                                      | Recommendation                                                                                               |
| -------- | ------------------- | -------------------------------------------------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| High     | AuthN/AuthZ         | API ist standardmäßig offen, wenn `AGORA_AUTH_TOKEN` nicht gesetzt ist | Unautorisierter Zugriff auf `/api/*` in falsch konfigurierten Deployments | Secure-by-default erzwingen (Prod-Fail ohne Token) oder expliziten `ALLOW_UNAUTH_DEV=true` Schalter nutzen |
| Medium   | Secret Handling     | Token-Fallback über Query-Parameter (`?token=`)                         | Token kann in Reverse-Proxy-Logs, Browser-History, Monitoring auftauchen    | Kurzfristig dokumentieren + Log-Redaction; mittelfristig kurzlebige Signed URLs/one-time tokens              |
| Medium   | Configuration       | Historischer Neo4j-Passwort-Default (`agora`) in Code                    | Risiko schwacher/vergessener Defaults in lokalen/CI-Setups                  | Default entfernen, Passwort zwingend via Env setzen                                                          |
| Low      | Dependency Security | Kein durchgängiger Security-Scan im `npm run check` Flow                | Schwachstellen werden ggf. spät entdeckt                                   | CI-Job mit `npm audit` + `pip-audit` (oder OSV-Scan) ergänzen                                           |
| Info     | Container Hardening | Container läuft als non-root User (agora)                                 | Positiv: reduziert Impact bei Container-Kompromittierung                    | Beibehalten, zusätzlich read-only rootfs + capabilities drop prüfen                                        |

## Findings

### Finding 1: API standardmäßig offen ohne gesetztes Auth-Token

- Severity: High
- File(s): `backend/app/utils/auth.py`, `backend/app/__init__.py`
- Description: Der Guard wird nur aktiv, wenn `AGORA_AUTH_TOKEN` gesetzt ist; sonst werden alle `/api/*` Requests ohne Auth akzeptiert.
- Risk: Fehlkonfigurierte Deployments können unabsichtlich öffentliche API-Endpunkte bereitstellen.
- Evidence: `_expected_token()` nutzt leere Default-Variable und `install_blueprint_guard` ist dann No-Op.
- Recommendation: In Nicht-Debug-Umgebungen einen Start-Abbruch ohne Token erzwingen oder explizites `AGORA_ALLOW_UNAUTHENTICATED=true` nur für lokale Dev erlauben.
- Suggested Fix: Konfigurationsvalidierung um Auth-Policy ergänzen (Follow-up-PR).

### Finding 2: Query-Token-Fallback erhöht Leakage-Risiko

- Severity: Medium
- File(s): `backend/app/utils/auth.py`, `frontend/src/api/stream.js`
- Description: Token kann per `?token=` übergeben werden, da `EventSource` keine Custom-Header setzt.
- Risk: URL-basierte Tokens können in Browser-History, Referrer, Proxy/Edge-Logs landen.
- Evidence: `_extract_token()` liest `request.args['token']`; Frontend hängt Token an SSE-URL an.
- Recommendation: Kurzfristig klare Ops-Doku + Log-Redaction; mittelfristig signed short-lived stream URLs oder serverseitige Session-Cookies.
- Suggested Fix: Security-Backlog-Issue für Signed stream tickets (TTL, one-time use, scope-bound).

### Finding 3: Insecure Neo4j Passwort-Default (behoben)

- Severity: Medium
- File(s): `backend/app/config.py`
- Description: Das Passwort hatte einen statischen Fallback (`agora`).
- Risk: Erhöht Wahrscheinlichkeit schwacher oder unbeabsichtigter Standard-Credentials.
- Evidence: Konfigurationswert im Code-Default.
- Recommendation: Kein Passwort-Default im Code.
- Suggested Fix: **Umgesetzt** — Default auf leer gesetzt, damit `validate()` fehlende Credentials erkennt.

## Dependency Review

- `npm audit --json`: keine bekannten Vulnerabilities im Root-Node-Set.
- `pip-audit` via `uv run pip-audit`: im aktuellen Environment nicht vollständig abgeschlossen (massiver Erstinstall inkl. großer ML/GPU-Artefakte, Laufzeit-/Ressourcenaufwand hoch).

Assumption:
Python-Dependency-Risiken sind nicht vollständig verifiziert.
Evidence:
Audit-Lauf startete mit umfangreichen Download-/Build-Schritten und konnte in sinnvoller Review-Zeit nicht final abgeschlossen werden.
Recommended verification:
Dedizierten CI-Job mit gecachtem `uv sync` + `pip-audit` (oder `osv-scanner`) einführen.

## Configuration Review

- Positiv: `SECRET_KEY` ist verpflichtend außerhalb Debug; CORS per Default auf localhost eingeschränkt; Upload-Limit (`50MB`) gesetzt.
- Risiko: Offene API im Default ohne `AGORA_AUTH_TOKEN`.
- Fix umgesetzt: Entfernen des statischen `NEO4J_PASSWORD`-Defaults.

## CI/CD Review

- Vorhandene lokale Quality-Gate-Skripte (`npm run check`) sind gut, aber Security-Scans sind nicht verpflichtender Teil.
- Empfehlung: CI um Security-Stufe erweitern (`npm audit`, Python-Audit, ggf. Secret-Scanner wie `gitleaks`).

## Open Questions

1. Soll in Production ein hartes Auth-Requirement gelten (Start-Fail ohne `AGORA_AUTH_TOKEN`)?
2. Welches Zielbild ist gewünscht für SSE-Auth ohne Query-Token (signed URLs vs Cookie-basiert)?
3. Soll ein offizieller Secret-Scanning-Workflow in CI verpflichtend werden?
