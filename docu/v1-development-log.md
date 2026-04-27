# v1.0 Development Log

**Start:** 2026-04-27
**Branch:** `feat/v1-api-contracts`
**Ziel:** Agora schrittweise Richtung v1.0 bringen: stabilere API-Verträge, bessere Operability, mehr reproduzierbare Tests und klar dokumentierte Migrationsschritte.

## Arbeitsregeln

1. Kleine, prüfbare Änderungen statt großer Umbauten.
2. Jede Verhaltensänderung bekommt Tests und einen kurzen Doku-Eintrag.
3. Bestehende lokale Änderungen außerhalb des aktuellen Scopes bleiben unangetastet.
4. Security-relevante Änderungen bevorzugen einheitliche Fehlerformen, Least Privilege und klare Rollback-Pfade.

## Schritt 1 — API-Contract: Auth-Fehler vereinheitlichen

**Problem:** Der zentrale API-Layer nutzt weitgehend die Envelope-Form `{"success": false, "error": "...", "code": "..."}`. Der Token-Guard in `backend/app/utils/auth.py` gab dagegen bisher nur `{"error": "unauthorized", "code": "auth_required"}` zurück.

**Änderung:**

- `token_required()` und `install_blueprint_guard()` verwenden jetzt denselben `json_error()`-Helper wie die übrigen API-Routen.
- Auth-Fehler liefern damit konsistent:

```json
{
  "success": false,
  "error": "unauthorized",
  "code": "auth_required"
}
```

**Tests:**

- Neuer Testblock `backend/tests/test_auth.py`
- Abgedeckt sind Open-Mode, fehlender Token, `X-Agora-Token`, `Authorization: Bearer ...` und Query-Token.

**Rollback:**

- Rückgängig machen von `backend/app/utils/auth.py` und Entfernen von `backend/tests/test_auth.py` stellt das alte Payload-Format wieder her.

## Schritt 2 — API-Contract: rohe Dict-Returns envelopen

**Problem:** `backend/app/utils/api_responses.py` dokumentierte bereits, dass `@handle_api_errors` rohe `dict`-Returns in `json_success()` überführt. Die Implementierung gab solche Dicts aber unverändert an Flask zurück.

**Änderung:**

- `handle_api_errors()` ruft die View auf, prüft das Ergebnis und wandelt `Mapping`-Returns in `json_success(dict(result))` um.
- Bestehende `Response`-Objekte und `(Response, status)`-Tupel werden unverändert durchgereicht.

**Tests:**

- `backend/tests/test_api_responses.py::test_handle_api_errors_wraps_raw_dict_return`

**Rollback:**

- Entfernen des Mapping-Branches in `handle_api_errors()` stellt das alte Flask-Default-Verhalten für rohe Dicts wieder her.
