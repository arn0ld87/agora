Beim SIGTERM bekommen alle laufenden In-Process-Jobs — `simulation_prepare`,
`report_generate`, `graph_build`, `ontology_generate` — sofort einen ehrlichen
terminalen Zustand `failed/process_restart`, statt auf die
Startup-Reconciliation beim nächsten Start zu warten. Der neue Shutdown-Hook
in `backend/app/services/sim/process_shutdown.py` erkennt anhand von
Worker-Token und PID, welche laufenden Runs diesem Prozess gehören, und setzt
sie in derselben Schreibreihenfolge wie `reconcile_stale_jobs`: erst das
Cancel-Flag für kooperativen Abbruch, dann — nur für `simulation_prepare` —
der SimulationState (F1-Invariante: State vor Manifest), zuletzt das
RunRegistry-Manifest.

Es entsteht kein neuer `TerminationReason`-Wert — `process_restart` wird
wiederverwendet, derselbe Wert, den die Reconciliation beim Neustart auch für
Runs setzt, die einen Prozessabsturz ohne SIGTERM nicht überlebt haben. Für
Debug-Modus mit Werkzeug-Reloader registriert sich der Handler nur im
Child-Prozess, um doppelte Registrierung zu vermeiden.

Wichtig, um keine Erwartung zu wecken, die der Code nicht einlöst: ein
vollständig persistierter `interrupted`-/Resume-Zustand entsteht dadurch
nicht. Der Job endet sichtbar und ehrlich als `failed`, nicht als
automatisch fortsetzbarer Zwischenstand. #1472 (Job-Queue mit eigenen Workern
für Out-of-Process-Ausführung) bleibt offen.
