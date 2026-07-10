# Agent-Tooling

Letzte Prüfung: 2026-07-10
Verantwortlicher Slice: Onboarding/Provider-Unification Slice 0

| Tool | Quelle/Lizenz | Version | Installationsweg | Status |
|---|---|---:|---|---|
| context-mode | <https://github.com/mksglu/context-mode>, Elastic-2.0 | 1.0.169 | Codex-Plugin | MCP/FTS/Hooks aktiv; Doctor meldet fehlendes globales Hooks-Flag |
| code-review-graph | <https://pypi.org/project/code-review-graph/>, MIT | 2.3.6 | MCP vorhanden; CLI reproduzierbar via gepinntem `uvx` | Graph erfolgreich gebaut |
| Codex CLI | <https://github.com/openai/codex>, Apache-2.0 | 0.142.5 | bestehende lokale Installation | aktiv |

## Konfiguration und Rechte

- Globale Codex- und Plugin-Konfiguration wird nicht ins Repository kopiert.
- Keine Auth-Dateien, Tokens, Browserprofile oder Keychain-Inhalte prüfen.
- context-mode verarbeitet große Read-only-Ausgaben und Session-Kontext.
- code-review-graph liest Repository-Struktur und schreibt generierte
  Graphdaten außerhalb versionierter Produktartefakte.
- Es läuft kein zusätzlicher Watcher; Aktualisierung erfolgt kontrolliert per
  MCP vor Architektur- und Delta-Reviews.

## Doctor-/Status-Ergebnis

- context-mode: Server, FTS5, Storage und fünf Plugin-Hooks OK; globales
  `[features].hooks` laut Doctor nicht explizit gesetzt.
- code-review-graph: 944 Dateien, 8.803 Knoten, 74.776 Kanten, 624 Flows,
  11 Communities, keine Build-Fehler.
- globaler `uv tool install code-review-graph==2.3.6` wurde nicht erzwungen,
  weil bereits ein Executable kollidiert. `--force` wäre ohne Backup und
  Herkunftsprüfung destruktiv.

## Upgrade und Rollback

Upgrades erfolgen nur in einem eigenen Maintenance-Slice:

1. offizielle Release Notes, Lizenz und Sicherheitsmeldungen prüfen;
2. Konfiguration sichern;
3. exakte Version pinnen;
4. Doctor, Graph-Build und Minimalabfrage ausführen;
5. bei Fehlern vorherige Plugin-/Tool-Version wiederherstellen.

Bis zur Klärung der CLI-Kollision:

```bash
uvx --from 'code-review-graph==2.3.6' code-review-graph status
```

## Einschränkungen

- Graphresultate ersetzen weder direkte Codeprüfung noch Tests.
- context-mode-Doctor ist wegen des Hooks-Flags nicht vollständig grün.
- Python-3.14-Warnungen in der lokalen Baseline sind kein Tooling-Erfolg.
