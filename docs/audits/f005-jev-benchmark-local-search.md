# Jev-Benchmark: local-search-relevance (minimal)

Stand: 21.09.2026. Feature f005, Slice `jev-benchmark`. Repository-Basis: `feat/f005-decision-pilot` (Task `real-jev-client`, Commit `f35af2e4`).

## Was dieser Bericht ist — und was nicht

**Ist:** ein einmaliger, echter Vergleich zwischen der bestehenden Rule-Baseline und einem echten Jev-Aufruf auf einer kleinen, handgebauten Fallmenge für genau den einen Use Case, der bereits produktiv im Shadow-Modus verdrahtet ist (`local-search-relevance`, `app/services/graph/graph_reader.py::local_search`).

**Ist NICHT:** der in `docs/research/f005/benchmark-design.md` spezifizierte vollständige Benchmark. Alex hat den Umfang während dieses Tasks explizit reduziert (2026-09-21): kein mehrtägiger, statistisch abgesicherter Lauf mit Power-Analyse, Kalibrations-/Test-Split-Trennung, Latenz-unter-Last-Messung oder Vergleichsarmen für günstiges/leistungsfähiges LLM. Ziel war ein lauffähiger End-to-End-Nachweis mit echtem API-Zugang, keine Forschungsarbeit.

**Ground Truth ist NICHT maintainer-geprüft.** Die Spezifikation verlangt das ausdrücklich für einen belastbaren Benchmark. Die zwölf Fälle in `backend/scripts/jev_benchmark_local_search.py` sind vom Implementierer konstruiert (Bundeskanzleramt/Bundesministerium/Bundestag-Domäne, passend zu den bestehenden Beispielen in `decision-map.md`), nicht aus einem echten AGORA-Lauf gezogen — es existiert kein Produktionsgraph, nur Testdaten. Dieser Bericht ist ein Anhaltspunkt, keine Freigabe für `authoritative`.

## Ergebnis (ein Lauf, 21.09.2026, `jev-1.13.0`)

| Metrik | Rule-Baseline | Jev |
|---|---|---|
| Accuracy (12 Fälle, nach Korrektur des BMF-Labels) | 67 % (8/12) | 100 % (12/12)¹ |
| Fehler (API/Schema) | — | 0 |
| Latenz median | ~0 ms (reiner Python-Code) | 288 ms |
| Latenz max | ~0 ms | 793 ms |
| Kosten gesamt | 0 | 159 Mikro-USD (12 Aufrufe, ~13 µ$/Aufruf) |

¹ Rückwirkend aus der dokumentierten Zuordnung des einzigen Jev-Fehlers zum BMF-Fall berechnet. Das ursprüngliche Label war semantisch falsch (`BMF` bezeichnet das Bundesministerium der Finanzen) und hatte Rule 9/12 sowie Jev 11/12 ausgewiesen. Rohantworten je Fall wurden nicht archiviert; diese korrigierte Zahl ist daher eine Rekonstruktion, kein neuer Live-Lauf und kein unabhängig auditierbarer Qualitätsnachweis.

Volle Falltabelle im Skript-Output, reproduzierbar mit einem gebundenen Jev-Key:

```bash
cd backend && uv run python scripts/jev_benchmark_local_search.py
```

## Beobachtungen

- **Die vier Rule-Fehler nach Label-Korrektur sind Keyword-Matching-Fallstricke:** `coincidental-substring` ("Rat" matcht zufällig in "Vorrat"), `single-keyword-weak-match` (ein einzelnes schwaches Keyword-Match ohne thematischen Bezug), `different-topic-shared-word` (gemeinsames Wort, anderes Thema) und `abbreviation-mismatch` (BMF ↔ "Bundesministerium der Finanzen"). Der BMF-Fall war im ursprünglichen Datensatz fälschlich als irrelevant markiert. Die dokumentierte Jev-Antwort war hier semantisch richtig; dieser Fehler lag im Benchmark-Label.
- **Kosten in dieser Stichprobe:** rund 13 Mikro-USD pro Entscheidung. Die Kosten pro Lauf hängen von der tatsächlichen Zahl der Suchaufrufe ab; diese wurde in diesem Benchmark nicht gemessen.
- **Latenz ist der eigentliche Kompromiss.** ~290 ms median gegen ~0 ms für die reine Python-Regel ist auf einem synchronen Retrieval-Pfad spürbar, besonders wenn `local_search` mehrfach pro Report-Abschnitt aufgerufen wird. Das produktive Shadow-Wiring (`local_search_shadow.py`) ruft ohnehin nur RuleProvider auf — dieser Befund ist relevant für eine spätere `authoritative`-Aktivierung, nicht für den heutigen Zustand.
- **State-Form-Unterschied zum produktiven Pfad:** Der produktive Shadow-Aufruf in `local_search_shadow.py` sendet bewusst nur `{"top_score": ...}` (kein Klartext), weil er nur RuleProvider anspricht. Dieses Benchmark-Skript sendet für den Jev-Arm zusätzlich Query und Fakt im Klartext — notwendig, damit Jev überhaupt etwas zu bewerten hat, aber eine andere (größere) Datenexposition als der heutige Produktivpfad. Vor einer echten `shadow`- oder `authoritative`-Aktivierung mit Jev müsste `local_search_shadow.py` entsprechend erweitert und die Datenschutzfrage (Klartext-Fakten an einen externen Dienst) explizit vom Maintainer freigegeben werden — offen, siehe `jev-provider-evidence.md`, Abschnitt Datenschutz.

## Einschätzung

Für **local-search-relevance** ist Jev auf dieser kleinen Stichprobe der Keyword-Regel überlegen, zu vernachlässigbaren Kosten, aber mit einer spürbaren Latenzzunahme und einer noch ungeklärten Datenschutzfrage (Klartext-Fakten an TypeSafe). Das rechtfertigt **weitere Datenerhebung mit maintainer-geprüfter Ground Truth**, nicht sofortige Promotion — die Fallmenge ist zu klein und zu wenig divers für eine Aussage mit Unsicherheitsintervall (Akzeptanzkriterium 1 aus `benchmark-design.md`), und die Datenschutzfreigabe für Klartext-State steht aus.

**Kein Ausgang dieser Bewertung ist "Reject"** — die Ergebnisse sind ermutigend genug, um eine größere, maintainer-verifizierte Stichprobe zu rechtfertigen, sobald sie priorisiert wird.

## Failure-Injection: was der Review am Runner gefunden hat

Der Review-Task dieses Slices hat den Runner mit einem ungültigen Key gegen die echte API laufen lassen (alle zwölf Aufrufe → `TypeSafeAuthenticationError`, HTTP 401, keine Retries — Auth-Fehler sind korrekterweise nicht transient). Dabei fielen zwei echte Mängel am Runner auf, beide behoben:

1. **Exit-Code 0 trotz komplett fehlgeschlagenem Jev-Arm.** Die Fehler standen zwar im Text, aber ein Wrapper oder eine Pipeline hätte den Lauf als erfolgreich gelesen. Der Runner gibt jetzt Exit-Code 1 zurück, wenn der Jev-Arm versucht wurde und fehlschlug; ein *übersprungener* Arm (kein Key gebunden) bleibt Exit-Code 0, weil das der dokumentierte Normalfall ohne Zugang ist.
2. **Teilausfall hätte eine nicht vergleichbare Quote gedruckt.** Bei z. B. sechs von zwölf geglückten Aufrufen wäre eine Jev-Accuracy über diese sechs neben der Rule-Accuracy über alle zwölf gestanden — zwei verschiedene Grundgesamtheiten, nebeneinander gedruckt und dadurch scheinbar vergleichbar. Der Runner weist jetzt bei *jedem* Fehler überhaupt keine Jev-Accuracy mehr aus und sagt explizit, warum.

Festgenagelt in `backend/tests/scripts/test_jev_benchmark_report.py` (vier Fälle: übersprungen, vollständig fehlgeschlagen, teilweise fehlgeschlagen, sauber). Verifiziert wurden alle drei Pfade gegen die echte API: gültiger Key → Exit 0 mit Bericht, ungültiger Key → Exit 1 ohne Quote, kein Key → Exit 0 mit Hinweis.

## Bekannte Grenzen dieses Piloten

- 12 Fälle, ein einziger Lauf, keine Wiederholung (keine Varianzabschätzung über mehrere Läufe).
- Keine Kalibrationsprüfung (Brier Score, Reliability-Diagramm) — `probability_yes` wird hier nur binär bei 0,5 geschnitten, nicht auf tatsächliche Kalibrierung geprüft.
- Kein Vergleichsarm für günstiges/leistungsfähiges LLM (Vergleichsarm 3/4 aus der Spezifikation fehlt).
- Keine Failure-Injection außerhalb des bereits im Integrationstest geprüften 401-Falls (`tests/integration/test_jev_provider_integration.py`) — Timeout, 429, API-Drift nicht gezielt provoziert.
- Latenz nur als Einzelwerte, nicht unter realistischer Nebenlast gemessen.

## Integration auf aktuellem `main` (30.09.2026)

Die fünf Benchmark-Commits wurden auf `origin/main` (`bc47d27fb`) in `feat/f005-jev-benchmark-landing` übernommen. Gezielt liefen nach dem Review 36 Tests grün (vier Live-API-Tests mangels explizitem `TYPESAFE_API_KEY` deselected), dazu 1.011 Contract-Tests, Schema-Drift-Check, Ruff und mypy. Ein erneuter Aufruf des Runners ergab Rule 8/12 und meldete den Jev-Arm mangels gebundenem Provider-Key ausdrücklich als übersprungen. Die oben genannten Jev-Werte sind eine nachträgliche Korrektur des am 21.09.2026 berichteten Laufs; sie sind kein neuer Live-Nachweis für diesen Branch.

## Nachtrag: fehlende Relevanz-Aussage im Jev-State (PR #1731, 30.09.2026)

Der Review von PR #1731 (Codex) hat einen echten Mangel im Jev-Arm dieses Runners gefunden: `jev_state` sendete nur `{"query": ..., "fact": ...}`, ohne eine Aussage, die Jev bewerten kann. `_NOUL_INSTRUCTIONS` in `jev_provider.py` fragt aber wörtlich nach der Wahrscheinlichkeit, dass „die Aussage im State" zutrifft — ohne eine explizite Aussage wie `"assertion": "Der Fakt ist für die Suchanfrage relevant."` (dieselbe, die `jev_rollout_probe.py` bereits verwendet) bewertet Jev nichts Definiertes gegen `expected_relevant`.

Der Runner ist entsprechend gefixt (`backend/scripts/jev_benchmark_local_search.py`). Damit war die oben berichtete Jev-Accuracy von 12/12 (Fußnote 1) nicht mehr belastbar — sie wurde am 21.09.2026 gegen die unterspezifizierte Prompt-Form gemessen, bevor dieser Fix existierte. Der Live-Lauf im nächsten Abschnitt ersetzt sie.

## Live-Lauf mit korrigierter Prompt-Form (30.09.2026, `jev-1.13.0`)

Erneuter Lauf des Runners auf `main` (`7b0f30c2`, enthält den `assertion`-Fix aus PR #1731) mit gebundenem Key gegen die echte API. Die Rohwerte je Fall sind hier archiviert, damit die Zahl unabhängig nachprüfbar ist.

| Fall | Query | top_score | erwartet | Rule | Jev-P(ja) | Jev korrekt | Kosten (µ$) | Latenz (ms) |
|---|---|---|---|---|---|---|---|---|
| exact-match | 'Bundeskanzleramt' | 100 | ja | ✓ | 0.88 | ✓ | 14 | 442 |
| keyword-overlap | 'Bundesministerium Finanzen' | 20 | ja | ✓ | 0.87 | ✓ | 14 | 288 |
| no-overlap | 'Bundeskanzleramt' | 0 | nein | ✓ | 0.06 | ✓ | 14 | 262 |
| coincidental-substring | 'Rat' | 100 | nein | ✗ | 0.34 | ✓ | 14 | 307 |
| partial-relevant | 'Bundestag Ausschuss' | 20 | ja | ✓ | 0.80 | ✓ | 14 | 276 |
| different-institution | 'Bundeskanzleramt' | 0 | nein | ✓ | 0.10 | ✓ | 14 | 270 |
| single-keyword-weak-match | 'Bundeskanzleramt Pressekonferenz' | 10 | nein | ✗ | 0.08 | ✓ | 14 | 283 |
| long-fact-relevant | 'Bundesministerium Digitales' | 20 | ja | ✓ | 0.87 | ✓ | 15 | 285 |
| abbreviation-mismatch | 'BMF' | 0 | ja | ✗ | 0.84 | ✓ | 14 | 271 |
| negation-in-fact | 'Bundeskanzleramt Stellungnahme' | 20 | ja | ✓ | 0.66 | ✓ | 14 | 281 |
| different-topic-shared-word | 'Bundeskanzleramt Sicherheit' | 10 | nein | ✗ | 0.19 | ✓ | 14 | 249 |
| multi-entity-relevant | 'Bundeskanzleramt Bundestag' | 20 | ja | ✓ | 0.80 | ✓ | 14 | 251 |

| Metrik | Rule-Baseline | Jev |
|---|---|---|
| Accuracy | 67 % (8/12) | 100 % (12/12) |
| Fehler (API/Schema) | — | 0 |
| Latenz median / max | ~0 ms | 278 ms / 442 ms |
| Kosten gesamt | 0 | 169 Mikro-USD (12 Aufrufe) |

Beobachtungen:

- Jev löst alle vier Keyword-Fallstricke der Regel, auch `abbreviation-mismatch` (P(ja) 0,84).
- Die knappsten Entscheidungen sind `coincidental-substring` (0,34) und `negation-in-fact` (0,66) — beide richtig, aber mit geringerem Abstand zur 0,5-Schwelle als der Rest. Das sind die ersten Kandidaten für eine Kalibrationsprüfung.
- Die Grenzen oben gelten unverändert: Ground Truth nicht maintainer-geprüft, ein Lauf, 12 Fälle, keine Kalibrationsprüfung, Datenschutzfreigabe für Klartext-State offen. Die Einschätzung („weitere Datenerhebung, kein Promote, kein Reject") bleibt deshalb bestehen.
