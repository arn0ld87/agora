### Behoben

- Zuschreibungen im Fließtext folgen der Beleglage. "Die Simulation zeigt …"
  wird zu "Die Quellenlage zeigt …", wenn keine Simulations-Evidence vorliegt;
  Interview-Formulierungen ohne stattgefundene Interviews ebenso. Ersetzt wird
  nur die Zeugenformel, nie die Aussage.
- Semantisch identische Claims aus mehreren Abschnitten erscheinen einmal.
  Zusammengeführt wird nur bei gleichen Zahlen, gleicher Belegmenge und hoher
  Wortüberlappung; Entferntes steht im Protokoll.
- Ein zusammengesetzter Claim gilt nur als belegt, wenn die Quelle jede seiner
  Teilaussagen berührt.
- Die Belegprüfung steht gesammelt im Anhang statt hinter jedem Abschnitt.
  Gelöscht wird nichts — die Marken im Fließtext bleiben satzgenau erhalten.

### Behoben (Regression aus diesem Branch)

- Der Report-Export antwortete mit 400, weil `to_dict()` ein `degraded`-Feld
  ausgab, das der strikte Contract nicht kennt.
