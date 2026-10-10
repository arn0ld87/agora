# Betriebskorrektur gns3 — #1834

Datum: 10.10.2026. Image unverändert `ghcr.io/arn0ld87/agora:sha-328d2b8`.

## Ursache

Die wirksame Compose-Konfiguration band `/home/schneider/.local/share/agora/codex` nach `/home/agora/.codex` ein. Das Hostverzeichnis war leer und root-owned 0755; der Container läuft mit UID/GID1000. `/home/alex/.local/share/agora/codex` war bereits vorhanden, UID1000, Modus0700 und enthielt die vorgesehene Agora-Anmeldung. Credential-Inhalte wurden nicht ausgegeben oder kopiert.

## Korrektur

Vorab keine aktiven Simulations-/Berichtsjobs in den Artefakten. Ausschließlich den nicht geheimen Wert `AGORA_CODEX_HOME` in der Host-`.env` auf `/home/alex/.local/share/agora/codex` korrigiert. Den bestehenden Compose-Stack mit denselben vier Konfigurationsdateien, `up -d --no-deps --no-build agora`, neu erstellt. Keine Modell-/Providerroute geändert, kein Image gebaut/aktualisiert.

## Nachweis

- Wirksamer Containermount zeigt auf das korrigierte Hostverzeichnis.
- `codex_cli_readiness`: binary_present=True, credentials=ok, ready=True.
- Container `healthy`; Neo4j/Redis unverändert gesund.
- Echter isolierter Aufruf über `_run_codex_cli` mit `model=gpt-6-astra`, ohne Tools: Antwort `OK`.

## Grenze und Rückweg

Dies belegt die behobene CLI-Verfügbarkeit, noch keinen vollständigen neuen Bericht und keine Modellqualität. Der Outline-Produktfix #1832 muss separat reviewt und ausgeliefert werden. Die historische leere Reportdatei bleibt erhalten. Rückweg: nur den vorher dokumentierten nicht geheimen Mountwert zurücksetzen und bei gestoppten Jobs neu erstellen; das würde den bekannten Startfehler wiederherstellen. Keine Credentials verschieben/löschen.
