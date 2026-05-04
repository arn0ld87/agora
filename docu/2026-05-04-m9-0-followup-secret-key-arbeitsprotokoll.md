# M9-0-Followup — SECRET_KEY/LLM_API_KEY in CI-Smoke-Env

**Datum:** 2026-05-04
**Branch:** `fix/m9-0-secret-key`
**Refs:** Run 25296986030 (post-Merge `5dd57f0` M9-0/N3 + `4fe1c8f` PR #241)
**Subagent:** keiner — direkter Orchestrator-Fix (4-Zeilen-YAML).

## Symptom

Verify-Skript-Step im `prod-proxy-smoke`-Job liefert `Result: 4 ok, 4 fail`:

```
OK   agora laeuft
FAIL nginx laeuft
OK   nginx /healthz (Sidecar-eigen)
FAIL Backend /health (via Proxy)
OK   Frontend / erreichbar (via Proxy)
FAIL DOMPurify im node_modules
FAIL markdown-Util importiert DOMPurify
OK   name->id Lookup im Service
```

Initiale Hypothese (aus Plan-Notiz): Container-Name-Mismatch (`nginx` vs.
`agora-nginx`) + nginx-Routing. Beides falsch.

## Root Cause

`docker compose ps` im Diagnose-Block zeigt:

```
agora    agora-agora    "/app/backend/.venv/…"   agora    Restarting (1) Less than a second ago
```

agora-Container kollabiert sofort beim Boot. Backend-Logs:

```
[01:51:52] ERROR: Config error: SECRET_KEY not configured (required when FLASK_DEBUG is false)
[01:51:52] ERROR: Config error: LLM_API_KEY not configured (set to any non-empty value, e.g. 'ollama')
RuntimeError: Critical configuration missing: SECRET_KEY not configured ..., LLM_API_KEY not configured ...
[2026-05-04 01:51:52 +0000] [22] [INFO] Worker exiting (pid: 22)
```

`Config.validate()` ([`backend/app/config.py:228`](../backend/app/config.py:228),
[`:241`](../backend/app/config.py:241)) erzwingt beide Vars in Non-Debug-Umgebungen.
Der M9-0/N3-Slice (5dd57f0) hatte sie in der CI-`.env`-Generierung vergessen.

Alle anderen Failures sind Cascade:
- `nginx laeuft` FAIL — nginx-Healthcheck (`wget /healthz`) noch `health: starting`,
  `docker compose ps nginx --status running -q` ist strikt.
- `Backend /health (via Proxy)` FAIL — nginx liefert `502 Bad Gateway` weil
  `agora:5001` nicht antwortet (Container in Restart-Loop). nginx-Access-Log
  bestätigt: `"GET /health HTTP/1.1" 502 157`.
- `DOMPurify im node_modules` / `markdown-Util` FAIL — `docker compose exec -T agora`
  schlägt fehl, weil agora restarted.

## Fix

`.github/workflows/docker-image.yml`:

1. `env`-Block des `prod-proxy-smoke`-Jobs ergänzt um:
   - `SECRET_KEY: ci_smoke_secret_key_for_prod_proxy_smoke_only_not_a_real_secret`
     (64 chars, nicht in `SECRET_KEY_PLACEHOLDERS`-Frozenset).
   - `LLM_API_KEY: ollama` (Beispiel-Wert aus der Config-Errormessage).

2. Step "CI-Umgebungsdatei generieren" — `printf`-Format-String und
   Argument-Liste um beide Vars erweitert.

Werte sind reine Smoke-Dummies. GitGuardian-Whitelist nicht nötig (keine
echten Geheimnisse, Strings sind explizit als CI-Marker erkennbar).

## Verify

Lokal nicht reproduzierbar (CI-only). Verify nach Merge: Re-Run des Workflows
auf dem Merge-Commit; Erwartung:

- `Result: 8 ok, 0 fail` (im Container-Health- und S1/S2-Block).
- N2-Loopback-Bind-Checks bleiben FAIL — das ist erwartetes Verhalten in CI
  (Vite/Flask laufen in Containern, nicht auf dem Host). Folge-Slice bei
  Bedarf: N2-Block in CI-Mode skippen.

## Out of Scope

- N2-Loopback-Checks CI-Mode-Skip (separater Slice, nicht critical).
- DOMPurify/markdown-Verify-Checks gegen Image-Pfad statt `frontend/node_modules`
  (Folge-Slice — die Checks sind auf Dev-Container ausgelegt, nicht auf das
  schlanke Prod-Image).
