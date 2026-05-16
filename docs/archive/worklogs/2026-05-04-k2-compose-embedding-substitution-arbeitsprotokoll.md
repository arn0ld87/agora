# Slice K.2 — Compose `EMBEDDING_BASE_URL` / `LLM_BASE_URL` auf Substitution

**Datum:** 2026-05-04
**Trigger:** Container-Reboot-Loop nach K.1-Embedding-Switch.

## Problem

`docker-compose.yml:71` und `docker-compose.prod.yml:56` hardcodeten
`EMBEDDING_BASE_URL=http://host.docker.internal:11434` und überschrieben
damit die `.env`-Werte des Users — mit explizitem Kommentar „These
overrides win over .env so dev users can keep localhost defaults".

Konsequenz nach K.1: User-`.env` setzte `EMBEDDING_MODEL=text-embedding-3-small`
und `EMBEDDING_API_KEY=sk-...`, aber die Compose-Hardcoded-URL zeigte
weiter auf Ollama (`host.docker.internal:11434`). Der `EmbeddingService`
erkannte `/v1` aus der Pfad-Detection (`_detect_provider`), schickte das
OpenAI-Format-Payload an Ollama, das Ollama mit
`model "text-embedding-3-small" not found, try pulling it first` (404)
quittierte. `validate_embedding_configuration()` warf
`RuntimeError: Embedding configuration invalid` → `create_app()`-Crash →
Container-Restart-Loop.

Host-Verifikation lief sauber durch (`OK provider=openai
model=text-embedding-3-small dim=1536`), weil der Host die `.env`
direkt liest. Erst der Container-Pfad war kaputt.

## Lösung

Beide Compose-Files auf `${VAR:-default}`-Substitution umgestellt:

```yaml
- LLM_BASE_URL=${LLM_BASE_URL:-http://host.docker.internal:11434/v1}
- EMBEDDING_BASE_URL=${EMBEDDING_BASE_URL:-http://host.docker.internal:11434}
```

`.env`-Werte gewinnen jetzt; Default-Fallback bleibt host-Ollama
(Local-first laut Projekt-Profil — `docker compose up` ohne weiteres
Setup funktioniert weiterhin Out-of-the-Box).

`NEO4J_URI` bleibt **hardcoded**, weil `localhost` aus der `.env` nicht
zum Compose-Service `neo4j` aufgelöst wird — eine `.env`-Übernahme
würde dort kaputtgehen, der Override ist semantisch korrekt.

## Files geändert

- `docker-compose.yml:69-77` — Substitution + erweiterter Kommentar
- `docker-compose.prod.yml:55-59` — analog

## Verifikation

```bash
# Default greift (leere .env, kein env-Override)
docker compose config | grep BASE_URL
#  EMBEDDING_BASE_URL: http://host.docker.internal:11434
#  LLM_BASE_URL: http://host.docker.internal:11434/v1

# .env / Shell-env gewinnt
EMBEDDING_BASE_URL=https://api.openai.com/v1 docker compose config | grep EMBEDDING
#  EMBEDDING_BASE_URL: https://api.openai.com/v1
```

## Risiken

Keine. Backwards-kompatibel: bestehende Setups ohne `EMBEDDING_BASE_URL`
in `.env` verhalten sich identisch zu vorher.

## Lokale Folgemaßnahme beim User

`docker-compose.override.yml` wurde temporär mit einem
`EMBEDDING_BASE_URL=https://api.openai.com/v1`-Override gepatcht
(K.A-Quickfix, NICHT committed). Nach Merge dieses Slices kann der
Override zurückgenommen werden:

```bash
git checkout docker-compose.override.yml
```

Die Konfiguration kommt dann sauber aus der `.env`.
