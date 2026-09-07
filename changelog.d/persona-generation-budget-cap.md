### Behoben

- Die parallele Persona-Generierung hält ein hartes `max_llm_calls`-Budget jetzt auch dann ein, wenn weniger Calls frei sind als Worker gestartet würden. Zuvor prüften alle Greenlets beziehungsweise Threads gegen denselben Vor-Aufruf-Stand, bevor eine Antwort ihre Nutzung verbucht hatte. Die Restbudget-Rechnung liegt neu in `RunBudgetEnforcer.remaining_hard_calls()`; `LLMClient.remaining_hard_call_budget()` reicht dorthin durch.
