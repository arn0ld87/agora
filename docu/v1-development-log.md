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
