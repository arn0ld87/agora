# Handover — Onboarding/Provider-Unification Slice 5.3

## Stand

- Datum: 2026-07-13
- Worktree: `/private/tmp/agora-onboarding-slice-5-3`
- Branch: `codex/onboarding-model-picker-slice-5-3`
- Basis: `origin/main` @ `331193d7` (Slice 5.2, PR #699, gemergt)
- Slice: 5.3 — Backend-Routing-Hierarchie (`AiRoute`)

## Fertig (Sub-Slice 5.3)

- Die bestehende Contract-SSoT `AiRoute` in
  `backend/app/contracts/ai_provider_contract.py` wurde additiv um die
  Quellen `run_override`, `project`, `workspace`, `provider_fallback` sowie
  `resolved_at` und `fallback_reason` erweitert. Es gibt bewusst keinen
  zweiten `ai_route_contract.py`.
- `ai_route_resolver.py` löst deterministisch
  `Stage-Override > Run-Override > Project > Workspace > Provider-Fallback`
  auf und lehnt fehlende bzw. capability-inkompatible Kandidaten typisiert ab.
- Stage-Snapshots werden crash- und race-sicher per atomarem First-writer-wins
  publiziert. Der bestehende `ResolvedRoute`-Snapshot bleibt als v3-Read-
  Adapter erhalten; zusätzlich wird pro Stage ein kanonischer, secret-freier
  `AiRoute`-Snapshot geschrieben.
- `ai_route_audit.py` persistiert pro Stage genau ein secret-freies
  `routing_resolved`-Event mit UTC-Zeit, Quelle und Fallback-Begründung.
- Die bestehenden `llm-routing`-Endpunkte liefern `ai_route` additiv. Alte
  Felder und Request-Shapes bleiben unverändert; die Frontend-Response-Typen
  markieren sie mit `@deprecated`. Der öffentliche Serializer entfernt den
  internen Legacy-Marker sowie nicht kanonische bzw. geheime Optionen.
- Backend-, Zod- und JSON-Schema-Spiegel sind synchron; lokale Ollama-
  Loopback-URLs bleiben im kanonischen Route-Vertrag zulässig.

## Verifikation

- Fokussierter Backend-Lauf: 96 passed.
- `ruff` und fokussiertes `mypy`: grün.
- Contract-/Frontend-Gates und voller Pre-Push-Gate: siehe PR-Checks.
- `graphify update .`: Graph auf 19.488 Nodes / 31.044 Edges aktualisiert.

## Bewusst offen

- 5.4 migriert die produktiven Auswahlstellen auf den neuen Resolver. Die
  bestehende, bereits verflachte `RuntimeLlmRouting` bleibt bis dahin ein
  Legacy-Read-Adapter und erfindet keine Project-/Workspace-Provenienz.
- 5.5 deprecatet alte Picker/Stores vollständig.
- 5.6 ergänzt Playwright-E2E einschließlich Run-Snapshot.
- Danach folgen Slice 6 (Persona-Count) und Slice 7 (Golden-Gate-Designsystem).
