### Added

- Der `authoritative`-Pfad von `local-search-relevance` prüft jetzt — wenn
  eine `run_id` vorliegt — vor jedem Jev-Call das Run-Budget
  (`RunBudgetEnforcer`) und bucht jeden Call (Erfolg wie Fehlschlag) ins
  Run-Usage-Ledger. Ein erschöpftes hartes Budget überspringt Jev und fällt
  direkt auf `RuleProvider` zurück (`fallback_reason=budget_exhausted`).
- Neuer Contract `app/contracts/llm_call_event_contract.py::LlmCallEvent`
  modelliert die Zeilen von `llm_call_events.jsonl` (u. a. das neue Feld
  `reported_cost_micros`), statt sie als handgeschriebenes Dict zu
  schreiben. Validiert wird die Schreibseite; die bewusst tolerante
  Leseseite (`run_usage_ledger.py`) bleibt unverändert.

### Fixed

- Ein fehlgeschlagener Jev-Call (Timeout, Auth-Fehler, SDK-Exception)
  schrieb bisher kein Ledger-Event. Da `llm_calls` ausdrücklich auch
  Fehlschläge mitzählen soll, ließ sich ein hartes `max_llm_calls`-Budget
  dadurch durch wiederholt scheiternde Jev-Calls umgehen. Fehlgeschlagene
  Attempts werden jetzt mit `success=False` und ehrlich unbekannten
  Kosten-/Token-Feldern gebucht.
- Im Erfolgsfall wurde die Budget-Reservierung freigegeben, **bevor** der
  Call ins Ledger geschrieben war — die anschließende Weich-Limit-Prüfung
  (`record_after_call`) sah den Ledger-Stand damit ohne genau den Call, der
  das Limit gerade erreicht hatte, und eine fällige Warnung konnte für
  diesen Call ausbleiben. Verbuchen läuft jetzt vor der Freigabe, in beiden
  Rückfallpfaden (Erfolg und erschöpfte Fallback-Kette).
