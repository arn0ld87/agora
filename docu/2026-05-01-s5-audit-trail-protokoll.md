# S5 — Self-Evidence raus aus `evidence`, in `audit_trail` · Arbeitsprotokoll

**Datum:** 2026-05-01
**Slice:** S5

## Implementierung

`backend/app/services/report_agent.py`:

- Modul-Konstante `FORBIDDEN_EVIDENCE_TYPES = {"model_generated_inference", "section_synthesis"}`.
- `_build_claims_for_section`:
  - Filtert verbotene Typen aus den `direct_items` raus, bevor Binding läuft.
  - Erzeugt das `model_generated_inference`-Item separat als `audit_trail`-Liste.
  - Hängt `audit_trail` an den Claim-Dict, ohne den Inferenzeintrag im `evidence`-Array zu führen.

Damit ist die Beleg-Schicht jetzt strukturell trennen von der Inferenz-Schicht: Reader sehen unter `evidence` nur Items, die wirklich extern stammen (Graph-Facts, Metriken), und unter `audit_trail` die Modell-Synthese.

## Test-Update

`test_report_claim_model_keeps_legacy_fields_and_numeric_score` aktualisiert: das `model_generated_inference`-Item darf nicht mehr im `evidence`-Array auftauchen, muss im `audit_trail` sein.

510 Backend-Tests grün.
