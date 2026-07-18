# Agora — Codex Instructions

Du arbeitest im Agora-Repository: einer lokal oder kontrolliert hybrid betreibbaren Multi-Agent-Analyseplattform für simulierte Zielgruppen-, Stakeholder- und Marktreaktionen.

## Aktueller Reifegrad

- Produktversion: `0.8.0` Technical Preview
- Release-Ziel: stabile Single-User-Version `1.0.0`
- Release-Gates: [`ROADMAP.md`](../ROADMAP.md)
- Istzustand: [`docs/STATUS.md`](../docs/STATUS.md)
- konkrete Arbeit: GitHub Issues

Historische Planungsdateien unter `docs/archive/` sind keine Taskquellen.

## Stack

- Backend: Flask, Python 3.14, Pydantic v2
- Frontend: Vue 3, TypeScript, Vite, Pinia, Zod
- Daten: Neo4j und Redis
- Simulation: OASIS/CAMEL
- Provider: Ollama lokal/cloud und OpenAI-kompatible APIs
- Paketmanager: `uv` und Bun
- Betrieb: Docker Compose, Gunicorn/gevent und optional nginx

## Quellenreihenfolge

1. `README.md`
2. `docs/STATUS.md`
3. `ROADMAP.md`
4. zugehöriges GitHub Issue
5. `AGENTS.md`, `CLAUDE.md`, ADRs und Runbooks

## Arbeitsprinzipien

1. Nie direkt auf `main` arbeiten.
2. Nur Issues mit prüfbarem Scope und Akzeptanzkriterien implementieren.
3. Verträge zuerst ändern, danach Schema-/Zod-Spiegel und Consumer.
4. Tests zuerst oder gemeinsam mit der Verhaltensänderung schreiben.
5. Keine neuen lokalen Provider-Heuristiken neben der Registry.
6. Keine neuen parallelen Frontends oder Legacy-Kompatibilitätsschichten.
7. Keine Secrets in Code, Logs, Fixtures oder Dokumentation.
8. Dokumentationsänderungen nur in der zuständigen Quelle:
   - Istzustand → `docs/STATUS.md`
   - Release-Ziel → `ROADMAP.md`
   - konkrete Arbeit → GitHub Issue
   - ausgelieferte Änderung → `CHANGELOG.md`

## Qualitäts-Gates

```bash
bash scripts/pre-push-gate.sh
bash scripts/pre-push-gate.sh backend
bash scripts/pre-push-gate.sh frontend
bash scripts/pre-push-gate.sh schemas
```

Keine globalen Skips, abgeschwächten Assertions, pauschalen Retries oder `--no-verify`-Bypässe ohne ausdrückliche Freigabe.

## Konventionen

- Branches: `feat/<scope>`, `fix/<scope>`, `refactor/<scope>`, `docs/<scope>`
- Commits: Conventional Commits
- Pull Requests referenzieren oder schließen ein GitHub Issue
- persistierte Datenänderungen benötigen Migration und Rollback
- Security-Ausnahmen benötigen Issue, Owner, Begründung und Deadline
