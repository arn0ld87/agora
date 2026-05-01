# Slice 1 — Secure Defaults + Config-Validation (PR1)

**Datum:** 2026-05-01
**Branch:** `claude/sleepy-torvalds-32f68f`
**Slice-Quelle:** Repo-Review PR1 (User-Prompt, „Secure defaults / config validation").

## Ziel

Die in `.env.example` ausgerollten Platzhalter-Strings dürfen im
Nicht-Debug-Betrieb nicht durchschlagen. Wer das Beispiel kopiert und
direkt deployed, hat ein Internet-Geheimnis.

## Ausgangslage

- [backend/app/config.py:204–217](../backend/app/config.py:204) blockte bisher
  nur **leere** Werte für `SECRET_KEY`, `NEO4J_PASSWORD`, `AGORA_AUTH_TOKEN`.
- [.env.example](../.env.example) hatte `FLASK_DEBUG=true` als Default und
  rollte unverschlüsselt `change-me-use-token_urlsafe-32` (SECRET_KEY) und
  `change-me` (NEO4J_PASSWORD) aus.
- Es gab Tests für die Token-Pflicht (P0.1a, [test_config_validate.py](../backend/tests/test_config_validate.py))
  aber keine für Placeholder-Rejects.
- DOMPurify (Slice 5/PR5) ist bereits gesetzt — keine Konflikte.

## Änderungen

### `backend/app/config.py`

- Neue Modul-Konstanten `SECRET_KEY_PLACEHOLDERS` (`{"change-me",
  "change-me-use-token_urlsafe-32", "agora", "password"}`) und
  `NEO4J_PASSWORD_PLACEHOLDERS` (`{"change-me", "agora", "neo4j",
  "password"}`).
- `validate()`:
  - SECRET_KEY-Pfad teilt jetzt drei Branches: leer (existing), Placeholder
    + `not DEBUG` (neu: error mit Token-Setup-Befehl), Placeholder + DEBUG
    (neu: `logger.warning`).
  - NEO4J_PASSWORD-Pfad analog: leer (existing), Placeholder + `not DEBUG`
    (neu: error), Placeholder + DEBUG (neu: warning).
  - Vergleich ist case-insensitive (`.lower()`), `.strip()` lässt
    Leerzeichen-Padding fallen.
- Auth-Token-Policy aus P0.1a unangetastet.

### `.env.example`

- `FLASK_DEBUG=true` → `FLASK_DEBUG=false` (secure-by-default).
- Kommentar-Block über `SECRET_KEY` und `NEO4J_PASSWORD` ergänzt mit
  Hinweis: bekannte Platzhalter werden im Nicht-Debug-Betrieb hart
  abgelehnt.
- Token-Erzeugungsbefehl als One-Liner über `AGORA_AUTH_TOKEN` dokumentiert.

### `backend/tests/test_config_security.py` (neu)

- `agora_config_log`-Fixture hängt einen `ListHandler` an den
  `agora.config`-Logger (der hat `propagate=False`, deshalb sieht caplog
  ihn sonst nicht).
- Cases:
  - `test_validate_non_debug_rejects_missing_token` — Sanity gegen den
    bestehenden P0.1a-Pfad.
  - `test_validate_non_debug_rejects_placeholder_secret_key`
    (parametrize: 4 Platzhalter).
  - `test_validate_non_debug_rejects_placeholder_neo4j_password`
    (parametrize: 4 Platzhalter).
  - `test_validate_debug_allows_placeholder_secret_with_warning` — Debug
    bleibt lax, aber laut.
  - `test_validate_non_debug_with_real_values_passes` — Negativ-Kontrolle.
  - `test_validate_case_insensitive_placeholder_match` — `CHANGE-ME` wird
    ebenfalls geblockt.
- Insgesamt 12 neue Test-Cases.

### `README.md`

- Sicherheits-Sektion erweitert: Hinweis auf Placeholder-Reject + Code-Block
  mit `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## Tests

```
$ cd backend && uv run pytest tests/test_config_security.py tests/test_config_validate.py -v
17 passed in 0.51s
```

Smoke gegen den echten Code:

```
$ FLASK_DEBUG=false SECRET_KEY=change-me-use-token_urlsafe-32 \
    NEO4J_PASSWORD=neo4j LLM_API_KEY=ollama AGORA_AUTH_TOKEN=test-token \
    NEO4J_URI=bolt://localhost:7687 EMBEDDING_MODEL=nomic-embed-text \
    VECTOR_DIM=768 uv run python -c "from app.config import Config; \
    errors = Config.validate(); [print('ERR:', e) for e in errors]"
ERR: SECRET_KEY uses a known placeholder value — generate a real secret with `python -c "import secrets; print(secrets.token_urlsafe(32))"` (required when FLASK_DEBUG is false)
ERR: NEO4J_PASSWORD uses a known placeholder value — set a real password (required when FLASK_DEBUG is false)
```

`npm run check` final grün — Werte siehe Slice-1-Reporting.

## Risiken

- **Lokale Dev-User mit `FLASK_DEBUG=false` + altem `.env`:** Wer aus dem
  alten `.env.example` kopiert hat und auf `false` umstellt, bekommt
  jetzt einen lauten Fehler. Beabsichtigt — bisherige offene Lab-Setups
  sind genau das Problem. Im Debug-Betrieb (alter Default) ändert sich
  nichts außer einer zusätzlichen Warning.
- **CI:** Backend-CI läuft mit `FLASK_DEBUG=true` (siehe
  [.github/workflows/ci.yml:82](../.github/workflows/ci.yml:82)),
  daher kein Bruch.
- **Compose:** `NEO4J_PASSWORD=:?` in
  [docker-compose.yml:85](../docker-compose.yml:85) erzwingt einen Wert
  vor dem `Config.validate()`-Schritt. Wer dort `change-me` einträgt,
  fällt jetzt im App-Start zusätzlich auf — gewünschter zweiter Schutz.

## Open Questions

Keine offenen Punkte. Nächster Slice: PR2 (Compose Dev/Prod-Trennung).

## Rollback

`git revert <Slice-1-SHA>` stellt den vorherigen Validation-Stand und das
alte `.env.example`-Layout wieder her. Bestehende `.env`-Dateien werden
nicht angefasst.
