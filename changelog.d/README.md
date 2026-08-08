# changelog.d — CHANGELOG-Fragmente

Seit 2026-08-08 schreibt **kein PR mehr direkt in `CHANGELOG.md`**. Stattdessen
legt jeder PR mit dokumentationspflichtiger Änderung genau **eine eigene
Fragment-Datei** in diesem Verzeichnis an. Eindeutige Dateinamen können nicht
kollidieren — damit ist die Klasse „jeder Merge macht den nächsten PR
konfliktbehaftet" strukturell beseitigt.

## Format

Dateiname: `<pr-oder-issue-nummer>-<kurzer-slug>.md`, z. B. `1140-trivy-severity.md`.

Inhalt: exakt der Block, der später in `CHANGELOG.md` unter `## [Unreleased]`
stehen soll — Überschrift im Keep-a-Changelog-Stil plus Bullet(s):

```markdown
### Fixed (Kurzbeschreibung — 2026-08-08)

- **Fettgedruckte Kernaussage:** Detailtext mit Begründung. (#1234)
```

Zulässige Kategorien: `Added`, `Changed`, `Fixed`, `Removed`, `Security`.

## Einsammeln (Release-Schnitt oder bei Bedarf)

```bash
python3 scripts/collect-changelog.py          # faltet Fragmente nach CHANGELOG.md, löscht sie
python3 scripts/collect-changelog.py --check  # nur prüfen: Exit 1, wenn Fragmente vorliegen
```

Das Skript sortiert Fragmente nach Dateiname (absteigend, neueste PR-Nummer
zuerst), fügt sie direkt unter `## [Unreleased]` ein und entfernt die
Fragment-Dateien im selben Commit.

## Regeln

- Ein PR = eine Fragment-Datei. Diese README bleibt liegen.
- `CHANGELOG.md` selbst wird nur noch von `collect-changelog.py` und beim
  Release-Cut angefasst.
- Review-Bots: Ein Fragment in `changelog.d/` erfüllt die
  AGENTS.md-Pflicht „ausgelieferte Änderung → CHANGELOG.md" — die Übernahme
  in die Datei passiert gesammelt beim Release-Schnitt.
