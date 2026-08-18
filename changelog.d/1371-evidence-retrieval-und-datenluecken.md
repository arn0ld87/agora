### Behoben

- Numerische Evidence wird deterministisch gefunden. Eine Quelle, die dieselbe
  Zahl in derselben Einheit nennt, ist Kandidat, auch wenn ihr Embedding-Score
  unter der Retrieval-Schwelle liegt. Ob sie den Claim belegt, entscheidet
  unverändert das Entailment.
- Absolutzahlen mit Adjektiv ("38 abweichende Dringlichkeitsfälle") werden
  überhaupt erst als Fakt erkannt.
- Eine gescheiterte Evidence-Bindung wird nicht mehr als Datenlücke exportiert.
  Als Data Gap gilt nur noch, wozu in keiner verfügbaren Quelle etwas steht.

### Neu

- `evidence_coverage_ledger` in der Evidence-Map: für jeden quantitativen
  Tool-Fakt entweder eine kanonische Evidence-ID oder ein Verwerfungsgrund.
  Additiv mit Default — bestehende persistierte Maps bleiben gültig.
