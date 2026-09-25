# ADR-0018: Multi-User vor 1.0 — Workspaces, Supabase Auth, RLS, Realtime

- Status: Zeitpunkt abgelöst durch [ADR-0019](0019-multi-user-after-1-0.md) (2026-09-25): Multi-User erst nach 1.0. Die technischen Entscheidungen bleiben das Zielbild.
- Datum: 2026-09-25
- Löst ab: [ADR-0001](0001-auth-model.md) (Auth-Zielbild Single-User für v1.0),
  ROADMAP-Regel 4 („Kein Multi-User-/SaaS-/Kubernetes-Ausbau vor einem
  belastbaren Single-User-1.0“)
- Bezug: Epic [#1610](https://github.com/arn0ld87/agora/issues/1610),
  [`docs/plans/supabase.md`](../plans/supabase.md) §14–18, §22, §23, §37

## Kontext

Der Supabase-Plan hat Workspaces (PR 5, §16), Supabase Auth und JWT (PR 10/11,
§14/15), Row Level Security (PR 12, §17/18) sowie Frontend-Client und Realtime
(§22/23) bis nach 1.0 zurückgestellt. ADR-0001 hat für v1.0 ein Single-User-Modell
mit geteiltem Token festgelegt. Am 2026-09-25 hat der Owner beides aufgehoben:
Die Punkte werden jetzt umgesetzt.

Stand der Metadaten: Fünf PostgreSQL-Adapter sind gebaut (LLM-Profile, Projekte,
Simulationen, Runs, Reports), alle per Schalter und im Default aus. Der
Produktiv-Cutover ist [#1592](https://github.com/arn0ld87/agora/issues/1592).
Heute authentifiziert `backend/app/utils/auth.py` über einen Master-Token
(`AGORA_AUTH_TOKEN`), Workspace-API-Keys (`ago_…`) und signierte Tickets. Eine
Identität gibt es nicht.

Zur Nummer: ADR-0016 und ADR-0017 sind im Code bereits für den Decision-Layer
vergeben (f005, #1547), auch wenn unter `docs/decisions/` keine Datei dafür liegt.
Dieses ADR trägt deshalb die 0018.

## Entscheidung

### 1. Identität: ein `Principal` für jeden Zugriffsweg

Jeder authentifizierte Request erzeugt einen `Principal` (Vertrag in
`backend/app/contracts/auth_contract.py`) mit `auth_type`
(`jwt | api_key | master_token | anonymous`), `user_id`, `workspace_id`, `roles`
und `scopes`. Autorisierung liest nur den Principal, nie eine vom Frontend
behauptete `workspace_id`.

### 2. Auth-Modi: `AGORA_AUTH_BACKEND=legacy|hybrid|supabase`, Default `hybrid`

| Modus | Reihenfolge | Master-Token |
|---|---|---|
| `legacy` | Master-Token → `ago_`-Key → Ticket (heutiger Pfad) | ja |
| `hybrid` (Default) | Supabase-JWT → `ago_`-Key → Master-Token → Ticket | ja |
| `supabase` | Supabase-JWT → `ago_`-Key → Ticket | abgelehnt |

Ein unbekannter Wert ist ein Startfehler, es gibt keinen Fallback.
Legacy-Principals (Master-Token, bestehende `ago_`-Keys) arbeiten im
Default-Workspace mit Rolle `owner`.

### 3. Sicherheitsinvariante: JWT nur mit vollständigem PostgreSQL-Backend

Der JWT-Zweig ist **nur** aktiv, wenn JWT konfiguriert ist
(`AGORA_SUPABASE_JWT_ISSUER` plus `AGORA_SUPABASE_JWKS_URL` oder
`AGORA_SUPABASE_JWT_SECRET`). Ist er konfiguriert, verlangt `Config.validate()`,
dass **alle fünf** Metadaten-Backends auf `postgres` stehen und `DATABASE_URL`
gesetzt ist, sonst bricht der Start ab. Grund: Die Datei-Backends kennen keine
Workspaces. Ein Nutzer sähe über sie die Daten aller anderen.

`hybrid` ohne JWT-Konfiguration verhält sich exakt wie `legacy`, und der Startlog
sagt das ausdrücklich. So bleibt der Default für lokale Entwicklung und CI ohne
Supabase-Instanz lauffähig, ohne dass der JWT-Zweig still halb aktiv ist.

### 4. JWT-Prüfung (§15)

Geprüft werden Signatur (JWKS mit Cache-TTL oder HS256-Secret), `iss`, `aud`
(Default `authenticated`), `exp`/`nbf` sowie `sub` als UUID. Eine
Algorithmus-Allowlist schließt `alg=none` und eine Verwechslung von HS und RS
aus. Weder Token noch Claims landen im Log. Der aktive Workspace kommt aus
`X-Agora-Workspace` und gilt nur mit bestätigter Mitgliedschaft; ohne Header und
bei genau einer Mitgliedschaft gilt diese.

### 5. Workspace-Modell (§16)

`agora.workspaces` und `agora.workspace_members` (Rollen `owner`, `admin`,
`member`, `viewer`). Die Migration legt einen Default-Workspace mit fester UUID
an. `workspace_id` wird auf allen fünf Metadaten-Tabellen Pflicht; der Bestand,
auch der Produktivbestand nach #1592, wird per Alembic auf den Default-Workspace
zurückgeschrieben. Zusammengesetzte Fremdschlüssel (`(id, workspace_id)`)
verhindern Referenzen über Workspace-Grenzen. `workspace_members.user_id` hat
keinen FK auf `auth.users`, weil die CI mit reinem PostgreSQL ohne
Supabase-Schema läuft.

### 6. Row Level Security (§17/18)

Alle Metadaten- und Workspace-Tabellen bekommen `ENABLE` und `FORCE ROW LEVEL
SECURITY`. Flask verbindet sich zur Laufzeit mit einer Rolle ohne Superuser, ohne
`BYPASSRLS` und ohne Tabellen-Ownership. Im JWT-Modus prüft das ein Start-Gate.
Alembic läuft über eine eigene Owner-URL. Je Transaktion setzt die Session
`SET LOCAL app.workspace_id` und `app.user_id`. Arbeit ohne Request (etwa die
Start-Reconciliation der Run-Registry) läuft nur über eine explizite
System-Session. RLS ist die zweite Schranke: Die Repositories filtern weiterhin
selbst nach `workspace_id`. Die Testmatrix aus §18 ist Abnahmekriterium.

### 7. Offene Registrierung mit §37-Härtung

Selbstregistrierung ist erlaubt. Dafür sind Pflicht:

- E-Mail-Bestätigung (`GOTRUE_MAILER_AUTOCONFIRM=false`, SMTP konfiguriert)
- GoTrue-Rate-Limits
- Mindestlänge fürs Passwort
- exakte `SITE_URL`/Redirect-Allowlist ohne Wildcards
- CORS-Allowlist in Flask
- Rate-Limits auf Auth- und Workspace-Endpunkten

Captcha ist optional. Der erste Login legt über einen expliziten, idempotenten
Endpunkt einen persönlichen Workspace mit Rolle `owner` an. Das geschieht nicht
als Nebeneffekt des Guards.

### 8. Frontend (§22)

`@supabase/supabase-js` wird **nur** für Auth verwendet: Login, Registrierung,
Logout, Session-Refresh und Passwort-Reset. Fachdaten laufen weiter über
Vue → Flask; das Frontend bekommt keine Schreibrechte auf Tabellen. Der Axios-Interceptor sendet
`Authorization: Bearer` und `X-Agora-Workspace`; der Legacy-Token-Pfad bleibt
für `legacy`.

### 9. Realtime nur für Listen (§23)

Ein Supabase-Realtime-Dienst veröffentlicht Änderungen an Projekten,
Simulationen, Runs und Reports, gefiltert durch RLS für die Rolle
`authenticated`. Das Frontend nutzt ein Event nur als Signal zum Neuladen über
die Flask-API und nicht als Datenquelle. Das SSE für laufende Läufe bleibt
unverändert.

## Konsequenzen

- ROADMAP-Regel 4 entfällt; „Team-/Rollenmodell und Multi-User“ steht nicht mehr
  unter „Nach 1.0.0“. Die übrigen 1.0-Regeln gelten weiter.
- Der Punkt aus ADR-0001, dass Agora v1.0 kein Multi-User-Tenancy-Modell hat, gilt
  nicht mehr. Die dort gehärteten Mechanismen gelten unverändert: signierte
  Tickets, `?token=`-Sperre in Prod und das Bundle-Token-Gate. Tickets werden
  zusätzlich an `user_id`/`workspace_id` gebunden.
- Die Angriffsfläche wächst: öffentliche Registrierung, Mail-Versand und
  JWT-Parsing. Deshalb ist §37 kein „später“ mehr, sondern Teil von M6.
- Das Single-User-Profil (`user_profile_store.py`, ADR-0008) und das
  Workspace-LLM-Routing bleiben vorerst prozessweit. Sie pro Nutzer oder pro
  Workspace zu schneiden, ist eine eigene Folgeentscheidung.
- Umsetzung in acht Tickets unter #1610. Die Alembic-Kette läuft strikt seriell
  (Workspaces → `workspace_id` → RLS).

## Nicht entschieden

- pgvector und `PostgresGraphStorage` (§24/25), LLM-Secrets in DB/Vault (§26):
  bleiben zurückgestellt.
- Kubernetes, Federation, gehostete Betriebsmodelle: unverändert nach 1.0.
