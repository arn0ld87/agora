# Embedding-Provider wechseln (Ollama ↔ OpenAI)

Agora ist Local-first und nutzt per Default Ollama-Embeddings. Die
Embedding-Pipeline (`backend/app/storage/embedding_service.py`) erkennt
OpenAI-kompatible Endpoints aber automatisch und schaltet auf Bearer-Auth
um — der Switch ist eine reine `.env`-Änderung. Code-Defaults bleiben
unangetastet.

## Default (Ollama, lokal)

```dotenv
EMBEDDING_BASE_URL=http://localhost:11434
EMBEDDING_MODEL=qwen3-embedding:4b
VECTOR_DIM=2560
# EMBEDDING_API_KEY wird ignoriert
```

Alternative Ollama-Modelle: `nomic-embed-text` (768), `embeddinggemma:300m`
(768), `qwen3-embedding:8b` (4096). Die bekannten Dimensionen sind in
`backend/app/config.py` (`KNOWN_EMBEDDING_DIMS`) hinterlegt; falsche Werte
werden beim Start hart abgelehnt.

## Switch auf OpenAI

```dotenv
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_API_KEY=sk-...   # oder LLM_API_KEY als Fallback
VECTOR_DIM=1536
```

Weitere OpenAI-Modelle:

| Modell | Dimension |
|---|---|
| `text-embedding-3-small` | 1536 |
| `text-embedding-3-large` | 3072 |
| `text-embedding-ada-002` | 1536 |

Andere OpenAI-kompatible Endpoints (z. B. self-hosted vLLM mit OpenAI-API)
funktionieren genauso, solange `EMBEDDING_BASE_URL` auf `/v1` endet — die
Provider-Erkennung in `EmbeddingService._detect_provider()` triggert
automatisch.

## Pflicht: Vector-Index in Neo4j neu erstellen

Beim Wechsel der `VECTOR_DIM` (also fast immer beim Provider-Wechsel)
lehnt Neo4j Inserts in den bestehenden Index ab — die Index-Dimension ist
fest. Drop + Rebuild:

```cypher
SHOW VECTOR INDEXES;
-- Den Namen aus der Ausgabe übernehmen, z. B. "entity_embedding_index"
DROP INDEX entity_embedding_index IF EXISTS;
DROP INDEX claim_embedding_index IF EXISTS;
DROP INDEX episode_embedding_index IF EXISTS;
```

Beim nächsten Graph-Build legt das Backend die Indexe automatisch mit der
neuen `VECTOR_DIM` an. Wer Daten behalten will, muss vorher alle Knoten
mit dem neuen Provider re-embedden — siehe
`backend/scripts/`-Verzeichnis (eigener Slice, noch nicht implementiert).

## Verifikation nach Switch

```bash
cd backend
uv run python -c "
from app.storage.embedding_service import EmbeddingService
svc = EmbeddingService()
vec = svc.embed_one('Probe')
print(f'OK — provider={svc._provider}, model={svc.model}, dim={len(vec)}')
"
```

Ausgabe muss `provider=openai`, `dim=1536` zeigen (für
`text-embedding-3-small`).

## Caveat: Kosten + Latenz

OpenAI `text-embedding-3-small` ist deutlich günstiger als `-3-large`
(~5× billiger pro 1M Tokens) und schneller, mit nur leicht reduzierter
Qualität. Für DACH-Texte ist `-3-small` praktisch identisch zu Qwen3
(2560-dim Lokal-Modell), wenn auch mit einer Cloud-Round-Trip-Latenz von
typisch 100–300 ms pro Batch — relevant für große Persona-Generierungen.
Für lokale Smoke-Runs lohnt sich der Switch zurück auf Ollama.
