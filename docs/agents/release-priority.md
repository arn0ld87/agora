# Aktuelle Release-Priorität

> **Progressive Disclosure** — ausgelagert aus [`AGENTS.md`](../../AGENTS.md). Freigabekriterien in [`../../ROADMAP.md`](../../ROADMAP.md); verifizierter Ist-Zustand in [`../STATUS.md`](../STATUS.md).

### 0.8.0 → 0.9.0

Erledigt: E2E-Smokes repariert (#739), Provider-/Secret-/Routing-SSoT abgeschlossen (#761), Dependency-SSoT bereinigt (#762), Produkt-/Manifest-Version automatisiert synchronisiert (#759).

Offen:

- E2E als Required Check aktivieren (Läufe sind stabil grün, `main` besitzt aber noch keine Branch-Protection)
- Vue-v4 als einziges Produktfrontend festlegen (Issue #760; Umsetzungskarte [#829](https://github.com/arn0ld87/agora/issues/829))

### 0.9.0 → 0.10.0

- reproduzierbare Run-Manifeste und Replay
- Kosten-, Token- und Zeitbudgets
- Backup, Restore, Upgrade und Rollback
- Kalibrierungs- und Baseline-Vergleich
- Feature-Freeze vor `1.0.0`

Details und Freigabekriterien: [`../../ROADMAP.md`](../../ROADMAP.md)