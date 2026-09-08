### Fixed

- **`install.sh` erzeugte im Host-Modus keine Pflicht-Secrets — trotz Aufruf
  von `ensure_secret` wäre der Fix wirkungslos geblieben.** `.env.example` Der Docker-Modus sichert dieselben beiden Master-Keys ab — er kannte sie zuvor gar nicht, weil `.env.docker.example` sie nie gefuehrt hat.
  enthält nicht-leere Platzhalter (`SECRET_KEY=change-me-use-token_urlsafe-32`,
  `NEO4J_PASSWORD=change-me`); der alte `ensure_secret`-Fruehausstieg
  (`grep -qE "^KEY=[^[:space:]]+"`) hielt einen Platzhalter für „gesetzt“ und
  griff nur im Docker-Modus, wo die Docker-Vorlage leere Werte nutzt.
  `ensure_secret` behandelt bekannte Platzhalter jetzt wie ungesetzt (Bash-Kopie
  der `SECRET_KEY_PLACEHOLDERS`/`NEO4J_PASSWORD_PLACEHOLDERS`-Frozensets aus
  `backend/app/config.py`, gegen Drift per Test abgesichert) und generiert im
  Host-Modus zusätzlich `AGORA_SECRET_KEY` und `AGORA_FERNET_KEY`.
- **`AGORA_SECRET_KEY`/`AGORA_FERNET_KEY` wären mit ungültigen Werten belegt
  worden.** Beide müssen gültige Fernet-Keys sein
  (`llm_provider_secrets_store.py`, `api_keys_persistence.py`); der bisherige
  Generator (`secrets.token_urlsafe(32)`) erzeugt kein gültiges Fernet-Format
  und hätte die Anwendung beim ersten Zugriff mit `RuntimeError` abbrechen
  lassen. `ensure_secret` erzeugt für diese beiden Keys jetzt
  `base64.urlsafe_b64encode(os.urandom(32))` — bit-identisch zu
  `Fernet.generate_key()`, aber ohne dass `cryptography` zum
  Installationszeitpunkt bereits installiert sein muss.
- Beide `AGORA_*`-Keys fehlten in `.env.example` und `.env.docker.example`
  vollständig und sind dort jetzt auskommentiert mit Zweck und
  Erzeugungsbefehl dokumentiert.
- `docs/backup-restore.md` verwies an fünf Stellen auf das nie existierende
  `./backend/reports/` — der reale Pfad ist `backend/uploads/reports/`
  (`Config.UPLOAD_FOLDER/reports`).
- README-Quickstart: redundantes `cp .env.example .env` entfernt (macht
  `install.sh` bereits selbst) und Requirements-Block um die tatsächlich von
  `install.sh` geprüften Voraussetzungen (`bun` >= 1.3, Node >= 20, `uv`)
  ergänzt.
- `backend/gunicorn.conf.py`: Kommentar ergänzt, warum `workers = 1` auch für
  `RunRegistry` und die Monitor-Threads in `app.services.sim.monitor`
  Pflicht ist (Prozess-lokaler State, Monitor-Generation-Zähler). Keine
  Wertänderung.
