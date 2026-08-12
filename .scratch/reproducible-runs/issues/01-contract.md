# Ticket 1: RunManifest Pydantic Contract

**Blocks:** 2, 3, 4, 5, 7, 8
**Size:** m
**Layer:** 0 (Contract)

## Aufgabe

`RunManifest` als Pydantic-v2-Modell in `backend/app/contracts/run_manifest_contract.py` definieren.

## Inhalt

- `RunManifest` mit allen Feldern aus SPEC.md
- `ManifestStatus`: `Literal["draft", "final", "legacy"]`
- `ManifestInputs`: seed_document_hash, seed_document_filename, simulation_config_hash, graph_id, graph_version, embedding_version
- `ManifestVersions`: agora_version, schema_version
- `ManifestRouting`: dict von stage_id → StageRoute (model, provider, base_url, ai_route_snapshot)
- `ManifestPrompts`: dict von prompt_key → PromptSnapshot (content, source_file)
- `ManifestSeeds`: random_seed, simulation_id_seed
- `ManifestRuntime`: started_at, completed_at, duration_seconds, rounds_completed, usage_summary, termination_reason
- `ReplayRequest`: run_id + overrides (seed_document_id, random_seed, ai_model_ref)
- `ReplayResponse`: run_id, status

## Akzeptanz

- [ ] `dump_schemas --check` grün
- [ ] Contract-Tests grün
- [ ] JSON Schema wird generiert
