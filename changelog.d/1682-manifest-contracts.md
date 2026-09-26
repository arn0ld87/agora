### Fixed

- `RunManifest` gab an mehreren Stellen fabrizierte Werte als echte Daten aus
  (Issue #1682, Teil von #1274). `ManifestSeeds.random_seed` war ein
  Hash über die `simulation_id` — Agora hat kein echtes RNG-Seed-Konzept
  (kein `np.random.seed`-Äquivalent), der Wert täuschte Reproduzierbarkeit
  vor, die nicht bestand. Das Feld ist jetzt `Optional[int] = None`, und der
  Run-Start schreibt `None` statt des Platzhalter-Hashs.
  `StageRoute.ai_route_snapshot` war ein offenes `dict[str, Any]` — jetzt ein
  striktes `AiRouteSnapshot`-Schema (`extra="forbid"`), das den internen
  `__legacy_stage_route__`-Transportkanal von `AiRoute` auflöst und
  secret-tragende Provider-Optionen entfernt; alte Manifeste mit dem vollen
  `AiRoute`-Dump bleiben über einen tolerierenden Vor-Validator lesbar,
  nicht rettbare Altbestände werden `None` statt eines `ValidationError`.
  `POST /api/runs/<id>/replay` setzte hart `platform="parallel"` und ließ
  `max_rounds`/`enable_graph_memory_update`/die Graph-Memory-ID komplett
  weg — ein neues `ManifestSimulationParams`-Feld persistiert diese
  Start-Parameter, und Replay übernimmt sie jetzt 1:1 aus dem
  Original-Manifest; übersteuerbar bleibt ausschließlich die Modell-Route.
  Ein Alt-Manifest ohne dieses Feld kann nicht ehrlich 1:1 repliziert
  werden — der Endpoint antwortet mit `409 code="manifest_missing_simulation_params"`
  statt einen Default stillschweigend als Original auszugeben. Ein neuer
  Replay-Run bekommt außerdem sein eigenes Draft-Manifest mit einem
  `deviations`-Feld (`{field, original, replay}`), das jede tatsächliche
  Abweichung vom Original dokumentiert. `ManifestCapture.migrate_legacy`
  übernimmt jetzt `completed_at`/Terminierungsgrund/Modell-Route aus
  Run-Metadaten, wo vorhanden, statt sie komplett zu ignorieren; nicht
  rekonstruierbare Felder sind `None` statt der Fake-Werte `"legacy"`/`0`.
- Nachbesserung aus dem Review (Issue #1686, Teil von #1274): Ohne
  expliziten `ai_model_ref`-Override seedete `POST /api/runs/<id>/replay`
  die Modell-Route aus den aktuellen Workspace-Defaults statt aus der im
  Original-Manifest erfassten Route — ein vermeintlich identisches Replay
  konnte so unbemerkt auf einem anderen Modell laufen, sobald sich Defaults
  oder Provider-Connections geändert hatten, und `deviations` blieb in
  diesem Fall leer. Ohne Override wird die Route jetzt aus
  `routing.stages.simulation_rounds` (bevorzugt deren `ai_route_snapshot`)
  rekonstruiert; die aufgelöste Replay-Route wird jetzt immer — nicht nur
  bei explizitem Override — mit der Original-Route verglichen. Ist die
  Original-Connection nicht mehr auflösbar, antwortet der Endpoint mit
  `409 code="manifest_route_unresolvable"` statt still auf Defaults
  zurückzufallen. `inputs.simulation_config_hash` im neuen Replay-Manifest
  ist jetzt der Hash der tatsächlich verwendeten Branch-Konfiguration (nach
  `create_branch`), nicht mehr der 1:1 kopierte Hash des Originals — die
  Branch-Konfiguration wird durch Overrides/Branch-Metadaten umgeschrieben
  und der alte Hash passte dann nicht mehr zur tatsächlichen Konfiguration.
  Das Draft-Manifest des Replay-Runs wird jetzt vor dem Start des
  Simulations-Subprozesses geschrieben statt danach: bei sofortigem
  Prozessende konnte der Monitor-Thread das Manifest finalisieren wollen,
  bevor der Draft überhaupt existierte, und der Run blieb dauerhaft im
  Status `draft` hängen. Scheitert der Start danach doch, wird das bereits
  geschriebene Draft-Manifest wieder entfernt.
