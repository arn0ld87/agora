### Behoben

- **`build-only` lief seit dem 2026-08-28 auf `main` und damit auf jedem PR rot:**
  Der `Trivy container scan` fand CVE-2026-14456 (HIGH) in `openssl`,
  `libssl3t64` und `openssl-provider-legacy` — installiert `3.5.6-1~deb13u2`,
  gefixt in `3.5.7-1~deb13u2`. Gescannt wird `target: prod`, also genau die
  Stage, die seit #1328 ein `apt-get update && apt-get upgrade -y` traegt. Der
  Upgrade lief trotzdem ins Leere: Der Build-Job zieht `cache-from: type=gha`,
  und solange FROM-Digest und Instruktion unveraendert bleiben, serviert
  BuildKit den alten apt-Layer — die Zeile wird gar nicht neu ausgefuehrt, der
  Debian-Fix erreicht das Image nie. Die prod-Stage haengt jetzt am aktuellen
  `python:3.14-slim`-Digest (`sha256:cad9a2c8...`, zuvor `sha256:cea0e604...`).
  Der Bump ersetzt den Upgrade nicht, er loest ihn aus: neuer FROM-Digest =
  invalidierter Layer = frischer apt-Lauf. Lokal verifiziert, dass
  `3.5.7-1~deb13u2` im neuen Basisimage als Candidate bereitsteht. (#1410)
