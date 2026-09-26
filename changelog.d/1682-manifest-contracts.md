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
