# Commands

> Laden bei Setup-, Build- oder Pruefaufgaben.

```bash
# Entwicklung
bun run setup:all          # Ersteinrichtung
bun run dev                # Backend + Frontend parallel
bun run backend            # nur Backend
bun run frontend           # nur Frontend

# Pruefung
bash scripts/pre-push-gate.sh [backend|frontend|schemas]
cd backend && uv run pytest -x -q
cd backend && uv run ruff check .
cd backend && uv run mypy app
cd backend && uv run python -m app.contracts.dump_schemas --check
cd frontend && bun run test && bun run check

# Produktionsnaher Stack
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f deploy/compose/docker-compose.prod-with-proxy.yml up -d --build
curl -fsS http://localhost/healthz
```
