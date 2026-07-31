# Runbook: lokaler E2E-Lauf

Ziel: eine Playwright-Spec gegen einen echten Compose-Stack verifizieren, ohne dafür CI-Runden zu verbrennen. Bei PR #983 brauchte es drei rote CI-Läufe, bis der lokale Lauf die Ursache in Minuten zeigte — dieser Weg lohnt sich, sobald eine Spec nicht offensichtlich grün ist.

Stand: Issue #989. Vorher kollidierte der E2E-Stack mit dem Dev-Stack, das ist behoben.

## Isolation gegenüber dem Dev-Stack

Der E2E-Stack läuft unter dem festen Compose-Projektnamen `agora-e2e` und vergibt eigene Container-Namen (`agora-e2e`, `agora-e2e-neo4j`, `agora-e2e-redis`, `agora-e2e-nginx`, `agora-e2e-mock-models`). Damit gilt:

- Der Dev-Stack (`agora`, `agora-neo4j`, …) darf während des Laufs weiterlaufen.
- `down -v` im E2E-Teardown trifft ausschließlich die Volumes des Projekts `agora-e2e`. Dev-Daten in Neo4j bleiben unberührt.
- Host-Ports kollidieren nicht: nach außen publiziert der E2E-Stack nur nginx auf `AGORA_PROXY_PORT`. Die Neo4j-Ports resettet `docker-compose.prod.yml`, den Backend-Port der Proxy-Override.

Auch zwei E2E-Stacks nebeneinander sind möglich, dann aber **beide** Variablen setzen: `AGORA_E2E_PROJECT=<name>` wählt Projektnamen, Volumes, Netzwerk und Container-Präfix — der veröffentlichte Host-Port hängt allein an `AGORA_PROXY_PORT` und ist nicht projektabhängig. Ohne unterschiedliche Ports scheitert der zweite Stack an der Portbindung, nicht mehr am Container-Namen.

**Einzige Kollisionsquelle bleibt `AGORA_PROXY_PORT`.** Der Default ist `80` — er stammt aus `scripts/e2e-up.sh` und deckt sich mit `playwright.config.ts`. Wer dort schon etwas liegen hat, **exportiert** einen anderen Wert (siehe unten).

> **Der Port muss exportiert werden, ein Eintrag allein in der `.env` genügt nicht** — und wird vom E2E-Lauf überschrieben. Grund: `e2e-up.sh` läuft als Kindprozess von Playwright. Ein aus der `.env` gelesener Port wäre für den Elternprozess unsichtbar; `playwright.config.ts` (`baseURL`) und `global-setup.ts` (Provider-Seeding) lesen beide nur `process.env.AGORA_PROXY_PORT`. Der Stack wäre dann auf dem einen Port gesund, während die Specs den anderen ansprechen.
>
> Umgekehrt trägt der Proxy-Override für dieselbe Variable den Compose-Default `8080`. Deshalb schreibt `e2e-up.sh` den aufgelösten Port **immer** in die `.env` — sonst publizierte Compose auf 8080, während `e2e-up.sh` und Playwright auf 80 warten. Beides zusammen ergibt genau einen Wert auf allen drei Seiten.

Die Compose-Invocation liegt an genau einer Stelle: [`scripts/e2e-compose.sh`](../../scripts/e2e-compose.sh). `e2e-up.sh`, `e2e-down.sh` und der Log-Dump in `frontend/tests/e2e/global-teardown.ts` rufen dieses Skript auf, statt die `-f`-Kette je eigenständig zu pflegen.

## Variante A — Playwright fährt den Stack selbst hoch

Der Normalfall. `global-setup.ts` ruft `scripts/e2e-up.sh`, `global-teardown.ts` ruft `scripts/e2e-down.sh`.

```bash
cd frontend
AGORA_E2E_LLM_MODE=stub \
AGORA_PROXY_PORT=8099 \
AGORA_E2E_BASE_URL=http://127.0.0.1:8099 \
AGORA_SKIP_EMBEDDING_PROBE=true \
npx playwright test <spec>.spec.ts --reporter=list
```

`AGORA_E2E_LLM_MODE=stub` ersetzt alle LLM-Calls durch deterministische Fixture-Antworten. Ohne diesen Schalter versucht das Backend echte Modell-Calls — im E2E-Stack gibt es keinen Ollama.

Einmalig nötig, sonst bricht der Lauf mit `browserType.launch: Executable doesn't exist` ab, obwohl der Stack gesund ist:

```bash
npx playwright install chromium
```

## Variante B — Stack von außen, Playwright nur als Client

Nützlich, wenn dieselbe Spec mehrfach gegen einen bereits stehenden Stack laufen soll (Boot dauert ~3–4 min).

```bash
# 1. Stack hochfahren
AGORA_E2E_LLM_MODE=stub AGORA_PROXY_PORT=8099 bash scripts/e2e-up.sh

# 2. Spec beliebig oft laufen lassen
cd frontend
AGORA_E2E_SKIP_STACK=true \
AGORA_PROXY_PORT=8099 \
AGORA_E2E_BASE_URL=http://127.0.0.1:8099 \
npx playwright test <spec>.spec.ts --reporter=list

# 3. Am Ende abräumen — zurück ins Repo-Root, Schritt 2 hat nach frontend/ gewechselt
cd ..
bash scripts/e2e-down.sh
```

`AGORA_E2E_SKIP_STACK=true` überspringt Up und Down — das Seeding der Provider-Connections läuft in beiden Pfaden, die Specs brauchen es.

## Ephemere Credentials

`scripts/e2e-up.sh` erzeugt selbst nur zwei Werte: `AGORA_SECRET_KEY` (Fernet-Key für den Provider-Secrets-Store — ohne ihn schlägt das Seeding mit HTTP 503 fehl) und `AGORA_PROXY_PORT` aus der Process-Env, ersatzweise `80`. Alle übrigen Werte kommen aus der Umgebung; fehlen sie, greifen die Platzhalter aus `.env.example`, die `Config.validate()` mit `RuntimeError` ablehnt.

Lokal einmalig erzeugen und exportieren:

```bash
export AGORA_AUTH_TOKEN="$(openssl rand -hex 24)"
export SECRET_KEY="$(openssl rand -hex 32)"
export NEO4J_PASSWORD="$(openssl rand -hex 16)"
```

`AGORA_AUTH_TOKEN` muss identisch sein zwischen Stack und Playwright — die Specs senden ihn als `X-Agora-Token`. Ohne Export fällt `global-setup.ts` auf `e2e-test-token-fixed-for-ci` zurück, der Stack aber nicht.

## Was `e2e-up.sh` in die `.env` schreibt

Compose liest `.env` mit Vorrang vor der Process-Env. Ein Export auf Shell-Ebene erreicht die Container also **nicht** — deshalb schreibt `e2e-up.sh` die Laufzeitwerte in die `.env`.

Seit Issue #989 geschieht das idempotent: pro Schlüssel genau eine Zeile, vorhandene Definitionen desselben Schlüssels werden vorher entfernt. Vorher wuchs die Datei mit jedem lokalen Lauf, und mehrere `AGORA_SECRET_KEY`-Zeilen mit je frisch erzeugtem Fernet-Key machten Secrets unlesbar, die ein früherer Lauf verschlüsselt hatte.

Geschrieben werden `AGORA_AUTH_TOKEN`, `SECRET_KEY`, `AGORA_SECRET_KEY`, `NEO4J_PASSWORD`, `AGORA_PROXY_PORT`, `AGORA_SKIP_EMBEDDING_PROBE` und `AGORA_E2E_LLM_MODE` — jeweils nur, wenn ein Wert vorliegt. `AGORA_SECRET_KEY` und `AGORA_PROXY_PORT` liegen immer vor, weil das Skript für beide einen Wert erzeugen kann.

`AGORA_E2E_LLM_MODE` entfernt `e2e-down.sh` am Ende wieder. Bleibt der Schalter stehen, übernimmt ihn der nächste normale `docker compose up` des Dev-Stacks, und das Backend liefert still Stub-Reports statt echter Modellantworten — erkennbar nur an der Log-Zeile `E2E-Stub aktiv — ueberspringe LLM-Call`.

Die übrigen Schlüssel bleiben bewusst stehen. `AGORA_SECRET_KEY` zu entfernen würde alles unlesbar machen, was damit verschlüsselt wurde.

## Logs

`e2e-down.sh` räumt den Stack ab — Logs also **vorher** ziehen:

```bash
bash scripts/e2e-compose.sh logs agora --tail=500
bash scripts/e2e-compose.sh logs neo4j --tail=200
```

Service-Namen, nicht Container-Namen: `docker compose logs` erwartet den Service-Key.

In CI dumpt `global-teardown.ts` diese Logs automatisch, sobald `CI` gesetzt ist.

## Wenn doch etwas hängen bleibt

```bash
bash scripts/e2e-compose.sh ps -a
bash scripts/e2e-compose.sh down -v --remove-orphans
```

Der Wrapper trägt dieselbe `-f`-Kette und denselben Projektnamen wie Up und Down — ein handgeschriebenes `docker compose -p agora-e2e …` ohne die Override-Dateien kennt `mock-models` nicht. Ein abweichendes `AGORA_E2E_PROJECT` muss auch hier gesetzt sein:

```bash
AGORA_E2E_PROJECT=<name> bash scripts/e2e-compose.sh down -v --remove-orphans
```

Der feste Projektname macht das aus jedem Verzeichnis heraus möglich — auch aus einem anderen Worktree als dem, der den Stack gestartet hat.

## Verwandte Runbooks

- [`pre-push-gate.md`](pre-push-gate.md) — was vor dem Push zu laufen hat
- [`e2e-required-check.md`](e2e-required-check.md) — E2E-Jobs als Required Checks
- [`worktree-strategy.md`](worktree-strategy.md) — Worktree-Isolation
