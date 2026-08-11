# Artefakte des Referenzlaufs vom 11. August 2026

Dieser Ordner gehört zum Referenzlauf `report_40236c4a59f0` / `sim_8495a5fe314b` — Einführung eines selbstgehosteten KI-Lernassistenten bei einem AZAV-zertifizierten Umschulungsträger.

## Maschinenlesbare Zusammenfassung

[`run-summary.json`](./run-summary.json) fasst die in der Referenzlauf-README genannten Kennzahlen und Befunde im Schema `agora-reference-run-summary-v1` zusammen:

- Run-Identität, Modelle und Embedding-Konfiguration,
- Simulationskennzahlen inklusive Cluster, Echo-Chamber-Index und Interaktionsverteilung,
- Claim-, Hypothesen- und Data-Gap-Zahlen sowie die Zusammensetzung des Evidence-Index,
- Gate-Entscheidungen nach Verstoßtyp,
- Persona-Diversitätskennzahlen,
- bestätigte positive Beobachtungen,
- bekannte Fehlerklassen und priorisierte Folgearbeit,
- zugehörige Issues.

Die Datei ist **kein vollständiger Evidence-Export** und kein Ersatz für die `evidence_map.json` oder die Rohlogs.

## Nicht in diesem Ordner

Die vollständigen Laufartefakte liegen im Betriebsverzeichnis und sind nicht Teil des Repositories:

- `backend/uploads/simulations/sim_8495a5fe314b/` — `simulation_config.json`, `run_state.json`, `reddit_profiles.json`, `twitter_simulation.db`, `reddit_simulation.db`, `simulation.log`
- `backend/uploads/reports/report_40236c4a59f0/` — `evidence_map.json`, `outline.json`, `section_01.md` bis `section_06.md`, `agent_log.jsonl`, `console_log.txt`

Die Simulationsdatenbanken enthalten Personendaten simulierter Personas und werden deshalb nicht mit veröffentlicht.

## Hinweis zur Auswertung der Simulationsdatenbanken

Reposts und Quotes sind in `post` eigene Zeilen mit gesetztem `original_post_id`; reine Reposts tragen leeres `content`. Ohne den Filter `original_post_id IS NULL` sieht jede Auswertung nach Mode-Collapse und leeren Posts aus, obwohl es korrekte Semantik ist.
