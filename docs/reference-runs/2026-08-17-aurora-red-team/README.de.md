# Referenzlauf 7 — AURORA-Entscheidungsreport mit Red-Team-Review

**Datum:** 17.08.2026  
**Simulation:** `sim_c2108c7f543e` (24 von 24 Runden abgeschlossen)  
**Report:** `report_b259e254ee3f` (Modus `balanced`, ReportV3-Schema 4)  
**Szenario:** fiktiver Städtischer Klinikverbund Falkenbrück / AURORA (`Nexora Triage Assist`)

Dieser Referenzlauf bewertet dieselbe Entscheidungsfrage wie Referenzlauf 6: Soll ein KI-gestütztes Triage- und Dokumentationssystem gleichzeitig an zwei Klinikstandorten produktiv gehen, zunächst gestaffelt in Falkenbrück-Mitte starten oder verschoben werden.

Anders als Referenzlauf 6 ist dies **kein Same-Simulation-Vergleich**. Der Lauf nutzt eine neue Simulation über 24 Runden und einen erweiterten Report mit sieben statt sechs Abschnitten. Er ist deshalb keine isolierte Reporter-Regression, sondern die aktuelle Referenz für zwei neue Pipeline-Stufen: das nachgeschaltete Red-Team-Review und das aktive Umleiten ungedeckter Faktenaussagen in den Hypothesen-Slot.

## Kennzahlen

| Kennzahl | Wert |
|---|---|
| Reportlaufzeit | 16:46 min (15:21:42 bis 15:38:28), zusätzlich 13 s Red-Team-Review |
| Reportabschnitte | 7: Kurzfazit, Vergleichsdimensionen, Bewertung je Variante, Unterschiede in den Reaktionsmustern, Abwägung, Unsicherheiten und Datenlücken, Handlungsempfehlung |
| Reporttext | 3.926 Wörter, 24 markierte Persona-O-Töne (2–4 je Abschnitt) |
| Evidenzdatensätze | 116 |
| Agenteninterviews | `interview_agents` in allen 7 Abschnitten, 6–8 Personas je Abschnitt, je 5 Fragen, 49 Antworten aus 43 Agentenprofilen |
| Claims | 29, jeder mit mindestens einem Evidenzbezug (40 Bezüge insgesamt, 1–5 je Claim) |
| Confidence | 29 von 29 `low`, Scope durchgängig `simulation_consensus`, Basis `persona` |
| Hypothesen | 136 |
| Data Gaps | 126, sämtlich Severity `medium` |
| Red-Team-Befunde | 9 (Intent `comparison`, Echo-Index 0,703) |
| Gating-Eingriffe | 10 ungedeckte Faktenaussagen aus dem Fließtext entfernt und als Hypothese geführt (Abschnitte 1, 2, 3, 6, 7) |
| Export-IDs | abschnittsqualifiziert und kollisionsfrei: 29/29 Claims, 126/126 Data Gaps, 136/136 Hypothesen |

## Was der Lauf zeigt

- **Red-Team-Review als eigene Pipeline-Stufe.** Nach dem Report läuft ein separater Review-Durchgang (`gpt-5.6-luna`, 12,96 s) und liefert 9 Befunde: unaufgelöste Spannungen zwischen Abschnitten, unbelegte Wirkungsbehauptungen und fehlende Gegenpositionen einzelner Stakeholdergruppen. Der Echo-Index von 0,703 quantifiziert, wie stark der Report die Eingabeformulierungen wiederholt.
- **Der Export-Fix aus [#1340](https://github.com/arn0ld87/agora/issues/1340), [#1341](https://github.com/arn0ld87/agora/issues/1341) und [#1342](https://github.com/arn0ld87/agora/issues/1342) ist im Artefakt belegt.** Die 9 Befunde und die Modellzuordnung der Review-Stufe überleben den Neuaufbau des ReportV3-Artefakts, statt beim zweiten Schreibpfad auf eine leere Liste zurückzufallen. Claims (`C1_01`), Datenlücken (`G1_01`) und Hypothesen (`H1_01`) tragen abschnittsqualifizierte IDs; alle 29, 126 und 136 Einträge sind eindeutig auflösbar.
- **Ungedeckte Präzision wird umgeleitet, nicht nur abgeschwächt.** In fünf von sieben Abschnitten wurden insgesamt 10 Faktenaussagen aus dem Fließtext entfernt und als Hypothese weitergeführt.
- **O-Ton-Anker sind auflösbar.** Alle 24 Persona-O-Töne verweisen auf eine konkrete `ev_`-ID im Evidence-Index; generische `seed_doc:…#chunk:0`-Anker treten in den Zitaten nicht mehr auf. Das war eine ausdrückliche Regressionserwartung aus Referenzlauf 6.
- **Vier Evidenzarten gemischt.** Der Report zieht Simulationsstimmen, Seed-Korpus, Graphrelationen und Agentenaktionen nebeneinander heran statt überwiegend Dokumentabrufe.
- **Ausdrückliche Vergleichsstruktur.** Der Report bewertet vier Varianten getrennt und empfiehlt einen **reversiblen Pilotbetrieb ausschließlich in Falkenbrück-Mitte**, gebunden an sieben benannte Nachweise vor der Freigabe, mit Verschiebung des gesamten Produktivstarts als Rückfalloption.

## Evidenzbindung

| Evidenzart | Datensätze | an Claims gebunden |
|---|---:|---:|
| `agent_quote` (Interviewantworten) | 49 | 7 |
| `seed_corpus` (Seed-Dokumente) | 31 | 17 |
| `graph_relation` (Graphrelationen) | 28 | 0 |
| `agent_action` (Simulationsaktionen) | 8 | 0 |
| **Summe** | **116** | **24** |

92 der 116 Evidenzdatensätze werden erhoben, im Artefakt persistiert und im Evidence Inspector angezeigt, tragen aber keinen Claim. Graphrelationen und Simulationsaktionen sind vollständig ungebunden. Der Simulationsanteil der validierten Claims liegt entsprechend bei 10,34 Prozent (3 von 29 Claims mit Simulationsevidenz).

## Warum dies ein Referenzlauf und keine Hochglanz-Demo ist

Im Artefakt sichtbare Grenzen:

- **Confidence differenziert nicht.** Alle 29 Claims tragen `low`, auch wenn mehrere Stakeholdergruppen dieselbe Aussage stützen. Die Hochstufung über Stakeholdergrenzen greift in diesem Lauf an keiner Stelle.
- **Interview- und Graphevidenz bleibt überwiegend ungebunden.** 42 der 49 Interviewantworten und alle 36 Graph- und Aktionsdatensätze sind an keinen Claim gebunden.
- **Data-Gap-Severity ist konstant.** 126 von 126 Lücken sind `medium`; eine Priorisierung ist daraus nicht ableitbar.
- **Hypothesenvolumen übersteigt die Claim-Basis deutlich.** 136 Hypothesen bei 29 Claims und 3.926 Wörtern Reporttext; ein Teil davon ist redundant.
- **Herkunftsfelder sind lückenhaft.** 85 der 116 Evidenzdatensätze haben keinen `source_id_anchor`, einer trägt weiterhin einen generischen `#chunk:0`-Anker. `source_model` ist bei allen 116 Datensätzen leer; `model_attribution` ist ausschließlich für die Red-Team-Stufe gesetzt.
- **Laufzeit ist gegenüber Referenzlauf 6 gestiegen** (16:46 min statt 8:19 min). Ursachen sind der siebte Abschnitt, Interviews in jedem Abschnitt und das Postprocessing je Abschnitt, dessen Claim-Extraktion und Evidenzbindung zwischen 14 und 59 Sekunden benötigt. Ein direkter Reporter-Vergleich mit Referenzlauf 6 ist wegen der anderen Simulation nicht zulässig.

Das Repository enthält **nicht** alle Artefakte und Replay-Daten, die für eine Reproduktion dieses Laufs aus einem frischen Checkout nötig wären. Er ist damit eine **beobachtbare Regressionreferenz, kein vollständig reproduzierbarer Golden Run**.

## Regressionserwartungen

Künftige Pipeline-Änderungen sollten gegen diesen Lauf mindestens prüfen:

1. Persona-O-Töne verweisen weiterhin ausnahmslos auf auflösbare `ev_`-IDs, nie auf generische Seed-Anker.
2. Von mehreren Stakeholdergruppen getragene Aussagen erhalten nicht pauschal `low` Confidence.
3. Die Bindungsquote steigt: Interviewantworten, Graphrelationen und Simulationsaktionen dürfen nicht als ungebundene Bestände auflaufen.
4. Data Gaps werden nach Severity differenziert statt vollständig als `medium` geführt.
5. Das Hypothesenvolumen bleibt gegenüber der Claim-Basis begründbar; Dubletten werden zusammengeführt.
6. `source_id_anchor` und `source_model` sind je Evidenzdatensatz gesetzt, `model_attribution` deckt alle beteiligten Stufen ab, nicht nur das Red-Team-Review.
7. Das Red-Team-Review bleibt eine eigene Stufe mit Befundliste und Echo-Index und wird nicht in die Abschnittsgenerierung zurückgefaltet.

[English version](./README.md)
