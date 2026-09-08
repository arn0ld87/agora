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

### Fixed (Installation - 2026-09-08, Codex-Review Runde 2)

- **Der Host-Modus erzeugt jetzt auch `AGORA_AUTH_TOKEN`.** `.env.example` führt den Key nur auskommentiert und setzt `FLASK_DEBUG=false`; ohne Token bricht `backend/run.py` beim Start mit `AGORA_AUTH_TOKEN missing in non-debug mode` aus `Config.validate()` ab. Eine frische Host-Installation war damit auch nach korrekt hinterlegten Neo4j-Zugangsdaten nicht startfähig.
- **Die Secret-Erzeugung setzt kein System-`python3` mehr voraus.** `install.sh` läuft vor `uv sync`; auf einem sauberen macOS mit den dokumentierten Voraussetzungen (bun, node, uv) bringt `uv` seinen eigenen Interpreter mit und `/usr/bin/python3` existiert nicht — die Generierung starb vor der ersten Abhängigkeitsinstallation. Neuer Helfer `random_urlsafe_32` mit Fallback-Kette `python3` → `openssl rand 32` → `head -c 32 /dev/urandom`, jeweils als URL-sicheres Base64 aus derselben Entropiequelle. Die Längenprüfung (44 Zeichen mit Padding für Fernet-Keys, 43 ohne für `token_urlsafe`-Äquivalente) bricht ab, bevor ein zu kurzer Wert in die `.env` geschrieben wird.
- **`README.md` nennt `NEO4J_PASSWORD` wieder im Quickstart.** `.env.example` liefert `NEO4J_PASSWORD=change-me`, und `Config.validate()` lehnt diesen Platzhalter außerhalb des Debug-Modus ab — die Kurzanleitung führte mit „nur LLM-Endpunkte konfigurieren, dann `bun run dev`" in einen Backend, der nicht startet.
- **Der Testblock in `install.sh` ist jetzt durch `# >>> ensure-secret-block` / `# <<< ensure-secret-block` markiert.** `test_install_ensure_secret.py` extrahierte ihn vorher per `sed`-Range bis zur ersten `^}` — jede zusätzliche Funktion vor `ensure_secret` hätte den Range still abgeschnitten.
