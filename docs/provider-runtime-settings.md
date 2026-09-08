# Provider-Runtime-Optionen

**Stand:** 08.09.2026  
**Geprüfte Main-Baseline:** `0c47737f`  
**Produktversion:** `0.9.5`

Diese Datei beschreibt die **heutige** Provider-, Secret- und Routing-Architektur. Der frühere Pfad „Provider im Browser auswählen, API-Key in `sessionStorage` halten und bei jedem Prepare/Start/Report im Request-Body mitschicken“ ist nicht mehr die kanonische Architektur.

Kanonische Referenzen:

- Provider-Matrix: [`backend/app/services/llm_provider_registry.py`](../backend/app/services/llm_provider_registry.py)
- Provider-Detection/Adapter: [`backend/app/llm/providers/registry.py`](../backend/app/llm/providers/registry.py)
- Verbindungen: `ProviderConnection`
- Modellreferenzen/Routing: `AiModelRef`, `AiRoute`, `LlmRoute`
- Secret Store: `backend/app/services/llm_provider_secrets_store.py`
- Workspace-Routing: `backend/app/services/llm_routing_seed.py` / Routing-API
- UI: [`frontend/src/components/v4/forms/AiModelPicker.vue`](../frontend/src/components/v4/forms/AiModelPicker.vue)
- Architektur-SSoT: [`agents/architecture-ssot.md`](agents/architecture-ssot.md)

---

## Grundmodell

Agora trennt vier Dinge, die früher teilweise vermischt waren:

1. **Provider-Definition** — welche Transport- und Auth-Art ein Provider besitzt.
2. **ProviderConnection** — konkrete, persistierte Verbindung/Endpoint-Konfiguration.
3. **Secret** — API-Key oder andere Credentials, separat gespeichert und verschlüsselt.
4. **Route** — welche Connection und welches Modell eine Pipeline-Stage tatsächlich verwendet.

Eine Modell-ID allein ist deshalb **keine vollständige Runtime-Konfiguration**.

```text
Workspace/Run
   ↓
AiRoute / LlmRoute
   ↓
ProviderConnection + model_id
   ↓
SecretResolver (falls auth_mode=api_key)
   ↓
Transport-Adapter (http | local | cli)
```

## Transport- und Auth-Klassen

Die Provider-Matrix kennt aktuell:

| Transport | Bedeutung | Typische Auth |
|---|---|---|
| `http` | externer oder lokaler HTTP-Endpunkt | `api_key` |
| `local` | lokaler HTTP-Dienst, derzeit insbesondere Ollama | `none` |
| `cli` | lokaler CLI-Subprozess ohne HTTP-Endpoint | `session` |

`cli` ist absichtlich nicht mit `local` gleichgesetzt: Ein lokaler Ollama-Server ist HTTP, `codex_cli` dagegen nicht.

## Aktuelle Provider-Matrix

Die verbindliche Liste steht im Code. Stand der geprüften Baseline:

| Provider | Transport | Auth | Bemerkung |
|---|---|---|---|
| OpenAI | `http` | `api_key` | nativer OpenAI-kompatibler Pfad |
| Anthropic | `http` | `api_key` | Registry-Eintrag vorhanden; native Chat-Transport-Schuld siehe #1284 |
| Google Gemini | `http` | `api_key` | OpenAI-kompatibler Endpoint |
| MiniMax | `http` | `api_key` | HTTP |
| Ollama Cloud | `http` | `api_key` | Cloud-Endpunkt |
| OpenAI Compatible | `http` | `api_key` | frei konfigurierbare Base-URL |
| Ollama lokal | `local` | `none` | lokaler HTTP-Server |
| OpenCode Go | `http` | `api_key` | Registry vorhanden, Adapter bewusst `unsupported` |
| GitHub Copilot | `http` | `api_key` | Registry vorhanden, Adapter bewusst `unsupported` |
| Amazon Bedrock | `http` | `api_key` | OpenAI-kompatibler Mantle-Pfad; native SigV4/Converse ist separates Thema |
| Codex CLI | `cli` | `session` | `codex login`, keine Base-URL, kein API-Key im Agora-Store |

### Codex CLI

`codex_cli` ist seit #1405/#1406 ein eigener Provider-Typ. Wichtige Regeln:

- `base_url=None` ist **normal** und kein Fehler.
- `auth_mode="session"`: Anmeldung liegt in der lokalen `codex`-Session.
- Agora darf bei einer aufgelösten CLI-Route **nicht** auf `LLM_BASE_URL`/`LLM_API_KEY` aus `.env` raten.
- Persona-Generierung führt `provider_type` inzwischen bis zum `LLMClient` durch (#1418/#1422).
- OASIS-Simulationsrunden besitzen einen eigenen Codex-CLI-Transport (#1423/#1424).
- Große Prompts werden über stdin an `codex exec` übergeben, nicht als einzelnes argv-Argument (#1425-Fix im #1424-Pfad).

## Verbindungen und Secrets

HTTP/API-Key-Provider werden über `ProviderConnection` und den Secret Store verwaltet.

Persistiert werden getrennt:

- secret-freie Connection-Metadaten, z. B. Provider-Typ und Base-URL,
- verschlüsselte Provider-Secrets,
- Workspace-/Stage-Routing.

Provider-Keys gehören **nicht** in Run-Manifeste, Report-Artefakte oder Frontend-Storage als dauerhafte Klartextquelle.

`AGORA_SECRET_KEY` ist der Master-Key für den Provider-Secret-Store. Verlust dieses Keys kann gespeicherte Provider-Credentials unbrauchbar machen; siehe [`secret-key-lifecycle.md`](secret-key-lifecycle.md).

## Workspace- und Stage-Routing

Ein Lauf kann unterschiedliche Modelle/Provider je Stage verwenden. Die kanonische Auswahl läuft über die Routing-Verträge und nicht über verstreute `.env`-Heuristiken.

Typische Stages umfassen je nach Pfad unter anderem:

- Ontologie/NER/Graph
- Persona-Generierung
- Simulation-Konfiguration
- Simulationsrunden
- Report/Report-Interviews

Die konkrete Stage-Liste ist im Pydantic-Vertrag unter `backend/app/contracts/llm_routing_contract.py` führend.

### Prioritätsregel

Wenn eine konkrete Route/Connection aufgelöst wurde, ist sie die Wahrheit. `.env`-Werte sind Legacy-/Bootstrap-Fallback und dürfen keine halb aufgelöste Route mit einem fremden Endpoint oder Key vermischen.

Der frühere Persona-Fehler aus #1418 war genau ein solcher Mix: Modell aus der Route, Endpoint/Key aus `.env`. Der Code-Fix ist gemergt.

## Active Config und Connection-Base-URL

Die aktive Auswahl und eine gespeicherte `ProviderConnection` sind unterschiedliche Objekte. Für Base-URL-Overrides existiert weiterhin technische Schuld: [#1289](https://github.com/arn0ld87/agora/issues/1289) beschreibt einen Pfad, bei dem beim Aktivieren ein Registry-Default statt der gespeicherten Connection-Base-URL gewinnen kann.

Besonders bei Amazon Bedrock ist das relevant, weil die Region Teil der Host-Subdomain ist. Ein UI-Edit der Connection ist deshalb bis zur vollständigen Behebung nicht automatisch ein Beweis dafür, dass exakt dieser Endpoint im Active-Config-Pfad verwendet wird.

## Amazon Bedrock

Der derzeitige Bedrock-Eintrag verwendet den OpenAI-kompatiblen Mantle-Pfad mit Bearer-Token. Das ist **nicht** dasselbe wie die native Bedrock Runtime `Converse`/`InvokeModel` mit SigV4.

Folgen:

- Nicht jedes im Bedrock-Katalog sichtbare Modell ist über `/v1/chat/completions` nutzbar.
- Native Claude- und GPT-5.x-Familien benötigen je nach Modell den noch separaten Converse/SigV4-Pfad; siehe #1287.
- Die Default-Region ist an die Registry-Base-URL gekoppelt; regionale Modellkataloge unterscheiden sich.

## Tool-Calling und JSON-Mode

Strukturierte JSON-Aufrufe laufen über `LLMClient.chat_json` und Pydantic-Schemas. Provider-/Modellfähigkeit für natives Tool-Calling wird zentral aus Provider-Typ und Modellfamilie beurteilt.

Wichtige Runtime-Schalter:

| Variable | Wirkung |
|---|---|
| `LLM_DISABLE_JSON_OBJECT_MODE=true` | `json_object` bei schema-losen Aufrufen unterdrücken |
| `LLM_DISABLE_JSON_SCHEMA_MODE=true` | strict `json_schema` unterdrücken; Pydantic-Validierung bleibt post-hoc |
| `LLM_DISABLE_JSON_MODE=true` | veralteter Legacy-Alias für `LLM_DISABLE_JSON_OBJECT_MODE` |

Bei Schema-Calls bleibt das Pydantic-Modell die fachliche Grenze, auch wenn der Provider keinen nativen Strict-JSON-Modus unterstützt.

## Run-Budgets und Provider-Calls

Seit #1478 werden Text-, native Tool-, Vision- und Interview-Aufrufe pro physischem Provider-Versuch gegen das Run-Budget geprüft und im Ledger verbucht. Budgetüberschreitungen werden nicht als weicher Interview-/Persona-Fehler verschluckt.

**Bekannte Grenze:** Der separate `ParallelIPCHandler` in `scripts/run_parallel_simulation.py` besitzt noch nicht dieselbe vollständige Report-Budget-Attribution wie der normale IPC-Handler. Siehe [`STATUS.md`](STATUS.md).

## Embeddings sind ein eigener Konfigurationspfad

Embedding-Routing wird bewusst **nicht** aus dem Chat-Provider-Routing abgeleitet. Kanonische Persistenz ist der `EmbeddingConfigurationStore`, Migrationen besitzen einen eigenen Lifecycle.

Aktuell offen: [#1417](https://github.com/arn0ld87/agora/issues/1417). Einige produktive Runtime-Consumer können weiterhin `Config.EMBEDDING_*` aus der Umgebung lesen, obwohl die UI eine andere Konfiguration als aktiv markiert. Bis zur Behebung darf die Embedding-UI nicht als vollständige Runtime-SSoT interpretiert werden.

## Debugging-Reihenfolge

Bei einem Routingfehler nicht zuerst fünf `.env`-Variablen drehen. Prüfen in dieser Reihenfolge:

1. aktive Workspace-/Run-Route,
2. `provider_id` und `model_id`,
3. gespeicherte `ProviderConnection`,
4. `transport` und `auth_mode` aus der Registry,
5. Secret-Resolver-Quelle,
6. erst danach Legacy-/Bootstrap-Env-Fallback.

Im LLM-Init-Log werden `provider_id` und `provider_type` getrennt ausgewiesen (#1457), damit ein CLI-Provider nicht nur als `provider_id=unknown` wie eine Fehlkonfiguration aussieht.
