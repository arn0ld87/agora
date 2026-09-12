# Runbook: Fresh-Host-Restore-, Upgrade- und Rollback-Drill

Zugehöriges Issue: [#766](https://github.com/arn0ld87/agora/issues/766).
Verfahren und Hintergrund: [`../backup-restore.md`](../backup-restore.md).

## Warum dieses Runbook existiert

`docs/backup-restore.md` beschreibt das Verfahren sorgfältig — als Prosa mit einer Checkliste zum Abhaken. Der Abnahmepunkt aus #766 verlangt etwas anderes: einen **nachgewiesenen** Durchgang. Eine Checkliste, die ein Mensch abhakt, lässt sich im Zweifel auch abhaken, wenn niemand hingesehen hat, und sie hinterlässt nichts, was man einem Issue anheften könnte.

Zwei Werkzeuge schließen genau diese Lücke:

| Werkzeug | Was es tut | Braucht |
|---|---|---|
| [`scripts/restore-drill.sh`](../../scripts/restore-drill.sh) | fährt Backup → Restore → Verifikation → Upgrade → Rollback in dieser Reihenfolge und schreibt ein Protokoll | frischer Host, Docker, echtes Backup |
| [`backend/scripts/restore_verify.py`](../../backend/scripts/restore_verify.py) | prüft die Checkliste aus `backup-restore.md` maschinell gegen das restaurierte Datenverzeichnis | nur das Datenverzeichnis |

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

Einzelne Phasen (`--phase backup|restore|verify|upgrade|rollback`) lassen sich getrennt fahren, wenn ein Durchgang abbricht und nur ein Teil zu wiederholen ist.

### Vor dem Lauf prüfen

Die `neo4j-admin`-Syntax hängt an der eingesetzten Neo4j-Version und Betriebsform. Das Skript pinnt sie bewusst nicht und protokolliert stattdessen einen Hinweis — ein Monate alter Befehl, der einen Server im Container stoppt und danach so tut, als könne man fröhlich weiter in denselben Prozess `exec`en, ist gefährlicher als gar keiner. Vor dem Drill gegen die laufende Version prüfen.

## Was das Protokoll wert ist

Der Drill gilt als bestanden, wenn:

- Exit-Code `0`,
- die Verifikation **keinen** übersprungenen Punkt meldet (ein `SKIP` ist kein Erfolg — ohne gesetzten `AGORA_SECRET_KEY` etwa bleibt die Secret-Prüfung ungeprüft, und dann ist genau der Teil offen, der am häufigsten bricht),
- Upgrade und Rollback jeweils mit einer eigenen Verifikation abgeschlossen sind.

Das Protokoll gehört an #766. Erst dann ist der Abnahmepunkt erfüllt.

## Verifikation ohne vollen Drill

Die maschinelle Checkliste lässt sich jederzeit gegen eine bestehende Installation fahren — sie ist auch außerhalb eines Drills nützlich, etwa nach einem ungeplanten Neustart:

```bash
cd backend
uv run python scripts/restore_verify.py --data-dir uploads
uv run python scripts/restore_verify.py --data-dir uploads --json   # für Automatisierung
```

Geprüft werden Artefakte (RunRegistry lesbar, Simulationen und Reports vorhanden), Reconciliation (kein Run steht fälschlich auf `pending`/`processing`/`paused` — siehe [#1476](https://github.com/arn0ld87/agora/issues/1476) und [#1472](https://github.com/arn0ld87/agora/issues/1472)) und Secrets (ProviderConnections vorhanden, Secret-Store mit dem restaurierten `AGORA_SECRET_KEY` entschlüsselbar).

Kein Klartext verlässt die Prüfung: gemessen wird ausschließlich, **ob** die Entschlüsselung gelingt. Das Protokoll ist zum Weitergeben gedacht.
