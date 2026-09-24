# Section-ReACT: Evidence-Deckung statt Tool-Call-Mindestzahl (#1294)

Der Section-ReACT-Loop wies einen fertigen Abschnittsentwurf zurück, solange
weniger als `min_tool_calls` (zuletzt 1) Werkzeugaufrufe gezählt waren. Ein
ergebnisloser Aufruf erfüllte die Schwelle, ein bereits belegter Entwurf ohne
Aufruf erfüllte sie nie.

Die Entscheidung trifft jetzt `report_agent/section_coverage.py` gegen den
Pool, an den der Abschnitt danach gebunden wird: Gedeckt ist ein Entwurf, wenn
das Retrieval des Abschnitts bindbare Evidence registriert hat oder jede
prüfbare Aussage thematisch in den vorab geladenen `global_evidence_refs`
vorkommt (`data_gap.topic_present_in_pool`, dieselbe Schwelle wie
`classify_claim_gap`, aber ohne dessen Zahlen-Kurzschluss). Geprüft werden
dieselben Einheiten, die der Binder später bindet (inklusive
`split_claim_chunks`); ein Entwurf ohne prüfbare Aussage ist nie gedeckt. Bei einer
Lücke fordert der Loop wie bisher gezielt Retrieval nach; die Hinweistexte
sprechen jetzt von einer Deckungslücke statt von einer Mindestzahl.

Erschöpft der Loop seine Iterationen, bleibt ein gültiger, nur mangels
Deckung zurückgewiesener Entwurf stehen. Vorher ersetzte die erzwungene
Endgenerierung ihn, und eine leere Antwort machte aus einem brauchbaren
Abschnitt den Fehlertext. Der Abschnitt bleibt als `forced_final` markiert.

Nachgelagerte Gates (Bindung, Entailment, Fließtext-Faktenprüfung) laufen
unverändert über jeden Claim.
