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

- 2.2 Quality-MVP — siehe Abschnitt unten.
- 2.3 Start-Gate: in `simulation_run.py` / `simulation_prepare.py` `409` werfen, wenn `PERSONA_REVIEW_ENABLED=true` und nicht alle Personas `approved`.
- 2.4 Frontend: Liste, Editor-Drawer, Quality-Badges in `Step2EnvSetup.vue`; API-Anbindung via `frontend/src/api/simulation.js` und ein `usePersonaReview.js`-Composable.

## 2.2 — Quality-MVP

### Vorgehen

1. Heuristiken bewusst deterministisch und ohne LLM-/Neo4j-Zugriff gehalten, weil das Endpoint im Hot-Path der UI-Liste landen wird.
2. Per-Persona-Detektoren:
   - `duplicate_username` (error) — case-insensitives Mehrfachvorkommen.
   - `duplicate_name` (warning) — case-insensitives Mehrfachvorkommen, leere Namen werden ignoriert.
   - `missing_core_fields` (warning bei einem fehlenden Kernfeld, error wenn alle drei `bio|persona|profession` fehlen).
   - `missing_entity_link` (info) — kein `source_entity_uuid` und nicht `is_manual=true`.
3. Globale Detektoren:
   - `no_personas` (warning) — leere Liste.
   - `role_diversity` — warning bei nur 1 distinct profession; info wenn distinct/total < 0.34, sonst kein Signal.
   - `mbti_diversity` — analog (warning nur wenn total > 1, sonst rauscht das Signal).
4. Summary liefert zusaetzlich Status-Counts (`approved`/`pending`/`rejected`) und Diversity-Ratios.
5. Route: `GET /<sim>/profiles/quality` ohne Existenz-Check fuer die Simulation, weil ein leerer Lauf das `no_personas`-Signal sowieso liefert. Antwort enthaelt `review_enabled` parallel zu `GET /profiles`, damit die UI ein einziges Truth-Source-Dokument zum Rendern hat.

### Geaenderte/Neue Dateien (2.2)

| Datei | Aenderung |
|---|---|
| `backend/app/services/persona_quality_service.py` | **Neu**: pure-Python Heuristik-Service, deterministisch, JSON-serialisierbar |
| `backend/app/api/simulation_profiles.py` | neue Route `GET /<sim>/profiles/quality` (liefert Summary, Per-Persona-Issues, Global-Issues, `review_enabled`) |
| `backend/tests/test_persona_quality_service.py` | **Neu**: 11 Service-Tests (Empty-Sim, Dubletten, Kernfelder, Entity-Link, Diversity-Severities, Default-Status-Normalisierung) |
| `backend/tests/test_simulation_api_routes.py` | API-Smoke-Tests `quality_route_returns_summary_and_issues`, `quality_route_validates_simulation_id` |

### Verifikation (2.2)

```bash
npm run check
```

Ergebnis: Backend-Lint gruen, **251 passed, 2 skipped**, Frontend-Lint gruen, Vite-Build gruen.

## 2.4 — Frontend (Step2EnvSetup)

### Vorgehen

1. Bestehende Step2-Komponente und API-Schicht inventarisiert; bestaetigt, dass `frontend/src/api/simulation.js` axios-`service` mit `patch`-Support exportiert und `Badge.vue`/`Btn.vue` die benoetigten Varianten (`success|warn|error|plasma|ghost`) bereits aus Slice 1 mitbringen.
2. API-Methoden in `frontend/src/api/simulation.js` ergaenzt:
   - `editSimulationProfile(simId, username, data)`
   - `approveSimulationProfile(simId, username, notes?)`
   - `rejectSimulationProfile(simId, username, reason?)`
   - `getSimulationProfilesQuality(simId)`
3. Composable `frontend/src/composables/usePersonaReview.js` neu angelegt:
   - reaktiver Cache `issuesByUsername` (`Map`), `summary`, `globalIssues`, `reviewEnabled`, `isLoading`, `error`.
   - Helfer `getIssuesFor(username)`, `highestSeverityFor(username)` fuer Badge-Logik.
   - Aktionen `refreshQuality`, `approve`, `reject`, `editProfile` werfen kontrolliert Fehler weiter.
4. `Step2EnvSetup.vue` erweitert, ohne Layout/UX umzubauen:
   - Persona-Karten zeigen jetzt einen Status-Badge (`approved`/`pending`/`rejected`) und einen Hinweis-Badge mit Anzahl + Severity-Farbe.
   - Detail-Modal hat eine Review-Bar (Status, Bearbeiten, Ablehnen, Freigeben) und listet die Quality-Issues unterhalb der Bar.
   - Edit-Modus toggelt das Read-Only-Layout in ein Form-Grid mit denselben Feldern wie der Add-Persona-Dialog; Save ruft den PATCH-Endpoint, anschliessender `refreshQuality()` aktualisiert Badges.
   - `applyProfileToList()` patcht das Profil sowohl in `profiles.value` als auch in `selectedProfile`, damit das Modal nach Approve/Reject/Edit ohne Reload sofort den neuen Status zeigt.
5. Quality-Fetch ist an `fetchProfilesRealtime()` gekoppelt: wenn Personas geladen sind, refresht der Composable im Hintergrund. Polling-Intervall bleibt 3s aus `usePolling`, kein zusaetzlicher Timer.

### Geaenderte/Neue Dateien (2.4)

| Datei | Aenderung |
|---|---|
| `frontend/src/api/simulation.js` | Vier neue Methoden (`editSimulationProfile`, `approveSimulationProfile`, `rejectSimulationProfile`, `getSimulationProfilesQuality`) |
| `frontend/src/composables/usePersonaReview.js` | **Neu**: reaktiver Wrapper um Review/Quality-Endpoints |
| `frontend/src/components/Step2EnvSetup.vue` | Karten zeigen Status-/Hinweis-Badges; Detail-Modal mit Review-Bar, Issue-Liste, Inline-Edit; Quality-Refresh nach jedem Profile-Polling-Tick; neue scoped Styles `persona-meta-row`, `review-bar`, `review-issues`, `review-error` |

### Bewusst nicht geaendert

1. Add-Persona-Dialog bleibt unveraendert; der Edit-Modus nutzt eine eigene, kleinere Form-Variante im bestehenden Detail-Modal.
2. Polling-Architektur (`usePolling`) wurde nicht erweitert; Quality-Refresh laeuft als Side-Effect im Profile-Tick.
3. Keine `i18n`-Keys ergaenzt — Slice-2-UI nutzt deutsche Inline-Strings im DACH-Default-Modus, konsistent mit den uebrigen Slice-2-Buttons.

### Verifikation (2.4)

```bash
npm run check
```

Ergebnis: Backend-Lint gruen, **251 passed, 2 skipped**, Frontend-Lint gruen, Vite-Build gruen (724 Module statt vorher 723; +ca. 8 KB JS gzip).

## 2.3 — Simulation-Start-Gate

### Vorgehen

1. Gate bewusst als **letzter** Slice-2-Schritt scharfgeschaltet, weil 2.1/2.2/2.4 produktiv ohne Verhaltenswechsel laufen mussten.
2. `PersonaReviewService.evaluate_start_gate(simulation_id)` ergaenzt: liefert `{allowed, total, approved[], pending[], rejected[]}` und liest selbst keinen Config-Flag, damit der Service unit-testbar bleibt.
3. Helper `_evaluate_persona_review_gate` in `backend/app/api/simulation_run.py`: prueft den globalen Flag, ruft den Service und liefert bei `allowed=False` ein `409 Conflict`-Envelope mit `code="persona_review_required"` plus dem vollen `review`-Objekt unter `extra={"review": ...}`. Frontend kann darueber direkt rendern, welche Personas blockieren.
4. Gate liegt in `start_simulation` direkt nach dem `404`-Check fuer die Simulation und vor `_check_simulation_prepared`/Status-Reset, damit Resume/Restart denselben Gate sehen wie ein Erststart.
5. Empty-Simulation-Edge-Case: `evaluate_start_gate` setzt `allowed=False` wenn keine Personas vorhanden sind — ein Run ohne Agenten waere ohnehin sinnlos und der Gate liefert dafuer eine eindeutige 409-Begruendung.
6. Tests: drei zusaetzliche Service-Tests (`blocks_when_pending_or_rejected`, `allows_when_all_approved`, `blocks_empty_simulation`) und zwei API-Smoke-Tests (`blocks_when_personas_pending`, `skips_gate_when_flag_disabled`). Letzterer monkeypatcht `Config.PERSONA_REVIEW_ENABLED=False` und prueft nur, dass kein 409 kommt — die Folgevalidierungen sind nicht Teil dieses Gates.

### Geaenderte/Neue Dateien (2.3)

| Datei | Aenderung |
|---|---|
| `backend/app/services/persona_review_service.py` | neue Methode `evaluate_start_gate(simulation_id)` |
| `backend/app/api/simulation_run.py` | Helper `_evaluate_persona_review_gate`; Aufruf direkt nach dem Existenz-Check der Simulation; Imports um `Config` und `PersonaReviewService` ergaenzt |
| `backend/tests/test_persona_review_service.py` | drei Gate-Tests (Pending/Rejected, alle approved inkl. manuelle, leere Simulation) |
| `backend/tests/test_simulation_api_routes.py` | zwei Route-Tests (`/api/simulation/start` mit Flag on/off, monkeypatched `Config.PERSONA_REVIEW_ENABLED`) und ein `_seed_ready_simulation`-Helper |

### Bewusst nicht geaendert

1. Resume-/Restart-Pfad teilt das gleiche Gate, weil `start_simulation` der einzige Eingang in den OASIS-Subprozess ist.
2. `prepare`/`generate-profiles` werden vom Gate NICHT erfasst — Reviewer:innen sollen Personas weiter editieren, approven oder rejecten koennen, auch wenn der Run blockiert ist.
3. Der OASIS-Subprozess selbst kennt das Gate nicht; sobald der Start zugelassen ist, laufen alle Personas (auch die mit `review_status=approved`) wie bisher in den OASIS-Configgenerator.

### Verifikation (2.3)

```bash
npm run check
```

Ergebnis: Backend-Lint gruen, **256 passed, 2 skipped**, Frontend-Lint gruen, Vite-Build gruen.

## Slice-2-Abschluss

Mit 2.1 → 2.2 → 2.4 → 2.3 ist die **Persona Review Foundation** komplett:

- Backend-Lifecycle (`pending|approved|rejected`) inkl. Edit-Reset, opt-in via `PERSONA_REVIEW_ENABLED`.
- Quality-MVP mit Per-Persona- und Global-Heuristiken.
- Frontend: Status- und Hinweis-Badges auf jeder Karte, Review-Bar im Detail-Modal, Inline-Edit-Form, reaktiver Cache via `usePersonaReview`.
- Start-Gate: blockiert OASIS-Run mit `409 persona_review_required`, solange das Flag aktiv ist und nicht alle Personas freigegeben sind.

Naechster sinnvoller Schritt aus `docu/2026-04-29-v07-umsetzungsplan.md`: **Slice 3 Run Dashboard** oder **Slice 4 Evidence & Confidence MVP**.
