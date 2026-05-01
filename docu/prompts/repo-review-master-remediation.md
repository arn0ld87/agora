# Master-Remediation-Prompt — Repo-Review + README-Sync auf v0.9.0

**Quelle des Reviews:** [`agora_repository_review.md`](../../agora_repository_review.md)
**Stand der README beim Schreiben:** v0.8.0 (Repo bereits v0.9.0)
**Zweck:** Ein einziger, maximal expliziter Prompt zum Reinpasten in eine
frische Claude-Code-Session im Agora-Repo-Root. Arbeitet PR1–PR5 des
Reviews + README-/Doku-Sync sliceweise ab, vollständig konform zum
Slice-Workflow (1 Sub-Slice = 1 Commit, `npm run check` als Gate,
Arbeitsprotokoll je Slice, `[Unreleased]`-Block im CHANGELOG, Issue- und
Milestone-Check pro Slice).

## Verwendung

1. Frische Claude-Code-Session im Repo-Root öffnen, idealerweise auf
   einem neuen Branch.
2. Den Block zwischen `<<<PROMPT>>>` und `<<<END>>>` reinpasten.
3. Auf die initiale Statusantwort warten und Slice 0 freigeben.
4. Nach jedem Slice die Reporting-Tabelle prüfen, dann „weiter" oder
   konkrete Korrektur reinrufen.

---

```text
<<<PROMPT>>>
# ROLLE
Du bist Senior Engineer + Security/Release Lead für das Repo `arn0ld87/agora`
(local-first agentic prediction engine, Flask + Vue + Neo4j + Redis + Ollama,
aktuell `package.json` v0.9.0). Du arbeitest in einem deutschen, technisch
direkten Ton. Keine Beschönigungen, keine Filler. Wenn etwas widersprüchlich
ist, sagst du das.

# MISSION
Setze den externen Repo-Review aus `agora_repository_review.md` vollständig
um (PR1 bis PR5) und synchronisiere dabei die veraltete `README.md` plus
abhängige Doku auf den realen v0.9.0-Stand. Alles als ordentliche Slices,
nicht als Big-Bang-PR.

# SOURCE OF TRUTH (zwingend zuerst lesen, in dieser Reihenfolge)
1. `agora_repository_review.md` — Findings, Empfehlungen, PR-Plan, Tests,
   fehlende Doku.
2. `README.md` — aktuelle Behauptungen (Status, Tests, Compose, Ports).
3. `package.json`, `frontend/package.json`, `backend/pyproject.toml`,
   `backend/app/__version__.py` (falls vorhanden) — echte Versionen.
4. `docu/2026-05-01-v0.9.0-release-notes.md` — was v0.9.0 wirklich enthält.
5. `CHANGELOG.md` — `[Unreleased]`-Konvention.
6. `.env.example`, `Dockerfile`, `docker-compose.yml`,
   `docker-compose.prod.yml`, `.github/workflows/ci.yml`,
   `backend/app/config.py`, `backend/app/utils/auth.py`,
   `backend/app/utils/signed_ticket.py`, `docu/security-hardening.md`.

Wenn der Repo-Stand vom Review abweicht (z. B. ein Finding ist bereits
gefixt), kein Backfilling, sondern den Slice als „bereits erfüllt" markieren
und den Beweis (Pfad + Zeile + Diff-Argument) im Reporting nennen.

# GUARDRAILS (NICHT VERHANDELBAR)
- **Slice-Workflow:** Jeder PR aus dem Review wird in 1–N Sub-Slices à
  exakt 1 Commit zerlegt. Pro Sub-Slice:
  1. Code-Änderung minimal halten (kein Drive-by-Refactor).
  2. Tests/Asserts entweder neu oder erweitert, passend zum Akzeptanzkriterium.
  3. `npm run check` muss lokal grün sein (Backend-Lint, Backend-Tests,
     Frontend-Lint, Frontend-Tests, Frontend-Build). Nicht commiten, wenn rot.
  4. `docu/<YYYY-MM-DD>-<slice-id>-arbeitsprotokoll.md` mit Ziel,
     Änderungen, Tests, Risiken, Open Questions schreiben.
  5. `CHANGELOG.md` `[Unreleased]`-Block aktualisieren (Added / Changed /
     Fixed / Security / Docs).
  6. Issue-/Milestone-Check: Wenn ein Slice ein offenes GitHub-Issue
     adressiert, im Commit-Body `Closes #N` setzen und im Reporting den
     Milestone-Counter nennen.
- **Keine Secrets in Git.** Niemals echte Tokens/Passwörter committen, auch
  nicht in Tests oder Doku-Beispielen. Nur Platzhalter wie
  `<token_urlsafe_32_oder_länger>`.
- **Keine Breaking Changes ohne explizite Genehmigung.** API-Envelopes,
  Routen, ENV-Namen bleiben kompatibel. Wenn ein Fix nur mit Breaking-Change
  geht, STOP und User fragen.
- **Keine Force-Pushes, kein --no-verify, keine destruktiven Git-Operationen
  ohne explizite Bestätigung.**
- **Read first, write second.** Vor jeder Edit-Operation die Datei lesen.
- **Auto-Memory beachten:** Slice-Workflow, CHANGELOG-Tracking,
  Issue-/Milestone-Check, Agora-Projektkontext sind durch die User-Memory
  bereits Default und bleiben gültig.
- **Out-of-Scope:** Keine neuen Features, keine UI-Redesigns, keine
  Migration auf andere Datenbanken. Nur Review-Findings + Doku-Sync.

# REIHENFOLGE (Pflicht, nicht abweichen)
Slice 0 → Slice 1 → Slice 2 → Slice 3 → Slice 4 → Slice 5.
Jeder Slice startet erst, wenn der vorige committet, gepusht (sofern User
das Pushen freigibt) und im Reporting abgehakt ist.

---

## Slice 0 — README & Doku-Sync auf v0.9.0 (vor jedem Code-Touch)

**Ziel:** Doku entspricht dem Repo. Keine Code-Logik wird verändert.

**Begründung (aus Review §Faktenbasis + Kritische Probleme #2):** README
behauptet v0.8.0, 488+31 Tests und Frontend auf 5173 via Default-Compose.
Repo ist v0.9.0. Default-Compose baut den `prod`-Stage und veröffentlicht
Neo4j-Ports auf `0.0.0.0`.

**Änderungen:**
- `README.md`:
  - Header-Badge/Status-Block: `v0.8.0` → `v0.9.0`, Datum vom v0.9.0-Release.
  - Engineering-Stand (DE + EN) aus
    `docu/2026-05-01-v0.9.0-release-notes.md` ableiten.
  - Testzahlen aus `npm run check`-Output verifizieren (Backend + Frontend).
  - Schnellstart-Sektion: explizit dokumentieren, dass der Default-Compose
    aktuell den `prod`-Stage baut UND/ODER (sobald PR2 läuft) `target: dev`
    setzt. In Slice 0 nur den Faktenstand spiegeln, keine Kosmetik.
  - Neo4j-Browser auf `http://localhost:7474` nur erwähnen, wenn Slice 0
    auch klar markiert: „Bind aktuell auf `0.0.0.0`, wird in Slice 5 auf
    Loopback gehärtet."
- `docu/v1-development-log.md` (falls vorhanden): Eintrag „Doku-Sync
  v0.9.0 abgeschlossen".
- `docu/<YYYY-MM-DD>-slice-0-readme-v090-sync-arbeitsprotokoll.md`.
- `CHANGELOG.md`: `[Unreleased] → Docs`-Eintrag.

**Akzeptanzkriterien:**
- `grep -n "v0.8.0\|v0\\.8" README.md` liefert keine Treffer mehr.
- README-Testzahlen stimmen mit `npm run check` überein.
- `npm run check` grün.
- Genau 1 Commit mit Body `docs: sync README to v0.9.0 + flag known
  compose/neo4j drift (Slice 0)`.

---

## Slice 1 — Secure Defaults + Config-Validation (Review PR1)

**Ziel:** Keine offene API durch versehentlich übernommene Beispielwerte.

**Änderungen:**
- `.env.example`:
  - `FLASK_DEBUG=true` → `FLASK_DEBUG=false`.
  - Klarer Kommentar: `AGORA_AUTH_TOKEN` ist im Nicht-Debug Pflicht.
  - `SECRET_KEY` Platzhalter eindeutig als Placeholder kennzeichnen
    (`change-me-use-token_urlsafe-32`).
- `backend/app/config.py`:
  - `Config.validate()` lehnt im Nicht-Debug-Modus folgende Werte HART ab
    (raise `ValueError`/`ConfigError`):
    - `SECRET_KEY in {"", "change-me", "change-me-use-token_urlsafe-32",
      "agora", "password"}`
    - `AGORA_AUTH_TOKEN` leer und `AGORA_ALLOW_ANONYMOUS != "true"`
    - `NEO4J_PASSWORD in {"agora", "neo4j", "password", ""}`
- `backend/app/utils/auth.py`:
  - Keine Logikänderung, aber Audit-Log-Warnung, wenn der Guard im
    Debug-Modus zur No-Op wird.
- `tests/test_config_security.py` (neu):
  1. `FLASK_DEBUG=false` + leerer Token → `ConfigError`.
  2. `FLASK_DEBUG=false` + Placeholder-`SECRET_KEY` → `ConfigError`.
  3. `FLASK_DEBUG=false` + Placeholder-`NEO4J_PASSWORD` → `ConfigError`.
  4. `FLASK_DEBUG=true` + leerer Token → erlaubt, Warning geloggt.
  5. `FLASK_DEBUG=false` + alle Werte gesetzt → ok.
- README-Sicherheits-Sektion: kurzen, sicheren Token-Setup-Befehl
  ergänzen (`python -c "import secrets;print(secrets.token_urlsafe(32))"`).

**Akzeptanzkriterien:**
- `cd backend && uv run pytest tests/test_config_security.py` grün.
- `npm run check` grün.
- App startet bei `FLASK_DEBUG=false` mit Placeholder-Secret nicht.
- 1 Commit `feat(security): reject placeholder secrets and empty token in
  non-debug (Slice 1, PR1 of review)`.

---

## Slice 2 — Docker Compose Dev/Prod sauber trennen (Review PR2)

**Ziel:** Reproduzierbarer Schnellstart, keine Port-Verwirrung, Neo4j nicht
ungeschützt veröffentlicht.

**Änderungen:**
- `docker-compose.yml` (Dev):
  - `services.agora.build.target: dev` explizit setzen.
  - Backend/Frontend nur auf Loopback binden:
    ```yaml
    ports:
      - "127.0.0.1:${AGORA_BACKEND_PORT:-5001}:5001"
      - "127.0.0.1:${AGORA_FRONTEND_PORT:-5173}:5173"
    ```
  - Neo4j-Service-Ports:
    ```yaml
    ports:
      - "127.0.0.1:7474:7474"
      - "127.0.0.1:7687:7687"
    ```
- `docker-compose.prod.yml` (Override):
  - `services.agora.build.target: prod`.
  - Kein Frontend-Port `5173`. Hinweis-Kommentar: „Frontend hinter
    Reverse-Proxy ausliefern; nur `5001` intern."
  - Neo4j: keine Host-Port-Veröffentlichung.
- `Dockerfile`: Reihenfolge der Stages prüfen, sicherstellen, dass
  `target: dev` und `target: prod` beide bauen.
- README-Schnellstart aktualisieren: zwei klar getrennte Blöcke
  „Local dev (`docker compose up -d`)" und „Prod-like
  (`docker compose -f docker-compose.yml -f docker-compose.prod.yml
  up -d`)".
- `tests/test_compose_snapshot.py` (neu, optional `pytest-subprocess`):
  - `docker compose config` enthält `target: dev`.
  - Prod-Override enthält keinen `5173`-Port.

**Akzeptanzkriterien:**
- `docker compose config | grep -A2 target` zeigt `dev`.
- `docker compose -f docker-compose.yml -f docker-compose.prod.yml config`
  zeigt keinen Frontend-Port `5173`.
- `docker compose up -d --build` startet Vite auf `127.0.0.1:5173`.
- `npm run check` grün.
- 1 Commit `feat(deploy): split dev/prod compose, lock ports to loopback
  (Slice 2, PR2 of review)`.

---

## Slice 3 — Redis-basierte Single-Use-Tickets (Review PR3)

**Ziel:** Signed Tickets sind auch bei `--workers 2` global single-use.

**Änderungen:**
- `backend/app/utils/signed_ticket.py`:
  - `_seen`-Dict bleibt als Fallback, aber `consume(sig)` versucht zuerst
    Redis: `SET ticket:<sig> 1 NX EX <ttl>`; nur wenn `True` zurückkommt,
    gilt das Ticket als unverbraucht.
  - Wenn Redis nicht erreichbar UND `EVENT_BUS_BACKEND != "file"` UND
    `--workers > 1`: Logger-Warning + Fallback dokumentieren.
- `backend/app/utils/redis_client.py` (oder bestehender Client) für
  Verbindung wiederverwenden, kein zweites Connection-Pool-Setup.
- `tests/test_signed_ticket_redis.py` (neu, mit `fakeredis`):
  - Erstes Consume → ok.
  - Zweites Consume desselben Tickets → blockiert.
  - Simulation zweier Worker (zwei separate Funktionen, gleicher
    fakeredis-Server) → zweites Consume blockiert.
  - Ohne Redis: In-Memory-Pfad funktioniert + Warning.
- `docu/security-hardening.md`: Abschnitt zu Tickets aktualisieren.

**Akzeptanzkriterien:**
- `cd backend && uv run pytest tests/test_signed_ticket_redis.py` grün.
- `npm run check` grün.
- 1 Commit `fix(security): redis-backed single-use tickets for multi-worker
  gunicorn (Slice 3, PR3 of review)`.

---

## Slice 4 — CVE-Baseline aktiv abbauen (Review PR4)

**Ziel:** Ignorierte CVEs sind tracked, nicht stillschweigend dauerhaft.

**Änderungen:**
- `.github/workflows/ci.yml`:
  - Neben jeder ignorierten CVE Kommentar: `# expires: YYYY-MM-DD,
    issue: #N`.
- Pro ignorierter CVE 1 GitHub-Issue erstellen (über `gh issue create`)
  mit:
  - Paket, betroffene Version, Upstream-Pin, Risiko, Zielversion, Frist.
  - Label `security`, `dependency-baseline`.
- `docu/dependency-risk-register.md` (neu):
  - Tabelle: CVE | Paket | Owner | Frist | Status | Issue-Link.
- Evaluieren, ob `camel-oasis` in einem Subprozess/Container mit
  reduzierten Rechten isoliert werden kann; Ergebnis als Notiz im
  Risk-Register.

**Akzeptanzkriterien:**
- CI bleibt grün.
- `gh issue list --label dependency-baseline` zeigt einen Eintrag pro
  ignorierter CVE.
- `docu/dependency-risk-register.md` existiert mit allen Einträgen.
- 1 Commit `chore(security): track ignored CVEs in risk register, link
  CI ignores to issues (Slice 4, PR4 of review)`.

---

## Slice 5 — Frontend-Token-Härtung + XSS-Regression (Review PR5)

**Ziel:** Weniger Schaden bei XSS oder Browser-Plugin-Zugriff.

**Änderungen:**
- `frontend/src/api/index.js` (oder zentraler Auth-Helper):
  - `localStorage`-Pfad nur als Dev-Fallback dokumentieren.
  - Prod-Pfad: Token im Memory (z. B. `Pinia`-Store ohne Persist) oder
    Backend-Session mit `HttpOnly`-Cookie als Empfehlung in Doku.
  - Kein Breaking Change am API-Vertrag — Default-Verhalten bleibt
    gleich, aber `AGORA_TOKEN_STORAGE=memory|local` ENV im Frontend
    erlauben.
- `frontend/src/utils/markdown.js`:
  - DOMPurify-Konfig prüfen.
  - Tests für: `<script>`, `<img onerror>`, `[x](javascript:alert(1))`,
    `<iframe>`, `data:` URLs.
- `frontend/src/components/Step4Report.vue`:
  - Sicherstellen, dass Markdown nur durch sanitized Pipeline geht.
- `docu/auth.md` (neu): Token-Header, Ticket-Flow,
  Query-Token-Deprecation, localStorage-Risiko.

**Akzeptanzkriterien:**
- `cd frontend && npm test` grün, neue Markdown-XSS-Tests bestehen.
- `npm run check` grün.
- Bestehender Dev-Flow funktioniert (manuell prüfen: Login → Run
  starten → Report sehen).
- 1 Commit `feat(security): markdown xss regression + memory-token mode
  (Slice 5, PR5 of review)`.

---

# DEFINITION OF DONE (über alle Slices)
- Alle 6 Slices als 6 separate Commits, in dieser Reihenfolge.
- `npm run check` nach JEDEM Slice grün.
- `CHANGELOG.md` `[Unreleased]` enthält je Slice einen Eintrag.
- `docu/<datum>-slice-<n>-*-arbeitsprotokoll.md` existiert je Slice.
- README + `docu/security-hardening.md` + `docu/auth.md` +
  `docu/dependency-risk-register.md` reflektieren den neuen Stand.
- Keine echten Secrets in Git.
- Falls offene Issues durch einen Slice geschlossen werden:
  Commit-Body enthält `Closes #N`, Reporting nennt Milestone-Counter.

# REPORTING-FORMAT (nach jedem Slice an mich)
Schreibe genau diese Tabelle als Antwort:

| Slice | Commit | Lint | Tests | Doku | Notes |
|------:|--------|:----:|:-----:|:----:|-------|
| n | <hash> kurzbeschreibung | OK/FAIL | <count> OK | datei | offene punkte |

Plus:
- Welche Findings aus dem Review wurden adressiert (Liste).
- Welche Findings sind bewusst NICHT in diesem Slice (mit Grund).
- Welche neuen Issues wurden erstellt (mit Nummern + Link).
- Was schlägst du als nächsten Slice / Folge-Issue vor.

# STOP-CONDITIONS (sofort an mich zurück)
- `npm run check` rot und Ursache nicht trivial.
- Ein Finding aus dem Review verlangt ein Breaking Change.
- Repo-Realität widerspricht dem Review fundamental (z. B. Datei
  existiert nicht).
- Tests verlangen externe Services, die im Sandbox-Run nicht laufen
  (Neo4j, Redis, Ollama). Dann: Skip-Mechanismus dokumentieren, nicht
  Tests deaktivieren.
- Du musst Secrets generieren oder echte API-Keys verwenden.
- Du müsstest mehr als ~400 Zeilen Code in einem einzigen Slice ändern.

# AUSGABE BEIM START
Vor dem ersten Code-Touch antwortest du mit:
1. Bestätigung, welche Source-of-Truth-Files du gelesen hast (mit Pfaden).
2. Welche Findings im Repo-Stand schon erfüllt sind (mit Beweis).
3. Welche Slices du in welcher Reihenfolge planst.
4. Bitte um Freigabe für Slice 0.

Erst nach meiner Freigabe startest du mit Slice 0.
<<<END>>>
```
