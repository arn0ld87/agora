# Slice 12 (Repo-Review-Folge, F5): Test-Coverage SSRF + Upload + Cypher + Auth-Mode

**Datum:** 2026-05-01
**Branch:** `claude/slice-12-test-coverage` (Worktree)
**Bezug:** [`docu/2026-05-01-v0.9.0-review-folge-slices-plan.md`](2026-05-01-v0.9.0-review-folge-slices-plan.md), Sub-Slice F5.

## Ziel

Die im Repo-Review explizit geforderten Sicherheits-Regression-Tests
schreiben. Code existierte zwar fuer SSRF-Blocker, Upload-Limits und
Cypher-Label-Sanitizer, war aber entweder nur indirekt oder gar nicht
durch dedizierte Test-Dateien gepinnt — eine Refactor-Aenderung an einem
dieser Pfade haette den Audit silently brechen koennen.

## Ausgangslage

- F5-Scope laut Plan:
  - `test_ssrf_blocker.py` — Cases: `localhost`, `127.0.0.1`,
    `10.0.0.1`, `169.254.169.254`, IPv6 `::1`, IPv6 link-local,
    valider externer Host. Targeting: `backend/app/services/web_tools.py`.
  - `test_upload_limits.py` — Cases: zu grosse Datei (>50 MB), falsche
    Endung, PDF-ohne-Magic-Header, Path-Traversal-Filename
    (`../../etc/passwd`), zulaessige Datei. Targeting:
    `backend/app/utils/file_parser.py` + Upload-Endpoint.
  - `test_cypher_label_sanitizer.py` — Cases: Backticks im Entity-Type,
    uebermaessig lange Labels, Sonderzeichen, leere Strings, regulaerer
    Label. Targeting: `backend/app/storage/neo4j_write.py`
    Label-Sanitizer (de-facto in `neo4j_mappings.sanitize_label`).
  - **Bonus**: `test_anonymous_in_healthcheck.py` — `AGORA_ALLOW_ANONYMOUS=true`
    taucht im Health-Endpoint auf.
- Akzeptanz: alle neuen Tests gruen, bestehende Tests gruen, `npm run check`
  gruen, Test-Counter im README-Status-Block aktualisiert.
- Code-Stand:
  - `_is_public_url(url)` in `web_tools.py`: prueft is_private/loopback/
    link_local/multicast/reserved/unspecified plus expliziten Metadata-IP-
    Blacklist (`169.254.169.254`, `fd00:ec2::254`); rejected
    Non-`http(s)`-Schemes vor DNS.
  - `Config.MAX_CONTENT_LENGTH = 50 * 1024 * 1024`,
    `Config.ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}`.
  - `allowed_file()` in `api/graph.py:41` prueft Extension + PDF-Magic
    (`%PDF`).
  - `ProjectManager.save_file_to_project()` in `models/project.py:241`
    nutzt `werkzeug.utils.secure_filename`, generiert UUID-Filename und
    macht defensiven Prefix-Check `os.path.abspath(file_path).startswith(
    os.path.abspath(cls.PROJECTS_DIR))`.
  - `sanitize_label()` in `storage/neo4j_mappings.py:36` mit Regex
    `^[A-Za-z_][A-Za-z0-9_]{0,49}$`; rejected `Entity` und Non-Strings.

## Vorgehen

1. **`tests/test_ssrf_blocker.py`** (10 Tests): parametrisierte
   Negativ-Cases ueber `monkeypatch` von `socket.getaddrinfo` (kein
   Netz-Zugriff in CI, deterministische IPs). Der Plan-Case
   `169.254.169.254 → "metadata"` greift im Code via
   `is_link_local`-Check vor der expliziten Metadata-Klausel — die
   Test-Assertion wurde auf den Reject-Effekt (nicht auf den
   Reason-String) gelockert mit erklaerendem Kommentar. Zusatz-Cases:
   Multi-Result-DNS (eine private IP unter mehreren), Unsupported-Scheme,
   DNS-Resolve-Fail.
2. **`tests/test_upload_limits.py`** (10 Tests): Werkzeug-`FileStorage`-
   Fixtures fuer Extension/Magic-Byte-Check; Path-Traversal-Test geht
   ueber `ProjectManager.save_file_to_project` direkt mit
   `monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", tmp_path)`,
   damit kein Test-FS-Mount noetig ist. `Config.MAX_CONTENT_LENGTH` als
   statischer Pin-Test ohne Live-Endpoint (Werkzeug enforces den Limit
   im `request.files`-Pfad — End-to-End-Test waere flaky und out-of-scope
   fuer diesen Slice).
3. **`tests/test_cypher_label_sanitizer.py`** (27 Tests): parametrisiert
   ueber legitime Labels, Backtick-Injection-Varianten, Hard-Rejects
   (leer, `Entity`, `1stClass`, `A` × 51, Specials-only, Unicode),
   Non-String-Inputs (`None`, `int`, `float`, `list`, `dict`, `bytes`)
   plus 50-vs-51-Char-Edge. Bewusste Doppelung mit
   `tests/test_neo4j_mappings.py` — die F5-Forderung war eine **eigene**
   Test-Datei unter audit-erkennbarem Namen.
4. **Auth-Mode-Bonus**: kleine Code-Erweiterung in
   `backend/app/api/status.py` — neue Funktion `_get_auth_mode()`
   klassifiziert in vier Werte (`token`, `anonymous`, `open`,
   `misconfigured`) mit dokumentierten Praezedenz-Regeln. Wird in
   `_get_backend_status()` als neues Feld `auth_mode` aufgenommen.
   Operator sieht damit per `/api/status.backend.auth_mode`, ob jemand
   heimlich `AGORA_ALLOW_ANONYMOUS=true` gesetzt hat.
5. **`tests/test_anonymous_in_healthcheck.py`** (7 Tests): autouse-
   `monkeypatch.delenv` fuer alle drei relevanten Env-Variablen, dann
   sechs Modus-Cases plus ein Payload-Smoke-Test (`auth_mode`-Feld
   landet wirklich im Backend-Status-Dict).
6. **README-Counter**: drei Stellen aktualisiert (Top-Banner, DE
   `Engineering-Stand`, EN `Engineering status`) — neue Werte
   **744 Backend + 52 Frontend = 796 Tests gruen** (+85 vs. v0.9.0-Tag).
7. **CHANGELOG `[Unreleased] › Security`** Block fuer Slice 12.
8. **Lint-Fix**: `import os` aus `tests/test_upload_limits.py` entfernt
   (Ruff F401, eine unused-import-Zeile).
9. `npm run check` als Gate, danach Commit + PR + Merge.

## Geaenderte / neue Dateien

| Datei | Aktion | Cases |
|---|---|---|
| `backend/tests/test_ssrf_blocker.py` | neu | 10 |
| `backend/tests/test_upload_limits.py` | neu | 10 |
| `backend/tests/test_cypher_label_sanitizer.py` | neu | 27 |
| `backend/tests/test_anonymous_in_healthcheck.py` | neu | 7 |
| `backend/app/api/status.py` | edit (`_get_auth_mode()` + `auth_mode`-Feld in `_get_backend_status()`) | — |
| `README.md` | edit (Test-Counter DE/EN + Top-Banner) | — |
| `CHANGELOG.md` | edit (`[Unreleased] › Security` Slice-12-Block) | — |
| `docu/2026-05-01-slice-12-test-coverage-arbeitsprotokoll.md` | neu | dieses File |

**Gesamt-Test-Delta:** +54 Backend (690 → 744). Frontend unveraendert
bei 52 (Slice 11/12 sind reine Backend-Slices).

## Verifikation

- `uv run pytest tests/test_ssrf_blocker.py -v` → 10 passed.
- `uv run pytest tests/test_upload_limits.py -v` → 10 passed.
- `uv run pytest tests/test_cypher_label_sanitizer.py -v` → 27 passed.
- `uv run pytest tests/test_anonymous_in_healthcheck.py tests/test_status.py -v` → 15 passed (7 neu, 8 Bestand).
- `npm run check` → 744 Backend + 52 Frontend gruen, Build OK.

## Akzeptanzkriterien (laut Plan)

- [x] Alle vier Test-Dateien existieren und enthalten die geforderten
      Cases.
- [x] Bestehende Tests gruen.
- [x] `npm run check` gruen.
- [x] Test-Counter im README-Status-Block aktualisiert.

## Issue / Milestone

- F5 ist Folge-Plan, kein offenes GitHub-Issue mit `Closes #N`.
- Repo-Review-Folge ohne Milestone-Counter.

## Followups

- F6 — Branch-Cleanup + README-Update (letzter Sub-Slice des
  Folge-Plans).
- Optional: docu/operations.md erwaehnt `/api/health/auth` — der neue
  `auth_mode`-Pfad in `/api/status` deckt das Use-Case ab; ein eigener
  `/api/health/auth`-Endpoint waere Redundanz und ist nicht geplant.

## Out-of-Scope

- End-to-End-Test fuer den `MAX_CONTENT_LENGTH`-Cap (Werkzeug rejected
  >50 MB im `request.files`-Pfad mit `RequestEntityTooLarge`). Live-
  Endpoint-Test ist flaky und ausserhalb der F5-Akzeptanz; der statische
  Pin auf `Config.MAX_CONTENT_LENGTH == 50 * 1024 * 1024` reicht zur
  Drift-Sicherung.
- Migration der `test_neo4j_mappings.py`-Sanitizer-Cases in die neue
  Datei. Das Repo-Review verlangt einen audit-erkennbaren Namen — wir
  liefern den, ohne den Bestand zu beruehren. Dedup als
  Tech-Debt-Folge-Slice.
