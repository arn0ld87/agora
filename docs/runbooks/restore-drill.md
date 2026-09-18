# Runbook: Fresh-Host-Restore-, Upgrade- und Rollback-Drill

Zugehöriges Issue: [#766](https://github.com/arn0ld87/agora/issues/766).
Verfahren und Hintergrund: [`../backup-restore.md`](../backup-restore.md).

## Warum dieses Runbook existiert

`docs/backup-restore.md` beschreibt das Verfahren sorgfältig — als Prosa mit einer Checkliste zum Abhaken. Der Abnahmepunkt aus #766 verlangt etwas anderes: einen **nachgewiesenen** Durchgang. Eine Checkliste, die ein Mensch abhakt, lässt sich im Zweifel auch abhaken, wenn niemand hingesehen hat, und sie hinterlässt nichts, was man einem Issue anheften könnte.

Zwei Werkzeuge schließen genau diese Lücke:

| Werkzeug | Was es tut | Braucht |
|---|---|---|
| [`scripts/restore-drill.sh`](../../scripts/restore-drill.sh) | fährt Backup → Restore → Verifikation → Upgrade → Rollback in dieser Reihenfolge und schreibt ein Protokoll | frischer Host, Docker, echtes Backup |
| [`backend/scripts/restore_verify.py`](../../backend/scripts/restore_verify.py) | prüft die Checkliste aus `backup-restore.md` maschinell gegen die restaurierten Verzeichnisse | Artefakt- und Store-Verzeichnis |

## Stand

**Der Drill ist nicht durchgeführt.** Was existiert, ist das Werkzeug dafür, inklusive Tests des Ablaufs (`backend/tests/scripts/test_restore_drill_script.py`, `..._restore_verify.py`). Die Verifikationsphase läuft in der Testsuite echt; Backup, Restore, Upgrade und Rollback brauchen einen Host mit Docker-Daemon und echten Daten und sind dort nur im Dry-Run abgedeckt.

#766 bleibt damit offen. Ein grünes Dry-Run-Protokoll ist ausdrücklich **kein** Betriebsnachweis — das Skript schreibt diesen Satz selbst ins Protokoll, damit ein solches Log nicht versehentlich als Nachweis an ein Issue wandert.

## Durchführung

Auf einem **frischen Host** — nicht auf dem Produktionshost, dessen Backup geprüft wird:

```bash
# 1. Vorbereitung: .env aus dem Backup einspielen, Master-Keys prüfen
#    (docs/backup-restore.md, Abschnitt "Reihenfolge der Secrets")

# 2. Erst den Ablauf ohne Wirkung durchsehen
bash scripts/restore-drill.sh \
  --phase all \
  --backup-dir /srv/agora-backup \
  --dry-run

# 3. Dann echt, mit Upgrade- und Rollback-Ziel
bash scripts/restore-drill.sh \
  --phase all \
  --backup-dir /srv/agora-backup \
  --upgrade-ref v0.9.5 \
  --rollback-ref v0.9.4 \
  --protocol /srv/agora-drill-$(date -u +%Y%m%d).log
```

### Der Restore weigert sich, in den eigenen Checkout zu schreiben

Die Vorgabewerte für `--data-dir`, `--store-dir` und `--instance-dir` zeigen auf `backend/uploads`, `backend/data` und `backend/instance` des Checkouts. Für das Backup ist das richtig — gesichert wird die laufende Installation. Für den Restore wäre es der teuerste Tippfehler im Repository, deshalb bricht `--phase restore` ab, sobald eines der drei Ziele unterhalb der Repository-Wurzel liegt:

```text
FEHLGESCHLAGEN: Restore würde in den eigenen Checkout schreiben.
```

Auf dem frischen Host, wo der Checkout *das* Ziel ist, hebt `--allow-repo-target` die Sperre auf. Das Flag gehört in den bewussten Aufruf, nicht in ein Skript, das jemand später aus dem Verlauf kopiert.

### Prüfsummen

`--phase backup` legt neben den Archiven ein `MANIFEST.sha256` an, je Lauf frisch. `--phase restore` prüft jedes Archiv dagegen und bricht bei Abweichung ab, bevor irgendetwas entpackt wird. Ein Archiv ohne Manifesteintrag — etwa aus einem Lauf vor dieser Prüfung — wird entpackt, aber im Protokoll als **ungeprüft** vermerkt; es ist damit kein Nachweis.

Backup-Verzeichnis und Archive entstehen mit `0700` beziehungsweise `0600`. Sie enthalten `backend/data` mit den Fernet-Stores und `backend/instance/llm_profiles.db`, das die Spalte `api_key` im Klartext führt — ein world-lesbares Backup-Verzeichnis wäre ein Exposure-Pfad unabhängig davon, dass die Stores selbst verschlüsselt sind.

### SQLite im WAL-Modus

`llm_profiles.db` läuft mit `journal_mode=WAL`. Zur Laufzeit besteht sie aus `.db`, `.db-wal` und `.db-shm`; ein reines `tar` würde den Zwischenzustand einfrieren, in dem die letzten Schreibvorgänge noch im WAL stehen. Die Backup-Phase setzt deshalb vorher `PRAGMA wal_checkpoint(TRUNCATE)`. Fehlt `sqlite3` auf dem Host, steht eine Warnung im Protokoll und das Archiv ist entsprechend weniger wert.

Einzelne Phasen (`--phase backup|restore|verify|upgrade|rollback`) lassen sich getrennt fahren, wenn ein Durchgang abbricht und nur ein Teil zu wiederholen ist.

### Was gesichert wird

Drei Verzeichnisse, je ein Archiv — dieselben, die `docs/backup-restore.md` mit Kritikalität „hoch" führt:

| Option | Vorgabe | Archiv | Inhalt |
|---|---|---|---|
| `--data-dir` | `backend/uploads` | `uploads.tar.gz` | Runs, Simulationen, Reports |
| `--store-dir` | `backend/data` (bzw. `AGORA_DATA_DIR`) | `data.tar.gz` | Provider-, Routing- und App-Stores |
| `--instance-dir` | `backend/instance` | `instance.tar.gz` | Instanzsettings |

Die Restore-Phase spielt sie in der dokumentierten Recovery-Reihenfolge zurück (Stores, Instanz, Artefakte, dann Neo4j) und kopiert den Neo4j-Dump vor dem `database load` zurück in den neu gestarteten Container — `docker compose down` nimmt den alten mitsamt seinem `/backups` mit.

### Vor dem Lauf prüfen

Die `neo4j-admin`-Syntax hängt an der eingesetzten Neo4j-Version und Betriebsform. Das Skript pinnt sie bewusst nicht und protokolliert stattdessen einen Hinweis — ein Monate alter Befehl, der einen Server im Container stoppt und danach so tut, als könne man fröhlich weiter in denselben Prozess `exec`en, ist gefährlicher als gar keiner. Vor dem Drill gegen die laufende Version prüfen.

## Was das Protokoll wert ist

Der Drill gilt als bestanden, wenn:

- Exit-Code `0` (`2` heißt: nichts ist rot, aber etwas blieb ungeprüft — das Skript wertet das als Fehlschlag),
- die Verifikation **keinen** übersprungenen Punkt meldet (ein `SKIP` ist kein Erfolg — ohne gesetzten `AGORA_SECRET_KEY` etwa bleibt die Secret-Prüfung ungeprüft, und dann ist genau der Teil offen, der am häufigsten bricht),
- Upgrade und Rollback jeweils mit einer eigenen Verifikation abgeschlossen sind.

Das Protokoll gehört an #766. Erst dann ist der Abnahmepunkt erfüllt.

## Verifikation ohne vollen Drill

Die maschinelle Checkliste lässt sich jederzeit gegen eine bestehende Installation fahren — sie ist auch außerhalb eines Drills nützlich, etwa nach einem ungeplanten Neustart:

```bash
cd backend
uv run python scripts/restore_verify.py --data-dir uploads --store-dir data
uv run python scripts/restore_verify.py --data-dir uploads --store-dir data --json
```

`--data-dir` zeigt auf die Artefakte (`backend/uploads`), `--store-dir` auf die
dateibasierten JSON-Stores (`backend/data` bzw. `AGORA_DATA_DIR`).
`provider_connections.json` liegt im zweiten — ohne den Pfad überspringt die
Prüfung den gesamten Provider/Secrets-Abschnitt.

Exit-Codes: `0` alle Punkte grün und keiner übersprungen, `1` mindestens ein
Punkt ist rot, `2` kein Fehler, aber mindestens ein Punkt konnte nicht geprüft
werden. `restore-drill.sh` behandelt `2` wie einen Fehlschlag — ein
übersprungener Punkt ist kein Nachweis.

Geprüft werden Artefakte (RunRegistry lesbar, Simulationen und Reports vorhanden), Reconciliation (kein Run steht fälschlich auf `pending`/`processing`/`paused` — siehe [#1476](https://github.com/arn0ld87/agora/issues/1476) und [#1472](https://github.com/arn0ld87/agora/issues/1472)) und Secrets (ProviderConnections vorhanden, Secret-Store mit dem restaurierten `AGORA_SECRET_KEY` entschlüsselbar).

Kein Klartext verlässt die Prüfung: gemessen wird ausschließlich, **ob** die Entschlüsselung gelingt. Das Protokoll ist zum Weitergeben gedacht.

Dasselbe gilt für `restore-drill.sh`: Protokollzeilen und die Ausgabe jedes ausgeführten Befehls laufen durch einen Redaktionsfilter, der `Authorization: Bearer …` sowie `token=`/`secret=`/`password=`/`api_key=` durch `[REDACTED]` ersetzt. Heute nimmt kein verdrahteter Befehl ein Geheimnis entgegen — der Filter sichert gegen den naheliegendsten nächsten Schritt ab, etwa den Health-Check mit Auth-Header aus `docs/backup-restore.md`.
