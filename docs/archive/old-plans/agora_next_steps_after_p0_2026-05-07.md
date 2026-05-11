# Agora – Nächste Schritte nach P0

Stand: 2026-05-07

## Kurzurteil

P0 ist als akute Dependency-/Security-Triage erledigt. Danach nicht direkt mit neuen Features weitermachen, sondern M11 sauber abarbeiten.

Empfohlene Reihenfolge:

1. P1-A: Dependabot-Aufräumen und P0-Ergebnis sauber im Repo schließen.
2. P1-B: v1.0-Hotspot-Refactors Phase 5.
3. P1-C: Contract-Generation + Status-Sync Phase 6.
4. P1-D: Playwright-Smokes Phase 7.
5. P2: Live-Settings im Frontend (#212).

## Warum diese Reihenfolge?

Der Repo-Status sagt: M9 und M10 sind abgeschlossen. Der nächste Block ist M11.

Aktuelle M11-Richtung:

- Hotspot-Refactors
- Contract-Generation + Status-Sync
- Playwright-Smokes
- Coverage-Gate-Anhebung
- später Komplexitäts-Gate

Das ist sinnvoll, weil Agora bereits MVP-nah ist. Jetzt geht es nicht mehr um „noch mehr Features“, sondern um Release-Stabilität, Wartbarkeit und nachweisbare End-to-End-Funktion.

## Sofort erledigen: P1-A

### Ziel

P0 sauber abschließen, damit keine halboffenen Dependabot-Leichen im Repo liegen. Die haben sonst die unangenehme Eigenschaft, später als CI-Zombie zurückzukommen.

### Aufgaben

1. PR #315 final behandeln:
   - Wenn P0 ergeben hat, dass `camel-ai` wegen `camel-oasis==0.2.5` weiter blockiert ist:
     - PR #315 schließen.
     - Kommentar setzen: blockiert durch hard pin in `camel-oasis`.
     - Issue/ADR/Dependency-Triage-Doku verlinken.
   - Wenn P0 eine kompatible Lösung gefunden hat:
     - Rebase/Update.
     - CI + contract-gates grün machen.
     - Dann mergen.

2. PR #323 `mistune` prüfen und mergen, falls:
   - CI grün
   - contract-gates grün
   - dependency-review grün
   - kein Verhalten in Markdown-/Report-Rendering bricht

3. PR #326 `pygments` prüfen und mergen, falls:
   - CI grün
   - contract-gates grün
   - dependency-review grün
   - kein Export-/Highlighting-Pfad betroffen ist

4. `docs/dependency-risk-register.md` aktualisieren:
   - P0-Ergebnis verlinken
   - CVEs unverändert offen lassen, wenn upstream-blockiert
   - keine neuen `--ignore-vuln` ohne Issue/Owner/Deadline

## Danach: P1-B Hotspot-Refactors Phase 5

### Ziel

Große zentrale Dateien entschärfen, ohne Verhalten zu ändern.

### Fokus

Nicht direkt alles aufbrechen. Nimm genau einen Hotspot pro PR.

Empfohlene Reihenfolge:

| PR | Ziel | Warum |
|---|---|---|
| 1 | `simulation_runner.py` Schnittgrenzen prüfen | niedrige Coverage, hoher Betriebsimpact |
| 2 | `graph_tools.py` in Query/Mutation/Formatting trennen | niedrige Coverage, zentrale Report-Abhängigkeit |
| 3 | Frontend-Wizard-Reste weiter reduzieren | UI-Regressionen vermeiden |
| 4 | gemeinsame Settings-/Config-Lesewege vorbereiten | Voraussetzung für Live-Settings |

### Nicht tun

- Kein Feature-Verhalten ändern.
- Keine UI umbauen.
- Keine Contracts ändern, außer es ist zwingend.
- Kein „bei der Gelegenheit“ Cleanup über 40 Dateien. Das ist kein Refactor, das ist eine Ausgrabung.

## Danach: P1-C Contract-Generation + Status-Sync

### Ziel

Schema-/Status-Drift weiter reduzieren.

### Aufgaben

- Contract-Dump reproduzierbar machen.
- Frontend-Zod-Spiegel automatisierter prüfen.
- `scripts/sync-status.sh` als Pflichtschritt dokumentieren oder in CI absichern.
- Status-Dateien nach größeren Merges automatisch konsistent halten.

## Danach: P1-D Playwright-Smokes

### Ziel

End-to-End-Nachweis für MVP.

### Minimal-Suite

1. Health/Login:
   - App lädt
   - Token/Auth funktioniert
   - `/health` erreichbar

2. Upload + Graph:
   - kleines Testdokument hochladen
   - Graph-Erstellung starten
   - Ergebnisstatus prüfen

3. Minimalreport:
   - vorhandenen kleinen Fixture-Run nutzen
   - Report generieren
   - Basisbestandteile im UI prüfen

### Wichtig

Playwright nicht als riesige Testpyramide starten. Drei stabile Smokes reichen für v1.0-Richtung. Menschen bauen sonst gern 90 UI-Tests und wundern sich dann über 90 kaputte UI-Tests.

## P2: Live-Settings (#212)

### Empfehlung

Noch nicht sofort.

Warum:
- `GET /api/settings` / `PUT /api/settings`
- Runtime-Persistenz
- Secrets-Redaction
- Event-Bus-Broadcast
- Services weg von `os.getenv`
- Frontend-Drawer
- Pinia + Zod + i18n

Das ist ein echter Architektur-Slice. Der sollte nach Hotspot-Refactors und Contract-Generation kommen, sonst ziehst Du Settings quer durch noch bewegliche Services.

## Codex /goal für den nächsten sinnvollen Slice

```text
/goal Ziel: Schließe den P0-Dependency-Slice sauber ab und bereite den Übergang zu M11 vor.

Kontext:
- Repo: arn0ld87/agora
- P0-Dependency-Triage ist fachlich abgeschlossen.
- M9/M10 gelten als abgeschlossen.
- Aktiver Übergang: M11.
- Offene relevante PRs: #315 camel-ai, #323 mistune, #326 pygments.
- Offene relevante Issues: #199 Python 3.14/tiktoken, #121-#126 und #296-#298 CVE-Watchlist, #212 Live-Settings.
- Nicht direkt auf main arbeiten.

Aufgaben:
1. Lies AGENTS.md, docs/status.md, docs/dependency-risk-register.md und die P0-Triage-Doku.
2. Prüfe den aktuellen Zustand von PR #315:
   - Wenn camel-ai weiterhin durch camel-oasis hard pin blockiert ist, dokumentiere das Ergebnis und bereite einen klaren Close-Kommentar vor.
   - Wenn eine kompatible Lösung vorliegt, mache CI und contract-gates grün.
3. Prüfe PR #323 und #326:
   - Wenn CI, contract-gates, dependency-review und CodeQL grün sind, empfehle Merge.
   - Wenn nicht, dokumentiere Blocker präzise.
4. Aktualisiere docs/dependency-risk-register.md nur, wenn sich durch P0 echte CVE-Auflösung oder neue Blocker ergeben haben.
5. Erstelle oder aktualisiere eine kurze M11-Startnotiz:
   - Nächste Reihenfolge: Phase 5 Hotspot-Refactors, Phase 6 Contract-Generation/Status-Sync, Phase 7 Playwright-Smokes.
   - Live-Settings #212 bleibt P2 nach M11-Stabilisierung.
6. Führe lokale Checks aus:
   cd backend && uv sync --group dev
   cd backend && uv run pytest tests/contracts/ -v
   cd backend && uv run ruff check .
   cd backend && uv run mypy app
   cd frontend && npm ci
   cd frontend && npm run lint
   cd frontend && npm run typecheck
   cd frontend && npm run test:coverage

Akzeptanz:
- Keine neuen CVE-Ignores.
- Keine Secrets.
- Keine direkten Pushes auf main.
- Ergebnis ist als kurze Markdown-Doku unter docs/ abgelegt.
- Git-Status ist sauber oder alle Änderungen sind nachvollziehbar.
```

## Codex /goal für den ersten echten M11-Slice

```text
/goal Ziel: Starte M11 Phase 5 mit einem risikoarmen Hotspot-Refactor ohne Verhaltensänderung.

Kontext:
- Repo: arn0ld87/agora
- M9/M10 abgeschlossen, P0-Dependency-Triage erledigt.
- M11 nächste Ziele laut docs/status.md:
  1. v1.0-Hotspot-Refactors Phase 5
  2. Contract-Generation + Status-Sync Phase 6
  3. M11.4 Playwright-Smokes Phase 7
- Ziel ist Wartbarkeit, nicht Feature-Ausbau.
- Nicht direkt auf main arbeiten.

Aufgaben:
1. Lies AGENTS.md, CLAUDE.md, docs/status.md und PLAN.md.
2. Wähle genau einen Hotspot für diesen PR:
   - bevorzugt backend/app/services/simulation_runner.py oder backend/app/services/graph_tools.py
   - keine parallelen Refactors an mehreren Hotspots
3. Erstelle zuerst eine kurze Schnittanalyse:
   - Verantwortlichkeiten
   - externe Call-Sites
   - vorhandene Tests
   - Risiko
   - geplante Extraktionsgrenze
4. Extrahiere nur klar abgrenzbare pure/helper Logik.
5. Ändere keine API-Contracts und kein Verhalten.
6. Ergänze/verschiebe Tests passend zur neuen Struktur.
7. Führe Checks aus:
   cd backend && uv run pytest
   cd backend && uv run ruff check .
   cd backend && uv run mypy app
   git diff --stat
8. Dokumentiere den Slice unter docs/<datum>-m11-phase5-hotspot-refactor.md.

Akzeptanz:
- Tests grün.
- Ruff grün.
- mypy grün.
- Kein Schema-Drift.
- Datei-Hotspot messbar kleiner.
- Verhalten unverändert.
- PR bleibt klein und reviewbar.
```
