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

1. **Repräsentativer Korpus:** Der Worktree enthält nur synthetische Fälle. Auf dem Armserver existieren im produktiven Neo4j 109 Graphen, 7.145 Entity-Knoten und 5.786 `RELATION`-Kanten; alle 5.786 Kanten haben ein `fact`-Feld (read-only Zählabfrage am 30.09.2026). Reale Fakten sind damit vorhanden. Echte Anfragen für *diesen* Use Case sind noch nicht als Korpus verfügbar: `local_search` läuft nur als Fallback bei einem Fehler der regulären Graphsuche (`graph_reader.py`), und die geprüften Container-Logs der letzten 30 Tage enthielten keinen `Using local search`-Eintrag. Der Code loggt Suchanfragen zudem nur gekürzt (`query[:30]` beziehungsweise `query[:50]`). Für eine belastbare Bewertung müssen echte Suchaufrufe künftig gezielt und minimiert erfasst, mit Graph-Fakten gepaart und mit Herkunft, Auswahlverfahren, getrennten Kalibrations-/Testfällen sowie maintainer-geprüften Labels versehen werden. Aus Entity-Namen erzeugte Testqueries wären hilfreich als Zusatzfälle, aber kein Ersatz für echte Suchanfragen.
2. **Rohdaten und Kalibration:** Ein neuer Lauf muss je Fall Ground Truth, Rule- und Jev-Antwort, Jev-Confidence, Fehler, Latenz, Kosten, Modell-/SDK-Version und Datensatzversion nachvollziehbar erfassen. Auf dem Testteil sind mindestens Accuracy, Precision, Recall, FPR, FNR und Kalibration sowie Fallback-Rate zu berechnen; ein Threshold wird nur aus dem Kalibrationsteil abgeleitet. Der alte Bericht enthält dafür weder archivierte Rohantworten noch einen Kalibrationssplit.
3. **Datenschutzentscheidung:** Der produktive Shadow-Pfad übermittelt derzeit nur `top_score` an eine lokale Regel. Der Benchmark sendet Query und Fakt im Klartext an TypeSafe. Der Maintainer hat am 30.09.2026 die Übermittlung **minimierter Suchanfragen und Fakten für den Jev-Test** ausdrücklich erlaubt. Das ist keine Freigabe für das dauerhafte Speichern dieser Texte in Telemetrie und keine Promotion des produktiven `authoritative`-Pfads.
4. **Betriebsgrenzen:** Ein späteres Freigabepaket braucht die pro Use Case gemessene Aufrufzahl, Latenzverteilung, Kosten-/Budgetbuchung, Ausfall- und Fallback-Tests sowie einen Rückschaltpfad. Der bisherige Lauf misst nur zwölf Einzelaufrufe; Jev-Kosten werden im Run-Budget-Ledger noch nicht gebucht.

**Entscheidungsstand:** Weitere Evidenz sammeln. Die Testdatenübermittlung ist freigegeben; reale Suchanfragen, geprüfte Labels und Kalibration fehlen weiter. `promote-cases`, `wire-fallbacks` und produktive Jev-Telemetrie bleiben offen, bis diese Nachweise vorliegen und der Maintainer eine bewusste Promotion-Entscheidung trifft.
