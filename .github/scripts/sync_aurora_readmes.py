from pathlib import Path
import re

EN = Path("README.md")
DE = Path("README.de.md")

en = EN.read_text()
en = en.replace(
    "2026-08-14-aurora/01-evidence-inspector.jpg",
    "2026-08-14-aurora/01-evidence-inspector.webp",
)
en = en.replace(
    "2026-08-14-aurora/02-agent-interviews.jpg",
    "2026-08-14-aurora/02-agent-interviews.webp",
)
en = en.replace(
    "**[→ Read the full Reference run 6 notes](./docs/reference-runs/2026-08-14-aurora-report/README.md)**",
    "**[→ Read the full Reference run 6 notes](./docs/reference-runs/2026-08-14-aurora-report/README.md)** · **[auf Deutsch](./docs/reference-runs/2026-08-14-aurora-report/README.de.md)**",
)
EN.write_text(en)

de = DE.read_text()
replacement = """## Referenzlauf

Die aktuelle Referenz ist **Referenzlauf 6: AURORA**, ein Entscheidungsbericht für den fiktiven Städtischen Klinikverbund Falkenbrück zum geplanten Rollout des KI-gestützten Triage- und Dokumentationssystems **Nexora Triage Assist**. Der Report wurde am **14.08.2026** als `report_3c594fcc7613` aus der bereits abgeschlossenen Simulation `sim_4245ff3d7b23` erzeugt.

Dieser Lauf ist besonders nützlich, weil **die Simulation unverändert blieb und nur die Report-Pipeline erneut ausgeführt wurde**. Er dient damit als Reporter-Referenz statt als Vergleich zweier unterschiedlicher stochastischer Simulationen. Die überarbeitete Pipeline verkürzte die End-to-End-Reportgenerierung von ungefähr **17:52 min auf 8:19 min** und nutzt gezielte `interview_agents`-Aufrufe über alle sechs Reportabschnitte hinweg.

Der Report empfiehlt einen **konditionierten, gestaffelten Rollout ab Falkenbrück-Mitte** und koppelt die Ausweitung an Sicherheits-, Schulungs-, Mitbestimmungs- und Fallback-Bedingungen. Im Evidence Inspector lassen sich Claims, Hypothesen, Confidence und die jeweils gebundenen Evidence Records direkt neben dem Report prüfen.

![AURORA-Referenzreport — Sections, Claims und Hypothesen im Evidence Inspector](./docs/assets/screenshots/reference-runs/2026-08-14-aurora/01-evidence-inspector.webp)

Die zweite Ansicht zeigt die Verbindung zwischen einem ausgewählten Claim und konkreten `agent_interview`-Evidence-Cards. Damit wird sichtbar, dass die simulierten Stakeholder während der Reportgenerierung erneut gezielt befragt werden und ihre Antworten als Evidence inspizierbar bleiben.

![AURORA-Referenzreport — Agenteninterviews als Evidence](./docs/assets/screenshots/reference-runs/2026-08-14-aurora/02-agent-interviews.webp)

> [!NOTE]
> Dies ist bewusst ein **Referenzlauf und keine Hochglanz-Demo**. Der Lauf zeigt reale Fortschritte bei Laufzeit, Interviewintegration und Evidence Gating, bewahrt aber bekannte Trust-Grenzen als Regressionstestfälle: Der dokumentierte Seed-Fakt zu **38 Fällen mit abweichender Dringlichkeitseinstufung** wird in einzelnen Sections weiterhin fälschlich als nicht ausreichend zahlenbelegt herabgestuft; einige simulierte Zitate tragen noch `seed_doc:seed_aurora#chunk:0`; stark passende `SUPPORTED` Evidence kann `low` Confidence behalten; und ein ReportV3-Contractfehler kann auftreten, während der Gesamtauftrag dennoch `completed` erreicht. Der Lauf ist deshalb eine **beobachtbare Reporter-Referenz**, aber ohne die fehlenden Laufartefakte kein vollständig reproduzierbares Fresh-Checkout-Replay.

**[→ Vollständige Notizen zu Referenzlauf 6](./docs/reference-runs/2026-08-14-aurora-report/README.de.md)** · **[English](./docs/reference-runs/2026-08-14-aurora-report/README.md)**

Frühere Läufe: [Referenzlauf 5](./docs/reference-runs/2026-08-12-domain-migration-20-runden/README.de.md) (Trust-Pipeline-Referenz) · [Referenzlauf 4](./docs/reference-runs/2026-08-11-ki-lernassistent-20-runden/README.de.md) (Evidence Binding at Scale; reichhaltigere Simulationsdynamik) · [Lauf 3](./docs/reference-runs/2026-08-11-ki-lernassistent/README.md) · [Lauf 2](./docs/reference-runs/2026-08-09-domain-migration-v2/README.md) · [Lauf 1](./docs/reference-runs/2026-08-09-domain-migration/README.md)

---

## Was ist Agora?"""

pattern = r"## Referenzlauf\n.*?\n---\n\n## Was ist Agora\?"
new_de, count = re.subn(pattern, replacement, de, count=1, flags=re.S)
if count != 1:
    raise SystemExit(f"Expected one Referenzlauf section, replaced {count}")
DE.write_text(new_de)
