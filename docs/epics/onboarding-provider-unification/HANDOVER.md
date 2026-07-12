# Handover — Onboarding/Provider-Unification Slice 2

## Stand

### Slice-3-Präzisierung (2026-07-12)

- `ProviderConnection.base_url` ist providerabhängig: lokales Ollama darf nur
  explizite Loopback-HTTP(S)-URLs verwenden; alle übrigen Verbindungen bleiben
  auf syntaktisch öffentliche HTTP(S)-URLs beschränkt. Die Korrektur schließt
  den zuvor ungetesteten Persistenzpfad für eine konfigurierbare lokale
  Ollama-Base-URL und ist durch Store-, Pydantic- und Zod-Tests belegt.

- Datum: 2026-07-11
- Worktree: `/private/tmp/agora-onboarding-slice-2`
- Branch: `feat/onboarding-user-profile` (Basis: `main` @ `df6a2b3`, Slice 1
  gemergt via PR #683)
- Slice: 2 — Benutzerprofil und resumierbares Onboarding-Grundgerüst
- Arbeitsstand: implementiert, alle Gates grün, Commit/PR in Arbeit
- context-mode: funktionsfähig (Batch-Analysen in dieser Session)
- code-review-graph: CLI 2.3.6 via `uvx`; Haupt-Repo-Graph am 2026-07-11 auf
  `main`-Stand `df6a2b3` neu gebaut. `detect-changes` lief im Worktree gegen
  eine frisch migrierte (leere) DB und ist daher NICHT belastbar (Risk 0.00
  bei 22 Dateien). Belastbarer Nachweis ist die volle grüne Testsuite;
  Graph-Refresh nach Merge auf `main` bleibt Follow-up.

## Implementiert

- **Layer 0**: `backend/app/contracts/user_profile_contract.py` —
  `UserProfile`, `UserProfileUpdateRequest`, `OnboardingState`
  (Status `not_started|in_progress|dismissed|completed`),
  `OnboardingStepUpdateRequest`, `OnboardingRequirements`,
  `OnboardingStatusResponse`; Konstanten `ONBOARDING_STEP_ORDER`,
  `REQUIRED_ONBOARDING_STEPS`, `ALLOWED_AVATAR_MIME_TYPES`,
  `MAX_AVATAR_BYTES`. Avatar-Referenzen per Pattern gegen Path-Traversal;
  IANA-Zeitzonen-Validierung; `extra="forbid"`. 5 neue JSON-Schemas +
  strikter Zod-Spiegel `frontend/src/contracts/userProfileContract.ts`.
- **Persistenz**: `user_profile_store.py` und `onboarding_state_store.py`
  (Muster `workspace_routing_store`: AGORA_DATA_DIR, flock, atomarer Write,
  0600, defensives Lesen; Singletons mit Test-Reset). Benutzerprofil und
  KI-Presets bleiben getrennte Schlüsselräume (ADR-0008, Migrationsplan).
- **API**: `user_profile_bp` (`GET/PUT /api/profile`,
  `POST/GET/DELETE /api/profile/avatar`) und `onboarding_bp`
  (`GET /api/onboarding`, `PUT /step`, `POST /complete|dismiss|reopen`)
  hinter dem Standard-Blueprint-Guard. Avatar-Upload prüft MIME-Allowlist
  UND Magic-Bytes (PNG/JPEG/WebP; SVG strukturell abgelehnt), 2-MB-Limit,
  serverseitig generierte Dateinamen. 409 `onboarding_incomplete` trägt
  `missing` top-level im Envelope (per API-Test fixiert).
- **Completion-Semantik (ADR-0008)**: serverseitig `profile_valid` +
  `chat_model_configured` + `embedding_configured`; bewusst
  Konfigurations- statt Erreichbarkeitscheck — Live-Discovery kommt in
  Slice 3. `dismissed` sperrt niemanden aus (Bestandsinstallationen können
  den Wizard wegklicken und über Settings wieder öffnen).
- **Frontend**: Pinia-Store `userProfile` (ensureLoaded mit In-Flight-Dedupe,
  Fail-open bei API-Fehlern), Router-Guard `onboardingGuard`
  (Redirect nur bei `onboarding_required`; jeder Fehlerpfad lässt durch),
  Wizard `/onboarding` (Betriebsmodus, Profilformular, ehrliche
  Status-Schritte mit Settings-Verweis, Zusammenfassung, Später-einrichten),
  `/settings/profile` mit gemeinsamem `ProfileForm`, Avatar als
  authentifizierter Blob-Fetch + Object-URL (funktioniert im
  AGORA_AUTH_TOKEN-Modus ohne Ticket-Nacharbeit), Sidebar „Users & Teams"
  → „Profil", `/settings/users-teams` → Redirect. i18n-Namespaces
  `onboarding`/`profileSettings` in de.json und en.json (Key-Parität geprüft).

## Frisch verifiziert (2026-07-11, unabhängig vom Root)

- Contracts importierbar; Schema-Dump idempotent (5 neue Schemas)
- Backend-Contract-Suite: 284 bestanden
- Voller Backend-Lauf: 3012 bestanden, 9 übersprungen, 7 deselektiert,
  Exit 0 (Baseline Slice 1: 2920/9/7 → +92)
- Ruff: grün; mypy: 211 Dateien, 0 Fehler
- Frontend: 152 Testdateien / 1202 Tests grün (Baseline: 146/1150);
  `bun run check` (Lint + Tests + Build) Exit 0; vue-tsc 0 Fehler
- Vitest-Teardown-Blocker aus Phase 0 ist durch PR #678 behoben
  (vor Slice-Beginn unabhängig mit Exit 0 verifiziert)
- Gate 7/8 (verify-after-subagent): einziger `EXPORT_SCHEMA_VERSION`-Treffer
  ist ein Bestands-Docstring identisch auf `main`; `report_agent.py` ist
  inzwischen ein Paket — Muster nicht mehr vorhanden

## Entscheidungen

- `chat_model_available` → `chat_model_configured` umbenannt: ohne
  Live-Discovery wäre „available" gelogen.
- Onboarding-Schritte providers/chat_model/embeddings sind in Slice 2
  ehrliche Status-Schritte (realer requirements-Zustand + Settings-Link),
  keine Attrappen; geführte Einrichtung folgt in Slice 3/4.
- Avatar-Anzeige über authentifizierten Blob-Fetch statt signierter
  Tickets — kein neues `?token=`, keine Backend-Ticket-Nacharbeit nötig.
- Kein Contract-Feld `avatar_ref` im Update-Request: Avatar wird
  ausschließlich über die Avatar-Endpunkte verändert.

## Noch offen

- Codegraph-Delta gegen den Haupt-Repo-Graph nach Merge (s. o.).
- Statusschritte verlinken einheitlich auf `SettingsLlmProviders`;
  Differenzierung chat_model/embeddings sobald Slice 3/4 eigene Routen bringt.
- Kein dedizierter Spec für `SettingsProfileView.vue` (Verhalten über
  ProfileForm- und Store-Specs abgedeckt).
- Playwright-E2E für Onboarding-Resume (Testplan) folgt, sobald die
  E2E-Suite die neuen Routen aufnimmt (kein E2E-Bestand für Settings-Views).

## Geänderte Verträge und Migrationen

- Nur additive Verträge; keine bestehenden Verträge geändert.
- Neue Stores legen ihre Dateien lazy an; keine Migration bestehender Daten.
- Rollback: Blueprints deregistrieren + neue Module entfernen; die
  JSON-Dateien unter `AGORA_DATA_DIR` sind unabhängig und können bleiben.

## Nächste exakt ausführbare Schritte

1. PR-Review (inkl. Gemini-Findings) sichten; erst danach mergen.
2. Nach Merge: `uvx code-review-graph build` auf `main` + Delta prüfen.
3. Slice 3 (Provider-Verbindungen und Discovery) gemäß
   `04-implementation-plan.md` beginnen; dabei die Onboarding-Schritte
   providers/chat_model an die echte Discovery anbinden.

## Relevante Dateien

- `backend/app/contracts/user_profile_contract.py`
- `backend/app/services/user_profile_store.py`
- `backend/app/services/onboarding_state_store.py`
- `backend/app/api/user_profile.py`, `backend/app/api/onboarding.py`
- `backend/tests/contracts/test_user_profile_contract.py`
- `backend/tests/services/test_user_profile_store.py`,
  `backend/tests/services/test_onboarding_state_store.py`
- `backend/tests/api/test_user_profile_api.py`,
  `backend/tests/api/test_onboarding_api.py`
- `frontend/src/contracts/userProfileContract.ts`
- `frontend/src/api/profile.ts`, `frontend/src/store/userProfile.ts`
- `frontend/src/router/onboardingGuard.ts`
- `frontend/src/views/onboarding/OnboardingView.vue`
- `frontend/src/views/Settings/SettingsProfileView.vue`
- `frontend/src/components/v4/forms/ProfileForm.vue`
- `schemas/user-profile*.json`, `schemas/onboarding-*.json`

## Befehle zur Verifikation

```bash
cd backend && uv run pytest tests/contracts/ -q
cd backend && uv run pytest tests/services/test_user_profile_store.py \
  tests/services/test_onboarding_state_store.py \
  tests/api/test_user_profile_api.py tests/api/test_onboarding_api.py -q
cd backend && uv run python -m app.contracts.dump_schemas --check
cd backend && uv run ruff check . && uv run mypy app
cd frontend && bun run check
```

## Doc-Impact

- `README.md`: geprüft, nicht betroffen — Setup/Betrieb unverändert; das
  Onboarding erklärt sich in der UI selbst (Anwenderdoku folgt mit dem
  Epic-Abschluss, wenn der Wizard vollständig ist).
- `AGENTS.md`: geprüft, nicht betroffen — Contract-/TDD-/Security-Regeln
  decken den Slice ab; keine neuen Befehle oder Tools.
- `CLAUDE.md`: geprüft, nicht betroffen.
- `PLAN.md`: aktualisiert — Slice-Status, Baseline-Absatz, Fußzeile.
- `docs/STATUS.md`: aktualisiert — via `scripts/sync-status.sh` regeneriert.
- `CHANGELOG.md`: aktualisiert — Added-Block profile/onboarding unter
  `[Unreleased]`.
- Epic-`HANDOVER.md`: aktualisiert — dieses Dokument.
- `docs/tooling/agent-tools.md`: geprüft, nicht betroffen — keine
  Tool-Version oder -Konfiguration geändert.
