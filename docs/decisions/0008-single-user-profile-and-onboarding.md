# ADR-0008: Single-User-Profil und Erst-Onboarding

- Status: Proposed
- Datum: 2026-07-10

## Kontext

„Profil“ bezeichnet derzeit KI-Konfigurationen, während ein lokales
Benutzerprofil fehlt. Agora v1 ist gemäß ADR-0001 ein Single-User-System.

## Entscheidung

Ein neues lokales `UserProfile` und ein resumierbarer Onboarding-State werden
eingeführt. Bestehende `LlmProfile` werden sichtbar als KI-Presets bezeichnet;
ihre Persistenz bleibt zunächst kompatibel. „Nutzer & Teams“ wird nicht als
fertige Funktion dargestellt.

Onboarding gilt als abgeschlossen, wenn Benutzerprofil, Chat-Modell und
Embedding-Konfiguration gültig sind. Jeder Schritt wird backendseitig
persistiert.

## Folgen

- klare Sprache ohne unnötigen Datenbankbruch;
- Avatar benötigt validierten lokalen Speicher;
- echte Teams und Rechte bleiben ein separates Epic.
