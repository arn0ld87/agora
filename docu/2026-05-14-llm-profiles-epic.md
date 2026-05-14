# Epic: LLM-Profile-Management + Per-Step-Provider-Auswahl

**Erstellt:** 2026-05-14  
**Status:** Planung  
**Ziel:** Mehrere LLM-Konfigurationen (Provider + Modell + Key) als benannte Profile
in Agora speichern; beim Starten eines Runs und pro Simulations-Schritt wählbar machen.

---

## Motivation

**Heutiger Zustand:**  
- Genau ein aktives LLM-Profil (global via Settings `LLM_BASE_URL` / `LLM_MODEL_NAME` / `LLM_API_KEY`)
- Provider-Routing basiert auf Modellname → führt zu 401-Fehler wenn `gpt-5.4-mini` + Ollama-Key kombiniert werden
- Kein Wechsel zwischen Schritten möglich

**Zielzustand:**  
- Mehrere benannte Profile (z. B. „Ollama lokal", „OpenAI GPT-4o", „Gemini Pro") speicherbar
- Bei Run-Start: Profil pro Schritt wählbar (Ontologie / Simulation / Report)
- Sicherer Fallback: kein Profil gewählt → Standard-Profil

---

## Scope

**In Scope:**
- LLM-Profile: CRUD (Backend + Frontend)
- Per-Step-Profil-Auswahl im Process-Flow (Step 2 / Run-Start)
- Backward-Compatible: bestehende `LLM_*`-Env-Variablen bleiben als Fallback-Profil "Standard"

**Out of Scope:**
- Live-Switch während eines laufenden Runs (nach Schritt-Fertigstellung, nicht mitten im LLM-Call)
- Streaming-Wechsel
- Token-Cost-Vergleich zwischen Profilen

---

## Layer-Einordnung

| Slice | Layer | Scope |
|---|---|---|
| P5.1 | 0 | Pydantic-Contract `LlmProfile` + Zod-Spiegel |
| P5.2 | 1 | Backend CRUD-API `/api/settings/llm-profiles` |
| P5.3 | 1 | Simulation-Pipeline akzeptiert `llm_profile_id` pro Schritt |
| P5.4 | 4 | Frontend: Profile-Manager in Settings |
| P5.5 | 4 | Frontend: Step-LLM-Picker im Process-Flow (Step 2) |

---

## Slice P5.1 — Pydantic-Contract `LlmProfile` + Zod-Spiegel

**Branch:** `feat/p5.1-llm-profile-contract`  
**Dateien:**
- `backend/app/contracts/llm_profile_contract.py` (neu)
- `frontend/src/contracts/llmProfileContract.ts` (neu, Zod-Spiegel)
- `backend/app/contracts/dump_schemas.py` erweitern

**Contract-Shape:**

```python
class LlmProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str                             # UUID, server-generiert
    name: str                           # Display-Name, z. B. "Ollama lokal"
    provider: Literal["ollama", "openai", "gemini", "anthropic", "custom"]
    base_url: str                       # z. B. http://localhost:11434/v1
    model_name: str                     # z. B. qwen2.5:32b
    api_key: str = ""                   # leer bei Ollama
    is_default: bool = False            # genau eines darf True sein
    created_at: datetime
    updated_at: datetime

class LlmProfileListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profiles: list[LlmProfile]

class LlmProfileCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    provider: Literal["ollama", "openai", "gemini", "anthropic", "custom"]
    base_url: str
    model_name: str
    api_key: str = ""
    is_default: bool = False
```

**Tests:** `backend/tests/contracts/test_llm_profile_contract.py`

**Akzeptanzkriterium:** `dump_schemas.py --check` grün, Zod-Spiegel typcheckt.

---

## Slice P5.2 — Backend CRUD-API

**Branch:** `feat/p5.2-llm-profiles-api`  
**Base:** P5.1  
**Dateien:**
- `backend/app/services/llm_profile_service.py` (neu)
- `backend/app/api/llm_profiles.py` (neu, Flask Blueprint)
- Storage: SQLite-Tabelle `llm_profiles` (kein Neo4j-Overhead für Settings)
  - Oder: in existierendes Settings-System integrieren (abzuwägen)

**API-Endpunkte:**

| Method | Path | Beschreibung |
|---|---|---|
| `GET` | `/api/settings/llm-profiles` | Alle Profile laden |
| `POST` | `/api/settings/llm-profiles` | Neues Profil erstellen |
| `PUT` | `/api/settings/llm-profiles/{id}` | Profil aktualisieren |
| `DELETE` | `/api/settings/llm-profiles/{id}` | Profil löschen |
| `POST` | `/api/settings/llm-profiles/{id}/set-default` | Als Standard setzen |

**Invariante:** Genau ein Profil hat `is_default=True`. Set-Default setzt alle anderen auf False.

**Bootstrap:** Beim ersten Start → auto-generiertes Profil "Standard" aus `LLM_*`-Env-Variablen.

**Tests:** `backend/tests/api/test_llm_profiles.py`

---

## Slice P5.3 — Simulation-Pipeline: Per-Step-Profil-Injektion

**Branch:** `feat/p5.3-per-step-llm`  
**Base:** P5.2  
**Scope:** Backend-only, kein Frontend-Touch

**Änderungen:**
- `backend/app/api/graph.py` → `generate_ontology` akzeptiert optionales `llm_profile_id`-Feld im Request-Body
- `backend/app/services/ontology_generator.py` → nimmt `llm_profile` statt globale Env-Variablen
- `backend/app/api/report.py` → Report-Endpunkte akzeptieren `llm_profile_id`
- `backend/app/utils/llm_client.py` → Fabrik-Funktion `build_client_from_profile(profile: LlmProfile)`

**Backward-Compat:**  
`llm_profile_id=None` (Default) → Fallback auf Standard-Profil → identisches Verhalten wie heute.

**Tests:** `backend/tests/services/test_ontology_generator_profile.py`

---

## Slice P5.4 — Frontend: Profile-Manager in Settings

**Branch:** `feat/p5.4-llm-profile-manager-ui`  
**Base:** P5.3  
**Dateien:**
- `frontend/src/components/v4/forms/LlmProfileManager.vue` (neu, ≤ 300 LOC)
- `frontend/src/api/llmProfiles.ts` (neu, API-Client)
- `frontend/src/store/llmProfiles.ts` (neu, Pinia-Store)
- `frontend/src/views/Settings/SettingsGeneralView.vue` — `LlmProfileManager` ergänzen
- i18n: `settings.v4.llmProfiles.*` in `de.json` + `en.json`

**UI-Verhalten:**
1. Liste aller Profile als Cards (Name, Provider-Badge, Modell, Default-Marker)
2. Neues Profil: Preset-Auswahl (wie bestehende `LlmProviderCard`) → Speichern
3. Profil bearbeiten: In-Place-Edit oder Modal
4. Profil löschen: Bestätigung, wenn es das Standard-Profil ist
5. Default setzen: Ein-Klick per "Als Standard" Button

**Tests:** `frontend/src/components/v4/forms/__tests__/LlmProfileManager.spec.ts`

---

## Slice P5.5 — Frontend: Step-LLM-Picker im Process-Flow

**Branch:** `feat/p5.5-step-llm-picker`  
**Base:** P5.4  
**Dateien:**
- `frontend/src/components/v4/dashboard/StepLlmPicker.vue` (neu, ≤ 150 LOC)
- `frontend/src/views/Process/ProcessView.vue` oder Step 2 — Picker einbinden
- API-Aufrufe aus Step 2/3 erweitern: `llm_profile_id` mitsenden

**UI-Verhalten (Process-Flow):**
- Unter dem bestehenden Modell-Selector in `HeroNewRun.vue` (oder Step 2):
  - Aufklappbarer Bereich „Erweiterte LLM-Einstellungen"
  - Drei Dropdowns: Ontologie / Simulation / Report
  - Default: Standard-Profil (leer = Standard-Profil verwendet)
- Beim Starten → gewählte `llm_profile_id`s per JSON an Backend

**Tests:** `frontend/src/components/v4/dashboard/__tests__/StepLlmPicker.spec.ts`

---

## Abhängigkeitsgraph

```
P5.1 (Contract)
  └── P5.2 (CRUD-API)
        └── P5.3 (Pipeline-Injektion)
              ├── P5.4 (Profile-Manager UI)
              │     └── P5.5 (Step-Picker UI)
              └── (Backend vollständig, Frontend optional pro Step)
```

P5.1 + P5.2 + P5.3 bilden den Backend-Trunk — alles sequenziell.  
P5.4 und P5.5 können nach P5.3 parallel gebaut werden.

---

## Risiken

| Risiko | Mitigation |
|---|---|
| `api_key`-Handling: Secrets dürfen nicht im API-Response stehen | Backend maskiert `api_key` in GET-Responses (`"***"`); nur bei POST/PUT im Body |
| `is_default`-Invariante bricht bei concurrent Updates | Datenbank-Constraint oder Lock in Service-Schicht |
| Bestehende Runs nutzen falschen Provider nach Profil-Löschung | Runs speichern `llm_profile_snapshot` (serialized) zum Zeitpunkt des Starts |

---

## Offene Fragen (vor P5.2 klären)

1. **Storage:** SQLite-Tabelle `llm_profiles` vs. Erweiterung des bestehenden Settings-Systems?  
   Empfehlung: eigene Tabelle (`backend/app/storage/llm_profiles_store.py`), kein Neo4j.

2. **Secret-Handling:** Werden `api_key`-Werte verschlüsselt gespeichert oder plain text in der DB?  
   Empfehlung: Gleiche Behandlung wie bestehende Settings-Secrets (kein zusätzlicher Crypto-Layer in MVP).

3. **Step-Granularität:** Drei Schritte (Ontologie / Simulation / Report) oder feiner?  
   Empfehlung: Drei Schritte für MVP; feiner auf Anfrage.
