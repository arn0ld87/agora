# Slice 1.2 — Report-Generierung serialisiert statt parallel

Eine zweite parallele Report-Generierung für dieselbe Simulation wird
deterministisch mit HTTP `409 report_generate_in_progress` abgewiesen, statt
kooperativ gebremst zu werden. Der neue Guard
`ReportGenerationService._reject_if_report_generate_active` fragt vor jedem
Start die RunRegistry nach einem Run mit `run_type=report_generate` und
Status `pending` oder `processing` für dieselbe `simulation_id` ab — bewusst
kein In-Memory-Dict, weil das einen Worker-Neustart nicht überleben würde und
den zweiten Start dann wieder durchließe.

Das ist eine bewusste Verhaltensänderung und für Nutzer, die bisher parallel
generiert haben, eine Laufzeit-Regression: der zweite Aufruf schlägt jetzt
fehl statt (unkontrolliert) mitzulaufen. Begründung ist der in #1265
belegte Faktor ~6 an Ressourcenverbrauch — Tokens, LLM-Calls, Laufzeit —, den
zwei parallele Generierungen für dieselbe Simulation ohne Mehrwert
verursachen.

Out-of-Process-Jobausführung bleibt 1.0-Vorarbeit und ist mit diesem Slice
nicht erledigt; der Guard serialisiert nur den Start, er ändert nichts an der
grundsätzlichen In-Process-Ausführung der Jobs selbst.
