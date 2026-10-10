# ADR-0022: Manuelle Herkunft im Wissensgraphen

- Status: Angenommen (2026-10-07, mit dem Merge von Etappe 8, [PR #1812](https://github.com/arn0ld87/agora/pull/1812) — so definiert der ADR selbst die Annahme)
- Datum: 2026-10-07
- Bezug: [#1808](https://github.com/arn0ld87/agora/issues/1808) (Etappe 8, Graphen bearbeiten), [#1790](https://github.com/arn0ld87/agora/issues/1790) (Frontend-Umbau), [ADR-0002](0002-evidence-gating.md), [ADR-0011](0011-evidence-entailment-and-provenance.md), [ADR-0013](0013-seed-corpus-document-anchor.md); Bauplan [`docs/plans/active/frontend-umbau.md`](../plans/active/frontend-umbau.md) §4.3, §7.1, §7.2

## Kontext

Etappe 8 erlaubt, Entitäten und Beziehungen eines Graphen in der Bibliothek von Hand anzulegen, zu ändern, zu löschen und zusammenzuführen. Eine Handeingabe hat keine Quelle im Dokument. Ohne Regel könnte der Bericht sie wie belegtes Wissen zitieren.

Dazu kommt eine Lücke im Bestand. Die Provenance einer Beziehung hängt an ihren `episode_ids` (`backend/app/storage/neo4j_write.py` setzt sie beim Anlegen der Kante; `_resolve_edge_provenance` in `backend/app/services/graph/graph_reader.py` löst sie über `get_episode_provenance` zu `(document_id, chunk_id)` auf). Ändert man den Text einer Beziehung, bleibt dieser Verweis bestehen. Der Bericht würde den geänderten Satz weiter mit Dokumentanker (`seed_doc:<document_id>#chunk:<chunk_id>`) liefern, und er würde als `seed_corpus` einsortiert (`_TYPE_TO_SOURCE_KIND` in `backend/app/services/report_agent/evidence.py`). Ein Dokumentanker für Text, den das Dokument nie enthielt, ist genau die vorgetäuschte Prüfbarkeit, die ADR-0013 ausschließen will.

Stand des Codes, auf den sich diese Entscheidung bezieht:

- `EvidenceSourceKind` (`backend/app/contracts/report_contract.py`) kennt `seed_corpus`, `agent_quote`, `agent_action`, `graph_relation`, `web_source`, `inferred`. Graph-Fakten ohne Dokumentbezug werden zu `graph_relation`.
- `cross_stakeholder_for_high` verlangt für `high` und `verified` unterstützende `agent_quote`-Evidence aus mindestens zwei Rollenfamilien. `agent_grounded_for_medium` verlangt für `medium` mindestens eine `agent_quote` mit Zitat und eine `seed_corpus`. `graph_relation` trägt damit schon heute weder `high` noch `medium` allein.
- Ein optionales Feld `document_role` steht am Evidence-Record neben `source_kind`.
- `MERGE` für Entität (`graph_id`, `name_lower`, `entity_type`), Beziehung (`uuid`) und Episode (`uuid`) liegt in `backend/app/storage/neo4j_write.py`. Es gibt kein Herkunftsmerkmal an Knoten oder Kanten.

## Entscheidung

### 1. Herkunft am Graphen

Entitäten und Beziehungen tragen ein Herkunftsmerkmal mit drei Zuständen:

| Zustand | Bedeutung | Merkmal |
|---|---|---|
| extrahiert | aus Dokumenten erzeugt (Bestand) | kein neues Merkmal nötig |
| manuell | von Hand angelegt | Markierung und Zeitpunkt |
| bearbeitet | extrahiert, danach von Hand geändert | Markierung und Zeitpunkt |

Altgraphen werden nicht nachgerüstet; ein fehlendes Merkmal bedeutet „extrahiert“. Episoden bleiben unverändert. ADR-0013 §3 gilt weiter: Es wird nichts geraten und nichts nachträglich verankert.

### 2. Kein Dokumentanker für Handarbeit

Eine manuelle Beziehung hat keine Episoden und damit keinen Anker. Eine bearbeitete Beziehung behält ihre Episoden zur Anzeige („ursprünglich aus Dokument X“), liefert aber **keinen** Dokumentanker mehr an den Bericht: Die Anker-Auflösung im Graph-Leser (`_resolve_edge_provenance`) verweigert ihn. Damit kann geänderter Text nie als `seed_corpus` erscheinen. Das ist eine Verschärfung von ADR-0013, keine Lockerung. Der Fakt bleibt `graph_relation`, wie jeder Graph-Fakt ohne verifizierten Anker.

### 3. Sichtbarkeit im Evidence-Record

Evidence aus manuellen oder bearbeiteten Graph-Elementen trägt ein **eigenes Feld** am Evidence-Record. Arbeitsname: `graph_origin` mit den Werten `manual` und `edited`. Vorbild ist `document_role`, das ebenfalls neben `source_kind` steht. Das Feld ist optional; fehlt es, gilt die Evidence als nicht von Hand erzeugt.

`source_kind` bleibt `graph_relation`. **`EvidenceSourceKind` wird nicht erweitert.** Anker 3 aus ADR-0002 bleibt unverändert, ein Eintrag in [`0002-supersedes.md`](0002-supersedes.md) ist nicht nötig.

### 4. Wirkung auf die Confidence

Manuelle und bearbeitete Graph-Evidence **zählt für keine Confidence-Stufe**. Sie ist im Bericht sichtbar, wird aber bei der Prüfung, ob ein Claim `high` oder `medium` tragen darf, und bei der Gewichtung nicht mitgezählt.

- Ein Claim darf `high` behalten, wenn er die bestehenden Regeln auch ohne diese Evidence erfüllt.
- Ein Claim, dessen Evidence ausschließlich manuell oder bearbeitet ist, kann nie `high` oder `medium` erhalten.

Umgesetzt wird das als **zusätzlicher** Validator auf `ReportClaimModel` und in der Confidence-Berechnung. `cross_stakeholder_for_high` und `reject_inferred_in_high_confidence` (Anker 4 und 5) bleiben textlich unverändert.

Einordnung: `graph_relation` trägt, wie oben beschrieben, schon heute weder `high` noch `medium` allein, weil beide Stufen `agent_quote` verlangen. Die neue Regel schreibt das für manuelle Evidence ausdrücklich fest und schließt die Lücke bei der Gewichtung, in der eine Handeingabe sonst wie ein extrahierter Graph-Fakt mitgezählt würde.

### 5. Darstellung

Manuelle Herkunft ist an drei Stellen sichtbar:

- im Graphen: Marke „manuell“ und gestrichelte Kante; „bearbeitet“ mit Verweis auf die ursprüngliche Quelle,
- in der Belegspalte des Berichts,
- im Export.

### 6. Sperre

Ein Graph ist gesperrt, sobald eine Simulation sein Projekt oder seine `graph_id` verwendet. Die Sperre wird aus dem Bestand abgeleitet (kein eigenes Feld) und serverseitig bei jedem Schreibzugriff durchgesetzt, auch bei den bestehenden Endpunkten zum Löschen und Zurücksetzen (HTTP 409). Bearbeitet wird eine Kopie (Duplizieren).

Folge: Der Graph, auf dem ein Bericht beruht, ändert sich nach dem Lauf nicht mehr.

## Die fünf Hartanker aus ADR-0002

| # | Anker | Stand | Begründung |
|---|---|---|---|
| 1 | `<evidence_gating priority="hard">`-Block in `backend/app/services/report_prompts/sections.py` | unberührt | Die Regel wirkt im Contract und in der Confidence-Berechnung, nicht im Prompt; kein Prompt-Text ändert sich. |
| 2 | Hedge-Snapshot `backend/tests/eval/snapshots/evidence-gating-hedge-words.txt` | unberührt | Es ändert sich kein Wortlaut und keine Hedge-Regel. |
| 3 | Enum `EvidenceSourceKind` | unberührt | Die Herkunft steht in einem eigenen Feld; das Enum bekommt keinen neuen Wert. |
| 4 | Validator `cross_stakeholder_for_high` | unberührt | Er bleibt textlich gleich; die neue Regel ist ein zusätzlicher Validator und lockert die Zwei-Gruppen-Schwelle nicht. |
| 5 | Validator `reject_inferred_in_high_confidence` | unberührt | Er bleibt textlich gleich; manuelle Evidence wird gerade nicht als `inferred` geführt (siehe Verworfene Alternativen b). |

## Konsequenzen

- Neue Eigenschaften an Knoten und Kanten in Neo4j, ohne Migration des Bestands. Der Eintrag in `docs/runbooks/upgrade.md` folgt mit dem Code (Änderung an Persistenz).
- Neues optionales Feld im Evidence-Vertrag samt JSON-Schema und Zod-Spiegel (`dump_schemas` im selben Commit). Nach ADR-0021 ist ein neues optionales Antwortfeld nicht Breaking.
- Ein zusätzlicher Validator auf `ReportClaimModel` und eine Anpassung der Confidence-Berechnung. Das Ausweisen im Bericht muss dem Downgrade-Muster folgen (sichtbar, nie still), damit ein Claim nicht den ganzen Bericht abbricht.
- Regressionstests: „manueller Fakt stützt keine hohe Confidence“ und „bearbeitete Kante liefert keinen Dokumentanker“.
- Prüfung durch `agora-evidence-auditor-m3` vor dem Merge der Etappe.
- Schreibende Endpunkte des Graphen prüfen die Sperre serverseitig; das betrifft auch die vorhandenen Endpunkte zum Löschen und Zurücksetzen.

## Verworfene Alternativen

**(a) Neuer Wert `graph_manual` in `EvidenceSourceKind`.** Ändert Anker 3 und die festgeschriebenen Tests, braucht einen Eintrag in `0002-supersedes.md` und bietet keinen zusätzlichen Schutz gegenüber dem eigenen Feld.

**(b) Einordnung als `inferred`.** Der vorhandene Validator würde `high` sperren, aber der Bericht zeigte Handeingaben als „abgeleitet“ und vermischte sie mit LLM-Ableitungen. Außerdem sperrt es `high` auch für Claims, die ohne die Handeingabe belegt wären.

**(c) Extrahierte Elemente unveränderlich lassen.** Kleinster Schnitt, widerspricht aber dem Entwurf von Etappe 8.

**(d) Sperre als Projektfeld.** Ein zweiter Zustand, der vom tatsächlichen Gebrauch abweichen kann. Abgeleitet aus dem Bestand kann er das nicht.

## Offene Punkte

- **Zusammenführen zweier Entitäten mit unterschiedlicher Herkunft:** Das Ergebnis gilt als „bearbeitet“. Offen ist, ob die Herkunft der beiden Ausgangsentitäten sichtbar bleiben muss.
- **Gleichzeitige Änderungen:** Das Verhalten bei zwei gleichzeitigen Schreibzugriffen auf denselben Graphen (letzte Änderung gewinnt oder Konflikt) ist nicht entschieden.
