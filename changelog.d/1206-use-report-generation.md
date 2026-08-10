### Geändert

- Report-Statusmaschine aus `Step4Report.vue` in das Composable
  `useReportGeneration` gezogen (#1206). Neun offene Status-Refs, die
  141-zeilige `pollStatus()`-Schleife samt Endzustands-Zweigen, die
  Transportfehler-Zählung aus #1023 und die Koordination der drei
  Polling-Instanzen liegen jetzt hinter dem Interface
  `{ status, progress, report, bootstrap(), start(), stop(), regenerate() }`;
  `usePolling` ist damit interne Abhängigkeit statt Detail der Komponente.
  Frontend-Gegenstück zu `RunLifecycle` (#1204). Verhalten unverändert — der
  Flow ist jetzt zusätzlich ohne `mount()` und ohne Modul-Mocks testbar.
