# v0.7 Slice 2 — Persona Review Foundation Arbeitsprotokoll

Datum: 2026-04-29  
Repo: `/mnt/brain/Projekte/Agora`  
Branch: `main`  
Vorgaenger-Slice: 1 (Design-Tokens, abgeschlossen mit Commit `027fec7`).

## Ziel

Slice 2 aus `docu/2026-04-29-v07-umsetzungsplan.md` startet die Persona Review Foundation: generierte und manuell hinzugefuegte Personas bekommen einen pruefbaren Lifecycle, koennen editiert und freigegeben werden, ohne den OASIS-Subprozess oder die `simulation_config.json`-Generierung anzufassen.

## Sub-Slice-Schnitt

Wegen Groesse von Slice 2 wurde der Block in vier Unter-Slices zerlegt (alle bestaetigt mit Nutzer):

1. **2.1 Backend-Review-State** (dieses Protokoll).
2. **2.2 Quality-MVP** — Dubletten, fehlende Kernfelder, Entity-Bezug, Rollen-Diversitaet.
3. **2.3 Simulation-Start-Gate** — bei `PERSONA_REVIEW_ENABLED=true` muessen alle Personas `approved` sein.
4. **2.4 Frontend-UI** — Persona-Liste mit Quality-Badges, Editor-Drawer, Approve/Reject in `Step2EnvSetup.vue`.

## 2.1 — Backend-Review-State

### Vorgehen

1. `sequential thinking` (mental, ohne MCP-Tool) genutzt, um Datenmodell und Endpoint-Schnitt festzulegen, weil der Slice quer durch Service-, API- und Tests-Schicht greift.
2. Vorhandene Persona-Infrastruktur inventarisiert: `backend/app/services/persona_library.py`, `backend/app/services/oasis_profile_generator.py`, `backend/app/api/simulation_profiles.py`, `backend/app/services/artifact_store.py` (Hexagonal-Port + In-Memory-Adapter).
3. Daten-/Persistenz-Modell festgelegt: kein neues Artefakt, statt dessen drei Felder pro Persona im bestehenden `reddit_profiles.json`:
   - `review_status` ∈ `pending|approved|rejected`,
   - `review_notes` (optionaler Reviewer-Kommentar),
   - `reviewed_at` (UTC-ISO-Timestamp).
4. Default-Strategie definiert:
   - Lese-Pfad ist **lazy normalisiert** — `list_profiles` ergaenzt fehlende `review_status`-Felder erst beim Lesen, der Artefakt-Store wird nicht mutiert.
   - Manuell hinzugefuegte Personas (`is_manual=true`) defaulten auf `approved`, weil sie explizit kuratiert wurden.
   - Generierte Personas defaulten auf `pending`.
5. Feature-Flag `PERSONA_REVIEW_ENABLED=false` als Opt-in eingefuehrt. Endpoints sind immer aktiv; das Flag schaltet erst in Slice 2.3 den Start-Gate scharf und wird in der GET-Profiles-Antwort als `review_enabled` mitgeliefert (Frontend-Vorbereitung).
6. Service `PersonaReviewService` implementiert:
   - `list_profiles(simulation_id, normalize=True)` — defensive Lese-Routine (skipt nicht-dict-Eintraege).
   - `get_profile`, `approve`, `reject`, `set_status`, `edit`.
   - `edit()` setzt approved/rejected zurueck auf `pending` (Reviewer-Re-Confirmation), ausser der Aufrufer schickt `review_status` explizit mit.
   - `_clean_updates()` whitelistet `_EDITABLE_FIELDS`, normalisiert `interested_topics` (Komma-String → Liste), validiert `review_status`.
   - Fehlerklassen `PersonaNotFoundError` (→ 404) und `InvalidReviewStatusError` (→ 400, ueber `ValueError`-Pfad in `handle_api_errors`).
7. API-Endpoints in `simulation_profiles.py`:
   - `PATCH /<sim>/profiles/<username>` — Edit.
   - `POST  /<sim>/profiles/<username>/approve` — optional `notes`.
   - `POST  /<sim>/profiles/<username>/reject` — optional `notes` oder `reason`.
   - `GET   /<sim>/profiles` liefert fuer Reddit jetzt normalisierten Review-State plus `review_enabled`-Flag.
   - Alle drei neuen Endpoints nutzen `request.get_json(silent=True)`, weil Tests/Clients ohne Content-Type sonst 415 produzieren wuerden.
8. Tests (12 Service + 3 API-Smoke-Tests) gegen den `InMemoryArtifactStore` geschrieben, also kein Filesystem-Tmp-Setup noetig.
9. Doku-Sync: `CLAUDE.md` und `AGENTS.md` um die neue `PERSONA_REVIEW_ENABLED`-Zeile ergaenzt.

### Geaenderte/Neue Dateien

| Datei | Aenderung |
|---|---|
| `backend/app/config.py` | `PERSONA_REVIEW_ENABLED`-Flag, opt-in via `PERSONA_REVIEW_ENABLED=true` |
| `backend/app/services/persona_review_service.py` | **Neu**: Service mit `list/get/approve/reject/set_status/edit` und Default-Status-Heuristik |
| `backend/app/api/simulation_profiles.py` | `GET /profiles` normalisiert + liefert `review_enabled`; neue Routes `PATCH /profiles/<username>`, `POST /profiles/<username>/approve`, `POST /profiles/<username>/reject` |
| `backend/tests/test_persona_review_service.py` | **Neu**: 12 Service-Tests (Lifecycle, Idempotenz, Edit-Reset, Validation, Not-found, Defensive Reads) |
| `backend/tests/test_simulation_api_routes.py` | API-Smoke-Tests fuer Approve/Edit/Reject-Round-Trip, 404-Pfad, 400 bei leerer Edit-Payload; `_build_test_app` akzeptiert jetzt einen `artifact_store`-Override |
| `CLAUDE.md` / `AGENTS.md` | Konfigurationsabschnitt um `PERSONA_REVIEW_ENABLED` ergaenzt |

### Bewusst nicht geaendert

1. `oasis_profile_generator.py`, `simulation_config_generator.py` — Generierung bleibt unangetastet, der Lifecycle ist komplett am bestehenden Artefakt aufgehaengt.
2. `simulation_manager.get_profiles()` — bleibt der Validations-Eintrag (raised, wenn die Simulation nicht existiert), die normalisierten Daten kommen direkt aus dem Service ueber den Artefakt-Store.
3. Kein Daten-Migrationsschritt — bestehende `reddit_profiles.json`-Files ohne `review_status` werden weiter akzeptiert und beim Lesen lazy normalisiert.
4. Kein Start-Gate fuer die Simulation — das ist Slice 2.3.

### Verifikation

```bash
npm run check
```

Ergebnis:

```text
lint:backend: All checks passed
pytest:       238 passed, 2 skipped
              (Redis-Phase-B-Integrationstests sauber geskippt ohne TEST_REDIS_URL)
lint:frontend: gruen
build:frontend: Vite build gruen
```

Vor Commit:

```bash
git diff --check
```

→ keine Whitespace-/Patchfehler.

### Naechste Schritte

- 2.2 Quality-MVP: Service `persona_quality_service.py` mit Heuristiken (Dubletten, fehlende Kernfelder, Entity-Bezug, Rollen-/MBTI-Diversitaet) und `GET /<sim>/profiles/quality`.
- 2.3 Start-Gate: in `simulation_run.py` / `simulation_prepare.py` `409` werfen, wenn `PERSONA_REVIEW_ENABLED=true` und nicht alle Personas `approved`.
- 2.4 Frontend: Liste, Editor-Drawer, Quality-Badges in `Step2EnvSetup.vue`; API-Anbindung via `frontend/src/api/simulation.js` und ein `usePersonaReview.js`-Composable.
