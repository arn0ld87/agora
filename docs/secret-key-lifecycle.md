# Secret- und Key-Lifecycle

**Stand:** 08.09.2026  
**Geprüfte Main-Baseline:** `0c47737f`  
**Scope:** Welche Schlüssel Agora besitzt, was sie schützen, wie sie gesichert werden und was bei Verlust passiert.

> [!IMPORTANT]
> `AGORA_SECRET_KEY` und `AGORA_FERNET_KEY` sind **zwei verschiedene Fernet-Master-Keys für zwei verschiedene Stores**. Sie sind nicht austauschbar. Die alte Dokumentation behandelte nur einen davon und war damit inzwischen gefährlich unvollständig.

Verwandte Dokumente:

- [`auth.md`](auth.md)
- [`backup-restore.md`](backup-restore.md)
- [`security-threat-model.md`](security-threat-model.md)
- [`.env.example`](../.env.example)

---

## 1. Schlüsselübersicht

| Variable | Typ | Schützt / verwendet für | Verlustfolge |
|---|---|---|---|
| `SECRET_KEY` | zufälliges App-Secret | Flask-/`itsdangerous`-Signing, signierte Tickets | bestehende Tickets/Signaturen werden ungültig |
| `AGORA_AUTH_TOKEN` | zufälliger Bearer-Token | administrativer Master-Zugriff auf `/api/*` | bei Leak Vollzugriff; bei Verlust neuen Token verteilen |
| `AGORA_SECRET_KEY` | Fernet-Key | Provider-Credentials in `backend/data/llm_provider_secrets.json` | gespeicherte Provider-Secrets ohne Backup nicht mehr entschlüsselbar |
| `AGORA_FERNET_KEY` | Fernet-Key | verschlüsselter Workspace-API-Key-Store `backend/data/api_keys.json` | persistierter API-Key-Store ohne Original-Key nicht mehr lesbar |
| `NEO4J_PASSWORD` | Passwort | Neo4j-Authentifizierung | DB-Zugriff bricht; Rotation muss Backend und DB synchron ändern |

Diese Werte gehören **nicht** in Git, Reports, Run-Manifeste, Screenshots oder Diagnose-Bundles.

---

## 2. Installation

Seit #1483 erzeugt `install.sh` in Host- und Docker-Modus automatisch sichere Werte für:

- `SECRET_KEY`
- `AGORA_AUTH_TOKEN`
- `AGORA_SECRET_KEY`
- `AGORA_FERNET_KEY`

Bekannte Platzhalter aus den `.env`-Templates gelten dabei als ungesetzt und werden ersetzt.

Für die beiden Fernet-Keys wird ein gültiger 32-Byte-Key in URL-safe Base64 erzeugt. Ein beliebiger `token_urlsafe(32)`-String ist **nicht automatisch ein Fernet-Key**.

`NEO4J_PASSWORD` bleibt eine Operator-/Datenbankkonfiguration und muss zur tatsächlichen Neo4j-Instanz passen.

---

## 3. Manuelle Erzeugung

Falls ein Key bewusst außerhalb von `install.sh` erzeugt wird:

### Fernet-Key

Für `AGORA_SECRET_KEY` oder `AGORA_FERNET_KEY`:

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Alternativ muss das Ergebnis exakt 32 zufällige Bytes in URL-safe Base64 repräsentieren.

### Master-Token

```bash
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

### Flask-Secret

```bash
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Keinen der ausgegebenen Werte in Shell-History, Tickets oder Chat kopieren, wenn vermeidbar.

---

## 4. `AGORA_SECRET_KEY` — Provider-Secrets

### Zweck

`AGORA_SECRET_KEY` verschlüsselt Cloud-/HTTP-Provider-Credentials im `LlmProviderSecretsStore`.

Persistenz:

```text
backend/data/llm_provider_secrets.json
```

Der Store enthält verschlüsselte Provider-Keys plus nicht geheime Metadaten. Klartext-Credentials sollen nur für die notwendige Laufzeit im Speicher existieren.

### Doctor-Script

Für **diesen** Store existiert:

```bash
uv run --project backend python scripts/llm-secrets-doctor.py status
uv run --project backend python scripts/llm-secrets-doctor.py verify
```

Diese Befehle prüfen den Provider-Secret-Store. Sie sind **kein allgemeiner Doctor für `AGORA_FERNET_KEY`/`api_keys.json`**.

### Rotation

Die vorhandene Provider-Secret-Rotation kann den Store mit einem neuen `AGORA_SECRET_KEY` neu verschlüsseln. Vor jeder Rotation:

1. aktuelles `.env` und `backend/data/` sichern,
2. `verify` mit dem alten Key ausführen,
3. neuen Fernet-Key erzeugen,
4. Store atomar neu verschlüsseln,
5. `.env` auf den neuen Key umstellen,
6. Backend neu starten,
7. erneut `verify` ausführen.

Die konkreten CLI-Flags des Doctor-Scripts sind dessen `--help` zu entnehmen; nicht aus einer alten Doku blind kopieren.

### Verlust

Ohne Backup des ursprünglichen `AGORA_SECRET_KEY` können die vorhandenen Provider-Ciphertexte praktisch nicht rekonstruiert werden.

Recovery:

- Original-Key aus sicherem Backup wiederherstellen, **oder**
- alten Provider-Store archivieren, neuen Key setzen und Provider-Credentials neu eingeben.

Workspace-Routing ohne Secrets kann separat erhalten bleiben.

---

## 5. `AGORA_FERNET_KEY` — Workspace-API-Key-Store

### Zweck

`AGORA_FERNET_KEY` verschlüsselt den kompletten JSON-Blob des Workspace-API-Key-Stores:

```text
backend/data/api_keys.json
```

Implementierung: `backend/app/services/api_keys_persistence.py`.

Security-Eigenschaften:

- Fernet-Verschlüsselung des gesamten Stores,
- atomarer Write via Temp-Datei + `os.replace`,
- Dateimodus `0600`,
- `fcntl.flock` auf POSIX,
- aktueller Produktions-Hardstop `gunicorn workers=1` reduziert zusätzliche Writer-Races.

### Fehlender Key

- Debug-Modus kann einen **temporären** Fernet-Key generieren und warnt laut.
- Nicht-Debug/Produktion: fehlender Key ist ein Konfigurationsfehler und führt zu `RuntimeError`.

Ein temporärer Debug-Key ist für persistierte API-Keys untauglich, weil nach einem Neustart ein anderer Key entsteht.

### Rotation

Für `AGORA_FERNET_KEY` ist in dieser Dokumentation **kein verifizierter automatischer Re-Encrypt-Workflow** freigegeben.

Deshalb nicht einfach den Wert in `.env` austauschen, solange `backend/data/api_keys.json` noch mit dem alten Key verschlüsselt ist. Ein ungeplanter Wechsel macht den Store unlesbar.

Sichere Vorgehensweisen sind derzeit:

1. alten Key aus Backup weiterverwenden, oder
2. in einem geplanten Wartungsfenster Workspace-API-Keys neu erzeugen und den alten verschlüsselten Store archivieren, oder
3. erst einen getesteten Migrations-/Re-Encrypt-Pfad implementieren.

### Verlust

Geht der Original-Key verloren und existiert kein Backup, können die gespeicherten API-Key-Datensätze nicht entschlüsselt werden. Die betroffenen Workspace-Keys müssen neu erzeugt und verteilt werden.

---

## 6. `SECRET_KEY` — Signaturen/Tickets

`SECRET_KEY` ist **nicht** der Provider- oder API-Key-Store-Master.

Er wird für Flask-/Signing-Zwecke verwendet, insbesondere kurzlebige signierte Tickets.

Rotation invalidiert bestehende Signaturen/Tickets. Da Tickets kurzlebig sind, ist das meist erwünscht und operativ überschaubar; trotzdem sollte ein geplanter Restart erfolgen.

`SECRET_KEY` niemals mit `AGORA_SECRET_KEY` oder `AGORA_FERNET_KEY` wiederverwenden. Getrennte Zwecke sollen getrennte Secrets besitzen.

---

## 7. `AGORA_AUTH_TOKEN` — Master-Zugriff

Der Master-Token besitzt administrative Wirkung und umgeht API-Key-Scopes.

Bei Leak-Verdacht:

1. neuen Token erzeugen,
2. `.env` aktualisieren,
3. Backend neu starten,
4. Browser/Automationen auf neuen Token umstellen,
5. alte Logs/Screenshots/Artefakte auf Leak-Quelle prüfen.

Der Token gehört nicht in Query-Parameter. Für SSE/Download-URL-Auth werden kurzlebige signierte Tickets verwendet.

---

## 8. Speicherung

### Mindeststandard Single-User

- `.env` nicht versionieren.
- Dateimodus möglichst `0600`.
- verschlüsseltes Backup auf getrenntem Medium.
- zusätzlicher Passwort-Manager-Eintrag für die beiden Fernet-Master-Keys sinnvoll.

### Besserer Betriebsstandard

Secret-Injection über einen geeigneten Passwort-/Secret-Manager oder systemd-/Container-Credentials, solange Agora die Werte beim Prozessstart als erwartete Umgebungsvariablen erhält.

Die Doku behauptet keine native Vault-/KMS-Integration, solange dafür kein produktiver Adapter existiert.

---

## 9. Backup-Pflicht

Mindestens gemeinsam sichern:

```text
.env
backend/data/
backend/uploads/
Neo4j-Daten/Dump
```

Die beiden kritischen Paare sind:

```text
AGORA_SECRET_KEY  + backend/data/llm_provider_secrets.json
AGORA_FERNET_KEY  + backend/data/api_keys.json
```

Ein Ciphertext-Backup ohne seinen Master-Key ist keine Wiederherstellungsstrategie, sondern dekorative Kryptographie.

Details und Restore-Reihenfolge: [`backup-restore.md`](backup-restore.md).

---

## 10. Rotationstabelle

| Secret | Rotation | Besonderheit |
|---|---|---|
| `AGORA_AUTH_TOKEN` | bei Leak-Verdacht / geplant | Clients müssen neuen Token erhalten |
| `SECRET_KEY` | bei Leak-Verdacht / geplant | bestehende Tickets/Signaturen verfallen |
| `AGORA_SECRET_KEY` | bei Leak-Verdacht / geplant | Provider-Store muss re-encrypted werden |
| `AGORA_FERNET_KEY` | nur mit Store-Migration/Neuerzeugung | sonst wird `api_keys.json` unlesbar |
| `NEO4J_PASSWORD` | gemäß DB-Policy | Backend und Neo4j synchron ändern |

Starre Kalenderfristen sind weniger wichtig als ein **getesteter** Rotations- und Recovery-Pfad. Ein jährlich rotierter Schlüssel, dessen Restore niemand geprüft hat, ist vor allem ein sehr disziplinierter Weg zum Datenverlust.

---

## 11. Checkliste nach Eingriffen

- [ ] `.env` ist nicht im Git-Tracking.
- [ ] `AGORA_SECRET_KEY` ist ein gültiger Fernet-Key.
- [ ] `AGORA_FERNET_KEY` ist ein gültiger Fernet-Key.
- [ ] Provider-Secret-Store lässt sich mit `llm-secrets-doctor.py verify` lesen.
- [ ] Workspace-API-Keys funktionieren nach Backend-Restart.
- [ ] `backend/data/` ist persistent gesichert.
- [ ] Backup enthält die zu den Ciphertext-Stores passenden Master-Keys.
- [ ] Keine Secrets sind in Commit, PR-Beschreibung, Logs oder Screenshots gelandet.
