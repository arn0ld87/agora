# Runbook: Kennzahlen "Simulation lebt"

**Zweck:** Zehn Kennzahlen (L1-L10), die belegen, dass eine Simulation
tatsächlich Diskursaktivität erzeugt hat — reagiert, repostet, widerspricht —
statt nur leere Runden abzuspulen oder sich in einem Altlauf-Defekt zu
verlieren.

Umgesetzt in Issue [#1713](https://github.com/arn0ld87/agora/issues/1713),
Slice S0.

**Wichtig:** Diese Kennzahlen belegen **Diskursaktivität**, keine
Verhaltensvorhersage und keine Aussage über reale Stakeholder — siehe
ADR-0002 / `CONTEXT.md`. Ein hoher `mutual_pair_share` heißt nicht, dass echte
Menschen so reagieren würden.

---

## Aufruf

```bash
cd backend
uv run python scripts/sim_liveness_metrics.py <run_dir> [--seed <pfad>]
```

`<run_dir>` ist ein Simulations-Run-Verzeichnis mit `simulation_config.json`,
`run_state.json` und mindestens einem von `twitter/actions.jsonl` /
`reddit/actions.jsonl`. `--seed` zeigt auf das Seed-Dokument (z. B.
`seed_document.md`) und aktiviert L7 (Seed-Echo); ohne `--seed` bleibt L7
`null`.

Auf armserver gegen einen laufenden Container:

```bash
ssh armserver 'docker exec -i agora /app/backend/.venv/bin/python /app/backend/scripts/sim_liveness_metrics.py /app/backend/uploads/simulations/<id>'
```

Ausgabe ist ein `SimulationLivenessReport` (siehe
`backend/app/contracts/simulation_liveness_contract.py`,
`schemas/simulation-liveness-report.schema.json`) als JSON auf stdout.
Diagnose/Warnungen (unparsebare Zeilen, fehlende Dateien) gehen als
strukturiertes Logging nach stderr.

**Mess-Seed:** `docs/test-seeds/ki-azubi-match-dortmund` — nur
`seed_document.md` und `prompt.md` als `--seed`-Quelle verwenden.
`erwartungshorizont.md` aus diesem Verzeichnis **nie** ins Projekt laden
(Seed-Leakage, [#1240](https://github.com/arn0ld87/agora/issues/1240)).

---

## Kennzahlen und Zielwerte

Jede Kennzahl ist `float | int | null`. `null` bedeutet **nicht bestimmbar**
aus den vorliegenden Logs (z. B. kein `--seed`, keine Runden) — nie eine
stillschweigende 0. Der Grund landet in `data_quality_notes`.

| # | Kennzahl | Definition | Zielwert |
|---|----------|------------|----------|
| L1 | `actions_per_agent_round` | reale Aktionen (ohne Startposts, `DO_NOTHING`, `REFRESH`, `SIGN_UP`) / (Agentenzahl × abgeschlossene Runden) | ≥ 0,6 |
| L2 | `active_agent_share_median` | Median je Runde von (aktive Agenten / Agentenzahl); aktiv = mind. eine geloggte Aktion inkl. `DO_NOTHING` | ≥ 40 % |
| L3 | `own_post_share` | (`CREATE_POST`+`QUOTE_POST`, ohne Startposts) / (`CREATE_POST`+`CREATE_COMMENT`+`QUOTE_POST`+`REPOST`) | ≥ 20 % |
| L4 | `mutual_pair_share` / `max_chain_length` | Reaktionsgraph (Kante Akteur→Zielautor über `post_id`/`comment_id`/`quoted_id`/`reposted_id`); Paare mit Kanten in beide Richtungen / Paare mit ≥1 Kante; `max_chain_length` = längster simpler Pfad | ≥ 15 % Paare, Kette ≥ 3 |
| L5 | `rejection_share` / `contra_reply_share` | `DISLIKE_POST`+`DISLIKE_COMMENT` / alle Like-/Dislike-Reaktionen; `contra_reply_share` bleibt in diesem Slice `null` (bräuchte Stance-Klassifikation) | ≥ 10 % |
| L6 | (Persona-Haltungsverteilung) | nicht in diesem Slice — keine Haltung dominiert mit > 70 % | — |
| L7 | `seed_echo_share` | Anteil eigener Post-/Quote-Aktionen, deren Inhalt eine Zahl aus dem Seed wörtlich oder eine wörtliche Tokenfolge ≥ 8 Wörter enthält; nur mit `--seed` | ≤ 20 % |
| L8 | `duplicate_log_lines` / `round_fill_share` | doppelt geloggte Startposts (Altlauf-Signatur #1713 Slice S1) bzw. Anteil vollständiger `round_start`/`round_end`-Paare | 0 Duplikate / 100 % Runde |
| L9 | (Prozess-/Budget-Fehler) | nicht in diesem Slice — siehe `run_state.json`/`budget_config.json` | 0 |
| L10 | (Laufzeit) | nicht in diesem Slice — Wall-Clock aus `run_state.json` | 3/3 Läufe < 30 min |

L6, L9, L10 werden bewusst nicht von diesem Skript berechnet — sie brauchen
Persona-/Budget-/Prozessdaten außerhalb von `actions.jsonl` und bleiben
manuelle Prüfung bzw. Folgearbeit.

---

## Interpretationsentscheidungen (dokumentiert, nicht selbstverständlich)

- **L4 `max_chain_length`** ist der längste simple Pfad im gerichteten
  Reaktionsgraphen (nicht die Repost-Kette allein) — Kanten sind dieselben
  wie für `mutual_pair_share`. Bei mehr als 400 Kanten wird die Pfadsuche
  übersprungen (`data_quality_notes`), weil sie exponentiell ist.
- **L7-Match** ist wörtlich (case-sensitive), nicht semantisch: eine Zahl aus
  dem Seed oder eine 8-Wort-Folge muss exakt im Post-Inhalt auftauchen.
- **`duplicate_log_lines`** zählt gezielt die #1713-Altlauf-Signatur (ein
  `CREATE_POST` mit identischem `(agent_id, content)` in Runde 0 *und* einer
  späteren Runde), nicht generische byte-identische Log-Zeilen — letztere
  würden das Original-Defektmuster (Runde differiert) nicht erfassen.
- Fehlt in einer Alt-Log-Zeile das `round`-Feld, wird die Runde aus dem
  zuletzt gesehenen `round_start`-Event in Dateireihenfolge abgeleitet; ganz
  ohne Bezug fällt die Zeile aus den rundenbasierten Kennzahlen heraus statt
  Runde 0 zu erfinden.

---

## Fixtures für Regressionstests

`backend/tests/fixtures/sim_liveness/clean_run/` und `.../legacy_run/` sind
von Hand konstruierte, minimale Run-Verzeichnisse — jede Kennzahl hat dort
einen nachrechenbaren erwarteten Wert (siehe
`backend/tests/scripts/test_sim_liveness_metrics.py`). `legacy_run/`
reproduziert gezielt die Altlauf-Signatur aus Slice S1.
