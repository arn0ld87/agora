### Added (Läufe allein aus gespeicherten Personas, 2026-08-19)

- **`POST /api/simulation/create-from-personas`** legt Projekt und Simulation an und bereitet sie ausschließlich aus Personas vor — Verweise in die Bibliothek (`template_ids`) oder Inline-Personas. Kein Dokument, keine Ontologie, kein Graph. Bewusst ein eigener Endpunkt: in `/create` bleibt die `graph_id` Pflicht, der reguläre Weg über Dokument und Graph weicht nicht auf.
- **`prepare_from_personas`** fährt denselben FSM-Pfad wie `branching_service.create_branch` (`CREATED → PREPARING → READY`, kein Direktsprung) und schreibt `reddit_profiles.json`/`twitter_profiles.csv` sowie eine `simulation_config.json`. Beim Übersetzen der Bibliothekseinträge werden Felder ergänzt, die die Bibliothek gar nicht führt: `user_id`, `karma`, `created_at` (auf das Tagesformat normiert), `persona_kind` — und vor allem `age`/`gender`/`mbti`, die **immer** existieren müssen, weil die OASIS-Bibliothek sie ungeschützt indiziert. `PersonaLibrary._normalize` lässt leere Werte weg, ein Eintrag ohne Alter hat den Schlüssel also gar nicht.

### Changed

- **Die harte Untergrenze von 30 Personas ist entfallen** (`_validate_persona_quota` im `simulation_config_generator`, Issue #496). Sie stand genau dem im Weg, wofür der neue Weg gedacht ist: einem kleinen, gezielten Lauf — einem Gremium aus acht Leuten etwa. 30 bleibt der Vorschlagswert im Dashboard, ist aber keine Schranke mehr; unterhalb erscheint ein Hinweis auf die dünnere Aussagekraft statt einer Sperre. Mit der Grenze fällt auch der Schalter, der sie aufhob: `AGORA_ALLOW_SMALL_SIM` und das gespiegelte `allow_small_sim` in `/api/status` sind entfernt, ebenso die Abfrage im Dashboard, die den Regler beim Mount wieder hochklemmte.

### Fixed

- **Berichte sagen jetzt, was einem Persona-Lauf fehlt.** Die drei Prüfpunkte (`report_generation.py`, `report.py`, `runs.py`) antworteten mit „Missing graph ID" — einem Satz, der jemandem nichts sagt, der nie einen Graphen bauen wollte. Sie nennen jetzt den Grund und halten fest, dass die Simulation selbst in Ordnung ist. Bewusst **kein** Platzhalter-Graph: ein formal gültiger Fake würde die Prüfungen passieren lassen, und der Bericht liefe ohne jede Graph-Evidenz durch — er sähe aus wie ein normaler. Ein klarer Abbruch ist ehrlicher.
