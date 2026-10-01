# Jev-Rollout: Evidenz zur Freigabe von `local-search-relevance`

Stand: 30.09.2026. **Keine Freigabe für `authoritative`.** Der Maintainer hat nach dem Minimalbenchmark weitere Datenerhebung statt Promote oder Reject entschieden. Der als `auto-passed` angezeigte `jev-choice`-Gate-Status ersetzt diese Entscheidung nicht.

## Prüfbogen für Ground Truth

Quelle aller zwölf Fälle: die konstruierte Liste `_CASES` in [`backend/scripts/jev_benchmark_local_search.py`](../../backend/scripts/jev_benchmark_local_search.py). Es sind keine Beispiele aus einem echten AGORA-Graphen. `Ja` bedeutet: Der Fakt ist für die Suchanfrage thematisch relevant, unabhängig davon, ob er die Anfrage bejaht. Die Spalte „Label“ ist die bisherige Implementierer-Annahme, **keine** Maintainer-Bestätigung.

| ID | Suchanfrage | Fakt | Label | Maintainer-Prüfung |
|---|---|---|---|---|
| exact-match | Bundeskanzleramt | Das Bundeskanzleramt koordiniert die Ressortabstimmung. | Ja | offen |
| keyword-overlap | Bundesministerium Finanzen | Das Bundesministerium der Finanzen legt den Haushaltsentwurf vor. | Ja | offen |
| no-overlap | Bundeskanzleramt | Der Stadtrat von München beschließt eine neue Verkehrsordnung. | Nein | offen |
| coincidental-substring | Rat | Der Vorrat an Ersatzteilen im Lager reicht bis zum Quartalsende. | Nein | offen |
| partial-relevant | Bundestag Ausschuss | Der Ausschuss für Digitales tagte am Dienstag im Bundestag. | Ja | offen |
| different-institution | Bundeskanzleramt | Der Bayerische Landtag debattierte über die Schulreform. | Nein | offen |
| single-keyword-weak-match | Bundeskanzleramt Pressekonferenz | Die Pressekonferenz des Vereins fand im Rathaus statt. | Nein | offen |
| long-fact-relevant | Bundesministerium Digitales | Nach monatelangen Verhandlungen hat das Bundesministerium für Digitales und Verkehr ein neues Foerderprogramm fuer laendliche Breitbandanbindung vorgestellt, das ab dem naechsten Quartal gilt. | Ja | offen |
| abbreviation-mismatch | BMF | Das Bundesministerium der Finanzen veroeffentlichte den Bericht. | Ja | offen |
| negation-in-fact | Bundeskanzleramt Stellungnahme | Das Bundeskanzleramt hat bislang KEINE Stellungnahme abgegeben. | Ja | offen |
| different-topic-shared-word | Bundeskanzleramt Sicherheit | Die IT-Sicherheit des Unternehmens wurde nach einem Vorfall extern geprueft. | Nein | offen |
| multi-entity-relevant | Bundeskanzleramt Bundestag | Vertreter des Bundeskanzleramts trafen sich mit Abgeordneten im Bundestag. | Ja | offen |

Für jeden Fall ist `bestätigt`, `korrigiert` oder `unklar` mit Begründung festzuhalten. Der BMF-Fall war im ersten Lauf falsch gelabelt; der [Benchmark-Bericht](f005-jev-benchmark-local-search.md) rekonstruiert die korrigierte Quote nur rückwirkend. Rohantworten je Fall wurden nicht archiviert. Die zwölf Fälle erlauben daher keine auditierbare Qualitätsfreigabe.

## Fehlende Nachweise vor einer Promotion

1. **Repräsentativer Korpus:** Auf dem Armserver existieren im produktiven Neo4j 109 Graphen, 7.145 Entity-Knoten und 5.786 `RELATION`-Kanten mit `fact` (read-only Zählabfrage am 30.09.2026). `local_search` läuft nur als Fehler-Fallback und ist in den geprüften Container-Logs der letzten 30 Tage nicht als nutzbarer Aufruf vertreten. Die Report-Traces unter `Config.UPLOAD_FOLDER/reports/*/agent_log.jsonl` enthalten jedoch vollständige `quick_search`-Werkzeugparameter mit `graph_id` aus dem Report-Start. `quick_search` ruft `graph_reader.search_graph` mit demselben Query-String auf, der bei einem Fehler an `local_search` weitergeht. Damit sind reale Anfragen für eine retrospektive *Proxy*-Stichprobe verfügbar, aber keine beobachteten Fallback-Entscheidungen.
2. **Rohdaten und Kalibration:** Ein neuer Lauf muss je Fall Ground Truth, Rule- und Jev-Antwort, Jev-Confidence, Fehler, Latenz, Kosten, Modell-/SDK-Version und Datensatzversion nachvollziehbar erfassen. Auf dem Testteil sind mindestens Accuracy, Precision, Recall, FPR, FNR und Kalibration sowie Fallback-Rate zu berechnen; ein Threshold wird nur aus dem Kalibrationsteil abgeleitet. Der alte Bericht enthält dafür weder archivierte Rohantworten noch einen Kalibrationssplit.
3. **Datenschutzentscheidung:** Der produktive Shadow-Pfad übermittelt derzeit nur `top_score` an eine lokale Regel. Der Benchmark sendet Query und Fakt im Klartext an TypeSafe. Der Maintainer hat am 30.09.2026 die Übermittlung **minimierter Suchanfragen und Fakten für den Jev-Test** ausdrücklich erlaubt. Das ist keine Freigabe für das dauerhafte Speichern dieser Texte in Telemetrie und keine Promotion des produktiven `authoritative`-Pfads. **Nachtrag 30.09.2026:** Der Maintainer hat zusätzlich die produktive Übermittlung von Query und Top-Fakt im Klartext an TypeSafe für `local-search-relevance` im `authoritative`-Modus mit Rule-Rückfall freigegeben (Feature f001). Die Freigabe zum Speichern dieser Texte in Telemetrie bleibt ausgeschlossen: der Laufzeitpfad loggt nur Hash, Provider, Wahrscheinlichkeit, Latenz, Kosten und Fehlerklasse.
4. **Betriebsgrenzen:** Ein späteres Freigabepaket braucht die pro Use Case gemessene Aufrufzahl, Latenzverteilung, Kosten-/Budgetbuchung, Ausfall- und Fallback-Tests sowie einen Rückschaltpfad. Der bisherige Lauf misst nur zwölf Einzelaufrufe; Jev-Kosten werden im Run-Budget-Ledger noch nicht gebucht.

**Entscheidungsstand:** Weitere Evidenz sammeln. Die Testdatenübermittlung ist freigegeben und ein begrenzter realer Probelauf wurde durchgeführt; geprüfte Labels und Kalibration fehlen weiter. `promote-cases`, `wire-fallbacks` und produktive Jev-Telemetrie bleiben offen, bis diese Nachweise vorliegen und der Maintainer eine bewusste Promotion-Entscheidung trifft.

## Retrospektive Stichprobe aus echten Report-Suchen

`backend/scripts/jev_rollout_corpus.py` liest die Traces und den produktiven Graphen nur lesend. Es bildet je echter `quick_search`-Anfrage genau die Kante mit dem höchsten lokalen Keyword-Score ab; Query, Fakt und Kanten-ID stammen damit aus demselben Graphen. Es verwirft leere Treffer, sehr lange Texte sowie offensichtliche URLs, E-Mail-Adressen und telefonnummerähnliche Muster. Diese Musterprüfung erkennt **nicht** jede personenbezogene Angabe und ersetzt keine manuelle Sichtung vor Drittanbieteraufrufen.

Am 30.09.2026: 172 Anfragen aus 42 Reports zu 26 Graphen; 166 Anfragen haben einen Keyword-Kandidaten, vier Paare wurden danach vom Längen-/Musterfilter ausgeschlossen. Aus 162 geeigneten Paaren wurden deterministisch 30 Fälle aus 19 Graphen ausgewählt (maximal zwei pro Graph). Die unlabelte Stichprobe liegt ausschließlich lokal unter `.pandaos/logs/jev-rollout-corpus.private.json` (Git-ignore, Dateimodus `0600`). Der Skript-Default gibt nur Zählwerte aus; Rohtexte erfordern `--emit-private-json`.

### Begrenzter Jev-Probelauf auf der realen Stichprobe

`backend/scripts/jev_rollout_probe.py` hat am 30.09.2026 genau diese 30 Fälle mit dem bestehenden `JevDecisionProvider`, `typesafe-sdk` 0.7.0 und dem gepinnten Modell `jev-1.13.0` an TypeSafe übermittelt. Der Aufruf verwendete ausschließlich den temporär aus Vaultwarden geladenen Test-Key; der produktive Provider-Secret-Store blieb unverändert. Eingabe-Hash (SHA-256): `5a5ea018946e04edbd3fc1c1e65b99e98836c24d29c99696a91a6f945a3a89f8`. Die einzelnen Antworten und Request-IDs liegen Git-ignoriert unter `.pandaos/logs/jev-rollout-probe.private.json` (Dateimodus `0600`); weder Datei noch Konsole enthalten Query- oder Fakttexte.

Alle 30 Aufrufe waren erfolgreich. Die bestehende `PricingRegistry` bezifferte anhand der gemeldeten Token-Nutzung jeden Aufruf: insgesamt 463 Mikro-USD, bei 30 Aufrufen also 15,43 Mikro-USD im Mittel. Die beobachtete Latenz lag bei p50 252 ms, p95 309 ms und Maximum 576 ms (p99 nach nearest-rank ebenfalls 576 ms; 30 Einzelaufrufe sind keine Last- oder SLO-Messung). Jev gab 25-mal eine Relevanzwahrscheinlichkeit ab 0,5 und fünfmal darunter zurück. Die Keyword-Regel stuft bei diesem **vorselektierten** Korpus alle 30 Fälle als relevant ein, weil die Auswahl einen positiven Keyword-Treffer voraussetzt. Die fünf abweichenden Fall-IDs stehen in der privaten Ergebnisdatei und sollten bei der manuellen Prüfung zuerst angesehen werden.

Alle 30 `expected_relevant`-Felder sind offen. Es gibt daher **keine gemessene Accuracy, Precision, Recall, FPR, FNR oder Kalibration**. Selbst nach Labeln ist diese nur aus Keyword-Treffern gezogene Proxy-Stichprobe keine unabhängige, repräsentative Kalibrations- und Testmenge. Vor einer Promotion sind maintainer-geprüfte Labels, auch für geeignete Negativ-/Grenzfälle, ein getrenntes Testset, Kalibrationsprüfung, Budgetbuchung und eine ausdrückliche Use-Case-Freigabe erforderlich.

### Explorative KI-Vorbewertung, ausdrücklich keine Ground Truth

Auf Wunsch des Maintainers wurden die 30 privaten Fälle ohne Sicht auf die Jev-Wahrscheinlichkeiten vorbewertet: 15 `ja`, 12 `nein`, 3 `unklar`. Rubrik: Der Fakt muss mindestens einen angefragten Sachpunkt stützen; ein gemeinsamer Projektname allein genügt nicht. Die Tabelle `.pandaos/logs/jev-rollout-labels.private.csv` hält pro Fall die Begründung und `review_status=assistant_provisional` fest. Der Originalkorpus behält `expected_relevant=null`.

`backend/scripts/jev_rollout_eval.py` vergleicht Korpus-Hash, Fall-IDs, Texte, Keyword-Scores und Jev-Wahrscheinlichkeiten vor der Auswertung. Ohne Maintainer-Bestätigung verweigert es die normale Ausführung; `--exploratory` weist immer `promotion_eligible=false` aus. Für die 27 nicht als unklar markierten KI-Vorschläge ergibt sich bei Schwelle 0,5: Jev 14 richtig positive, 4 richtig negative, 8 falsch positive und 1 falsch negativer Fall; die bestehende Keyword-Regel hat 15 richtig positive und 12 falsch positive Fälle. Diese Zahlen sind **nur eine Fehlersuchhilfe**, keine unabhängige Qualitätsmessung. Der Korpus ist auf positive Keyword-Treffer vorselektiert und besitzt weder Kalibrations- noch Holdout-Teil.

Reproduktion ausschließlich lokal, ohne API-Aufruf: `cd backend && uv run python scripts/jev_rollout_eval.py ../.pandaos/logs/jev-rollout-corpus.private.json ../.pandaos/logs/jev-rollout-labels.private.csv ../.pandaos/logs/jev-rollout-probe.private.json --exploratory`.

Auch der Laufzeitpfad ist noch nicht bereit: `local_search_shadow.py` sendet gegenwärtig ausschließlich `top_score` an eine lokale Regel. Ein sinnvoller Jev-Aufruf müsste Query und Fakt übertragen. Die Maintainer-Zustimmung vom 30.09.2026 galt dem begrenzten Test; ein dauerhafter produktiver Datentransfer, Budgetbuchung und die Prüfung externer SDK-Fehlermeldungen im Log sind offen. Der `authoritative`-Modus bleibt gesperrt.

**Stand f001 (01.10.2026):** Der Maintainer hat entschieden, Jev für `local-search-relevance` trotz der oben offenen Labels und Kalibration `authoritative` zu schalten. `local_search_shadow.py` ist durch `local_search_relevance.py::resolve_relevance` ersetzt: im `authoritative`-Modus sendet es `{assertion, query, fact}` an Jev (Timeout `AGORA_JEV_TIMEOUT_S`, Default 2 s, höchstens ein Retry) und fällt bei fehlendem Key, Auth-Sperre (5 min) oder jeder Ausnahme auf die Regel zurück. SDK-Ausnahmen werden nur mit Klassenname und Request-ID geloggt. Budgetbuchung und die Wirkung des Verdikts auf die Suchtreffer folgen in eigenen Slices; bis dahin verändert der Modus die Suchergebnisse nicht.
