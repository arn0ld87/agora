# Aktuelle Release-Priorität

> Kompakte Orientierung für Agenten. Die verbindliche Reihenfolge und Freigabekriterien stehen in [`../../ROADMAP.md`](../../ROADMAP.md); der verifizierte Istzustand in [`../STATUS.md`](../STATUS.md).

## 0.9.5 → 0.10.0

Priorität vor neuen Features:

1. **Restart-sichere Langläufer** — Prepare, Report und Graph-Build dürfen bei Webprozess-Restarts nicht zustandslos verschwinden (#1472).
2. **Embedding Runtime SSoT** — aktive Store-/Connection-Konfiguration muss produktive Consumer steuern; Env nur Legacy/Bootstrap (#1417).
3. **Vollständige Budget-Attribution** — verbleibende `ParallelIPCHandler`-Lücke aus #1478 schließen.
4. **Entitäts-/Persona-Kohärenz** — Alias/Koreferenz und Domänendrift (#1470/#1471).
5. **Simulationstreue** — Role Leakage und Twitter-Recommender (#1323/#1236).
6. **Evidence-/Eval-Trust** — Quantoren und Seed-Lösungstexte (#1345/#1240), Claim-/Confidence-Kalibrierung (#1301/#1400).
7. **Reproduzierbarkeit** — vollständiges Run-Manifest, echte Seed-Wiring-Semantik und Replay (#763/#1274).
8. **Operations-Nachweis** — Fresh Install, Backup/Restore, Upgrade/Rollback, Release-Artefakte (#766).
9. **Produktnachweis** — Agora gegen Single-Prompt-/statische Persona-Baselines und reale Referenzen messen (#765).

## Bereits erledigt / nicht erneut als offene Kernarbeit planen

- Preflight sowie Zeit-/Token-/Kosten-/LLM-Call-Budgets sind grundsätzlich vorhanden.
- parallele Persona-Generierung reserviert harte LLM-Calls (#1461).
- Tool-, Vision- und Interview-Pfade sind in Budget/Ledger integriert (#1478), abgesehen vom oben genannten Parallelrunner-Follow-up.
- Simulations-Startup-Reconciliation ist vorhanden (#1476).
- Partial Reports enden ehrlich als `INCOMPLETE` (#1479).

## Nicht vor 1.0 priorisieren

- Multi-User/SaaS
- Kubernetes/Helm
- Federation
- allgemeines Plugin-System
- weiterer großer Frontend-Rewrite
- neue Provider nur um die Providerliste länger aussehen zu lassen

Details und Abnahme: [`../../ROADMAP.md`](../../ROADMAP.md).
