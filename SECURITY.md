# Security Policy

Agora ist ein lokal-first Multi-Agent-Simulator (Python/Flask + Vue 3 +
Neo4j + Ollama, OASIS via Subprozess). Diese Datei beschreibt, wie
Sicherheitslücken vertraulich gemeldet werden und welcher Stand für
Updates gepflegt wird.

## Supported Versions

Solo-Maintainer-Projekt im aktiven Sprint. Sicherheits-Fixes nur für die
jeweils aktuelle Minor-Version auf `main`.

| Version | Unterstützt        |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

**Bevorzugt:** Private Mail an
**[schneider@alexle135.de](mailto:schneider@alexle135.de)**
mit Betreff `[Agora Security] <kurzbeschreibung>`.

Optional: GitHub Private Vulnerability Reporting via
[Security Advisories](https://github.com/arn0ld87/Agora/security/advisories/new).

Bitte enthalten:

- Betroffene Komponente / Pfad / Version
- Reproduktions-Schritte oder PoC
- Beobachteter und erwarteter Effekt
- Optional: Vorschlag für Mitigation

**Bitte NICHT:**

- Public-Issue für noch nicht gefixte Schwachstellen anlegen
- Findings auf Twitter/Mastodon/o.ä. veröffentlichen, bevor ein Fix
  oder eine Veröffentlichungs-Absprache existiert

## Response-SLA (informell)

| Schritt                              | Ziel-Frist        |
| ------------------------------------ | ----------------- |
| Eingangsbestätigung                  | 72 Stunden        |
| Erste Einschätzung (Severity, Scope) | 7 Tage            |
| Fix oder dokumentiertes Tracking     | 30 Tage (Best Effort) |
| Public Disclosure                    | nach Absprache    |

Da es sich um ein privates Open-Source-Projekt ohne SLA-Vertrag handelt,
sind Fristen Best-Effort. Kritische Funde (RCE, Auth-Bypass,
Datenexfiltration) priorisiere ich vor allen Feature-Slices.

## Sicherheitsrelevante Umgebungsvariablen

### AGORA_CORS_ALLOW_ALL

`AGORA_CORS_ALLOW_ALL=true` setzt den CORS-Filter auf Wildcard (`*`) und
deaktiviert `Access-Control-Allow-Credentials`. **Nur in Entwicklung verwenden —
niemals in Produktion, auch nicht temporär.**

Die App verweigert den Start wenn `AGORA_CORS_ALLOW_ALL=true` im
Produktionsmodus gesetzt ist, also wenn `FLASK_DEBUG` nicht `true` ist
(fail-closed — ohne explizites Dev-Signal greift der Guard).

Für produktionsseitige Origin-Freigaben: `AGORA_EXTRA_ORIGINS` als
komma-separierte Whitelist verwenden.

---

## Bekannte Watchlist (Upstream-blockierte CVEs)

Einige CVEs in transitiven Abhängigkeiten sind dokumentiert und
gepinnt-getrackt, weil ein Upstream-Fix noch aussteht. Tracking-Issues:

- [#121–#126 Security-Watchlist](https://github.com/arn0ld87/Agora/issues?q=label%3Asecurity)
- Dokumentation: [`docs/`](docs/) — Sub-Slice 31 (Layer 10)

Sobald Upstream patcht, zieht Dependabot automatisch (siehe
[`.github/dependabot.yml`](.github/dependabot.yml)).

## Lizenz / Disclosure-Hinweis

Agora steht unter **AGPL-3.0**. Wer einen Fork als Service betreibt,
muss Sourcen offen halten — das gilt auch für sicherheitsrelevante
Patches. Embargo-Zeiträume zwischen Fix-Merge und Public Disclosure
werden im Einzelfall mit Reporter abgestimmt.
