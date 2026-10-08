### Fixed

- „Neuer Lauf“ → Datei und Frage → „Graph bauen“ endete auf beiden Deployments in
  einer leeren Seite: Die URL wechselte auf `/v4/graph-build/new?maxRounds=…`, aber
  der StepGraphBuildView mountete nie und die Pipeline startete nicht — kein einziger
  `POST /api/graph/ontology/generate` ging hinaus. Ursache war die Route-Transition in
  `frontend/src/App.vue` mit `mode="out-in"`: Beim Verlassen einer Fensterroute
  (Startdialog `/library/runs/new`, Einstellungen; `meta.windowOverBackground`) ruft
  Vue in `afterLeave` `instance.update()` und patcht dabei den Mehrfach-Root-Baum der
  App; `prevTree.el` ist dabei `null` und es wirft
  `Cannot read properties of null (reading 'parentNode')`. Der Wurf bleibt unbehandelt
  und die Transition hängt im Leave-Zustand — der neue View wird nie eingehängt.
  Abhilfe ist das Entfernen von `mode="out-in"` (einzige verifizierte Variante; `:key`
  am `<component>` und ein Einzel-Root-Wrapping waren ohne Wirkung): Die Transition
  läuft als Kreuzblende, Hülle und Kopf bleiben stehen, nur der Inhaltsbereich
  überblendet kurz. Die explizite `:duration` bleibt Pflicht (Hintergrund-Tab-Problem,
  siehe Kommentar in `App.vue`). Regressionstest:
  `frontend/tests/e2e/graph-build-navigation.spec.ts` fährt den echten Dialog-Weg
  (Frage, Quelldatei, Start) und behauptet den Ontologie-Request, die URL mit echter
  Projekt-ID und den sichtbaren Pipeline-Stepper; er läuft als achter Job
  `graph-build-navigation-smoke` in der CI gegen den Docker-Stub-Stack und ist
  zunächst kein Required Check (Praxis wie `run-budget-smoke`).