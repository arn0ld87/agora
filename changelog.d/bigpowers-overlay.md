### Hinzugefügt

- `bun run bigpowers:sync` legt das Bigpowers-Tooling als relative Symlinks auf
  `node_modules/bigpowers` in `scripts/` und `.claude/skills/` ab und traegt sie
  zugleich in `.git/info/exclude` ein. Die Symlinks sind maschinenlokale
  Build-Artefakte und bleiben damit aus dem Repo heraus, ohne dass jemand sie
  von Hand ausschliessen muss. Vorhandene AGORA-Dateien werden nie
  ueberschrieben — gleichnamige Bigpowers-Dateien meldet das Skript als
  Konflikt und laesst sie liegen. `--check` verifiziert das Overlay
  (kaputte Symlinks, fehlende Ausschluesse) und eignet sich als Gate-Schritt.
