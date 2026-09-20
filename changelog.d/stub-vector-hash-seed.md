### Fixed

- `EmbeddingService._stub_vector` (Stub-Modus, `AGORA_E2E_LLM_MODE=stub`) hat den
  Vektor aus Pythons eingebautem `hash(text)` gebildet, obwohl `hash()` für Strings
  per `PYTHONHASHSEED` prozessweise randomisiert ist — ein Schutz gegen
  Hash-Flooding, kein deterministischer Wert. Der Docstring behauptete trotzdem
  Determinismus und dass jeder Text einen einzigartigen Vektor liefert. Beides war
  falsch: erstens war der Vektor zwischen Prozessen nicht reproduzierbar, zweitens
  kollidierten zwei unterschiedliche Texte, sobald ihre Hashes zufällig modulo 1000
  übereinstimmten (rund 1:1000 pro Textpaar und Prozesslauf). Genau das hat
  `test_stub_embed_different_texts_produce_different_vectors` in CI-Lauf
  35496474317 rot gemacht, während ein Re-Run desselben Codes grün war — der Test
  war also auf jedem Branch ein echter Flake, keine Regression im geänderten Code.
  Die Vektorbildung nutzt jetzt einen stabilen Byte-Hash (`hashlib.blake2b` über die
  UTF-8-Bytes des Texts) statt `hash()`. Formel, Dimension und L2-Normierung bleiben
  unverändert; Kollisionen bei `% 1000` sind weiterhin möglich, aber jetzt für einen
  gegebenen Text stabil und nicht mehr vom zufälligen Prozess-Seed abhängig. Der
  Docstring beschreibt Determinismus jetzt korrekt und nennt den Grund für
  `blake2b` statt `hash()`.
