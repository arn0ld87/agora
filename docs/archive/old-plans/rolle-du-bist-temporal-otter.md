# Plan — Repo-Review-Umsetzung Slice 0–5 + README/Doku-Sync auf v0.9.0

> **Modus:** Plan-Modus, kein Code-Touch ohne Freigabe.
> **Ziel:** Die im User-Prompt vorgegebenen PR1–PR5 als 6 Sub-Slices (inkl. Doku-Sync) ausführen.
> **Branch:** `claude/sleepy-torvalds-32f68f` (Worktree).
> **Source-of-Truth (vom User bestätigt):** Das User-Prompt selbst (PR1–PR5) ist verbindlich. Die im Repo liegende Datei `agora_repo_review_neuer_stand.md` ist ein anderer, nicht maßgeblicher Review und wird nur für Querverweise genutzt (z. B. „XSS bereits gefixt").

---

## Context

Agora ist auf v0.9.0 (`package.json` v0.9.0, Release Notes [docs/2026-05-01-v0.9.0-release-notes.md](docs/2026-05-01-v0.9.0-release-notes.md), 671 Backend + 40 Frontend = 711 Tests). README im Repo behauptet v0.8.0 mit 519 Tests — also genau die Diskrepanz, die Slice 0 adressiert. Dazu kommen offene Hardening-Findings aus dem User-Prompt (Secure Defaults, Compose-Trennung, Redis-Tickets, CVE-Baseline, Token-Storage). XSS-Sanitizer ist bereits gefixt ([frontend/src/utils/markdown.js](frontend/src/utils/markdown.js) + 9 Tests in [frontend/src/utils/__tests__/markdown.spec.js](frontend/src/utils/__tests__/markdown.spec.js)) — Slice 5 wird deshalb auf den Token-Storage-Anteil + Auth-Doku reduziert.

---

## Source-of-Truth gelesen (Stand jetzt)

| Pfad | Erkenntnis |
|---|---|
| [agora_repo_review_neuer_stand.md](agora_repo_review_neuer_stand.md) | Im Repo vorhandener Review — fokussiert XSS, Vitest-CI, Prod-Dockerfile, Ruff-Scope, Build-vs-Prebuilt. **Nicht** identisch mit dem User-Prompt-Review. |
| `agora_repository_review.md` | **Existiert nicht** — STOP-Condition gemäß User-Prompt. Workaround: User-Prompt selbst als Source-of-Truth. |
| [README.md](README.md) | v0.8.0, 488+31 Tests, Default-Compose-Schnellstart, Neo4j-Browser auf `localhost:7474`. Nicht synchron mit Realität. |
| [package.json](package.json) | `version: 0.9.0`. |
| [docs/2026-05-01-v0.9.0-release-notes.md](docs/2026-05-01-v0.9.0-release-notes.md) | 12/12 Issues, 671+40 = 711 Tests, Backend-`pyproject.toml` driftet noch auf 0.6.1. |
| [CHANGELOG.md](CHANGELOG.md) | `[Unreleased]`-Block leer, `[0.9.0] — 2026-05-01` Eintrag schon drin. |
| [.env.example](.env.example) | `FLASK_DEBUG=true` (Review will false), `SECRET_KEY=change-me-use-token_urlsafe-32`, `NEO4J_PASSWORD=change-me`. |
| [backend/app/config.py](backend/app/config.py:198) | `Config.validate()` blockt **leere** `SECRET_KEY`/`NEO4J_PASSWORD`/`AGORA_AUTH_TOKEN` außerhalb DEBUG. **Erkennt aber keine Placeholder-Strings** (`change-me`, `agora`, `neo4j`, `password`). |
| [backend/app/utils/auth.py:163](backend/app/utils/auth.py:163) | `log_auth_mode` warnt im Debug-Off-Fall, validierung-bypass gibt `logger.error`. Audit-Hook für Slice 1 vorhanden. |
| [backend/app/utils/signed_ticket.py](backend/app/utils/signed_ticket.py) | `_seen`-Dict in-process — Multi-Worker-Lücke. Modulkommentar (Z. 22–25) bestätigt das Finding. |
| [backend/tests/test_config_validate.py](backend/tests/test_config_validate.py) | Existiert, deckt Placeholder-Werte aber **nicht** ab. Slice 1 ergänzt `tests/test_config_security.py`. |
| [docker-compose.yml](docker-compose.yml) | Kein `target: dev` (Multi-Stage-Last-Stage = `prod` → Default-`docker compose up` startet gunicorn statt vite-dev). Ports binden auf `0.0.0.0`. Neo4j 7474/7687 ebenfalls `0.0.0.0`. |
| [docker-compose.prod.yml](docker-compose.prod.yml) | Setzt `target: prod` explizit, exposed nur 5001. **Erbt** Neo4j-7474/7687 vom Default → muss in Slice 2 abgeklemmt werden. |
| [Dockerfile](Dockerfile) | Multi-Stage: `base → dev`, `base → prod-builder → prod`. Letzter Stage ist `prod`, daher Default-Build = prod. |
| [.github/workflows/ci.yml](.github/workflows/ci.yml:43) | 6 `--ignore-vuln` ohne Expiry/Issue-Annotation. Frontend-Vitest läuft bereits (Z. 129–131) — Repo-Review-Finding ist veraltet. |
| [frontend/src/utils/markdown.js](frontend/src/utils/markdown.js) | DOMPurify aktiv. **Slice-5-XSS-Teil ist bereits erfüllt.** |
| [frontend/src/utils/__tests__/markdown.spec.js](frontend/src/utils/__tests__/markdown.spec.js) | 9 XSS-Regression-Tests vorhanden (`<script>`, `onerror`, `<iframe>`, `javascript:`, `<style>`). |
| [frontend/src/api/index.js:17](frontend/src/api/index.js:17) | `getAgoraToken` liest unkonditional aus `localStorage`. Kein Memory-Mode-Switch. |
| [docs/security.md](docs/security.md) | Existiert; Tickets-Abschnitt muss in Slice 3 nachgezogen werden. |
| `docs/auth.md` | Existiert **nicht** — Slice 5 erstellt. |
| `docs/dependency-risk-register.md` | Existiert **nicht** — Slice 4 erstellt. |

---

## Bereits erfüllte Findings (mit Beweis)

| User-Prompt-Anforderung | Status | Beweis |
|---|---|---|
| Auth-Token-Pflicht im Nicht-Debug | ✅ erfüllt | [backend/app/config.py:222–232](backend/app/config.py:222) |
| Leerer `SECRET_KEY` außerhalb DEBUG abgewiesen | ✅ erfüllt | [backend/app/config.py:205–211](backend/app/config.py:205) |
| Leeres `NEO4J_PASSWORD` abgewiesen | ✅ erfüllt | [backend/app/config.py:216–217](backend/app/config.py:216) |
| Audit-Log bei No-Op-Guard im Debug | ✅ erfüllt | [backend/app/utils/auth.py:174–178](backend/app/utils/auth.py:174) |
| Compose-Prod-Override exposed nur Backend | ✅ erfüllt für `agora`-Service | [docker-compose.prod.yml:19–21](docker-compose.prod.yml:19) |
| DOMPurify-Sanitizer für Markdown-`v-html` | ✅ erfüllt | [frontend/src/utils/markdown.js:24](frontend/src/utils/markdown.js:24) |
| XSS-Regression-Tests (script, onerror, iframe, javascript:) | ✅ erfüllt | [frontend/src/utils/__tests__/markdown.spec.js:11–67](frontend/src/utils/__tests__/markdown.spec.js:11) |
| Vitest läuft im CI | ✅ erfüllt | [.github/workflows/ci.yml:129–131](.github/workflows/ci.yml:129) |
| Compose hat `:?`-Guard auf `NEO4J_PASSWORD` | ✅ erfüllt | [docker-compose.yml:85](docker-compose.yml:85) |

---

## Offene Findings (zu erledigen)

| Slice | Punkt | Pfad / Beweis |
|---|---|---|
| 0 | README v0.8.0 → v0.9.0 + Testzahlen 519 → 711 + Compose-Realität markieren | [README.md:11](README.md:11), [README.md:24](README.md:24), [README.md:166–191](README.md:166) |
| 0 | `[Unreleased]`-Block leer — `Docs:`-Eintrag fehlt | [CHANGELOG.md:6](CHANGELOG.md:6) |
| 1 | Placeholder-`SECRET_KEY` (`change-me*`) wird nicht abgewiesen | [backend/app/config.py:205–211](backend/app/config.py:205) |
| 1 | Placeholder-`NEO4J_PASSWORD` (`agora`/`neo4j`/`password`/`change-me`) wird nicht abgewiesen | [backend/app/config.py:216–217](backend/app/config.py:216) |
| 1 | `.env.example` hat `FLASK_DEBUG=true` (Review will false als secure-by-default) | [.env.example:15](.env.example:15) |
| 1 | Tests für Placeholder-Rejects fehlen | [backend/tests/test_config_validate.py](backend/tests/test_config_validate.py) (kein `test_config_security.py`) |
| 2 | `docker-compose.yml` ohne `target: dev` → Default-Build zieht `prod`-Stage | [docker-compose.yml:8](docker-compose.yml:8) + [Dockerfile:62–63](Dockerfile:62) |
| 2 | Frontend/Backend Ports binden 0.0.0.0 statt Loopback | [docker-compose.yml:13–14](docker-compose.yml:13) |
| 2 | Neo4j-Ports 7474/7687 binden 0.0.0.0 (auch im Prod-Override) | [docker-compose.yml:79–81](docker-compose.yml:79) |
| 3 | Single-Use-Tickets in-process → Multi-Worker-Lücke | [backend/app/utils/signed_ticket.py:22–25](backend/app/utils/signed_ticket.py:22) |
| 4 | 6 `--ignore-vuln` ohne Expiry-/Issue-Annotation | [.github/workflows/ci.yml:46–53](.github/workflows/ci.yml:46) |
| 4 | `docs/dependency-risk-register.md` fehlt | n/a (neu) |
| 5 | Token immer aus `localStorage`, kein Memory-Mode | [frontend/src/api/index.js:16–19](frontend/src/api/index.js:16) |
| 5 | `docs/auth.md` fehlt | n/a (neu) |

---

## Slice-Reihenfolge & Aufwand

Genau die Reihenfolge aus dem User-Prompt: **Slice 0 → 1 → 2 → 3 → 4 → 5**. Pro Slice exakt 1 Commit, Arbeitsprotokoll, CHANGELOG-Update, `npm run check`. Issues-Closes-Refs nur, wenn ein offenes Issue im Repo existiert (separat per `gh issue list` zu klären, **nicht** spekulieren).

### Slice 0 — README & Doku-Sync auf v0.9.0
- **Edits:** [README.md](README.md) (Status-Block, Engineering-Stand, Testzahlen, Schnellstart-Hinweis „Default-Compose baut aktuell `prod`-Stage; Neo4j auf 0.0.0.0 — wird in Slice 2/Slice 5 entschärft"), [docs/v1-development-log.md](docs/v1-development-log.md) (neuer Eintrag), neuer `docs/2026-05-01-slice-0-readme-v090-sync-arbeitsprotokoll.md`, [CHANGELOG.md](CHANGELOG.md) `[Unreleased] → Docs`.
- **Verifikation:** `grep -n "v0.8.0\|v0\\.8" README.md` leer, `npm run check` grün, Testzahlen aus dem Lauf in den README-Block übernommen.
- **Commit-Body:** `docs: sync README to v0.9.0 + flag known compose/neo4j drift (Slice 0)`.

### Slice 1 — Secure Defaults + Config-Validation (PR1)
- **Edits:** [backend/app/config.py](backend/app/config.py): `validate()` erweitert um Placeholder-Sets (`{"", "change-me", "change-me-use-token_urlsafe-32", "agora", "password"}` für `SECRET_KEY`; `{"agora", "neo4j", "password", "change-me", ""}` für `NEO4J_PASSWORD`). Auth-Token-Pflicht behält bestehenden Pfad. [backend/app/utils/auth.py](backend/app/utils/auth.py): No-Op-Audit-Warnung bleibt; nichts Funktionales ändern. [.env.example](.env.example): `FLASK_DEBUG=true` → `false`, Kommentar präzisieren, README-Sicherheits-Sektion um `python -c "import secrets;print(secrets.token_urlsafe(32))"` ergänzen.
- **Neu:** [backend/tests/test_config_security.py](backend/tests/test_config_security.py) mit 5 Cases (siehe Prompt: Token-leer, SECRET_KEY-Placeholder, NEO4J-Placeholder, Debug-Mode-OK, Alles-gesetzt-OK).
- **Verifikation:** `cd backend && uv run pytest tests/test_config_security.py -v`, `npm run check`, manueller Smoke: `FLASK_DEBUG=false SECRET_KEY=change-me-use-token_urlsafe-32 ... uv run python run.py` muss abbrechen.
- **Commit-Body:** `feat(security): reject placeholder secrets and empty token in non-debug (Slice 1, PR1 of review)`.

### Slice 2 — Compose Dev/Prod-Trennung (PR2)
- **Edits:** [docker-compose.yml](docker-compose.yml): `agora.build.target: dev` setzen, Ports `127.0.0.1:${...}:5173` und `127.0.0.1:${...}:5001`, Neo4j-Ports `127.0.0.1:7474:7474` + `127.0.0.1:7687:7687`. [docker-compose.prod.yml](docker-compose.prod.yml): Frontend-Port endgültig draußen lassen + Neo4j-Override (`ports: !reset []` oder explizites Leeren) damit Prod-Override Neo4j nicht ungeschützt vererbt. README-Schnellstart in zwei Blöcke (Dev / Prod) zerlegen.
- **Neu (optional):** [backend/tests/test_compose_snapshot.py](backend/tests/test_compose_snapshot.py) mit `subprocess.run(["docker", "compose", "config"], check=True)` und Asserts auf `target: dev` und kein `5173` im Prod-Override. **Skip-Mechanik** (`@pytest.mark.skipif(shutil.which("docker") is None)`), damit CI-Sandbox ohne Docker grün bleibt.
- **Verifikation:** `docker compose config | grep -A2 target` → `dev`. `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` → kein `5173`-Mapping, kein `7474:7474` öffentlich. `docker compose up -d --build` → Vite auf `127.0.0.1:5173`.
- **Commit-Body:** `feat(deploy): split dev/prod compose, lock ports to loopback (Slice 2, PR2 of review)`.

### Slice 3 — Redis-basierte Single-Use-Tickets (PR3)
- **Edits:** [backend/app/utils/signed_ticket.py](backend/app/utils/signed_ticket.py): `consume()` versucht zuerst `SET ticket:<sig> 1 NX EX <ttl>` über existierenden Redis-Client; erfolgreiches `True` → ok, `False` → Replay. In-Memory-Pfad bleibt Fallback mit Warning. Existierenden Redis-Client wiederverwenden (kein neuer Pool); ggf. via `current_app.extensions` oder dem Container.
- **Neu:** [backend/tests/test_signed_ticket_redis.py](backend/tests/test_signed_ticket_redis.py) mit `fakeredis` (3 Cases: Replay-Block, Multi-Worker-Sim, In-Memory-Fallback + Warning).
- **Doku:** [docs/security.md](docs/security.md) Tickets-Sektion aktualisieren.
- **Verifikation:** `cd backend && uv run pytest tests/test_signed_ticket_redis.py`. `npm run check`. `fakeredis` ggf. via `pyproject.toml` dev-group ergänzen.
- **Commit-Body:** `fix(security): redis-backed single-use tickets for multi-worker gunicorn (Slice 3, PR3 of review)`.

### Slice 4 — CVE-Baseline aktiv abbauen (PR4)
- **Edits:** [.github/workflows/ci.yml](.github/workflows/ci.yml) Z. 46–53: hinter jeder `--ignore-vuln` ein Inline-Kommentar `# expires: YYYY-MM-DD, issue: #N`. Ablaufdatum konservativ +90 Tage.
- **Neu:** [docs/dependency-risk-register.md](docs/dependency-risk-register.md) mit Tabelle (CVE | Paket | Owner | Frist | Status | Issue-Link).
- **Issues:** **Alle 6 in einem Rutsch** per `gh issue create` (User-Freigabe vorab erteilt). Reihenfolge: CVE-2026-25990 → CVE-2026-40192 → CVE-2025-71176 → CVE-2026-1839 → CVE-2024-46455 → CVE-2025-64712. Pro Issue: Title `security: track ignored <CVE-ID> until upstream fix`, Body mit Paket, Pin-Begründung (`camel-oasis 0.2.5` / `camel-ai 0.2.78` / `sentence-transformers 3.0.0`), Risiko, Zielversion, Frist (+90 Tage = 2026-07-30), Labels `security` + `dependency-baseline`. Issue-Nummern werden danach in `dependency-risk-register.md` und in den CI-Inline-Kommentaren ergänzt — alles im selben Slice-Commit.
- **Verifikation:** `gh issue list --label dependency-baseline` zeigt 6 Einträge. CI weiterhin grün.
- **Commit-Body:** `chore(security): track ignored CVEs in risk register, link CI ignores to issues (Slice 4, PR4 of review)`.

### Slice 5 — Frontend-Token-Härtung + Auth-Doku (PR5, XSS schon erledigt)
- **Edits:** [frontend/src/api/index.js](frontend/src/api/index.js) `getAgoraToken`: Default-Pfad bleibt `localStorage`, neuer Memory-Mode via `import.meta.env.VITE_AGORA_TOKEN_STORAGE === "memory"` + reactiver Pinia/Module-Variable. `localStorage`-Pfad explizit als Dev-Fallback markieren.
- **Bestätigt erfüllt:** [frontend/src/utils/markdown.js](frontend/src/utils/markdown.js) + 9 XSS-Tests in [frontend/src/utils/__tests__/markdown.spec.js](frontend/src/utils/__tests__/markdown.spec.js) — Slice schreibt nur einen Verweis ins Arbeitsprotokoll, **fügt keine Duplicate-Tests hinzu**.
- **Neu:** [docs/auth.md](docs/auth.md) mit Token-Header-Vertrag, Ticket-Flow, Query-Token-Deprecation, `localStorage`-Risiko, Empfehlung `HttpOnly`-Cookie/Session-Backend für Prod.
- **Verifikation:** `cd frontend && npm test`, `npm run check`, manueller Dev-Smoke: Login → Run starten → Report sehen.
- **Commit-Body:** `feat(security): memory-token mode + auth.md, confirm xss regression (Slice 5, PR5 of review)`.

---

## Verifikation (über alle Slices)

1. Pro Slice: `npm run check` grün → 1 Commit. Bei rot → STOP, Reporting an User.
2. Reporting im vom User vorgegebenen Tabellenformat nach jedem Slice.
3. End-to-End nach Slice 5: `npm run check` final, manueller Dev-Smoke (Frontend `127.0.0.1:5173`, Backend `127.0.0.1:5001/health`), `docker compose config`-Snapshot prüfen.
4. **Keine echten Secrets** ins Repo. Tests nutzen `monkeypatch`/`fakeredis`/Platzhalter.

---

## Stop-Conditions, die heute schon greifen

- Slice 2 ändert lokales Port-Verhalten. Wenn User aktive Sessions an `0.0.0.0:7474` Neo4j hat, kurz vor dem Push hinweisen.
- Slice 3 verlangt eine neue Dev-Dependency (`fakeredis`) im `backend/pyproject.toml` `dev`-Group. Falls Auto-Add gegen das User-Prinzip „Dependencies bewusst" verstößt, fallback auf `unittest.mock`-Stub mit niedrigerem Realismus — Entscheidung im Slice-3-Reporting einholen.
- Slice 4 erzeugt **6 Github-Issues in einem Rutsch** (Freigabe vorab erteilt). Falls `gh auth status` rot ist, abbrechen und User pingen.

---

## Dauer-Schätzung

| Slice | LOC-Diff (geschätzt) | Tests neu | Risiko |
|---|---:|---:|---|
| 0 | ~80 | 0 | niedrig |
| 1 | ~60 | 5 | mittel (Dev-UX wenn `.env.example`-Default umkippt) |
| 2 | ~30 | 1 (skip-fähig) | mittel (Compose-Verhalten) |
| 3 | ~80 | 3 | mittel (Redis-Fallback) |
| 4 | ~40 | 0 | niedrig (Doku + Annotation) |
| 5 | ~70 | 0 (XSS schon abgedeckt) | niedrig |

Alles unter dem 400-LOC-Slice-Limit aus dem User-Prompt.
