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

# Python-Interpreter pruefen (siehe Abschnitt unten)
cd backend && uv run python -VV

# Produktionsnaher Stack
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f deploy/compose/docker-compose.prod-with-proxy.yml up -d --build
curl -fsS http://localhost/healthz
```

## Python-Interpreter: nur finale 3.14

`backend/pyproject.toml` verlangt `>=3.14,<3.15`. Eine **Vorabversion** erfuellt
diese Bedingung formal, ist aber unbrauchbar: pydantic schaltet seinen Aufruf
von `typing._eval_type(..., prefer_fwd_module=...)` hinter
`sys.version_info >= (3, 14)`, und `3.14.0rc2` erfuellt die Bedingung, hat den
Parameter aber noch nicht. Folge ist kein einzelner roter Test, sondern ein
Abbruch beim Einsammeln der gesamten Suite:

```text
TypeError: _eval_type() got an unexpected keyword argument 'prefer_fwd_module'
Unable to evaluate type annotation 'RootModelRootType'
```

Pruefen:

```bash
cd backend && uv run python -c "import sys; print(sys.version_info)"
# releaselevel muss 'final' sein, nicht 'candidate'
```

Trifft das zu, wurde das venv auf einer Vorabversion gebaut — neu anlegen.
**Erst den Interpreter pruefen, dann loeschen:** `command -v python3.14` kann
genau die Vorabversion liefern, die das defekte venv erzeugt hat, und der
Neuaufbau stellte den Fehler unveraendert wieder her.

```bash
PY314="$(command -v python3.14)"
"$PY314" -c 'import sys; v=sys.version_info; raise SystemExit(0 if v[:2]==(3,14) and v.releaselevel=="final" else 1)' \
  && (cd backend && rm -rf .venv && uv venv --python "$PY314" && uv sync --frozen) \
  || echo "‼ $PY314 ist keine finale 3.14 — anderen Interpreter besorgen (siehe .claude/hooks/session-start.sh)"
```

In Claude-Code-Web-Sessions erledigt das `.claude/hooks/session-start.sh`
automatisch: der Hook verwirft ein venv auf einer Vorabversion und baut es auf
einem finalen 3.14 neu.
