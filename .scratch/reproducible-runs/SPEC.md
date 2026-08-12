# Spec: Reproduzierbare Runs, Manifest und Replay (#763)

## Ziel

Jeder Run besitzt ein kanonisches, maschinenlesbares Manifest und kann mit identischer oder bewusst veränderter Konfiguration erneut ausgeführt und verglichen werden.

## Design-Entscheidungen (aus Grilling)

| # | Entscheidung |
|---|---|
| D1 | Gesamter Run (Sim+Report). Varianten-Replay = gleiche Config, anderes Seed-Doku/Seed |
| D2 | Snapshot — alles eingefroren, keine Live-Referenzen |
| D3 | `manifest.json` im Run-Dir (autoritativ) + Summary-Felder in Neo4j (Index) |
| D4 | Migration: rekonstruieren was automatisch geht, Rest `null`/`unknown` |
| D5 | Resume = gleiche run_id. Replay = neue run_id + `replayed_from_run_id` |
| D6 | Alles ins Manifest: Hashes, Modelle, Provider, Prompts, Seeds, Versionen, Routing |
| D7 | Vollständige Prompt-Texte (kein Diff) |
| D8 | `POST /api/runs/<run_id>/replay` mit Override-Body |
| D9 | Zwei Phasen: Draft bei Start, final bei Ende |
| D10 | ZIP-Export: `manifest.json` + Artefakte |
| D11 | Pydantic-Validierung + Preflight-Check (warnt, blockiert nicht) |
| D12 | `replayed_from_run_id` + `parent_run_id` getrennt |
| D13 | SHA-256 des rohen Upload-Textes |
| D14 | Replay-Button in Run-Detail + eigenes Untermenü |

## Manifest-Inhalt

```yaml
RunManifest:
  schema_version: 1
  run_id: str
  replayed_from_run_id: str | null
  captured_at: datetime  # Zeitpunkt der Erstellung

  # Eingangsdaten
  inputs:
    seed_document_hash: str  # SHA-256 des rohen Upload-Textes
    seed_document_filename: str
    simulation_config_hash: str  # SHA-256 der simulation_config.json
    graph_id: str
    graph_version: str | null
    embedding_version: str | null

  # Versionen
  versions:
    agora_version: str
    schema_version: str

  # Modell & Provider
  routing:
    stages:
      <stage_id>:
        model: str
        provider: str
        base_url: str  # ohne Secrets
        ai_route_snapshot: dict  # komplette AiRoute

  # Prompts (Snapshot)
  prompts:
    <prompt_key>:
      content: str  # vollständiger Prompt-Text
      source_file: str  # woher der Prompt kam (z.B. sections.py:200)

  # Seeds
  seeds:
    random_seed: int
    simulation_id_seed: str  # der Seed, aus dem random_seed abgeleitet wurde

  # Laufzeit (nur im finalen Manifest)
  runtime:
    started_at: datetime
    completed_at: datetime | null
    duration_seconds: int | null
    rounds_completed: int | null
    usage_summary: RunUsage | null
    termination_reason: str | null

  # Status
  status: "draft" | "final" | "legacy"
```

## API

### Replay
```
POST /api/runs/<run_id>/replay
Body: {
  overrides: {
    seed_document_id: str | null,   # Variante: anderes Dokument
    random_seed: int | null,        # Variante: anderer Seed
    ai_model_ref: AiModelRef | null # Variante: anderes Modell
  }
}
Response: 202 { run_id: str, status: "pending" }
```

### Export
```
GET /api/runs/<run_id>/export
Response: application/zip (manifest.json + Artefakte)
```

### Manifest
```
GET /api/runs/<run_id>/manifest
Response: RunManifest (JSON)
```

## Constraints

- Keine Secrets im Manifest (API-Keys, Passwörter)
- Prompt-Snapshots sind byte-genau
- Draft-Manifest wird bei Run-Start geschrieben
- Finales Manifest wird bei Run-Ende geschrieben
- Abgestürzte Runs behalten Draft-Manifest
- Legacy-Runs bekommen `status: "legacy"` mit rekonstruierten Feldern
