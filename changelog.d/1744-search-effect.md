### Added

- Im Modus `AGORA_DECISION_LAYER_MODE=authoritative` wirkt das
  Relevanz-Verdikt des Decision Layers jetzt tatsächlich auf
  `local_search`: ist der bestbewertete Treffer laut Jev/Rule-Rückfall
  irrelevant (`probability_yes < 0.5`), entfernt `local_search` genau
  diese Kante samt Fakt. Eine erschöpfte Fallback-Kette
  (`provider="unresolved"`, kein `probability_yes`) ist fail-open — es
  wird nichts gefiltert. `shadow`/`disabled` bleiben byte-gleich zum
  bisherigen Verhalten.
- `GET`/`POST`-Antworten von `local_search` tragen im `authoritative`-Modus
  ein neues `relevance`-Feld (`top_fact_relevant`, `provider`,
  `probability_yes`, `fallback`) — modelliert als Pydantic-Contract
  `app/contracts/graph_relevance_contract.py::SearchRelevanceVerdict`
  statt als handgeschriebenes Dict.
