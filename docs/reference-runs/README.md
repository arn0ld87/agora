# Referenzläufe und Evaluationen

Referenzläufe dokumentieren reale Agora-End-to-End-Läufe einschließlich Szenario, Simulationsmetriken, Reportausgabe, Evidenzgrenzen und bekannter Produktmängel.

Sie sind **keine** Nachweise dafür, dass Agora reales menschliches Verhalten vorhersagt. Simulierte Personas und Social-Aktionen sind Modelloutput; belastbare Aussagen über reale Menschen benötigen weiterhin empirische Daten.

## Verfügbare Läufe

- **[2026-08-14 · Referenzlauf 6: AURORA-Entscheidungsreport](./2026-08-14-aurora-report/README.de.md) — aktueller Referenzlauf.** Reporter-Referenz auf derselben abgeschlossenen Simulation `sim_4245ff3d7b23`: der Report wurde neu erzeugt, ohne die Simulation zu verändern. Zeigt die deutlich schnellere Report-Pipeline, gezielte Agenteninterviews über alle sechs Sections und den Evidence Inspector mit Claims, Hypothesen und `agent_interview`-Evidence. Bekannte Trust-Grenzen bleiben bewusst dokumentiert. Der Lauf ist ein beobachtbarer Regressionstestfall, aber ohne die fehlenden Laufartefakte kein vollständig reproduzierbares Fresh-Checkout-Replay.
- [2026-08-12 · Referenzlauf 5: Domainmigration, 20 Runden](./2026-08-12-domain-migration-20-runden/README.de.md) — Trust-Pipeline-Referenz. Post-Hardening-Trust-Audit mit 46 validierten Claim-Zeilen, 141 Hypothesen und 133 Data Gaps; zeigt unter anderem den Verlust des epistemischen Status korrekt gebundener Seed-Fragmente, Fremdrollen-Evidence und Scope-/Basis-Mismatches.
- [2026-08-11 · Referenzlauf 4: KI-Lernassistent, 20 Runden](./2026-08-11-ki-lernassistent-20-runden/README.de.md) — erster Lauf mit Evidence Binding in brauchbarer Größenordnung (39 validierte Claims); bleibt mit 665 Social Actions und sechs Clustern die reichhaltigere Referenz für Simulationsdynamik.
- [2026-08-11 · Referenzlauf 3: KI-Lernassistent, 10 Runden](./2026-08-11-ki-lernassistent/README.md) — früherer Lernassistenten-Lauf mit `deepseek-v4-flash`, der Mechanismen und Fehlerklassen dokumentiert, auf denen Referenzlauf 4 aufbaut.
- [2026-08-09 · Domainmigration v2 nach Evidence-Identity-Remediation](./2026-08-09-domain-migration-v2/README.md) — Follow-up mit 30 konsistent erfassten Agenten, 412 Graph-Interaktionen, 540 Social Actions, adaptiver Reportplanung und section-spezifischen Deep Interviews; dokumentiert offen den weiterhin bestehenden Interview→Evidence-Binding-Defekt und `0` validierte ReportV3-Claims.
- [2026-08-09 · Domainmigration alexle135.de → alex-schneider.dev](./2026-08-09-domain-migration/README.md) — erster öffentlicher Referenzlauf mit Social-Multi-Agenten-Simulation, Evidence Gating, strukturiertem Entscheidungsreport, bekannten Grenzen und nachgelagerter Remediation.

## Einordnung

Referenzlauf 6 ist die aktuelle **Reporter-/Evidence-Inspector-Referenz**. Referenzlauf 5 bleibt die gezielte **Trust-Pipeline-Referenz**, Referenzlauf 4 die reichhaltigere Referenz für **Simulationsdynamik**. Keiner der Läufe ist als „Golden Run“ oder als Nachweis prädiktiver Validität zu verstehen.
