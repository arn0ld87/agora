# Jev-Benchmark: local-search-relevance (minimal)

Stand: 21.09.2026. Feature f005, Slice `jev-benchmark`. Repository-Basis: `feat/f005-decision-pilot` (Task `real-jev-client`, Commit `f35af2e4`).

## Was dieser Bericht ist — und was nicht

**Ist:** ein einmaliger, echter Vergleich zwischen der bestehenden Rule-Baseline und einem echten Jev-Aufruf auf einer kleinen, handgebauten Fallmenge für genau den einen Use Case, der bereits produktiv im Shadow-Modus verdrahtet ist (`local-search-relevance`, `app/services/graph/graph_reader.py::local_search`).

**Ist NICHT:** der in `docs/research/f005/benchmark-design.md` spezifizierte vollständige Benchmark. Alex hat den Umfang während dieses Tasks explizit reduziert (2026-09-21): kein mehrtägiger, statistisch abgesicherter Lauf mit Power-Analyse, Kalibrations-/Test-Split-Trennung, Latenz-unter-Last-Messung oder Vergleichsarmen für günstiges/leistungsfähiges LLM. Ziel war ein lauffähiger End-to-End-Nachweis mit echtem API-Zugang, keine Forschungsarbeit.

**Ground Truth ist NICHT maintainer-geprüft.** Die Spezifikation verlangt das ausdrücklich für einen belastbaren Benchmark. Die zwölf Fälle in `backend/scripts/jev_benchmark_local_search.py` sind vom Implementierer konstruiert (Bundeskanzleramt/Bundesministerium/Bundestag-Domäne, passend zu den bestehenden Beispielen in `decision-map.md`), nicht aus einem echten AGORA-Lauf gezogen — es existiert kein Produktionsgraph, nur Testdaten. Dieser Bericht ist ein Anhaltspunkt, keine Freigabe für `authoritative`.

## Ergebnis (ein Lauf, 21.09.2026, `jev-1.13.0`)

| Metrik | Rule-Baseline | Jev |
|---|---|---|
| Accuracy (12 Fälle) | 75 % (9/12) | 92 % (11/12) |
| Fehler (API/Schema) | — | 0 |
| Latenz median | ~0 ms (reiner Python-Code) | 288 ms |
| Latenz max | ~0 ms | 793 ms |
| Kosten gesamt | 0 | 159 Mikro-USD (12 Aufrufe, ~13 µ$/Aufruf) |

Volle Falltabelle im Skript-Output, reproduzierbar mit einem gebundenen Jev-Key:

```bash
cd backend && uv run python scripts/jev_benchmark_local_search.py
```

## Beobachtungen

- **Jev schlägt die Keyword-Regel genau dort, wo Semantik zählt.** Drei der vier Rule-Fehler sind klassische Keyword-Matching-Fallstricke: `coincidental-substring` ("Rat" matcht zufällig in "Vorrat"), `single-keyword-weak-match` (ein einzelnes schwaches Keyword-Match ohne thematischen Bezug) und `different-topic-shared-word` (gemeinsames Wort, anderes Thema). Jev hat alle drei korrekt als irrelevant bzw. relevant eingeordnet — das ist genau die Fehlerklasse, die eine reine Keyword-Regel strukturell nicht lösen kann.
- **Jevs einziger Fehler (`abbreviation-mismatch`, BMF ↔ "Bundesministerium der Finanzen") ist ein Prompt-Qualitätsproblem, kein Modellversagen.** Der `DecisionState` für diesen Piloten trägt nur `{"query": ..., "fact": ...}` mit einer generischen Anweisung ("Beantworte mit der Wahrscheinlichkeit, dass die Aussage im State zutrifft") — keine Aufgabenbeschreibung, die "Anfrage" und "Kandidatentext" als solche benennt. Vor einer belastbaren Aussage über Jevs Grenzen müsste die Anweisung diesen Kontext explizit machen.
- **Kosten sind vernachlässigbar für diesen Use Case.** 13 Mikro-USD pro Entscheidung — bei den in AGORA üblichen Suchvolumina (Dutzende bis Hunderte Suchen pro Lauf) ökonomisch unbedeutend, verglichen mit einem LLM-Call.
- **Latenz ist der eigentliche Kompromiss.** ~290 ms median gegen ~0 ms für die reine Python-Regel ist auf einem synchronen Retrieval-Pfad spürbar, besonders wenn `local_search` mehrfach pro Report-Abschnitt aufgerufen wird. Das produktive Shadow-Wiring (`local_search_shadow.py`) ruft ohnehin nur RuleProvider auf — dieser Befund ist relevant für eine spätere `authoritative`-Aktivierung, nicht für den heutigen Zustand.
- **State-Form-Unterschied zum produktiven Pfad:** Der produktive Shadow-Aufruf in `local_search_shadow.py` sendet bewusst nur `{"top_score": ...}` (kein Klartext), weil er nur RuleProvider anspricht. Dieses Benchmark-Skript sendet für den Jev-Arm zusätzlich Query und Fakt im Klartext — notwendig, damit Jev überhaupt etwas zu bewerten hat, aber eine andere (größere) Datenexposition als der heutige Produktivpfad. Vor einer echten `shadow`- oder `authoritative`-Aktivierung mit Jev müsste `local_search_shadow.py` entsprechend erweitert und die Datenschutzfrage (Klartext-Fakten an einen externen Dienst) explizit vom Maintainer freigegeben werden — offen, siehe `jev-provider-evidence.md`, Abschnitt Datenschutz.

## Einschätzung

Für **local-search-relevance** ist Jev auf dieser kleinen Stichprobe der Keyword-Regel überlegen, zu vernachlässigbaren Kosten, aber mit einer spürbaren Latenzzunahme und einer noch ungeklärten Datenschutzfrage (Klartext-Fakten an TypeSafe). Das rechtfertigt **weitere Datenerhebung mit maintainer-geprüfter Ground Truth**, nicht sofortige Promotion — die Fallmenge ist zu klein und zu wenig divers für eine Aussage mit Unsicherheitsintervall (Akzeptanzkriterium 1 aus `benchmark-design.md`), und die Datenschutzfreigabe für Klartext-State steht aus.

**Kein Ausgang dieser Bewertung ist "Reject"** — die Ergebnisse sind ermutigend genug, um eine größere, maintainer-verifizierte Stichprobe zu rechtfertigen, sobald sie priorisiert wird.

## Bekannte Grenzen dieses Piloten

- 12 Fälle, ein einziger Lauf, keine Wiederholung (keine Varianzabschätzung über mehrere Läufe).
- Keine Kalibrationsprüfung (Brier Score, Reliability-Diagramm) — `probability_yes` wird hier nur binär bei 0,5 geschnitten, nicht auf tatsächliche Kalibrierung geprüft.
- Kein Vergleichsarm für günstiges/leistungsfähiges LLM (Vergleichsarm 3/4 aus der Spezifikation fehlt).
- Keine Failure-Injection außerhalb des bereits im Integrationstest geprüften 401-Falls (`tests/integration/test_jev_provider_integration.py`) — Timeout, 429, API-Drift nicht gezielt provoziert.
- Latenz nur als Einzelwerte, nicht unter realistischer Nebenlast gemessen.
