# Handover — Onboarding/Provider-Unification Slice 1

## Stand

- Datum: 2026-07-11
- Worktree: `/private/tmp/agora-onboarding-provider-contracts`
- Branch: `codex/onboarding-provider-contracts`
- Arbeitsstand: unabhängig verifiziert, committet und als PR eröffnet
  (Root, 2026-07-11)
- Slice 1 ist implementiert und unabhängig verifiziert. Der finale
  unabhängige Re-Review des `base_url`-Fixes ist abgeschlossen:
  **MERGE-READY** mit drei non-blocking Follow-ups (F1–F3, siehe
  Arbeitsprotokoll).
- Provider-Detection-SSoT
  `backend/app/llm/providers/registry.py::detect_provider` blieb unverändert.

## Implementierter Vertrag

- `ProviderConnection`, `AiModel` und `AiRoute` sind kanonische
  Pydantic-v2-Verträge mit `extra="forbid"` sowie generierten JSON-Schemas und
  strikten Zod-Spiegeln.
- Secrets bleiben außerhalb der kanonischen Verträge; ausschließlich
  `secret_ref` wird geführt.
- Modellfähigkeiten sind Tri-State (`supported|unsupported|unknown`).
  `unknown` gilt niemals als unterstützt.
- `provider_options` ist eine geschlossene fachliche Allowlist. Aktuell sind
  ausschließlich die tatsächlich verwendeten Routing-Optionen `base_url`,
  `num_ctx` und die interne Legacy-Roundtrip-Struktur erlaubt. Credential-Keys
  werden dadurch sowohl top-level als auch verschachtelt strukturell blockiert.
- Gemeinsame Fixtures prüfen Pydantic, generiertes JSON-Schema und Zod auf
  gültige und ungültige Grenzfälle.

## Security-Remediations und Legacy-Adapter

- Ein Legacy-`api_key` ohne aufgelöste Referenz erzeugt nicht mehr
  `auth_mode="none"`, sondern explizit `auth_mode="api_key"`, Status
  `degraded` und eine secret-freie Fehlstatusmeldung.
- Der Rückadapter zu `ProviderDescriptor` verlangt das Fallback-Modell-Sidecar
  zwingend; stiller Verlust durch ein implizites leeres Array ist unmöglich.
- `StageLLMRoute`-Roundtrips erhalten einen kollidierenden reservierten Key mit
  Wert `None` sowie `reasoning_effort=None` verlustfrei.
- Kanonische `base_url` ist eine öffentliche HTTP(S)-Basis-URL: Scheme
  `http`/`https` und Host sind Pflicht; Port und Pfad sind erlaubt. Userinfo,
  Query und Fragment sind vollständig verboten.
- Der `ProviderDescriptor`-Legacy-Adapter entfernt Userinfo, Query und Fragment
  aus einer unsicheren Legacy-URL, übernimmt keinen privaten Anteil und
  markiert die Verbindung mit einer secret-freien Reconfigure-Meldung als
  `degraded`.
- Der `StageLLMRoute`-Adapter lehnt eine unsichere `base_url` explizit ab.

## Frisch verifiziert nach dem letzten `base_url`-Fix

Vom Implementer:

- Backend-Zieltest: 39 bestanden
- Frontend-Zieltest: 17 bestanden
- Backend-Contract-Suite: 250 bestanden
- mypy: 206 Dateien, 0 Fehler
- Ruff: grün
- Schema-Dump: idempotent
- Frontend standalone: 146/146 Testdateien, 1150/1150 Tests
- Frontend Lint, Typecheck und Build standalone: grün
- Pytest-Inventar: 2934 total, 2927 selektiert, 7 deselektiert

Vom Root unabhängig erneut bestätigt:

- Imports
- Schema-Idempotenz
- Backend-Zieltest: 39 bestanden
- Backend-Contract-Suite: 250 bestanden
- Ruff
- mypy: 206 Dateien, 0 Fehler

Vom Root am 2026-07-11 zusätzlich unabhängig bestätigt:

- vollständiger Backend-Testlauf: 2920 bestanden, 9 übersprungen,
  7 deselektiert, Exit 0
- Frontend-Zieltest (17), Frontend Full (146 Testdateien / 1150 Tests),
  Lint, Typecheck und Build — alle grün
- Security-Probes: Credential-Keys in `provider_options` blockiert,
  Userinfo-`base_url` abgelehnt, keine Secret-Muster im Diff

## Bekannte Baselines und offene Punkte

- Der letzte vollständige Backend-Lauf vor dem `base_url`-Fix hatte
  2900 bestandene, 9 übersprungene und 7 deselektierte Tests; der
  unabhängige Lauf nach dem Fix 2920/9/7 (Exit 0).
- `npm run check` hatte vor dem `base_url`-Fix fachlich bestandene
  Coverage-Tests, endete aber wegen eines vorbestehenden Vitest-
  `EnvironmentTeardownError` aus `CompareView.spec.ts` mit Exit 1. Standalone
  Full Tests, Lint, Typecheck und Build sind grün. Den Teardown nicht in diesem
  Slice beheben.
- Der vorherige Reviewer fand den `base_url`-Secret-Pfad. Der Fix ist
  implementiert; der finale unabhängige Re-Review (2026-07-11) ergab
  **MERGE-READY** mit drei non-blocking Follow-ups F1–F3 (Port-Parity-Drift
  Zod/Pydantic, nicht-totaler Legacy-Adapter, Backslash-Host-Differential) —
  Details im Arbeitsprotokoll.
- Codegraph vor dem `base_url`-Fix, letzter Full-Stand: 945 Dateien,
  8965 Knoten, 75474 Kanten und 624 Flows. Der damalige Impact war hoch:
  138 zusätzliche Dateien, 1 Schema-Dump-Flow und 0 Testlücken. Der Refresh
  nach dem `base_url`-Fix war in der Abschluss-Session nicht ausführbar
  (CRG nicht verbunden) und bleibt Follow-up.
- In einer früheren Prozessdiagnose wurde ein Credential eines fremden
  Prozesses in einer Tool-Ausgabe sichtbar. Vorsorgliche Rotation ist separat
  erforderlich; der Wert darf nicht erneut ausgegeben, dokumentiert oder
  anderweitig reproduziert werden.

## Nächste exakt ausführbare Schritte

1. `git diff` und `git status` prüfen; Security-Probes für Credential-Keys und
   öffentliche `base_url` unabhängig wiederholen.
2. Vollständigen Backend-Testlauf ausführen und exakte Passed/Skipped/
   Deselected-Zahlen festhalten.
3. Frontend-Zieltest, Full Tests, Lint, Typecheck und Build unabhängig
   wiederholen. Den bekannten Composite-Check-Teardown separat dokumentieren,
   nicht in diesem Slice reparieren.
4. Codegraph full oder inkrementell aktualisieren und Delta, Impact, Flow sowie
   Testlücken prüfen.
5. Reviewer-Re-Review des `base_url`-Fixes durchführen.
6. Doku-Zahlen gegen die frischen unabhängigen Läufe prüfen und gegebenenfalls
   korrigieren.
7. Nur die konkreten Slice-Dateien stagen, atomaren Commit erstellen, Branch
   pushen und PR eröffnen. Nicht direkt auf `main` mergen.

## Relevante Dateien

- `backend/app/contracts/ai_provider_contract.py`
- `backend/app/contracts/__init__.py`
- `backend/app/contracts/dump_schemas.py`
- `backend/tests/contracts/test_ai_provider_contract.py`
- `frontend/src/contracts/aiProviderContract.ts`
- `frontend/src/contracts/__tests__/aiProviderContract.spec.ts`
- `schemas/ai-provider-connection.schema.json`
- `schemas/ai-model.schema.json`
- `schemas/ai-route.schema.json`
- `schemas/fixtures/ai-provider-contract-fixtures.json`
- `CHANGELOG.md`
- `PLAN.md`
- `docs/STATUS.md`
- `docs/2026-07-10-onboarding-provider-unification-slice-1-arbeitsprotokoll.md`

## Doc-Impact

- `README.md`: geprüft, nicht betroffen — noch kein neues Anwender- oder
  UI-Verhalten.
- `AGENTS.md`: geprüft, nicht betroffen — Contract-, Schema-, TDD- und
  Security-Regeln decken den Slice bereits ab.
- `CLAUDE.md`: geprüft, nicht betroffen — Detection-SSoT und Schema-Befehle
  bleiben unverändert.
- `PLAN.md`: aktualisiert — Slice implementiert, Root-Re-Review offen.
- `docs/STATUS.md`: aktualisiert — aktuelles Pytest-Inventar und Frontend-
  Testdateien.
- `CHANGELOG.md`: aktualisiert — kanonische Verträge, öffentliche `base_url`
  und Legacy-Sanitizing unter `[Unreleased]`.
- Epic-`HANDOVER.md`: aktualisiert — dieser operative Übergabestand.
- `docs/tooling/agent-tools.md`: geprüft, nicht betroffen — keine Tool-Version,
  Installation oder Konfiguration geändert.
