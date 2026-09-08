### Added

- Echte Integrationstest-Schicht gegen laufendes Neo4j/Redis (Slice 9, Tech-Review 2026-09-07): neuer `integration`-Marker (`backend/pyproject.toml`), standardmäßig ausgeschlossen wie `llm`; `backend/tests/integration/conftest.py` mit `redis_client`- und `neo4j_session`-Fixtures, die bei fehlenden `AGORA_TEST_*`-Env-Variablen kontrolliert überspringen; `neo4j_session` erzeugt eine pro Lauf eindeutige Kennung und räumt im Teardown ausschließlich die davon markierten Knoten ab. Zwei Tests: Redis-Event-Bus Publish/Subscribe über einen echten Server, sowie Idempotenz des Episode/RELATION-Schreibpfads gegen echtes Neo4j. Neuer CI-Job `integration` (`redis:7` + `neo4j:5` als Services), läuft nur auf `push:main` und `workflow_dispatch`. `AGORA_TEST_REQUIRE_SERVICES=1` (im CI-Job gesetzt) macht aus dem Env-Skip ein hartes Fail — sonst meldete sich der Integrationsjob gruen, wenn ein Service-Container gar nicht hochkommt.

### Fixed

- Kein Fix in diesem Slice — B9 (`_entity_identity_key`) und B11 (`update_run`/`updated_at`) waren bei Prüfung gegen `main` bereits behoben; dieser Slice ergänzt für B11 den fehlenden Regressionstest (Passthrough-Feld-only Update bumpt `updated_at`). B9 hatte bereits einen Regressionstest (`backend/tests/services/test_persona_cap_dedup.py::test_gleicher_name_unter_verschiedenen_typen_bleibt_getrennt`).
