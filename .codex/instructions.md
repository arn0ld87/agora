# Agora – Codex System Instructions

Du arbeitest im **Agora**-Projekt: einer multi-agent KI-Plattform mit Django-Backend, React-Frontend und Docker-basierter Infrastruktur.

## Stack
- **Backend:** Django + Django REST Framework (Python)
- **Frontend:** React + Vite + TypeScript
- **Infra:** Docker Compose, PostgreSQL, Redis
- **Auth:** JWT-basiert

## Coding-Standards
- Python: PEP 8, Type Hints, Docstrings
- TypeScript: strict mode, keine `any`
- Commits: Conventional Commits (`feat:`, `fix:`, `chore:` etc.)
- Security: Least Privilege, keine Secrets im Klartext, Env-Vars für alles Sensitive

## Arbeitsprinzipien
1. Lies `docs/archive/old-plans/CODEX_PLAN.md` am Anfang jeder Session
2. Prüfe `.codex/config.json` für aktuellen Provider/Modell
3. Nach jedem abgeschlossenen Schritt: Frage ob Provider/Modell gewechselt werden soll
4. Nutze `/provider-switch` zum Wechseln, `/provider-status` zur Statusanzeige
5. Verändere nie API-Keys direkt in Dateien

## Konventionen
- Branch-Namen: `feat/beschreibung`, `fix/beschreibung`
- PR-Titel: folgen Conventional Commits
- Tests schreiben bei jedem neuen Feature
- `PLAN.md` und `CHANGELOG.md` nach Abschluss aktualisieren
