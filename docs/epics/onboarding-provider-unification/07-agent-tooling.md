# Agent Tooling

## context-mode

- geprüft: 2026-07-10;
- Version: 1.0.169;
- Quelle: <https://github.com/mksglu/context-mode>;
- Status: MCP, FTS5, Storage und Plugin-Hooks funktionieren;
- Abweichung: Doctor meldet fehlendes `[features].hooks` in der globalen
  Codex-Konfiguration;
- Entscheidung: kein globales Upgrade im Feature-Epic. Separater
  Tooling-Maintenance-Schritt mit Backup, Doctor und Rollback.

## code-review-graph

- geprüfte stabile Version: 2.3.6;
- Quelle: <https://pypi.org/project/code-review-graph/>;
- Lizenz: MIT;
- `uv tool install` kollidiert mit einem vorhandenen Executable; kein `--force`;
- reproduzierbarer CLI-Fallback:
  `uvx --from 'code-review-graph==2.3.6' code-review-graph ...`;
- MCP ist erreichbar und hat den Worktree-Graph erfolgreich aufgebaut;
- ein Aktualisierungsweg: MCP-Update vor Architektur-/Delta-Reviews, kein
  zusätzlicher Watcher.

## Verwendung im Epic

- Graph vor modulübergreifenden Änderungen aktualisieren.
- Minimal Context, Impact Radius und betroffene Tests vor Direct Reads.
- Nach Änderungen Delta-Review und Testlückenprüfung.
- Große Logs und Multi-File-Recherche über context-mode.
- Toolausfall dokumentieren; keine Resultate erfinden.

## Secret-freier Check

[`scripts/agent-tools-doctor.sh`](../../../scripts/agent-tools-doctor.sh) prüft
nur Versionen und Graphstatus. Globale Konfiguration und Auth-Dateien werden
nicht gelesen oder ausgegeben.
