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
| L4 | `mutual_pair_share` / `max_chain_length` | `mutual_pair_share`: Reaktionsgraph (Kante Akteur→Zielautor über `post_id`/`comment_id`/`quoted_id`/`reposted_id`); Paare mit Kanten in beide Richtungen / Paare mit ≥1 Kante. `max_chain_length`: längste Beitrags-Antwortkette (`CREATE_POST`/`CREATE_COMMENT`/`QUOTE_POST`/`REPOST`, je höchstens ein referenzierter früherer Beitrag) | ≥ 15 % Paare, Kette ≥ 3 |
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

- **L4 `max_chain_length`** ist die längste Beitrags-Antwortkette, nicht der
  längste Pfad im Akteur-Reaktionsgraphen (der bleibt `mutual_pair_share`
  vorbehalten). Jeder inhaltliche Beitrag (`CREATE_POST`, `CREATE_COMMENT`,
  `QUOTE_POST`, `REPOST`) referenziert höchstens einen früheren Beitrag über
  `post_id`/`comment_id`/`quoted_id`/`reposted_id` bzw. `original_post_id` —
  daraus ergibt sich in Zeitordnung ein Wald/DAG, dessen Tiefe sich in einem
  Durchlauf (O(n), Memoisierung über die bereits gesehenen Beiträge)
  berechnen lässt. Likes und Follows zählen nicht als Kettenglied. Ein
  Startpost ohne `post_id` (Runde 0, siehe `_log_initial_post`) kann nicht
  als Elternteil identifiziert werden — ein späterer Beitrag, der ihn
  referenziert, wird dadurch selbst zur Wurzel statt die Kette zu
  verlängern.
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

## Hebel: Aktivitätskonfiguration und Feed-Parameter (#1713 S4)

Baseline-Läufe (vor diesem Slice) lagen bei 0,16-0,22 Aktionen/Agent/Runde
(L1-Ziel ≥ 0,6) und rund 25 % aktiven Agenten/Runde (L2-Ziel ≥ 40 %). Drei
Konfigurationswerte konnten das strukturell verhindern — LLM-Output *und*
Regel-Fallback unabhängig voneinander:

- `agents_per_hour_min`/`agents_per_hour_max` (Zeitkonfiguration) —
  begrenzen den Ziel-Kandidatenpool je Runde.
- `activity_level` (Agentenkonfiguration) — Pro-Agent-Wahrscheinlichkeit,
  in einer aktiven Stunde überhaupt Kandidat zu werden.
- `active_hours` (Agentenkonfiguration) — grenzt Agenten auf enge
  Tagesfenster ein (z. B. Behörden nur 9-17 Uhr) und leert den
  Kandidatenpool in allen übrigen Stunden, unabhängig von `activity_level`.

`backend/app/services/simulation_activity_policy.py` hebt alle drei Werte
auf eine Untergrenze an (`agents_per_hour_min ≥ ceil(0,4·N)`,
`agents_per_hour_max ≥ ceil(0,7·N)`, `activity_level ≥ 0,5`, `active_hours`
deckt mindestens 06-23 Uhr ab — 0-5 Uhr bleibt bewusst die
DACH-Nachtruhe-Ausnahme). Die Runden-Auswahl selbst
(`select_active_agent_ids`) ist seitdem ein gemeinsamer Helfer für
`platform_runner.py` und `run_parallel_simulation.py` statt zweier
Kopien.

Zusätzlich vergrößert Agora den Twitter-Feed gegenüber dem engen
OASIS-Default (`refresh_rec_post_count`/`max_rec_post_len`/
`following_post_count` von 2/2/3 auf 5/5/5) — Details in
`docs/runbooks/simulation-recommender.md` §Feed-Parameter. Reddit bleibt
unverändert.

**Wichtig:** Diese Untergrenzen erhöhen ausschließlich den
*Erwartungswert* aktiver Agenten pro Runde, um L1/L2 erreichbar zu machen.
Sie behaupten keine Aussage über reales Stakeholder-Verhalten (ADR-0002) —
Agora sagt kein menschliches Verhalten vorher.

## Fixtures für Regressionstests

`backend/tests/fixtures/sim_liveness/clean_run/` und `.../legacy_run/` sind
von Hand konstruierte, minimale Run-Verzeichnisse — jede Kennzahl hat dort
einen nachrechenbaren erwarteten Wert (siehe
`backend/tests/scripts/test_sim_liveness_metrics.py`). `legacy_run/`
reproduziert gezielt die Altlauf-Signatur aus Slice S1.
