# Referenzläufe und Evaluationen

Referenzläufe dokumentieren reale Agora-End-to-End-Läufe einschließlich Szenario, Simulationsmetriken, Reportausgabe, Evidenzgrenzen und bekannter Produktmängel.

Sie sind **keine** Nachweise dafür, dass Agora reales menschliches Verhalten vorhersagt. Simulierte Personas und Social-Aktionen sind Modelloutput; belastbare Aussagen über reale Menschen benötigen weiterhin empirische Daten.

## Verfügbare Läufe

- **[2026-08-14 · Referenzlauf 6: AURORA Report-Regression](./2026-08-14-aurora-report/README.de.md) — aktueller Referenzlauf.** Derselbe abgeschlossene Simulationslauf wurde mit der überarbeiteten Report-Pipeline erneut ausgewertet. Dadurch lassen sich Änderungen an Laufzeit, Interviewintegration und Evidence Gating beobachten, ohne einen neuen stochastischen Simulationslauf einzuführen. Der Lauf dokumentiert zugleich verbleibende Fehler bei numerischem Evidence Binding, Quote-Ankern, Confidence und ReportV3-Abschlusssemantik. Er ist eine beobachtbare Regressionreferenz, kein vollständig reproduzierbarer Golden Run.
- [2026-08-12 · Referenzlauf 5: Domainmigration, 20 Runden](./2026-08-12-domain-migration-20-runden/README.de.md) — Post-Hardening-Trust-Audit mit 46 validierten Claim-Zeilen, 141 Hypothesen und 133 Data Gaps. Zeigt als zentrale verbleibende Trust-Grenze, dass ein korrekt gebundenes Seed-Fragment seinen epistemischen Status verlieren kann; dokumentiert außerdem Fremdrollen-Evidence, Scope-/Basis-Mismatch und verbleibende Persona-Eignungsfehler.
- [2026-08-11 · Referenzlauf 4: KI-Lernassistent, 20 Runden](./2026-08-11-ki-lernassistent-20-runden/README.de.md) — erster Lauf mit Evidence Binding in brauchbarer Größenordnung (39 validierte Claims); bleibt mit 665 Social Actions und sechs Clustern die reichhaltigere Referenz für Simulationsdynamik.
- [2026-08-11 · Referenzlauf 3: KI-Lernassistent, 10 Runden](./2026-08-11-ki-lernassistent/README.md) — früherer Lernassistenten-Lauf mit `deepseek-v4-flash`.
- [2026-08-09 · Domainmigration v2 nach Evidence-Identity-Remediation](./2026-08-09-domain-migration-v2/README.md) — Follow-up mit 30 konsistent erfassten Agenten, 412 Graph-Interaktionen, 540 Social Actions und section-spezifischen Deep Interviews.
- [2026-08-09 · Domainmigration alexle135.de → alex-schneider.dev](./2026-08-09-domain-migration/README.md) — erster öffentlicher Referenzlauf mit Social-Multi-Agenten-Simulation, Evidence Gating und strukturiertem Entscheidungsreport.

## Einordnung

Referenzlauf 6 ist die aktuelle **Report-/Trust-Pipeline-Referenz**. Referenzlauf 5 bleibt als vorheriger Trust-Pipeline-Vergleich erhalten; Referenzlauf 4 dokumentiert weiterhin die stärkere Social-/Simulationsdynamik. Keiner der Läufe ist als Nachweis prädiktiver Validität zu verstehen.
