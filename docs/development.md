# Development

Diese Datei beschreibt den normalen Entwicklungsfluss. Für Runtime-Details siehe [deployment-dev.md](deployment-dev.md) und [deployment-prod.md](deployment-prod.md).

## Setup

```bash
npm run setup:all
```

Start:

```bash
npm run dev
```

Quality-Gate:

```bash
npm run check
```

## Backend

```bash
cd backend && uv run pytest
cd backend && uv run ruff check app/ tests/
cd backend && uv run mypy app
```

Gezielte Contract-Checks:

```bash
cd backend && uv run pytest tests/contracts/ -v
cd backend && uv run python -m app.contracts.dump_schemas
git diff --exit-code schemas/
```

## Frontend

```bash
cd frontend && npm run check
```

Weitere Teilchecks:

```bash
cd frontend && npm test -- --run
cd frontend && npm run lint
cd frontend && npm run build
```

## Branching

- Nicht direkt auf `main` arbeiten.
- Branches: `feat/<scope>-<slug>`, `fix/<scope>-<slug>`, `chore/<scope>-<slug>`.
- Slice-Arbeit bevorzugt in `/private/tmp/agora-<slice-id>/`.
- Keine Rewrites veröffentlichter Commits.
- Merge nach `main` linear per `--ff-only`.

## PR-Erwartungen

- Kleine, nachvollziehbare Diffs.
- Tests oder begründeter Smoke-Check.
- Keine CI-, Coverage- oder Security-Gates entfernen.
- Nach `gh pr create` Gemini-Code-Assist-Findings abwarten und prüfen.
- HIGH-Findings vor Merge adressieren.
- MEDIUM-Findings bewusst entscheiden und dokumentieren.

Details: [runbooks/code-review.md](runbooks/code-review.md)

## Tests als Spec

Vor Refactors die relevanten Tests lesen. Bei Vertragsänderungen zuerst Contract-/Schema-Tests aktualisieren, dann Implementierung anpassen.

Wichtige Gates:

- Backend: `pytest`, `ruff`, `mypy`
- Frontend: `typecheck`, `vitest`, `lint`, `build`
- Contracts: Pydantic -> JSON Schema -> Zod
- Security/CI: Dependency Review, CodeQL, CVE-Monitor, Secret-Scan

## Schema-Drift

Pydantic-Verträge sind die Quelle. JSON-Schemas werden generiert, nicht von Hand gepflegt.

```bash
cd backend && uv run python -m app.contracts.dump_schemas
git diff --exit-code schemas/
```

Wenn `schemas/` danach driftet, gehört die Änderung bewusst in den Commit.

## `.env`

`.env` bleibt lokal und wird nicht committet. Neue Konfigurationen gehören in `.env.example` und in die passende Doku.

Wichtige Pflichtwerte für Non-Debug:

```env
SECRET_KEY=<token_urlsafe_32>
NEO4J_PASSWORD=<setzen>
AGORA_AUTH_TOKEN=<setzen>
```

Embedding-Modell und `VECTOR_DIM` müssen zusammenpassen:

| Modell | VECTOR_DIM |
|---|---:|
| `nomic-embed-text` | 768 |
| `embeddinggemma:300m` | 768 |
| `qwen3-embedding:4b` | 2560 |
| `qwen3-embedding:8b` | 4096 |

## Secrets

- Keine echten Tokens/Keys committen.
- Keine Secrets in Issues, PRs, Screenshots, Logs oder Diffs.
- Beispiele über Platzhalter oder `.env.example` dokumentieren.
- Bei Verdacht auf Secret-Leak sofort rotieren und den Commit-Verlauf prüfen.

## Dokumentation

Neues Verhalten braucht kurze Doku an einer passenden Stelle:

- `README.md` nur für Einstieg und Links
- `docs/development.md` für Entwicklungsabläufe
- `docs/architecture.md` für Systemstruktur
- `docs/deployment-*.md` für Runtime
- `docs/security.md` und `SECURITY.md` für Security
- `docs/archive/worklogs/` nur für historische Arbeitsprotokolle
