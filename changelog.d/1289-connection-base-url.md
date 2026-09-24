### Fixed

- `PUT /api/llm/active-config` hat `base_url` ausschließlich aus der statischen
  Provider-Registry abgeleitet (`ProviderConnectionDefinition.default_base_url`)
  und damit eine über das Connection-UI gespeicherte, abweichende `base_url`
  stillschweigend verworfen — der Nutzer sah seinen Wert im Connection-Record,
  zur Laufzeit lief `LLMClient` trotzdem gegen den Registry-Default. Beobachtet
  am 13.08.2026 bei der Bedrock-Diagnose (#1282/#1288): eine auf `us-east-1`
  gesetzte Connection blieb aktiv auf `eu-central-1`. `put_active_config` liest
  `base_url` jetzt zuerst aus dem `ProviderConnectionStore` und fällt erst ohne
  gespeicherte Connection (bzw. ohne dort gesetzte `base_url`) auf den
  Registry-Default zurück. Für `transport="cli"`/`auth_mode="session"`-Provider
  (`codex_cli`) wird weiterhin nie eine `base_url` erfunden. Der Request-Body
  bleibt für `base_url` unverändert ignoriert — die SSRF-Härtung aus #478 ist
  davon nicht betroffen, Body-Input und persistierter Connection-Record sind
  zwei verschiedene Vertrauensstufen. `llm/client.py` brauchte keine Änderung:
  es liest `base_url` bereits aus der persistierten Active-Config, die ab jetzt
  korrekt befüllt wird.
