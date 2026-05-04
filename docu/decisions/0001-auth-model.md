# ADR-0001 — Auth-Zielbild für v1.0

**Status:** Accepted (User-Sign-off via Merge PR #277, 2026-05-04)
**Datum:** 2026-05-04
**Accepted:** 2026-05-04
**Slice:** M10.4
**Autor:** arn0ld87 + Claude Opus 4.7
**Bezug:** [`PLAN.md § Status-Sync 2026-05-04`](../../PLAN.md#status-sync-2026-05-04), [`docu/plan.heuristic.md § ADR-0001 Local-first`](../plan.heuristic.md), Issue [#106](https://github.com/arn0ld87/agora/issues/106)

---

## Kontext

Agora ist seit der Fork-Linie (MiroFish-Offline → Agora) als **lokal-first**-Simulator konzipiert. Die Auth-Architektur ist heute:

- **Single Shared Token** (`AGORA_AUTH_TOKEN`) im Header `X-Agora-Token` oder `Authorization: Bearer <token>`. Pflicht im Non-Debug, sonst weigert sich `Config.validate()` zu starten.
- **Signed Tickets** (P0.2) für URL-bound Endpunkte — `POST /api/auth/ticket` gibt 60 s gültige, scope-bound, single-use Tickets aus (`sse:<id>`, `download:report:<id>`, `download:simulation_config:<id>`, `download:simulation_script:<id>`, `llm-stream`). Implementiert in [`backend/app/api/auth.py`](../../backend/app/api/auth.py) und [`backend/app/utils/signed_ticket.py`](../../backend/app/utils/signed_ticket.py). Default-TTL 60 s, Max-TTL 300 s.
- **Query-Token-Block** in Prod (F2.2): `?token=` wird im Non-Debug-Modus mit Logger-Error abgelehnt, SSE/Downloads müssen Tickets nutzen.
- **Bundle-Token-Gate** (F2.1): `Dockerfile` ARG `ALLOW_BUILD_TIME_TOKEN=false` als Default — Frontend bekommt keinen Token einkompiliert, sondern setzt ihn zur Laufzeit per `setAgoraToken()`.
- **Loopback-Default**: Compose bindet auf `127.0.0.1`, Override für Tailnet/LAN über `AGORA_BIND_HOST=0.0.0.0`.

**Was fehlt für v1.0:**

- Kein User-Konzept — der Shared Token ist nicht an eine Identität gebunden.
- Kein Logout (außer „Token aus dem Frontend-Storage löschen").
- Keine Token-Rotation außer Container-Neubau mit neuem `AGORA_AUTH_TOKEN`.
- Kein Audit-Trail wer wann was getan hat.
- Kein Rollen- oder Berechtigungskonzept.
- Keine Multi-User-Tenancy.

**Auslöser für diesen ADR:** PLAN.md führt M10.4 als „Auth-Zielbild-ADR" als kritischen Hardening-Block. ROADMAP-v1.0-Eintrag „AuthN/AuthZ — beyond the current optional `AGORA_AUTH_TOKEN`" verlangt eine Entscheidung. Issue #106 (Reverse-Proxy) ist faktisch durch M9.6 closeable, aber die Auth-Frage bleibt offen.

---

## Optionen

### Option A — Single-User-only-v1 (formalisieren)

**Was:** Status quo mit expliziter Single-User-Garantie. README/SECURITY/`/api/status` deklarieren: „Agora v1.0 ist ein lokaler/Tailnet-Single-User-Simulator. Multi-User ist Out-of-Scope."

**Implementation:**

- Keine Code-Änderung am Auth-Pfad.
- README + `docu/security-hardening.md` ergänzen explizite Warnung: „Public-Internet-Deployment nicht supported. Für Mehrbenutzer-Betrieb ist v2 in Planung."
- `/api/status` liefert `auth_mode: "single_user_token"`.
- Token-Rotation: dokumentiert als Container-Neubau-Prozedur in `docu/security-hardening.md`.

**Vor:**
- Null Aufwand. Code ist da, Tests sind grün.
- Passt zum Local-first-Kernprinzip (ADR-0001 in plan.heuristic.md).
- v1.0 wird realistisch in 4-6 Wochen erreichbar.
- Signed Tickets + Bundle-Gate + `?token=`-Block sind bereits hardened — die Hauptangriffsvektoren sind zu.

**Nach:**
- Kein Audit, keine Rotation ohne Restart, kein Multi-User-Pfad.
- v2 muss komplett neu geschnitten werden, wenn Multi-User real wird.
- Einige Marketing-/Verkaufs-Use-Cases (z.B. SaaS-Variante) sind ausgeschlossen.

### Option B — HttpOnly-Session (Server-Side-Sessions)

**Was:** Echtes User-Modell mit Login-Page, Cookie-Session (HttpOnly + Secure + SameSite=Strict), Server-Side-Session-Store in Redis. Multi-User-fähig.

**Implementation:**

- Backend: `flask-login` (oder ähnliches) + Redis-Session-Backend.
- Login-Endpunkt `POST /api/auth/login` mit Username/Passwort, setzt HttpOnly-Cookie.
- Logout-Endpunkt `POST /api/auth/logout` invalidiert Session in Redis.
- User-Tabelle in Neo4j oder SQLite (Argon2-Passwort-Hashes).
- Frontend: Login-View, automatischer Redirect bei 401, Cookie-basiertes Auth (kein localStorage-Token mehr).
- SSE/Downloads: Tickets bleiben (Cookie funktioniert für `EventSource` über Same-Origin).
- Bundle-Token-Pfad bleibt für Backwards-Compatibility, wird deprecated.

**Vor:**
- Echtes User-Modell mit Logout, Audit, Rotation pro User.
- Gut bekannt, viele Tutorials, niedrige Angriffsfläche bei sauberer Implementation.
- Multi-User-fähig ohne weitere Architekturänderung.
- Kein Token-Leak-Risiko (HttpOnly = JavaScript hat keinen Zugriff).

**Nach:**
- ~3-4 Wochen Implementations-Aufwand (Backend + Frontend + Tests + Migration).
- v1.0-Termin verschiebt sich.
- CSRF-Schutz wird nötig (zusätzlicher Aufwand).
- Public-Internet-Deployment wäre zwar möglich, aber dann braucht es Rate-Limits, Brute-Force-Schutz, Password-Reset-Flow — alles weiteres Scope.
- Lokaler Single-User-Use-Case wird umständlicher (jede Sim-Session = Login).

### Option C — Bearer + Refresh-Token

**Was:** OAuth2-ähnliches Modell — kurzlebige Access-Tokens (15 min), langlebige Refresh-Tokens (30 Tage). User-Tabelle wie in B, aber API-Auth über `Authorization: Bearer <jwt>`.

**Implementation:**

- Backend: JWT-Library, Token-Issue-Endpunkt, Refresh-Endpunkt.
- Token-Blacklist in Redis (für Logout).
- Frontend: Token-Refresh-Interceptor in Axios, kein Cookie.
- SSE: signed tickets bleiben (oder Bearer im Header — aber `EventSource` kann das nicht, also Tickets).

**Vor:**
- Multi-User-fähig + Stateless (Access-Token).
- Skaliert horizontal ohne Sticky Sessions.
- Industriestandard für API-First-Apps.

**Nach:**
- Höchster Implementations-Aufwand (~4-6 Wochen): JWT-Generierung, Refresh-Flow, Blacklist-Sync, Frontend-Interceptor, Tests.
- Refresh-Token-Storage im Frontend ist heikel (XSS-Risiko bei localStorage, HttpOnly-Cookie bringt's wieder zurück zu Option B).
- Stack-Komplexität: Local-first + JWT-Refresh fühlt sich oversized an.
- v1.0-Termin verschiebt sich deutlich.

---

## Entscheidung (Vorschlag)

**Option A: Single-User-only-v1 explizit machen.**

### Begründung

1. **Local-first ist das Kernprinzip** ([ADR-0001 in `plan.heuristic.md`](../plan.heuristic.md)). LLM-/Embedding-/Graph-Workloads sind teuer, langsam, schwer multi-tenant-sicher. Lokale Ollama-/Neo4j-Setups passen zum ursprünglichen Use Case.
2. **Die Hauptangriffsvektoren sind bereits geschlossen:**
   - Bundle-Token-Gate (F2.1) ✅
   - `?token=`-Block in Prod (F2.2) ✅
   - Signed tickets für URL-bound Auth (P0.2) ✅
   - Loopback-Default (S3) ✅
   - Container-Hardening (`no-new-privileges`, `cap_drop: ALL`, tmpfs) ✅
   - Config fail-fast (S2) ✅
3. **Aufwand-Nutzen-Verhältnis:**
   - v1.0 ist ein 4-6-Wochen-Ziel laut PLAN.md M11/M12/M13.
   - Option B/C würde v1.0 um mindestens 4 Wochen verschieben.
   - Real existierende Use-Cases sind Solo-Devs auf Tailnet/Localhost — kein dokumentierter Multi-User-Bedarf.
4. **Migrationspfad bleibt offen:**
   - Wenn ein konkreter Multi-User-Use-Case kommt (z.B. Klassenraum, Forschungsgruppe), kann v2 mit Option B nachgeschoben werden.
   - Die signed-ticket-Infrastruktur ist multi-user-kompatibel (Tickets sind scope-bound, nicht user-bound — kann erweitert werden).
5. **Ehrlichkeit gegenüber Operatoren:** Eine explizite Single-User-Garantie ist ehrlicher als ein halbgar implementiertes Multi-User-Modell, das in der Praxis nicht ausreichend gehärtet ist (Rate-Limits, Audit, Brute-Force-Schutz fehlen).

---

## Konsequenzen

### Aus der Entscheidung folgt

- **README + `docu/security-hardening.md`** bekommen einen klaren Block: „Agora v1.0 ist Single-User-Only. Public-Internet-Deployment ist nicht supported. Für Mehrbenutzer-Betrieb v2 abwarten oder eigenes Auth-Frontend zwischen Proxy und Backend setzen."
- **`/api/status`** liefert `auth_mode: "single_user_token"` (kleines Code-Update in `backend/app/api/status.py`).
- **`/api/version`** (M13.1) liefert zusätzlich `auth_model: "single_user_v1"` für Operator-Transparenz.
- **Token-Rotation-Prozedur** wird in `docu/security-hardening.md` dokumentiert: Stop-Container, neuer `AGORA_AUTH_TOKEN` in `.env`, Container-Rebuild, Frontend setzt neuen Token zur Laufzeit. Kein File-System-State-Verlust.
- **Rate-Limits** (M10.5) bleiben Pflicht — Single-User schützt nicht vor Brute-Force auf gestohlenen Token oder Abuse über offene Endpunkte.
- **Issue #106** (Reverse-Proxy) bleibt aktiv-relevant: Tailnet-Deploys brauchen Proxy-Termination (Tailscale Funnel, Cloudflare Tunnel) — Single-User-only heißt nicht „auf Internet exponieren".

### Aus der Entscheidung folgt **nicht**

- Kein User-Konzept im Backend nötig.
- Keine Login-View im Frontend nötig.
- Kein Session-Store nötig.
- Kein JWT-Stack nötig.

### Hardstops für v1.0

- **Keine Public-Internet-Werbung** für Agora bis v2 mit echtem Auth-Modell.
- **Keine Marketing-Aussagen wie „Multi-User-Simulator"** — Agora ist Single-User-Local-First.
- **Keine `?token=`-Reaktivierung** in Prod (Hardstop ist code-verifiziert in `backend/app/utils/auth.py::_extract_token`).

### Trigger für v2-ADR (= ADR-0001 wird durch v2-ADR ersetzt)

Wenn eine der folgenden Bedingungen wahr wird, ist ein neuer ADR Pflicht:

- Konkreter Multi-User-Use-Case (Klassenraum, Forschungsgruppe, SaaS-Beta) wird beauftragt.
- Public-Internet-Deployment wird beworben.
- Audit-Trail-Anforderung von außen (z.B. Compliance, DSGVO bei Multi-User-Daten).
- Rollen/Permissions-Granularität wird im Frontend gefordert.

---

## Alternativen, die wir verworfen haben

- **Option B (HttpOnly-Session):** Korrekt, aber für v1.0 oversized. Reservieren für v2.
- **Option C (Bearer+Refresh):** Stack-Komplexität passt nicht zu Local-first. Verworfen.
- **Hybrid Single-User + Multi-User-Opt-In:** Operator-Verwirrung, doppelte Code-Pfade, doppelte Tests. Verworfen.

---

## Umsetzung

Diese ADR braucht **keine Code-Änderung im Auth-Pfad**. Was nachgezogen werden muss (separate Slices):

1. **Doku-Slice** (Haiku, ~1 Tag):
   - README + `docu/security-hardening.md` Single-User-Block ergänzen.
   - `/api/status` `auth_mode`-Feld dokumentieren.
   - Token-Rotation-Prozedur dokumentieren.
2. **Code-Slice** (Sonnet, ~½ Tag):
   - `backend/app/api/status.py`: `auth_mode: "single_user_token"` hinzufügen.
   - Test in `tests/api/test_status.py` ergänzen.
3. **M10.5 Rate-Limits** (Sonnet, ~1-2 Tage): bleibt eigener Slice, nicht Teil von M10.4.
4. **M13.1 `/api/version`** (Sonnet, ~½ Tag): `auth_model`-Feld bei Implementierung mitnehmen.

---

## Offen für User-Sign-off

Diese ADR ist **proposed**, nicht **accepted**. Sign-off-Optionen für den User:

- **(A) Akzeptieren wie vorgeschlagen** — Status auf „Accepted" setzen, Umsetzungs-Slices 1+2 als Followups planen.
- **(B) Andere Option wählen** — Status bleibt „Proposed", neue ADR-Version mit Option B oder C als Entscheidung.
- **(C) Vertagen** — Status auf „Deferred" setzen, M10.4 bleibt offen, User entscheidet später.

Default bei Schweigen: (A) — passt zum Local-first-Kernprinzip und dem v1.0-Zeitplan.
