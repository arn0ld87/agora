### Fixed (Prepare Checkpointing, Fallback-Enrichment und Identity-Bindings — 2026-10-29)

- **Checkpoint bei Abbruch erhalten (Befund 5.1):** In `_phase_generate_profiles` wird der Checkpoint nicht mehr vorzeitig gelöscht, wenn `is_cancel_requested` für `run_id` oder `simulation_id` aktiv ist. Dadurch bleibt ein Resume nach kooperativem Nutzerabbruch funktionsfähig.
- **Vollständige Anreicherung von Fallback-Profilen (Befund 5.2):** Im Exception- und Notfallpfad von `oasis_profile_batch.py` und `oasis_profile_batch_results.py` erhalten Fallback-Profile nun `segment` (aus Entity-Attributen/Quota), `generation_source="rule_based"`, `generation_error` sowie ein deterministisches `identity_binding`. Dies verhindert Schema- und Quota-Validierungsfehler in `_validate_persona_quota`.
- **Identity-Binding-Persistenz und Backfill-Hook (Befund 5.3):**
  - Synthetische Skeptiker erhalten ein valides Identity-Binding (`origin="source_collective"` bzw. `"synthetic_supplement"`) und `_persist_identity_bindings` wird nach ihrer Profilerzeugung aufgerufen.
  - `prepare_from_personas` persistiert `persona_identity_bindings.json` im Simulationsverzeichnis und `build_identity_binding_manifest` unterstützt neben Profil-Objekten auch Dict-Mappings.
  - `_backfill_rejected_slots` reicht den `on_profile_saved`-Callback durch und ruft ihn fehlertolerant bei jedem nachbesetzten Slot auf, sodass auch nachgerückte Reserve-Profile im Checkpoint landen.
