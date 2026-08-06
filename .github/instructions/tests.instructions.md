---
applyTo: "backend/tests/**/*.py,frontend/src/__tests__/**,frontend/tests/**"
---

# Tests

Tests sind die Spezifikation, nicht die Nachdokumentation.

## Verbindlich

- Ein Verhaltensfix bringt einen Regressionstest mit, der genau den Defekt trifft.
  Dass der Test vorher rot war, prüfst du einmal beim Schreiben — dokumentiert wird das nirgends,
  weder im PR-Text noch im Commit.
- Keine abgeschwächten Assertions, keine globalen Skips, keine pauschalen Retries, um rote Tests
  kosmetisch grün zu machen. Ein instabiler Test bekommt ein Issue, keinen `xfail`.
- Keine echten Netzwerkzugriffe und keine echten LLM-Provider in Unit- oder Contract-Tests.
- Keine API-Keys oder Secrets in Fixtures.
- Contract-Tests liegen unter `backend/tests/contracts/` und laufen als eigener, schneller Scope.

## Kommandos

```bash
cd backend  && uv run pytest tests/contracts/ -x -q   # Contract-Scope
cd backend  && uv run pytest                          # Backend vollständig
cd frontend && bun run test                           # Vitest
cd frontend && bun run test:coverage
```

E2E läuft nicht nebenbei mit — siehe `docs/runbooks/e2e-local.md`.
