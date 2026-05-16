# AGORA_SECRET_KEY Lifecycle

**Stand:** 2026-05-15
**Scope:** Wie der Fernet-Master-Key für den Multi-Provider-Hub
(`backend/data/llm_provider_secrets.json`) erzeugt, sicher gespeichert,
rotiert und im Verlustfall wiederhergestellt wird.
**Related:** [`backup-restore.md`](backup-restore.md),
[`security-threat-model.md`](security-threat-model.md), Issue
[#450](https://github.com/arn0ld87/agora/issues/450) P1.4.

---

## Was ist `AGORA_SECRET_KEY`?

Ein **URL-safe base64-kodierter 32-Byte-Schlüssel** (Fernet-Format), den
Agoras `LlmProviderSecretsStore` zum Verschlüsseln der gespeicherten
Provider-API-Keys nutzt. Pro Provider werden Klartext-Keys nur kurzzeitig
im Backend-Speicher gehalten und sofort als Fernet-Ciphertext in
`backend/data/llm_provider_secrets.json` (Mode `0600`) persistiert.

**Konsequenz:** Wer `AGORA_SECRET_KEY` und die JSON-Datei hat, kann jeden
Provider-Key im Klartext rekonstruieren. Wer nur die JSON-Datei hat, hat
einen unbenutzbaren Fernet-Ciphertext.

---

## Key erzeugen

Einmalig pro Deployment. Lokal:

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Output ist ein 44-Zeichen-String (z. B. `Tx8N…=`). Diesen Wert
**niemals** in Slack, E-Mail oder Tickets pasten.

---

## Sicher speichern

Reihenfolge nach Aufwand × Sicherheit (steigend):

1. **Repo-`.env`** (lokales Single-User-Setup). `.env` ist via
   `.gitignore` ausgeschlossen — Pflicht-Check vor jedem `git push`. Auf
   dem Host mit `chmod 600 .env` schließen.
2. **Passwort-Manager** mit 1Password-CLI / Bitwarden / `pass`:
   ```bash
   pass insert agora/AGORA_SECRET_KEY
   # später in .env injecten:
   echo "AGORA_SECRET_KEY=$(pass agora/AGORA_SECRET_KEY)" >> .env
   ```
3. **Systemd-CredentialsLoad** (Linux-Prod):
   ```ini
   [Service]
   LoadCredential=agora_secret_key:/etc/agora/secret_key
   Environment="AGORA_SECRET_KEY_FILE=%d/agora_secret_key"
   ```
   Agora liest den Wert aus `.env` direkt — wer Credentials-Loader nutzt,
   exporiert die Variable über ein Wrapper-Script vor `docker compose up`.
4. **Hardware-Token / Hashicorp-Vault** — wenn die Threat-Model-Stufe es
   verlangt.

Hinweise:

- Der Key **nicht** versionieren. Auch nicht in einem privaten Repo. Auch
  nicht für „nur Dev-Stuff" — Dev-Keys leaken regelmäßig in Stack-Traces.
- Wenn `.env` auf einen anderen Host kopiert wird (Restore-Drill, Migration),
  immer mit `scp -i`, niemals per Slack.

---

## Routine-Check (Doctor-Script)

`scripts/llm-secrets-doctor.py` ist die Operator-CLI, um den Key + Store
zu prüfen.

```bash
# Schnelle Status-Anzeige (Schlüssel valid? Welche Provider sind gespeichert?)
uv run --project backend python scripts/llm-secrets-doctor.py status

# Decrypt-Roundtrip für jeden Eintrag (Klartext bleibt im Memory)
uv run --project backend python scripts/llm-secrets-doctor.py verify
```

Exit-Codes:

| Code | Bedeutung |
|---|---|
| 0 | Alles ok |
| 1 | `AGORA_SECRET_KEY` fehlt oder ist invalid |
| 2 | Mindestens ein Eintrag lässt sich nicht decryptieren (Key passt nicht oder File ist korrupt) |

---

## Rotation

Wann rotieren?

- **Sofort:** Verdacht auf Leak (.env exfiltriert, Backup auf
  unkontrollierter Festplatte, Mitarbeiter ausgeschieden).
- **Geplant:** mindestens jährlich.
- **Pflicht:** nach Reset/Recovery eines defekten `.env`-Files (s. unten).

Ablauf:

```bash
# 1. Neuen Key erzeugen
NEW_KEY=$(python -c \
    'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')

# 2. Mit Doctor-Script re-encrypten (alter Key bleibt der aktive aus .env)
AGORA_SECRET_KEY=$OLD_KEY NEW_AGORA_SECRET_KEY=$NEW_KEY \
  uv run --project backend python scripts/llm-secrets-doctor.py rotate \
    --old-key-env AGORA_SECRET_KEY \
    --new-key-env NEW_AGORA_SECRET_KEY

# 3. .env auf neuen Key umstellen
sed -i.bak "s|^AGORA_SECRET_KEY=.*|AGORA_SECRET_KEY=$NEW_KEY|" .env

# 4. Container neu starten — neue Decrypts laufen mit neuem Key
docker compose restart agora

# 5. Roundtrip-Verifikation gegen neuen Key
AGORA_SECRET_KEY=$NEW_KEY \
  uv run --project backend python scripts/llm-secrets-doctor.py verify
```

Wichtig: Während der Rotation läuft das Backend mit dem **alten** Key in
`.env` weiter. Die Datei wird in-place mit dem neuen Ciphertext überschrieben.
Erst nach `.env`-Switch + Container-Restart wechselt der aktive
Decrypt-Pfad. Auf einem laufenden System: kurz Maintenance-Fenster (ggf.
neue API-Aufrufe gegen den alten Provider, der dann mit unbekanntem Key
arbeiten würde), aber für Single-User-Setups vernachlässigbar.

---

## Verlust-Verhalten

Wenn `AGORA_SECRET_KEY` verloren geht (Festplatte tot, `.env`
versehentlich gelöscht, Passwort-Manager-Master-Password vergessen):

1. **Backup prüfen.** `.env` aus dem letzten verschlüsselten Restic-Snapshot
   restaurieren (siehe [`backup-restore.md`](backup-restore.md)).
2. **Wenn kein Backup:** `llm_provider_secrets.json` ist verloren. Die
   gespeicherten Ciphertexte sind ohne den Original-Schlüssel kryptographisch
   nicht wiederherstellbar (Brute-Force gegen ein 32-Byte-Fernet-Secret ist
   nicht praktikabel).
3. **Recovery-Pfad:**
   ```bash
   # Doctor-Status zeigt InvalidToken-Fehler beim Decrypt
   uv run --project backend python scripts/llm-secrets-doctor.py verify
   # Neuen Key erzeugen
   NEW_KEY=$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')
   # Alten Store wegräumen (Backup zur Sicherheit)
   mv backend/data/llm_provider_secrets.json backend/data/llm_provider_secrets.json.orphan-$(date +%Y%m%d)
   rm -f backend/data/llm_provider_secrets.lock
   # Neuen Key in .env, Container neu starten
   echo "AGORA_SECRET_KEY=$NEW_KEY" >> .env
   docker compose restart agora
   ```
4. **Provider-Keys neu eingeben** über die UI (oder API). Workspace-Routing-
   Defaults sind nicht betroffen — die liegen im Klartext-JSON.

---

## Tests

`backend/tests/scripts/test_llm_secrets_doctor.py` (10 Tests) deckt ab:

- Status mit gültigem Key
- Status ohne Key (rc=1)
- Status mit invalidem Key (rc=1)
- Status ohne Store-File
- Verify mit korrektem Key
- Verify mit falschem Key (rc=2)
- Rotation re-encryptet korrekt
- Rotation bricht ab, wenn old-key falsch ist (rc=2)
- Rotation ohne Store-File
- Rotation behält Store-Struktur (version, masked_value, ciphertext-Header)

Klartext-API-Keys landen in keinem dieser Tests in stdout/stderr.

---

## Checklist nach jedem Eingriff

- [ ] `AGORA_SECRET_KEY` ist gesetzt und ist ein 44-Zeichen-Fernet-String.
- [ ] `backend/data/llm_provider_secrets.json` hat Mode `0600`
      (`stat -c '%a' backend/data/llm_provider_secrets.json`).
- [ ] `scripts/llm-secrets-doctor.py status` zeigt die erwarteten Provider.
- [ ] `scripts/llm-secrets-doctor.py verify` returnt rc=0.
- [ ] `.env` ist nicht im git-Tracking
      (`git check-ignore -v .env` muss `0:1:.env` zurückgeben).
- [ ] Aktueller Restic-Backup des `.env`-Files existiert (mindestens einer
      pro Monat) und ist nicht mit demselben `AGORA_SECRET_KEY` verschlüsselt.
