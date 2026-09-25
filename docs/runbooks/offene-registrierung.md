# Offene Registrierung einrichten

Seit #1616 (ADR-0018, Plan §37) kann sich jeder mit bestätigter E-Mail-Adresse
registrieren. Er bekommt genau einen persönlichen Workspace. Zugang zu fremden
Workspaces vergeben nur deren Owner und Admins.

## 1) Ziel

Registrierung mit E-Mail-Bestätigung freischalten, ohne dass ein Konto ohne
bestätigte Adresse oder ein fremder Workspace erreichbar wird.

## 2) Voraussetzungen

- Supabase-Stack aus `supabase/` läuft (`bootstrap.sh`).
- Agora mit allen fünf Metadaten-Backends auf `postgres`, `DATABASE_URL` auf
  eine Rolle ohne RLS-Umgehung ([`rls-rollen.md`](rls-rollen.md)).
- Ein SMTP-Konto für Bestätigungs- und Reset-Mails.

## 3) Schritt-für-Schritt

1. SMTP und Registrierung in `supabase/.env` setzen:

   ```bash
   # Bestätigung ist Pflicht, sonst genügt eine fremde Adresse
   DISABLE_SIGNUP=false
   ENABLE_EMAIL_SIGNUP=true
   ENABLE_EMAIL_AUTOCONFIRM=false
   PASSWORD_MIN_LENGTH=12
   SMTP_HOST=<smtp-host>
   SMTP_PORT=587
   SMTP_USER=<smtp-user>
   SMTP_PASS=<smtp-passwort>
   SMTP_ADMIN_EMAIL=<absender@domain>
   # Ziel der Bestätigungslinks: die Agora-Oberfläche
   SITE_URL=https://<agora-host>
   ```

2. GoTrue neu starten:

   ```bash
   cd supabase
   docker compose up -d auth
   ```

3. JWT im Backend aktivieren (`.env` von Agora):

   ```bash
   AGORA_AUTH_BACKEND=hybrid
   AGORA_SUPABASE_JWT_ISSUER=https://<supabase-host>/auth/v1
   AGORA_SUPABASE_JWT_SECRET=<JWT_SECRET aus supabase/.env>
   # Öffentlich, für den Browser-Client
   AGORA_SUPABASE_URL=https://<supabase-host>
   AGORA_SUPABASE_ANON_KEY=<ANON_KEY aus supabase/.env>
   # Pflicht mit JWT
   AGORA_CORS_ALLOW_ALL=false
   ```

4. Backend neu starten und das Start-Log prüfen: Ein Konfigurationsfehler
   (fehlendes Backend auf `postgres`, `AGORA_ALLOW_ANONYMOUS`,
   `AGORA_CORS_ALLOW_ALL`) lässt JWT aus.

## 4) Überprüfung

```bash
# Erwartet: "jwt_enabled": true und die beiden öffentlichen Angaben
curl -s https://<agora-host>/api/auth/config

# Registrierung ohne Bestätigung liefert kein access_token
curl -s -X POST https://<supabase-host>/auth/v1/signup \
  -H "apikey: <ANON_KEY>" -H 'Content-Type: application/json' \
  -d '{"email":"test@example.org","password":"mindestens-12-zeichen"}'

# Nach Bestätigung und Login: persönlicher Workspace, beim zweiten Aufruf created=false
curl -s -X POST https://<agora-host>/api/workspaces/bootstrap \
  -H "Authorization: Bearer <access_token>" -H 'Content-Type: application/json' -d '{}'
```

## 5) Warum?

Ohne Bestätigung könnte jeder mit einer fremden Adresse ein Konto anlegen. Der
persönliche Workspace hängt an der Nutzer-ID; deshalb ist der Bootstrap
idempotent und öffnet keinen fremden Workspace. Registrierung schließen:
`DISABLE_SIGNUP=true`, bestehende Konten bleiben gültig.

## 6) Nächste Schritte

- Mitglieder einladen: `PUT /api/workspaces/current/members/<user_id>` als Owner oder Admin.
- Frontend-Login über den Supabase-Client (#1617).
- Realtime für Listen-Projektionen (#1618).
