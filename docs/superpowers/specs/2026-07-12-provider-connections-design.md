# Provider-Verbindungen — Slice-3-Design

**Status:** Von Alex am 2026-07-12 freigegeben.

## Ziel und Scope

Slice 3 führt eine kanonische Lifecycle-Schicht für Provider-Verbindungen ein.
Sie verwaltet Konfiguration, Secret-Referenz, Test, Modell-Discovery und
normalisierten Status für:

- OpenAI API, Anthropic API, Gemini API, MiniMax API, Ollama Cloud und
  OpenCode Go (API-Key);
- OpenAI-kompatible HTTP-Endpunkte (API-Key und benutzerdefinierte Base-URL);
- lokales Ollama (konfigurierbare lokale Base-URL, ohne API-Key).

Bestehende LLM-Presets und API-Key-Endpunkte bleiben kompatibel. Die Migration
ist additiv und legt Daten erst bei Benutzung an.

## Nicht im Scope

- Codex- oder Claude-Code-Subscription-Bridges;
- Auslesen von Cookies, Keychains, OAuth-Tokens oder privaten Auth-Dateien;
- Re-Embedding und gemeinsamer Model-Picker (nachfolgende Slices).

Subscription-Bridges bleiben als `unsupported` sichtbar, bis ein separater,
positiver Security-Spike eine offizielle nichtinteraktive Nutzung belegt.

## Architektur

`ProviderConnection` bleibt der Pydantic-v2-Quellvertrag und wird im Frontend
durch Zod gespiegelt. Eine Connection referenziert Secrets ausschließlich über
den bestehenden verschlüsselten Secret-Store; API-Antworten und Browser-Storage
enthalten nie Klartext-Schlüssel.

Eine gemeinsame Service-Schicht führt den Lifecycle aus. Kleine Adapter
unterscheiden nur Transport und Authentisierung:

| Verbindungsklasse | Transport | Authentisierung |
|---|---|---|
| API-Key-Provider | providerspezifisches oder OpenAI-kompatibles HTTP | API-Key |
| OpenAI-kompatibel | OpenAI-kompatibles HTTP | API-Key |
| Ollama lokal | Ollama HTTP | keine |

Adapter liefern ein einheitliches Testergebnis und eine Modellliste. Sie
enthalten keine Persistenz- oder HTTP-Routenlogik.

## API und Verhalten

Die API unterstützt Connections listen, anlegen/ändern/löschen, testen und
Modelle entdecken. Tests und Discovery verwenden kurze Timeouts. Sie geben
normalisierte Statuswerte und sichere Fehlermeldungen zurück; Details mit
Secrets werden weder geloggt noch serialisiert.

Öffentliche Base-URLs bleiben für benutzerdefinierte HTTP-Anbieter verpflichtend.
Nur lokales Ollama erhält eine explizit eng begrenzte lokale Ausnahme. Fehler
werden zu `unconfigured`, `available`, `unavailable`, `invalid_credentials`,
`degraded` oder `unsupported` normalisiert.

## Teststrategie und Akzeptanz

Die Umsetzung folgt Red-Green-Refactor:

1. Contract- und Schema-Tests für Connection, Status und sichere Responses.
2. API-Tests für CRUD, Secret-Referenzen, ungültige Base-URLs und Fehlerfälle.
3. Adapter-Tests mit kontrolliertem HTTP-Transport für jeden unterstützten
   Verbindungstyp.
4. Frontend-Tests für den Zod-Spiegel und den Settings-Flow.

Vor Abschluss laufen zielgerichtete Tests, Schema-Drift, relevante Lint- und
Typecheck-Gates sowie eine Doc-Impact-Prüfung für README, AGENTS, CLAUDE, PLAN,
STATUS, CHANGELOG, Handover und Tooling-Dokumentation.

## Risiken und Gegenmaßnahmen

- **Secret-Leakage:** Nur Referenzen persistieren; Maskierung und Response-Tests.
- **SSRF über Custom HTTP:** bestehende Public-URL-Validierung beibehalten und
  explizit testen.
- **Provider-Drift:** Adapter von Registry-Metadaten trennen; Discovery als
  best-effort und Status klar als zeitgebundene Beobachtung ausweisen.
- **Falsche Subscription-Semantik:** Bridges nicht als verbunden markieren.
