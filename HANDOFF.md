# Handoff — Agora Richtung 0.10.0-RC

**Stand:** 02.10.2026
**Geprüfte Basis:** `main@4cbf0eb849502472e4107fdd947559d417842b90`
**Produktversion:** `0.9.6` Stability Beta; nächster Schnitt `0.10.0-rc.1`.

Diese Übergabe ersetzt den [Stand vom 24.09.2026](https://github.com/arn0ld87/agora/blob/4cbf0eb849502472e4107fdd947559d417842b90/HANDOFF.md). Dessen offene PRs und pauschale Aussage „alle verbleibenden Slices blockiert“ sind keine aktuelle Arbeitsgrundlage.

## Quellen und PandaOS

1. [README](README.md): Produkt und Einstieg.
2. [STATUS](docs/STATUS.md): verifizierter Istzustand, CI-Nachweise und Grenzen.
3. [ROADMAP](ROADMAP.md): Release-Reihenfolge.
4. [Release-Priorität](docs/agents/release-priority.md) und aktuelle GitHub-Issues: nächste ausführbare Arbeit.

Der historische PandaOS-Auftrag ist Tracked Work `f006` („Agora 0.10.0: die neun Release-Prioritäten“). **Der lokale PandaOS-Work-Stand wurde bei diesem GitHub-Abgleich nicht eingesehen.** Mit verfügbaren Work-Tools den aktiven Auftrag und seine Tasks lesen, mit aktuellen Issue-Zuständen abgleichen und die Arbeit dort fortführen. Weder einen neuen Epic noch alte Blockaden ungeprüft übernehmen; geschlossene Tickets können noch historische `ready-for-human`-Labels tragen.

## Nächste ausführbare Arbeit

1. **Security-Audit:** [PR #1748](https://github.com/arn0ld87/agora/pull/1748) ist offen und aktualisiert pypdf gezielt auf 6.19.0. Erst dessen Stand/Nachweise prüfen, keine zweite Implementierung starten. Auf Main ist der Python-Audit in [Run 36898610864](https://github.com/arn0ld87/agora/actions/runs/36898610864) rot; Backend, Frontend und echte Integration sind dort grün. Normale PR-Läufe führen den Python-Audit nicht aus.
2. **Test-Isolation #1632:** RunRegistry/ManifestCapture und Test-Konfiguration von echten `uploads`-/`AGORA_DATA_DIR`-Pfaden trennen; temporäre Fixtures und einen Guard verifizieren. Keine reale Hostbereinigung ohne gesonderten Auftrag.
3. **Rest vor Feature-Freeze:** #1663, #1664, #1661, #1670, #1671, #1672; operative Abnahme #1592 benötigt armserver-Zugriff. Reihenfolge/Abhängigkeiten aus den aktuellen Issues übernehmen.

## Erledigt, nicht neu implementieren

| Bereich | Geschlossene Tickets | Verbleibende Grenze |
|---|---|---|
| Job-Recovery | #1472; #1265 an #1551 übergeben | Eigene Worker und Report-Parallelität später |
| Embedding | #1417 | Realer Modellwechsel-Nachweis in #1592 |
| Persona-/Entitätsbehandlung | #1470, #1471, #1323 | LLM-Koreferenz außerhalb des Scopes; Role Leakage lesend markieren |
| Trust / Simulation | #1236, #1345, #1301, #1400, #1224 | Eval-Seed-Gegenlauf #1240; native CAMEL-Pfade nicht pauschal gehärtet |
| Manifest / Replay | #763, #1274 | `random_seed=null`; keine identischen Ausgaben zugesagt |
| Ops / Gates | #1633, #1634, #1660, #1669, #1673 | Security-Audit aktuell rot; Fresh-Host-Drill #766 offen |

## Betrieb und Produktabnahme

Der Metadaten-Cutover auf armserver ist im STATUS dokumentiert; Code-Defaults bleiben Legacy. #1592 ist für formale Cutover-/Beobachtungs-/Drill-Nachweise offen. #766 verlangt einen realen Fresh-Host-Install/Restore; ein grüner Skripttest ersetzt ihn nicht. #1662 liefert AURORA gegen Single-Prompt- und statische Persona-Baseline; #1674 ergänzt sichtbare Grenzen.

Feature-Freeze beginnt erst mit `0.10.0-rc.1`. Danach nur Fixes, Tests und Doku. `1.0.0` verlangt sieben Tage ohne neuen P0/P1; ein neuer Blocker bedeutet Fix, neuen RC und neuen Soak.

## Arbeits- und Prüfhygiene

- AGENTS.md und relevante Regeln lesen; eigener Branch ab aktuellem `origin/main`, nie auf einem bereits gemergten Feature-Branch weiterarbeiten.
- CRG für Code/Impact, ctx für größere Abfragen; gezielter Fallback bei fehlenden Tools.
- Verhaltensfix mit Regressionstest, Changelog-Fragment; STATUS synchronisieren, generierte Testzähler nur per Skript.
- Pflicht vor Push: `bash scripts/pre-push-gate.sh [backend|frontend|schemas]`; Umfang und Vollmodus im [Runbook](docs/runbooks/pre-push-gate.md).
- Persistenz-/Migrations-/Env-/Compose-Änderungen ziehen das [Upgrade-Runbook](docs/runbooks/upgrade.md) im selben PR nach.
- Nachweise unterscheiden: lokal geprüft, PR-CI am finalen Commit grün, auf Main bestätigt, operativ noch offen. Keine Release-Freigabe aus einem historischen grünen Lauf ableiten.
