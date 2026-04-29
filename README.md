# Agora

Local-first Multi-Agenten-Simulation mit Flask, Vue, Neo4j, OASIS und Ollama.

Agora nimmt ein Dokument entgegen, extrahiert daraus einen Wissensgraphen,
erzeugt Agenten-Personas, simuliert Reaktionen und erstellt daraus einen Report.
Der Standardbetrieb ist lokal. OpenAI-kompatible LLM-Endpunkte koennen alternativ
konfiguriert werden.

## Voraussetzungen

- Node.js 18+
- Python 3.11+
- `uv`
- Docker Compose, wenn du die Container-Variante nutzt
- Neo4j 5.18+
- Ollama mit passenden Modellen

Empfohlene Ollama-Modelle:

```bash
ollama pull qwen2.5:32b
ollama pull qwen3-embedding:4b
```

`qwen3-embedding:4b` braucht `VECTOR_DIM=2560`. Fuer `nomic-embed-text` nutze
`VECTOR_DIM=768`.

## Installation mit Docker Compose

```bash
git clone https://github.com/arn0ld87/agora.git
cd agora
cp .env.example .env
docker compose up -d
```

Danach:

- Frontend: <http://localhost:5173>
- Backend Health: <http://localhost:5001/health>
- Neo4j Browser: <http://localhost:7474>

Ollama laeuft standardmaessig auf dem Host und wird aus dem Container ueber
`host.docker.internal` erreicht.

## Lokale Installation

```bash
git clone https://github.com/arn0ld87/agora.git
cd agora
cp .env.example .env
npm run setup:all
npm run dev
```

## Konfiguration

Alle Laufzeitwerte kommen aus `.env`.

Minimalbeispiel:

```env
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL_NAME=qwen2.5:32b

EMBEDDING_BASE_URL=http://localhost:11434
EMBEDDING_MODEL=qwen3-embedding:4b
VECTOR_DIM=2560

NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=agora

AGENT_LANGUAGE=de
REPORT_LANGUAGE=German
TIME_PROFILE=dach_default

ENABLE_AGENT_TOOLS=false
```

In Non-Debug-Setups ist ein API-Token sinnvoll:

```env
AGORA_AUTH_TOKEN=change-me
SECRET_KEY=change-me-too
```

## Nützliche Kommandos

```bash
npm run setup:all
npm run dev
npm run build
npm run check
```

Backend einzeln:

```bash
npm run backend
```

Frontend einzeln:

```bash
npm run frontend
```

## Sicherheit

Agora ist fuer lokale Single-User-Setups und vertrauenswuerdige Netze gedacht.
Nicht ohne zusaetzliche Absicherung direkt ins Internet haengen.

`.env`, Uploads, Logs, Caches und lokale Arbeitsdateien sind nicht versioniert.

## Lizenz

AGPL-3.0, siehe [LICENSE](./LICENSE).

Agora ist ein Fork/Derivat von
[nikmcfly/MiroFish-Offline](https://github.com/nikmcfly/MiroFish-Offline),
basierend auf [MiroFish](https://github.com/666ghj/MiroFish).
