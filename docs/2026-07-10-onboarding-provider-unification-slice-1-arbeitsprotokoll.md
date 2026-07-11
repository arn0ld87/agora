# Arbeitsprotokoll — Onboarding/Provider-Unification Slice 1

Datum: 2026-07-10  
Branch: `codex/onboarding-provider-contracts`  
Scope: kanonische Provider-/Modell-/Route-Verträge

## Ablauf

1. Epic-Dokumente, ADR-0006, bestehende Contracts/Tests und Codegraph geprüft.
   Der Impact für zentrale Contract-Exports ist hoch (115 Dateien innerhalb
   von zwei Hops); deshalb blieb die Änderung auf neue Verträge, Exporte,
   Schemas und Adapter begrenzt.
2. RED geschrieben:
   `backend/tests/contracts/test_ai_provider_contract.py` scheiterte bei der
   Collection erwartungsgemäß mit
   `ModuleNotFoundError: app.contracts.ai_provider_contract` (Exit 2).
   Der Frontend-Spiegeltest scheiterte parallel am fehlenden Modul.
3. GREEN implementiert: `ProviderConnection`, `AiModel`, `AiRoute`,
   Tri-State-Capabilities, Legacy-Adapter, Zod-Spiegel und Schema-Dump.
4. TypeScript-RED im ersten Typecheck: Zod akzeptierte `{}` nicht als
   `.default()` für den bereits transformierten Capability-Output. Minimaler
   Fix: expliziter vollständig unbekannter Default; danach Typecheck grün.
5. Schemas erzeugt, zweiten Dump auf identischen Diff-Hash geprüft und
   Contract-/Frontend-Gates ausgeführt.
6. Security-Re-Review am 2026-07-11: Provider-Optionen auf fachliche Allowlist
   begrenzt, Legacy-Secret-Status/Fallback-/Roundtrip-Pfade gehärtet und
   öffentliche `base_url` als gemeinsame Pydantic-/JSON-Schema-/Zod-Regel
   eingeführt. Legacy-Descriptor-URLs werden secret-frei saniert und als
   `degraded` markiert; Stage-Routen lehnen unsichere URLs ab.

## Ergebnis und Tests

- neue Backend-Contract-Tests: 39 bestanden
- Backend-Contract-Suite: 250 bestanden, Exit 0
- neue Frontend-Contract-Tests: 17 bestanden, Exit 0
- Backend Ruff (neue Dateien): Exit 0
- Backend mypy (neuer Vertrag): Exit 0
- Frontend Typecheck: Exit 0
- Frontend standalone: 146/146 Testdateien, 1150/1150 Tests; Lint, Typecheck
  und Build grün
- `npm run check` vor dem `base_url`-Fix: fachliche Coverage-Tests grün, Exit 1
  durch bekannte `EnvironmentTeardownError` aus `CompareView.spec.ts`
- Testinventar: 2934 Backend-Tests total, 2927 selektiert, 7 deselektiert
- letzter Full-Backend-Lauf vor dem `base_url`-Fix: 2900 bestanden,
  9 übersprungen, 7 deselektiert
- unabhängiger Full-Backend-Lauf nach dem `base_url`-Fix (Root, 2026-07-11):
  2920 bestanden, 9 übersprungen, 7 deselektiert, Exit 0
- Schema-Dump: 34 Dateien, zweiter Dump idempotent
- mypy: 206 Dateien, 0 Fehler; Ruff: vollständig grün
- Codegraph: 945 Dateien, 8965 Knoten, 75474 Kanten, 624 Flows; hoher Impact,
  138 zusätzliche Dateien, 1 Schema-Dump-Flow, 0 Testlücken

## Doc-Impact

- `README.md`: geprüft, nicht betroffen
- `AGENTS.md`: geprüft, nicht betroffen
- `CLAUDE.md`: geprüft, nicht betroffen
- `PLAN.md`: aktualisiert
- `docs/STATUS.md`: aktualisiert (Testzahlen)
- `CHANGELOG.md`: aktualisiert (`[Unreleased]`)
- Epic-`HANDOVER.md`: aktualisiert
- `docs/tooling/agent-tools.md`: geprüft, nicht betroffen

## Bewusst offen

- Persistente Provider-Connections und Discovery sind Slice 3.
- Benutzerprofil/Onboarding, Embeddings und Persona-Zahl sind nicht Teil
  dieses Slices.
- Legacy-Secrets bleiben außerhalb kanonischer Verträge und müssen beim
  Rückadapter separat aus dem Secret-Store bereitgestellt werden.
- Codegraph-Refresh nach dem `base_url`-Fix: in der Abschluss-Session nicht
  ausführbar (CRG-MCP nicht verbunden, CRG-CLI nicht gefunden); als Follow-up
  vor dem nächsten Slice nachholen.

## Root-Verifikation und Re-Review (2026-07-11)

Unabhängig vom Implementer wiederholt und bestätigt: Security-Probes
(Credential-Keys in `provider_options` top-level und verschachtelt blockiert;
Userinfo-`base_url` abgelehnt; keine Secret-Muster im Diff), Backend-Zieltest
39, Contract-Suite 250, Full-Backend 2920/9/7, Frontend-Zieltest 17, Frontend
Full 146 Testdateien / 1150 Tests, Lint, Typecheck, Build.

Finaler adversarialer Re-Review des `base_url`-Fixes: **MERGE-READY**. Kein
Bypass gefunden (u. a. percent-encodete Userinfo, Mehrfach-`@`, leerer Host,
Steuerzeichen, IDN, Query-/Fragment-Secrets); Sanitizer-Output und
`status_message` sind secret-frei, Zod und JSON-Schema gleich streng. Drei
non-blocking Follow-ups:

- F1 (LOW–MEDIUM): Out-of-Range-Ports (`:0`, `:65536`) akzeptiert Pydantic/
  JSON-Schema, Zod lehnt ab — Spiegel-Parity-Drift.
- F2 (MEDIUM): `provider_connection_from_descriptor` wirft bei
  Scheme-Großschreibung (`HTTPS://…`) oder Underscore-Host eine unhandled
  `ValidationError` statt zu degradieren — Adapter ist nicht total.
- F3 (LOW–MEDIUM): Backslash-Host-Parser-Differential (`urlsplit` vs. WHATWG)
  kann im Legacy-Sanitizer den Host still umschreiben (SSRF-adjazent,
  degraded-Pfad, kein Secret-Leak).
