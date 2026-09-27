### Behoben

- Die öffentliche Demo (`AGORA_DEMO_MODE=true`) startet jetzt ohne Betreiber-`LLM_API_KEY`: `Config.validate()` verlangt ihn im Demo-Modus nicht mehr, die Embedding-Startup-Probe und das Neo4jStorage-Setup laufen im ausdrücklich gebundenen Operator-Scope, und der Default-NER des Storage wird erst bei Bedarf gebaut (#1688).
