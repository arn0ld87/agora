### Added

- `AGORA_DECISION_LAYER_MODE=authoritative` ist jetzt ein nutzbarer Wert (f005,
  ADR-0016/0017) für den Use Case `local-search-relevance`:
  `local_search_relevance.py::resolve_relevance` ruft Jev (TypeSafe) als
  Primärprovider, `RuleProvider` ist Rückfall bei jeder Jev-Ausnahme, fehlendem
  API-Key oder aktiver Auth-Sperre (300 s nach einem vorherigen Auth-Fehler).
  Default bleibt `disabled`, bestehendes Verhalten ändert sich ohne explizites
  Opt-in nicht. Im `authoritative`-Modus gehen Suchanfrage und bestbewerteter
  Fakt im Klartext an TypeSafe — abgedeckt durch die Maintainer-
  Datenschutzfreigabe vom 30.09.2026 (Alexander Schneider), beschränkt auf
  genau diesen Modus mit Rule-Rückfall.
- Neuer Konfigurationswert `AGORA_JEV_TIMEOUT_S` (Default `2.0`, gültiger
  Bereich `0 < Wert <= 30`) begrenzt das Timeout-Budget eines einzelnen
  Jev-Aufrufs auf dem heißen `local_search`-Retrievalpfad.

### Fixed

- Scheiterte im `authoritative`-Pfad sowohl Jev als auch der anschließende
  `RuleProvider`-Rückfall, lieferte `resolve_relevance` bisher `None` —
  ununterscheidbar vom deaktivierten Modus oder einem fehlenden `top_fact`.
  Der Vertrag (`DecisionResult`) reserviert für genau diesen Fall
  `provider="unresolved"`; dieser Zustand wird jetzt tatsächlich
  zurückgegeben, mit der durchlaufenen Fallback-Kette `["jev", "rule"]`.
  Aufrufer verwerfen das Ergebnis dieses Moduls aktuell ohnehin noch
  (lokale Suche filtert nicht danach), die Telemetrie war aber bisher
  irreführend.
- Die gemeldete `latency_ms` auf dem Rückfallpfad (Jev scheitert, Rule
  übernimmt) kam bisher ausschließlich aus `RuleProvider` und maß damit nur
  die quasi-instantane Regelausführung, nicht die tatsächlich verstrichene
  Zeit inklusive des vorangegangenen Jev-Versuchs. Beide Rückfallpfade
  (Rule-Erfolg wie Rule-Scheitern) melden jetzt die Gesamtdauer seit Beginn
  des authoritative-Versuchs.
