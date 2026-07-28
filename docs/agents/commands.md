# Commands

> **Progressive Disclosure** — ausgelagert aus [`AGENTS.md`](../../AGENTS.md). Bei Setup-/Build-/Prüfaufgaben laden.

```bash
# Setup und Entwicklung
bun run setup:all
bun run dev
bun run backend
bun run frontend

# Gesamtprüfung
bun run check
bash scripts/pre-push-gate.sh

# Backend
cd backend && uv run pytest -x -q
cd backend && uv run ruff check .
cd backend && uv run mypy app
cd backend && uv run python -m app.contracts.dump_schemas

# Frontend
cd frontend && bun run check
cd frontend && bun run test

# Produktionsnaher lokaler Stack
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f deploy/compose/docker-compose.prod-with-proxy.yml up -d --build
curl -fsS http://localhost/healthz
```