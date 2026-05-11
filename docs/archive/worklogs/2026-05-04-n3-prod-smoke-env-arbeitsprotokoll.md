# Arbeitsprotokoll: Sub-Slice M9-0 (N3) — prod-proxy-smoke CI-Fix

**Datum:** 2026-05-04
**Branch:** `fix/n3-prod-smoke-env`
**Issue:** [#227](https://github.com/arn0ld87/agora/issues/227)

---

## Befund: Echter Fehler aus `gh run view --log-failed`

Run-ID: 25292544231 (letzter von 5 aufeinanderfolgenden `failure`-Runs auf `main`).

Schlüssel-Log-Zeilen:

```
env:
  VITE_AGORA_TOKEN:   ← leer
  AGORA_AUTH_TOKEN:   ← leer
  NEO4J_PASSWORD:     ← leer

error while interpolating services.neo4j.environment.[]:
  required variable NEO4J_PASSWORD is missing a value:
  NEO4J_PASSWORD muss in .env gesetzt sein
##[error]Process completed with exit code 1.
```

**Fail-Zeitpunkt:** Step „Compose-Stack starten" — kein `docker build` wurde je gestartet.

---

## Hypothesen vs. tatsächliche Ursache

| Hypothese (aus Task-Body) | Status |
|---|---|
| ALLOW_BUILD_TIME_TOKEN fehlt → Dockerfile-Build-Fail | FALSCH — Build wurde nie gestartet |
| Doppelter npm-Build erzeugt Drift / Hard-Fail | NEIN — Doppel-Build ist Sekundärbefund, kein Fail-Grund |
| Leerer VITE_AGORA_TOKEN durch Default-Propagation | NEIN — nicht die unmittelbare Ursache |

**Tatsächliche Ursache:** Die drei Steps „CI-Umgebungsdatei generieren" und „Compose-Stack starten" referenzierten `${{ env.X }}` — den **Workflow-`env:`-Kontext**, der nirgends definiert war. Kein Job-Level- oder Workflow-Level-`env:`-Block existierte. Alle drei Variablen waren leer. Der `.env`-Step schrieb `NEO4J_PASSWORD=\n`. Compose brach beim Interpolieren von `docker-compose.yml:110` ab (`${NEO4J_PASSWORD:?...}`-Gate).

**Sekundärbefund (kein Fail-Grund, aber Drift):** `deploy/compose/docker-compose.prod-with-proxy.yml:37` mountet `./frontend/dist` als Host-Bind-Mount in nginx. Der Dockerfile-`prod-builder`-Stage legt `dist` im Image ab, nicht auf dem Runner-Dateisystem. Der Runner-`npm run build`-Step ist deshalb korrekt und notwendig — ohne ihn wäre nginx' Bind-Mount leer. Der Schritt darf nicht entfernt werden.

---

## Zusätzliche Diagnose-Findings

- `AGORA_AUTH_TOKEN` und `VITE_AGORA_TOKEN` existieren nicht als Repo-Secrets
  (`gh secret list` zeigt nur: `CLAUDE_CODE_OAUTH_TOKEN`, `DOCKERHUB_TOKEN`, `DOCKERHUB_USERNAME`, `LLM_API_KEY`, `LLM_BASE_URL`)
- Der `Logs sammeln (immer)`-Step scheiterte im gleichen Run selbst an der
  Compose-Interpolation — nützliche Logs konnten deshalb nicht gesammelt werden
- `AGORA_BIND_HOST` war nicht gesetzt → Backend band auf `127.0.0.1`, was im
  CI-Netz kein Problem ist (Compose-interner nginx erreicht `agora:5001`), aber
  defensiv explizit auf `0.0.0.0` gesetzt

---

## Änderungen in `.github/workflows/docker-image.yml`

### Hunk 1: Job-Level `env:`-Block (neu, Z. 65–73)

```yaml
env:
  NEO4J_PASSWORD: ci_smoke_neo4j
  AGORA_AUTH_TOKEN: ci_smoke_token
  VITE_AGORA_TOKEN: ci_smoke_vite_token
  ALLOW_BUILD_TIME_TOKEN: "true"
  AGORA_BIND_HOST: "0.0.0.0"
```

Rationale: Keine echten Secrets nötig für Smoke. `NEO4J_PASSWORD` muss nur
nicht leer sein. `ALLOW_BUILD_TIME_TOKEN=true` ist für Single-User-Tailnet-CI
zulässig (N6/F2.1). `AGORA_BIND_HOST=0.0.0.0` defensiv explizit.

### Hunk 2: `CI-Umgebungsdatei generieren` (Z. 86–89)

- `env:`-Block am Step entfernt (jetzt Job-Level)
- `.env` enthält jetzt zusätzlich `AGORA_BIND_HOST=0.0.0.0`

### Hunk 3: `Compose-Stack starten` (Z. 91–101)

- `env:`-Block am Step entfernt (jetzt Job-Level)
- Kommentar: Begründung für `ALLOW_BUILD_TIME_TOKEN=true` in CI

### Hunk 4: `Frontend-Bundle bauen` — bleibt unverändert mit Kommentar (Z. 77–84)

Step ist korrekt und notwendig (nginx-Host-Bind-Mount-Erklärung im Kommentar).

### Hunk 5: `Auf Proxy-Health warten` — Timeout-Diagnose angereichert (Z. 103–119)

Bei Timeout jetzt zusätzlich:
- `docker compose ps -a`
- `docker inspect agora-nginx`
- `docker inspect agora`

### Hunk 6: `Logs sammeln (immer)` — angereichert (Z. 124–130)

- `docker compose ps -a` statt `ps`
- `--tail=100` statt `--tail=50`
- `docker inspect agora-nginx` und `docker inspect agora` ergänzt

---

## Verifikation

```
YAML OK           ← python3 yaml.safe_load
Schemas kein Drift ← git diff --exit-code schemas/
1363 passed, 9 skipped ← uv run pytest -x -q
```

Backend-Tests unverändert grün. Keine Contracts berührt.

---

## Akzeptanz-Lauf

Echte CI-Verifikation nach Push durch den Orchestrator.
Erwartetes Ergebnis: `prod-proxy-smoke` grün (NEO4J_PASSWORD jetzt gesetzt,
ALLOW_BUILD_TIME_TOKEN=true, frontend/dist auf Runner vorhanden).
