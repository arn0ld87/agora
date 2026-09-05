### Hinzugefügt

- `bun run bigpowers:sync` legt das Bigpowers-Tooling als relative Symlinks auf
  `node_modules/bigpowers` in `scripts/` und `.claude/skills/` ab und traegt sie
  zugleich in `.git/info/exclude` ein. Die Symlinks sind maschinenlokale
  Build-Artefakte und bleiben damit aus dem Repo heraus, ohne dass jemand sie
  von Hand ausschliessen muss. Vorhandene AGORA-Dateien werden nie
  ueberschrieben — gleichnamige Bigpowers-Dateien meldet das Skript als
  Konflikt und laesst sie liegen. Symlinks, die auf eine inzwischen entfernte
  Bigpowers-Datei zeigen, raeumt das Skript beim Sync weg.

  `--check` verifiziert das Overlay gegen die installierte Abhaengigkeit statt
  gegen den Ist-Zustand des Arbeitsbaums: fehlende, kaputte oder nicht
  ausgeschlossene Symlinks sind Drift, und ein Lauf ohne installiertes
  Bigpowers meldet Drift statt Erfolg. Damit eignet es sich als Gate-Schritt.
  In Git-Worktrees (`.git` ist dort eine Datei, kein Verzeichnis) findet das
  Skript den gemeinsamen Ausschlusspfad ueber `git rev-parse --git-common-dir`.
