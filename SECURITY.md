# Security Policy

Agora ist ein lokal-first Multi-Agent-Simulator für Single-User-Setups. Diese Datei ist der kurze Security-Einstieg. Details stehen in [docs/security.md](docs/security.md), [docs/security-threat-model.md](docs/security-threat-model.md) und [docs/adr/0001-auth-model.md](docs/adr/0001-auth-model.md).

## Security-Modell

- Agora v1 ist **Single-User-only**.
- Der API-Schutz basiert auf einem geteilten `AGORA_AUTH_TOKEN`.
- Es gibt keinen vollständigen Multi-User-AuthN/AuthZ-Stack.
- Nicht direkt ins öffentliche Internet stellen.
- Betrieb nur hinter Reverse Proxy, Tunnel oder Tailnet.
- Non-Debug-Setups brauchen echte Werte für `SECRET_KEY`, `NEO4J_PASSWORD` und `AGORA_AUTH_TOKEN`.
- `?token=` ist im Non-Debug-Modus blockiert; SSE und Downloads nutzen signed Tickets (`?ticket=`).

## Secrets

- Keine echten Tokens, Keys, `.env`-Dateien oder Provider-Secrets in Issues, PRs, Logs, Screenshots oder Diffs posten.
- Beispiele immer über `.env.example` oder Platzhalter dokumentieren.
- Rotationen und Deployment-Härtung sind in [docs/security.md](docs/security.md) beschrieben.

## Supported Versions

Sicherheits-Fixes werden für die aktuelle Version auf `main` gepflegt.

| Version | Unterstützt |
|---|---|
| 1.0.x | ja |
| < 1.0 | nein |

## Reporting a Vulnerability

Bevorzugt: private Mail an [schneider@alexle135.de](mailto:schneider@alexle135.de) mit Betreff `[Agora Security] <kurzbeschreibung>`.

Optional: GitHub Private Vulnerability Reporting über [Security Advisories](https://github.com/arn0ld87/Agora/security/advisories/new).

Bitte enthalten:

- betroffene Komponente, Pfad und Version
- Reproduktionsschritte oder PoC
- beobachteter und erwarteter Effekt
- optionaler Mitigation-Vorschlag

Bitte keine Public-Issues für noch nicht gefixte Schwachstellen anlegen.

## Watchlist

Upstream-blockierte CVEs und Dependency-Risiken werden in [docs/dependency-risk-register.md](docs/dependency-risk-register.md) und den GitHub-Security-Issues getrackt. Der CVE-Monitor läuft über GitHub Actions.
