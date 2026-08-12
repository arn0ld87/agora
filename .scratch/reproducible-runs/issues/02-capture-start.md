# Ticket 2: Manifest Capture at Run Start

**Blocked by:** 1
**Blocks:** 3
**Size:** m
**Layer:** 2 (Service)

## Aufgabe

Bei jedem Run-Start ein Draft-Manifest schreiben.

## Scope

- `ManifestCapture` Service-Klasse in `backend/app/services/manifest_capture.py`
- `capture_draft(run_id, ...)` — sammelt alle zum Startzeitpunkt verfügbaren Daten:
  - Seed-Dokument-Hash (SHA-256 des rohen Upload-Textes)
  - simulation_config.json Hash
  - Agora-Version, Schema-Version
  - Graph-ID, Graph-Version, Embedding-Version
  - Stage-Routing (aus `RuntimeRunConfig` Snapshots)
  - Prompt-Snapshots (alle Prompt-Module auslesen und einfrieren)
  - Random-Seed (aus simulation_config.json oder Ableitungslogik)
- Schreibt `manifest.json` ins Run-Dir mit `status: "draft"`
- Integration in `RunLifecycle.begin()` oder als expliziter Aufruf nach `begin()`

## Akzeptanz

- [ ] Jeder neue Run hat ein `manifest.json` im Run-Dir
- [ ] Manifest enthält keine Secrets
- [ ] Prompt-Texte sind byte-genau
- [ ] SHA-256-Hashes sind korrekt
- [ ] Test: `manifest.json` existiert nach Run-Start und hat `status: "draft"`
