### Fixed (Hermetischer Report-Resume-Test — 2026-08-09)

- **Resume-422-Test an die kanonische Routing-Naht gebunden:** Der Regressionstest mockt jetzt `LLMClient.from_route`, kontrolliert die gelockte Report-Route und prüft die Übergabe der `run_id`, sodass lokale Provider-Konfigurationen das Ergebnis nicht mehr verändern. (Refs #984)
