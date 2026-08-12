# Referenzläufe und Evaluationen

Referenzläufe dokumentieren reale Agora-End-to-End-Läufe einschließlich Szenario, Simulationsmetriken, Reportausgabe, Evidenzgrenzen und bekannter Produktmängel.

Sie sind **keine** Nachweise dafür, dass Agora reales menschliches Verhalten vorhersagt. Simulierte Personas und Social-Aktionen sind Modelloutput; belastbare Aussagen über reale Menschen benötigen weiterhin empirische Daten.

## Verfügbare Läufe

- **[2026-08-12 · Referenzlauf 5: Domainmigration, 20 Runden](./2026-08-12-domain-migration-20-runden/README.de.md) — aktueller Referenzlauf.** Post-Hardening-Trust-Audit mit 46 validierten Claim-Zeilen, 141 Hypothesen und 133 Data Gaps. Zeigt als zentrale verbleibende Trust-Grenze, dass ein korrekt gebundenes Seed-Fragment seinen epistemischen Status verlieren kann; dokumentiert außerdem Fremdrollen-Evidence, Scope-/Basis-Mismatch und verbleibende Persona-Eignungsfehler.
- [2026-08-11 · Referenzlauf 4: KI-Lernassistent, 20 Runden](./2026-08-11-ki-lernassistent-20-runden/README.de.md) — erster Lauf mit Evidence Binding in brauchbarer Größenordnung (39 validierte Claims); bleibt mit 665 Social Actions und sechs Clustern die reichhaltigere Referenz für Simulationsdynamik.
- [2026-08-11 · Referenzlauf 3: KI-Lernassistent, 10 Runden](./2026-08-11-ki-lernassistent/README.md) — früherer Lernassistenten-Lauf mit `deepseek-v4-flash`, der Mechanismen und Fehlerklassen dokumentiert, auf denen Referenzlauf 4 aufbaut.
- [2026-08-09 · Domainmigration v2 nach Evidence-Identity-Remediation](./2026-08-09-domain-migration-v2/README.md) — Follow-up mit 30 konsistent erfassten Agenten, 412 Graph-Interaktionen, 540 Social Actions, adaptiver Reportplanung und section-spezifischen Deep Interviews; dokumentiert offen den weiterhin bestehenden Interview→Evidence-Binding-Defekt und `0` validierte ReportV3-Claims.
- [2026-08-09 · Domainmigration alexle135.de → alex-schneider.dev](./2026-08-09-domain-migration/README.md) — erster öffentlicher Referenzlauf mit Social-Multi-Agenten-Simulation, Evidence Gating, strukturiertem Entscheidungsreport, bekannten Grenzen und nachgelagerter Remediation.

## Einordnung

Referenzlauf 5 ist die aktuelle **Trust-Pipeline-Referenz**. Referenzlauf 4 bleibt bewusst erhalten, weil er die stärkere Social-/Simulationsdynamik dokumentiert. Keiner der Läufe ist als „Golden Run“ oder als Nachweis prädiktiver Validität zu verstehen.
