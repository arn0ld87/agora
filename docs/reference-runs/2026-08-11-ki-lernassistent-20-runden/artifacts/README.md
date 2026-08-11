# Artifacts — reference run 11 August 2026 (20 rounds)

*[Deutsch weiter unten](#artefakte--referenzlauf-vom-11-august-2026-20-runden)*

Belongs to reference run `report_4786a1a3d4ea` / `sim_eb9037a01fb4` — introduction of a self-hosted AI learning assistant at an AZAV-certified retraining provider, 20 simulation rounds.

## Machine-readable summary

[`run-summary.json`](./run-summary.json) follows the schema `agora-reference-run-summary-v1` and contains run identity, models, simulation metrics, claim/hypothesis/data-gap counts, evidence composition, gate decisions, persona-eligibility figures, confirmed positive behaviors, known failure classes, remediation priorities and related issues.

It is **not** a full evidence export and does not replace `evidence_map.json` or the raw logs.

## Not in this folder

The complete run artifacts live in the operational directory and are not part of the repository:

- `backend/uploads/simulations/sim_eb9037a01fb4/` — `simulation_config.json`, `run_state.json`, `reddit_profiles.json`, `twitter_simulation.db`, `reddit_simulation.db`, `simulation.log`
- `backend/uploads/reports/report_4786a1a3d4ea/` — `evidence_map.json`, `outline.json`, `section_01.md` … `section_06.md`, `agent_log.jsonl`, `console_log.txt`

The simulation databases contain personal data of simulated personas and are therefore not published.

## Note on reading the simulation databases

Reposts and quotes are separate rows in `post` with `original_post_id` set; plain reposts carry empty `content`. Without the filter `original_post_id IS NULL`, any analysis looks like mode collapse plus empty posts, although the semantics are correct.

---

# Artefakte — Referenzlauf vom 11. August 2026 (20 Runden)

Gehört zum Referenzlauf `report_4786a1a3d4ea` / `sim_eb9037a01fb4` — Einführung eines selbstgehosteten KI-Lernassistenten bei einem AZAV-zertifizierten Umschulungsträger, 20 Simulationsrunden.

## Maschinenlesbare Zusammenfassung

[`run-summary.json`](./run-summary.json) folgt dem Schema `agora-reference-run-summary-v1` und enthält Run-Identität, Modelle, Simulationskennzahlen, Claim-/Hypothesen-/Data-Gap-Zahlen, Evidence-Zusammensetzung, Gate-Entscheidungen, Persona-Eligibility-Werte, bestätigte positive Beobachtungen, bekannte Fehlerklassen, Remediation-Priorität und zugehörige Issues.

Sie ist **kein** vollständiger Evidence-Export und ersetzt weder `evidence_map.json` noch die Rohlogs.

## Nicht in diesem Ordner

Die vollständigen Laufartefakte liegen im Betriebsverzeichnis und sind nicht Teil des Repositories — Pfade siehe oben. Die Simulationsdatenbanken enthalten Personendaten simulierter Personas und werden deshalb nicht mit veröffentlicht.

## Hinweis zur Auswertung der Simulationsdatenbanken

Reposts und Quotes sind in `post` eigene Zeilen mit gesetztem `original_post_id`; reine Reposts tragen leeres `content`. Ohne den Filter `original_post_id IS NULL` sieht jede Auswertung nach Mode-Collapse und leeren Posts aus, obwohl es korrekte Semantik ist.
