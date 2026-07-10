# ADR-0006: Kanonische KI-Provider-Verbindungen

- Status: Proposed
- Datum: 2026-07-10

## Kontext

Provider-Metadaten, Modelle, Profile, Runtime-Konfiguration und Routing sind
heute auf mehrere Verträge und Services verteilt. Fähigkeiten und Fallbacks
können voneinander abweichen.

## Entscheidung

`ProviderConnection`, `AiModel` und `AiRoute` werden Pydantic-SSoT. Bestehende
Verträge bleiben zunächst über Adapter lesbar. Die Detection-SSoT
`detect_provider(..., mode=...)` bleibt unverändert. Fähigkeiten stammen aus
Live-Discovery, markiertem Cache oder markiertem Fallback.

CLI-Subscription-Bridges sind keine normalen API-Verbindungen. Sie bleiben
lokal, experimentell und standardmäßig deaktiviert, bis ein separater
Security-/Machbarkeitsslice positiv abgeschlossen ist.

## Folgen

- Migration braucht dual-read/new-write und Contract-Tests.
- UI und Routing können einen gemeinsamen Modellvertrag nutzen.
- Secret-Werte bleiben außerhalb der Verträge; nur `secret_ref` wird geführt.
