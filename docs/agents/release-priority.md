# Aktuelle Release-Priorität

> Kompakte Orientierung für Agenten. Die verbindliche Reihenfolge und Freigabekriterien stehen in [`../../ROADMAP.md`](../../ROADMAP.md); der verifizierte Istzustand in [`../STATUS.md`](../STATUS.md).

## 0.9.6 → 0.10.0

`0.9.6` ist ein Zwischenrelease zwischen `0.9.5` und `0.10.0` — kein `0.10.0` und erfüllt dessen Release-Gates nicht. Einordnung: Abschnitt „0.9.6 — Zwischenrelease" in [`../../ROADMAP.md`](../../ROADMAP.md).

Priorität vor neuen Features:

1. **Restart-sichere Langläufer** — Prepare, Report und Graph-Build dürfen bei Webprozess-Restarts nicht zustandslos verschwinden (#1472). **Teil erledigt:** Slice 1.1 terminalisiert per SIGTERM abgeschnittene In-Process-Jobs noch im selben Lauf als `failed/process_restart` (#1525/#1528/#1530), statt allein auf die Startup-Reconciliation zu warten. **Offen:** eine persistente Job-Queue mit eigenen Workern und ein wiederaufnehmbarer Zwischenstand — `_BACKEND` bleibt `"thread"`.
2. **Embedding Runtime SSoT** — aktive Store-/Connection-Konfiguration muss produktive Consumer steuern; Env nur Legacy/Bootstrap (#1417). **Teil erledigt:** Slice 2.1 löst Lese- und Schreibpfad kanonisch über den Store auf (#1533), Slice 2.2 macht den Cutover korruptionssicher — die neue Indexversion wird erst nach erfolgreicher Re-Embedding- und Indexprüfung `active`, ein fehlgeschlagener Lauf schaltet nie um (#1533). **Offen:** `VECTOR_DIM`-SSoT (Slice 2.3), Legacy-View für Bestandsgraphen (Slice 2.4), Frontend-Zod-Spiegel für den neuen `building`-Status.
3. **Entitäts-/Persona-Kohärenz** — Alias/Koreferenz (#1470) weiterhin offen; Domänendrift (#1471) abgeschlossen.
4. **Simulationstreue** — Role Leakage und Twitter-Recommender (#1323/#1236). Weiterhin offen.
5. **Evidence-/Eval-Trust** — Quantoren und Seed-Lösungstexte (#1345/#1240), Claim-/Confidence-Kalibrierung (#1301/#1400). Weiterhin offen; #1492 hat nur die Prüfseite der Fließtext-Faktenprüfung gehärtet, nicht die Quantoren-/Eval-Leakage-Punkte selbst.
6. **Reproduzierbarkeit** — vollständiges Run-Manifest, echte Seed-Wiring-Semantik und Replay (#763/#1274). **Teil erledigt:** `RunManifest` existiert strukturell und atomar geschrieben, ein Replay-Pfad mit `AiModelRef`-Overrides und strukturierten Fehler-Envelopes ist gemergt (#1273). **Nicht erledigt:** die Garantie selbst. Prompt-Snapshots, Seed-Dokument-Hash, echte RNG-Wiring-Semantik und vollständige Replay-Parameter fehlen weiterhin — „gleicher Seed = reproduzierbarer Run" bleibt eine zu starke Aussage.
7. **Operations-Nachweis** — Fresh Install, Backup/Restore, Upgrade/Rollback, Release-Artefakte (#766). **Teil erledigt:** Der Restore-Drill ist ausführbar und maschinell prüfbar (`restore-drill.sh`, `restore_verify.py`, Zielschutz gegen Overwrite im eigenen Checkout, `migration_baseline.py` für Vorher/Nachher-Vergleiche, #1514). **Offen:** der tatsächlich durchgeführte Fresh-Host-Restore-/Upgrade-/Rollback-Smoke mit echtem Backup — das Werkzeug ist kein Nachweis.
8. **Produktnachweis** — Agora gegen Single-Prompt-/statische Persona-Baselines und reale Referenzen messen (#765). Weiterhin offen.

## Bereits erledigt / nicht erneut als offene Kernarbeit planen

- Preflight sowie Zeit-/Token-/Kosten-/LLM-Call-Budgets sind grundsätzlich vorhanden.
- parallele Persona-Generierung reserviert harte LLM-Calls (#1461).
- Tool-, Vision- und Interview-Pfade sind in Budget/Ledger integriert (#1478), **ParallelIPCHandler BudgetExceededError-Handling geschlossen (Slice 3.1, #1527)**. Offen bleibt die `SubprocessBudgetGuard`-Anbindung im Default-Parallelrunner (`scripts/run_parallel_simulation.py`) selbst — eigenes Issue.
- Simulations-Startup-Reconciliation ist vorhanden (#1476).
- Partial Reports enden ehrlich als `INCOMPLETE` (#1479).

## Nicht vor 1.0 priorisieren

- Multi-User mit Workspaces, Supabase Auth, RLS und Realtime (ADR-0019, Epic #1610; gemergter Code bleibt inaktiv)
- SaaS/gehosteter Betrieb
- Kubernetes/Helm
- Federation
- allgemeines Plugin-System
- weiterer großer Frontend-Rewrite
- neue Provider nur um die Providerliste länger aussehen zu lassen

Details und Abnahme: [`../../ROADMAP.md`](../../ROADMAP.md).
