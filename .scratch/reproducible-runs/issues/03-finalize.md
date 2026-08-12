# Ticket 3: Manifest Finalization at Run End

**Blocked by:** 2
**Size:** s
**Layer:** 2 (Service)

## Aufgabe

Draft-Manifest bei Run-Ende mit Laufzeitdaten finalisieren.

## Scope

- `ManifestCapture.finalize(run_id)` — ergänzt:
  - `runtime.started_at`, `runtime.completed_at`
  - `runtime.duration_seconds`
  - `runtime.rounds_completed` (aus Simulation-Snapshot)
  - `runtime.usage_summary` (aus `usage_summary.json`)
  - `runtime.termination_reason`
- Setzt `status: "final"`
- Integration in `RunLifecycle` — bei Terminal-Transition (completed/failed/stopped)
- Bei Abbruch/Absturz: Draft bleibt erhalten (kein finalize)

## Akzeptanz

- [ ] Abgeschlossener Run hat `status: "final"` im Manifest
- [ ] Laufzeitdaten sind korrekt
- [ ] Abgestürzter Run behält Draft
- [ ] Test: Manifest nach Run-Ende hat alle runtime-Felder
