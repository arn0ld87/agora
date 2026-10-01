# Runbook: Decision-Provider-Secrets binden (Jev)

Zugehöriger Kontext: f005, ADR-0016/0017 (Jev-Pilot), siehe Moduldoc von
[`backend/app/services/decisions/jev_provider.py`](../../backend/app/services/decisions/jev_provider.py).

## Warum ein eigenes Skript statt `llm-secrets-doctor.py`

Der Jev-API-Key (TypeSafe) liegt im selben verschlüsselten
Provider-Secret-Store wie die LLM-Chat-Provider-Keys
(`backend/data/llm_provider_secrets.json`), aber unter einer eigenen Ref
(`jev`, siehe `app.services.decisions.jev_provider.JEV_SECRET_REF`).
[`scripts/llm-secrets-doctor.py`](../../scripts/llm-secrets-doctor.py) nimmt
jede `provider_id` entgegen — ein Tippfehler dort könnte versehentlich einen
LLM-Chat-Provider-Key überschreiben. Binden/Löschen von
Decision-Provider-Secrets läuft deshalb über
[`backend/scripts/bind_decision_secret.py`](../../backend/scripts/bind_decision_secret.py),
das nur Refs aus einer festen Allowlist akzeptiert.

## Voraussetzungen

- `AGORA_SECRET_KEY` ist im Container bereits gesetzt (Fernet-Master für den
  gesamten Provider-Secret-Store, fail-fast ohne ihn — siehe
  `llm_provider_secrets_store.py`). Dieses Runbook setzt ihn nicht; er muss
  Teil der produktiven Container-Umgebung sein, bevor hier etwas gebunden
  wird.
- Der Key-Wert kommt aus Vaultwarden (`vw get TYPESAFE_API_KEY`), nie im
  Klartext in Shell-History, einem Commit oder einem Log.
- Servicename laut [`docker-compose.yml`](../../docker-compose.yml): `agora`.
  Arbeitsverzeichnis im Container `/app/backend`, venv unter
  `/app/backend/.venv` — das Prod-Image ([`Dockerfile`](../../Dockerfile),
  Stage `prod`) enthält kein `uv`, deshalb direkter Aufruf über
  `.venv/bin/python` statt `uv run`.

## Key binden

```bash
vw get TYPESAFE_API_KEY | docker compose exec -T agora sh -c \
  'cd /app/backend && .venv/bin/python scripts/bind_decision_secret.py jev'
```

Die Pipe hält den Klartext aus der Shell-History jedes beteiligten Prozesses
heraus. Die Ausgabe zeigt ausschließlich die maskierte Form (`key-...abcd`),
nie den Klartext. Exit `0` = gebunden (inklusive interner
Decrypt-Roundtrip-Prüfung); Exit `2` = Konfigurationsfehler (z. B.
`AGORA_SECRET_KEY` fehlt/ungültig im Container, leere Eingabe, unbekannte
Ref).

## Entfernen

```bash
docker compose exec -T agora sh -c \
  'cd /app/backend && .venv/bin/python scripts/bind_decision_secret.py jev --delete'
```

Danach **immer** `docker compose restart agora`: im Modus `authoritative`
cacht der Backend-Prozess den Jev-Client samt Key (siehe Abschnitt
„Key-Rotation“ unten) — das Löschen entfernt nur den persistierten Eintrag,
der laufende Prozess sendet mit dem gelöschten Key weiter, bis er neu
startet. Ohne Neustart ist der Key operativ noch nicht widerrufen, auch
wenn der Store ihn nicht mehr enthält.

## Prüfen, dass der Key ankommt

Zuerst ohne Umschalten, über das Benchmark-Skript (echte Aufrufe gegen
`https://api.typesafe.ai`, ohne Key meldet es den Jev-Arm als
"übersprungen"):

```bash
docker compose exec -T agora sh -c \
  'cd /app/backend && .venv/bin/python scripts/jev_benchmark_local_search.py'
```

Dann scharf schalten (setzt PR #1740 voraus — vorher lehnt
`validate_decision_layer_mode` den Wert `authoritative` beim Start ab):
`AGORA_DECISION_LAYER_MODE=authoritative` in der produktiven `.env`, optional
`AGORA_JEV_TIMEOUT_S` (Default `2.0`), dann `docker compose up -d agora`.
Nach dem ersten Report-Lauf zeigt das Log je Suche eine Zeile
`decision_layer_authoritative … provider=jev … fallback_chain=['jev']`.
`provider=rule` mit `fallback_chain=['jev', 'rule']` heißt Rückfall; der
Grund steht in `fallback_reason` (`no_key`, `auth_blocked`, Fehlerklasse).

## Rückweg

`AGORA_DECISION_LAYER_MODE` in der `.env` auf `shadow` oder `disabled`, dann
`docker compose up -d agora`. Der Key kann gebunden bleiben; im Modus
`shadow`/`disabled` wird er nicht verwendet. Ohne gebundenen Key fällt
`authoritative` von selbst auf die Regel zurück.

## Key-Rotation

Ein erneutes Binden (`bind_decision_secret.py jev`, ohne `--delete`)
überschreibt den bestehenden Eintrag (`upsert`, `created_at` bleibt
erhalten). Das reicht für einen reinen API-Key-Wechsel bei gleichbleibendem
`AGORA_SECRET_KEY`. Im Modus `authoritative` cacht der Backend-Prozess den
Jev-Client samt Key; danach deshalb `docker compose restart agora`, sonst
gilt der neue Key erst nach dem nächsten 401 des alten.

Ein Wechsel des **Master-Keys** `AGORA_SECRET_KEY` selbst ist ein anderer
Vorgang (`scripts/llm-secrets-doctor.py rotate`, re-encryptet alle
Einträge inklusive `jev`) und braucht zwingend einen Neustart des
Backend-Containers: Docker-Umgebungsvariablen eines laufenden Containers
sind nicht nachträglich änderbar, der neue Wert muss beim Start gesetzt
sein.
