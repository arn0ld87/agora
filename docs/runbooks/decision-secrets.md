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

## Prüfen, dass der Key ankommt

**Abweichung von der ursprünglichen Planung für diesen Abschnitt:** Geplant
war, nach dem Umschalten auf `AGORA_DECISION_LAYER_MODE=authoritative` eine
Log-Zeile `decision_layer_authoritative … provider=jev` zu prüfen. Das ist
mit dem heutigen Code nicht möglich, und wird deshalb hier bewusst nicht so
dokumentiert:

- `backend/app/config.py::validate_decision_layer_mode` lehnt
  `authoritative` als **Startvalidierungsfehler** ab ("is not usable yet: no
  wired use case has an authoritative handler … refusing to start"). Der
  Container würde mit diesem Wert gar nicht erst hochkommen — es gäbe keine
  Log-Zeile zu prüfen, weil der Prozess vorher stirbt.
- Der einzige verdrahtete Use Case,
  `backend/app/services/decisions/local_search_shadow.py`, ruft im
  Produktionspfad ausschließlich den kostenlosen, deterministischen
  `RuleProvider` auf (hartkodierter Default, kein Caller übergibt dort
  aktuell einen `JevDecisionProvider`). Selbst im gültigen Modus `shadow`
  entsteht also keine Zeile mit `provider=jev`, nur
  `decision_layer_shadow … provider=rule …`.

Der gebundene Key wird heute ausschließlich von einem Codepfad tatsächlich
entschlüsselt und verwendet: dem Benchmark-Skript.

```bash
docker compose exec -T agora sh -c \
  'cd /app/backend && .venv/bin/python scripts/jev_benchmark_local_search.py'
```

Ohne gebundenen Key markiert der Bericht den Jev-Arm als "übersprungen"; mit
gebundenem Key laufen echte Aufrufe gegen `https://api.typesafe.ai` und der
Bericht zeigt eine Jev-Accuracy, Latenz und Kosten. Binden bereitet damit die
künftige Verdrahtung in einen Live-Use-Case vor (das in `config.py`
erwähnte `jev-choice`-Gate), schaltet aber nichts automatisch scharf — dafür
braucht es eine eigene, separate Code-Änderung samt bestandenem Benchmark.

## Rückweg

Binden/Löschen des Keys selbst hat keinen Effekt auf
`AGORA_DECISION_LAYER_MODE` — es gibt für diesen Schritt nichts
zurückzudrehen außer `--delete` (siehe oben). Für den Decision-Layer-Modus
selbst (`disabled`/`shadow`, gültige Werte laut
`backend/app/config.py::DECISION_LAYER_MODES`) gilt wie bei jeder
Env-Änderung: Wert in der produktiven `.env` anpassen, dann
`docker compose up -d agora`, damit der Container neu startet und ihn liest.

## Key-Rotation

Ein erneutes Binden (`bind_decision_secret.py jev`, ohne `--delete`)
überschreibt den bestehenden Eintrag (`upsert`, `created_at` bleibt
erhalten). Das reicht für einen reinen API-Key-Wechsel bei gleichbleibendem
`AGORA_SECRET_KEY` — kein Neustart nötig, weil jeder `get_plaintext`-Aufruf
frisch entschlüsselt.

Ein Wechsel des **Master-Keys** `AGORA_SECRET_KEY` selbst ist ein anderer
Vorgang (`scripts/llm-secrets-doctor.py rotate`, re-encryptet alle
Einträge inklusive `jev`) und braucht zwingend einen Neustart des
Backend-Containers: Docker-Umgebungsvariablen eines laufenden Containers
sind nicht nachträglich änderbar, der neue Wert muss beim Start gesetzt
sein.
