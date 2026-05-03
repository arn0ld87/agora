> **HISTORISCHER SNAPSHOT (Stand 2026-04-2x).**
>
> Aktueller Stand siehe:
> - Architektur & Plan: `CLAUDE.md` / `PLAN.md` / `plan.heuristic.md`
> - Test-Status: `docu/STATUS.md`
> - Diese Datei wurde aus dem Repo-Root nach `docu/history/` verschoben.
>
---

- Security-Job mit pip-audit, npm audit und Gitleaks
- Backend-Job mit pytest und Ruff
- Frontend-Job mit lint und build
- Docker-Image-Workflow für Docker Hub und GHCR
- Docker Compose ist deutlich gehärtet: read-only RootFS, tmpfs, no-new-privileges, cap_drop ALL
- Redis und Neo4j sauber als Services eingebunden
- Frontend-Test-Dependencies für echte Component-/Composable-Tests vorhanden

Die wichtigsten offenen Punkte:
- XSS-Risiko in `Step4Report.vue` ist weiterhin offen: `marked.parse()` + `v-html` ohne DOMPurify.
- CI-Frontend-Job führt aktuell keinen `npm test` / Vitest aus, obwohl lokale Scripts vorhanden sind.
- Dockerfile startet weiter `npm run dev`; gut für Dev/Lab, aber keine echte Production-Variante.
- Docker-Compose-Kommentar sagt „Pre-built Image“, aber `image:` ist auskommentiert und `build: .` aktiv.
- Backend-Ruff im CI ist noch gescoped, lokal prüft Root-Script bereits `app/ tests/`.

## Neue Bewertung

| Bereich | Letztes Urteil | Jetzt | Kommentar |
|---|---:|---:|---|
| Architektur | 8.5/10 | 8.5/10 | stabil gut |
| Frontend-Struktur | 7/10 | 7.2/10 | Log-Polling weiter konsolidiert |
| Backend-Struktur | 8.5/10 | 8.5/10 | keine große neue Änderung geprüft |
| CI/DevOps | 6/10 | 7.5/10 | deutlicher Sprung durch Actions |
| Container-Security | 7/10 | 8/10 | read-only, tmpfs, cap_drop ALL stark |
| Security gesamt | 7/10 | 7/10 | XSS bleibt P0 |
| Produktionsreife | 6/10 | 6.5/10 | näher dran, aber noch dev-server-basiert |
| Gesamt | 8/10 | 8.2/10 | echter Fortschritt |

## Wichtigster Befund

Der größte Blocker bleibt der Markdown/XSS-Punkt:

```js
function renderMarkdown(text) {
  if (!text) return ''
  try { return marked.parse(text) } catch { return text }
}
```

Das Ergebnis wird per `v-html` gerendert. Das muss mit DOMPurify oder einer Markdown-Konfiguration ohne HTML entschärft werden.

## Empfohlene nächste PRs

1. `fix(security): sanitize markdown rendering with DOMPurify`
2. `ci(frontend): run Vitest in GitHub Actions`
3. `build(prod): add production Docker target with built frontend and gunicorn`
4. `ci(ruff): align GitHub Ruff scope with local app/tests scope`
5. `docs(deploy): clarify build vs prebuilt image workflow`

## Gesamturteil

Agora ist inzwischen ein sehr starkes KI-gesteuertes Portfolio-Projekt. Für ein FISI-Pflichtpraktikum zeigt es sehr gut:
- Tooling-Kompetenz
- KI-Orchestrierung
- DevOps-Verständnis
- Security-Bewusstsein
- GitHub-/Issue-/CI-Workflow
- Systemintegration mit Docker, Redis, Neo4j, Flask und Vue

Nicht als „ich bin Senior Fullstack-Entwickler“ verkaufen. Als „ich kann KI-gestützte technische Projektarbeit, Infrastruktur, Review und Automatisierung steuern“ ist das inzwischen richtig stark.
