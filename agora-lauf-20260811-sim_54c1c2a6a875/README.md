# Agora-Lauf 11.08.2026 — Artefakte

Simulation `sim_54c1c2a6a875`, Projekt `proj_623bbb4845a5`, Graph `b8d0c6dc-3509-45ad-a19d-1b2de08135ea`.
Testfall: AZAV-Umschulungsträger Sachsen-Anhalt, Einführung eines selbstgehosteten KI-Lernassistenten.

Code-Stand: Container-Image gebaut 03:33, `evidence.py` / `manager.py` / `simulation_config_generator.py` / `oasis_profile_generator.py` byte-identisch (md5) mit dem Arbeitsbaum zum Zeitpunkt des Laufs.

## Inhalt

| Ordner | Inhalt |
|---|---|
| `sim_54c1c2a6a875/` | `simulation_config.json`, `run_state.json`, `simulation.log`, `reddit_profiles.json`, `twitter_simulation.db`, `reddit_simulation.db` |
| `report_glm-5.2_9107e3d60b10/` | Report-Lauf 1 — `glm-5.2`, Sections 1–3, `evidence_map.json`, `agent_log.jsonl` |
| `report_deepseek_7ce9e4882bae/` | Report-Lauf 2 — `deepseek-v4-flash:0731`, Section 1, `evidence_map.json`, `agent_log.jsonl` |

Beide Reports laufen auf **derselben Simulation und demselben Evidence-Pool**. Der einzige Unterschied ist das Report-Modell — ein kontrollierter Vergleich.

## Simulation

`runner_status: completed`, 10/10 Runden auf beiden Plattformen, 404 Aktionen (Twitter 157, Reddit 247), 30 Agenten.

Trace-Verteilung:

```
Twitter: like_post 67, refresh 56, quote_post 34, create_post 32, sign_up 30, follow 8, repost 6, do_nothing 1
Reddit : like_post 132, refresh 79, create_comment 59, like_comment 34, sign_up 30, create_post 11, search_user 2
```

**Auswertungsfalle:** Reposts und Quotes sind eigene Zeilen in `post` mit gesetztem `original_post_id`; reine Reposts haben leeres `content`. Ohne den Filter `original_post_id IS NULL` sieht jede Auswertung nach Mode-Collapse und leeren Posts aus, obwohl es korrekte Semantik ist.

## Evidence-Bindung — der Kernbefund

| | glm-5.2 | deepseek-v4-flash |
|---|---|---|
| Claims in Section 1 | 40 | 21 |
| **validierte Claims** | **0** | **0** |
| Hypothesen | 41 | 21 |
| data_gaps | 40 | 20 |
| Einträge im `evidence_index` | 41 | 38 |
| Bindungsdauer Section 1 | 343 s | 370 s |
| Gate-Verstöße | 40× `no_supporting_evidence`, 1× `prose_fact_unsupported` | 20× `no_supporting_evidence`, 1× `reviewer_floor_insufficient_evidence` |

Der Evidence-Pool ist inhaltlich passend besetzt (13 `seed_document`, 8 `agent_interview`, 8 `relationship_chain`, 8 `agent_action`, 4 `graph_metric`). Gebunden wird trotzdem nichts. Zusammen mit den beiden Läufen aus #1209 (`deepseek-v4-flash`, `glm-5.2`) ist das der dritte und vierte modellunabhängige Beleg.

## Zitat-Kennzeichnung

| `section_01.md` | glm-5.2 | deepseek |
|---|---|---|
| `**Simulierter Persona-O-Ton**` | 8 | **0** |
| `persona_id:` / `seed_anchor:` | 8 | **0** |
| Blockquotes | 16 | 3 |

Bei glm tragen alle 8 Zitate denselben `seed_anchor: seed_doc:interview_transcript_07` — das ist wörtlich der Beispielstring aus `report_prompts/sections.py:196`. Bei deepseek fehlt die Tag-Syntax ganz, wodurch die Validierung in `evidence.py` keine Quotes findet und `valid=True` liefert.

## Inhaltliche Divergenz bei identischen Daten

Beide Reports nennen denselben ersten Bruchpunkt (Honorarkräfte), aber eine **verschiedene Hauptkonfliktlinie**:

- glm-5.2: Honorarkräfte ↔ Geschäftsführung
- deepseek: Geschäftsführung ↔ Betriebsrat

Gleiche Simulation, gleiche 41 bzw. 38 Evidence-Einträge, zwei verschiedene zentrale Antworten — jeweils als *das* Ergebnis präsentiert.

## Zugehörige Issues

- **#1226** — fünf Befunde: Poster-Zuordnung aller Initial-Posts auf einen Agenten (IHK), Twitter verwirft 8 von 9 Seed-Posts, Persona-Rollendubletten und Nicht-Stakeholder, Provenance-Anker aus dem Prompt-Beispiel, Report-Cancel wird produktiv nie durchgereicht.
- **#1209** — Regressionsmatrix: Befund 3 bestätigt behoben, Befund 1 und 2 erfüllt aber unabgehakt, Befund 4 und 6 reproduzieren trotz gesetzter Haken.
