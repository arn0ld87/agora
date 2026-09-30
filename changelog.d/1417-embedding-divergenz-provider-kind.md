### Fixed

- `/readyz` und `POST /api/llm/embedding/configurations/sync-legacy` melden keine
  Env/Store-Divergenz mehr, wenn nur der geratene Provider-Typ abweicht. Ein
  eigener OpenAI-kompatibler Embedding-Endpunkt mit API-Key (Store: `custom`,
  Env-Heuristik: `openai`) machte `/readyz` dauerhaft rot (503), der Container
  wurde nie healthy. Entscheidend sind jetzt nur Modell und Dimension.
