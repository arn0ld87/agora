# Security Followup Plan — Post-P0/P1/P2

**Datum:** 2026-04-29 (Europe/Berlin)
**Branch-Konvention:** `security/followup-<sub-slice>`
**Quellen:** `docs/archive/reviews/SECURITY_REVIEW.md`, `docs/security.md`, `docs/SECURITY_REVIEW_SUMMARY.md`

## Status der Original-Findings aus `docs/archive/reviews/SECURITY_REVIEW.md`

| Finding | Severity | Status | Commit/Doc |
|---|---|---|---|
| F1 — API offen ohne Token | High | **DONE** | `5bd6b14`, `docs/2026-04-29-p0-1a-auth-fail-fast.md` |
| F2 — Query-Token `?token=` Leakage | Medium | **PARTIAL** — Tickets live, `?token=` noch als Deprecation-Pfad | `92cfdf9`, `201c0a0`, `0b940ab` |
| F3 — Neo4j-Passwort-Default | Medium | **DONE** | `caa6967` |
| Low — CI-Security-Scans | Low | **DONE** | `b225506` (P1) |
| Info — Container Hardening | Info | **OFFEN** — read-only rootfs + cap_drop fehlen | — |
| Q1 — Hartes Auth-Requirement | Open Q | **DONE** (Config.validate fail-fast) | `5bd6b14` |
| Q2 — SSE-Auth-Zielbild | Open Q | **TEILWEISE** — Signed Tickets done, Cookie-Session out-of-scope | `0b940ab` |
| Q3 — Secret-Scanning verpflichtend | Open Q | **DONE** — gitleaks in CI | `b225506` |

`docs/archive/reviews/SECURITY_REVIEW.md` selbst ist überholt und sollte auf Snapshot-Status markiert werden.

## Ziel

Drei Residual-Arbeiten als getrennte Sub-Slices, jeder mit 1 Commit + Arbeitsprotokoll. Optional ein vierter Slice für die Cookie-Session-Migration als Future-Outlook (out-of-scope hier).

---

## Sub-Slices

### S1 — `docs/archive/reviews/SECURITY_REVIEW.md` Status-Sync

**Ziel:** Alte Review-Datei als historischen Snapshot markieren, Status-Tabelle vorne anhängen.

**Files:**
- Modify: `docs/archive/reviews/SECURITY_REVIEW.md` (Header + Status-Block)

- [ ] **Step 1: Header umbauen**

Oben in `docs/archive/reviews/SECURITY_REVIEW.md` einfügen:

```markdown
> **Stand 2026-04-29:** Dieser Review ist ein **historischer Snapshot** (2026-04-22).
> Aktueller Status der Findings siehe [`docs/2026-04-29-security-followup-plan.md`](./docs/2026-04-29-security-followup-plan.md)
> und [`docs/security.md`](./docs/security.md).
> F1, F3, Low, Q1, Q3 sind erledigt. F2 läuft im Deprecation-Pfad. Container-Hardening (Info) ist offen.
```

- [ ] **Step 2: Commit**

```bash
git add docs/archive/reviews/SECURITY_REVIEW.md docs/2026-04-29-security-followup-plan.md
git commit -m "docs(security): mark docs/archive/reviews/SECURITY_REVIEW.md as historical snapshot"
```

**Arbeitsprotokoll:** `docs/2026-04-29-security-followup-s1-protokoll.md` (kurz, 5 Zeilen).

---

### S2 — `?token=` Hard-Removal

**Voraussetzung:** Telemetrie aus dem Deprecation-Pfad bestätigt: kein Live-Setup nutzt `?token=` mehr. Logger-Warning aus `auth.py:54-59` muss seit ≥2 Wochen leise sein. Falls Telemetrie noch nicht ausgewertet — diesen Slice **vertagen**, nicht raten.

**Files:**
- Modify: [backend/app/utils/auth.py:46-60](backend/app/utils/auth.py#L46-L60) — `_extract_token()` ohne `request.args["token"]`-Pfad
- Modify: [docs/security.md](docs/security.md) — Phase-2-Tabelle aktualisieren
- Modify: [CLAUDE.md](CLAUDE.md) + [AGENTS.md](AGENTS.md) — `?token=`-Erwähnung entfernen
- Test: `backend/tests/test_auth.py` — Regression: `?token=` darf nicht mehr authentifizieren

- [ ] **Step 1: Failing Test schreiben**

`backend/tests/test_auth.py` ergänzen:

```python
def test_query_token_no_longer_accepted(monkeypatch, app_with_token):
    monkeypatch.setenv("AGORA_AUTH_TOKEN", "secret")
    client = app_with_token.test_client()
    resp = client.get("/api/status?token=secret")
    assert resp.status_code == 401
    assert resp.get_json()["code"] == "auth_required"
```

- [ ] **Step 2: Test laufen lassen, FAIL erwarten**

```bash
cd backend && uv run pytest tests/test_auth.py::test_query_token_no_longer_accepted -v
```

Erwartet: FAIL (Status 200, weil `?token=` aktuell noch akzeptiert wird).

- [ ] **Step 3: `_extract_token()` zurückbauen**

In `backend/app/utils/auth.py` den `query_token`-Block (Zeilen 53–60) komplett entfernen. Resultat:

```python
def _extract_token() -> str:
    hdr = request.headers.get("X-Agora-Token")
    if hdr:
        return hdr
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""
```

Der `?ticket=`-Pfad in `_try_consume_ticket()` bleibt unangetastet.

- [ ] **Step 4: Tests laufen lassen, alle PASS**

```bash
cd backend && uv run pytest tests/test_auth.py -v
```

Erwartet: alle PASS, inkl. neuer Regression.

- [ ] **Step 5: Doku-Sync**

In `CLAUDE.md` Sektion „Konfiguration": die Erwähnung `?token=<bearer>` entfernen. In `AGENTS.md` synchron. In `docs/security.md` Phase-2-Tabelle: Zeile zu `?token=` als „entfernt 2026-04-29" markieren.

- [ ] **Step 6: Commit**

```bash
git add backend/app/utils/auth.py backend/tests/test_auth.py CLAUDE.md AGENTS.md docs/security.md
git commit -m "feat(security): remove deprecated ?token= URL auth fallback"
```

**Arbeitsprotokoll:** `docs/2026-04-29-security-followup-s2-protokoll.md` mit Telemetrie-Evidence.

---

### S3 — Container Hardening (read-only rootfs + cap_drop)

**Ziel:** Defense-in-Depth gegen Container-Compromise — Schreibrechte aufs Image-FS sperren, unnötige Linux-Capabilities droppen.

**Files:**
- Modify: [docker-compose.yml](docker-compose.yml) — `agora`-Service security-hardenen
- Modify: [Dockerfile](Dockerfile) — falls neue Tmp-Pfade nötig
- Test: manuell + `docker compose up -d` Smoke

- [ ] **Step 1: `agora`-Service in `docker-compose.yml` ergänzen**

Innerhalb `services.agora`:

```yaml
    read_only: true
    tmpfs:
      - /tmp:size=128M,mode=1777
      - /app/backend/.cache:size=64M,mode=0700
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETUID
      - SETGID
      - DAC_OVERRIDE
```

`backend/uploads` bleibt schreibbar via existierendes Bind-Mount.

- [ ] **Step 2: Schreibpfade auditieren**

```bash
grep -rn "tempfile\|/tmp/\|\.cache\|os.makedirs" backend/app | grep -vE "test_|__pycache__"
```

Alle Schreibziele müssen entweder im Bind-Mount `./backend/uploads` oder im neuen `tmpfs` liegen. Falls anders → Pfad in den Mount verschieben oder zusätzliches `tmpfs` ergänzen, kein Workaround mit `read_only: false`.

- [ ] **Step 3: Smoke-Test**

```bash
docker compose down
docker compose build agora
docker compose up -d
docker logs -f agora    # auf Permission-Errors achten
curl -fsS http://localhost:5001/health
curl -fsS -H "X-Agora-Token: $AGORA_AUTH_TOKEN" http://localhost:5001/api/status
```

Anschließend: ein Beispiel-Upload + Graph-Build durchspielen, damit Schreibpfade real getroffen werden.

- [ ] **Step 4: cap_add minimieren**

Falls der Smoke-Test ohne einzelne Capabilities sauber durchläuft, dieselben aus `cap_add` rausnehmen. Ziel: minimaler Cap-Set.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml Dockerfile docs/security.md
git commit -m "feat(security): harden agora container with read-only rootfs and cap_drop"
```

**Arbeitsprotokoll:** `docs/2026-04-29-security-followup-s3-protokoll.md` mit Smoke-Log + finaler Cap-Liste.

---

## Out-of-Scope (eigener Folge-Slice)

- **Cookie-basierte Session-Auth** statt Static-Bearer-Token. Größerer Umbau, separate Spezifikation, eigene Brainstorming-Runde nötig (Logout, CSRF, Multi-User, Token-Rotation).
- **pip-audit-Baseline-Reduktion**: 6 Ignores warten auf `camel-oasis`/`camel-ai`-Upgrade. Tracking nicht hier — der nächste Lockfile-Bump prüft die Ignore-Liste; wenn ein Pin entfällt, Ignore raus.

## Reihenfolge

S1 → S2 → S3, voneinander unabhängig. S2 setzt Telemetrie-Check voraus, S3 nicht.

## Abnahme-Kriterien

- `npm run check` bleibt grün (alle 214 Backend-Tests + neue Regression in S2).
- `docker compose up -d` startet sauber, Health + `/api/status` antworten.
- `docs/archive/reviews/SECURITY_REVIEW.md` zeigt prominent den aktuellen Status, niemand verwechselt das Dokument mit einer offenen TODO-Liste.
