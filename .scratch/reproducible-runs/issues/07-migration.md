# Ticket 7: Migration für bestehende Runs

**Blocked by:** 1
**Size:** s
**Layer:** 2 (Service)

## Aufgabe

Für bestehende Runs ein Legacy-Manifest generieren.

## Scope

- `ManifestCapture.migrate_legacy(run_id)` — rekonstruiert was automatisch geht:
  - Run-Metadaten (run_id, started_at, completed_at, status)
  - Modell aus `metadata.llm_model`
  - Provider aus `metadata.llm_provider` (redacted)
  - Graph-ID aus `metadata.graph_id`
  - Versionen aus `AGORA_VERSION` (soweit bekannt)
- Nicht rekonstruierbare Felder auf `null`
- Setzt `status: "legacy"`
- Einmalig ausführbar (überschreibt kein vorhandenes Manifest)
- Optional: CLI-Kommando `python -m app.scripts.migrate_manifests`

## Akzeptanz

- [ ] Legacy-Manifest hat `status: "legacy"`
- [ ] Bekannte Felder sind gefüllt
- [ ] Nicht rekonstruierbare Felder sind `null`
- [ ] Überschreibt kein vorhandenes Manifest
