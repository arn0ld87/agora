# ADR-0020: Isolierte öffentliche Bewerbungsdemo vor 1.0

- Status: Accepted (Owner-Anweisung vom 26.09.2026 zur öffentlichen Bewerbungsdemo)
- Datum: 26.09.2026
- Bezug: [ADR-0019](0019-multi-user-after-1-0.md), [#1688](https://github.com/arn0ld87/agora/issues/1688)

## Kontext

ADR-0019 hält den Produktivbetrieb bis 1.0 bei einem Nutzer und deaktiviert
offene Registrierung. Für eine Bewerbung soll Agora dennoch von externen
Personen unter `agora.alexle135.de` registriert und mit eigenen Provider-Keys
benutzt werden können. Die bisherige Agora-Instanz enthält persönliche
Bestandsdaten und nutzt eine Datenbank eines anderen Supabase-Projekts.

## Entscheidung

Die Ausnahme gilt ausschließlich für eine **getrennte Demo-Instanz**:

1. Eigener Checkout, Compose-Projekt, Artefaktpfad, Neo4j, Redis und
   Supabase-Stack mit eigener Auth- und Agora-Metadatenbank.
2. Öffentlichkeit nur über HTTPS für Agora und den Supabase-Auth-Pfad
   `/auth/v1`; Datenbanken, Studio und interne Dienste bleiben privat.
3. Anmeldung mit bestätigter E-Mail und persönlichem Workspace. Externe
   Modellaufrufe verwenden ausschließlich verschlüsselt gespeicherte Keys
   des jeweiligen Workspace. Kein Betreiber-Key-Fallback für JWT-Läufe.
4. Der bisherige persönliche Betrieb bleibt Tailnet-gebunden. Die Demo ist
   kein Nachweis, dass Multi-User Teil des 1.0-Produktumfangs ist.

Die Freigabe der öffentlichen DNS- und Proxy-Route setzt grüne Code-Gates,
einen Zwei-Konten-Isolationstest und einen echten Registrierungs- und
Bestätigungsdurchlauf voraus.

## Konsequenz

ADR-0019 bleibt für den regulären 1.0-Produktivbetrieb gültig. Die Ausnahme
ist an die isolierte Demo-Topologie und [#1688](https://github.com/arn0ld87/agora/issues/1688)
gebunden; die bestehende Installation wird nicht in einen offenen
Mehrbenutzerbetrieb umgeschaltet.
