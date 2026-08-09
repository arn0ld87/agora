# Domain Migration Reference Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Den realen Agora-Lauf `report_41f7b1bcf1e4` als öffentlichen, kritisch dokumentierten End-to-End-Referenzlauf im Repository veröffentlichen und ihn knapp aus README und Dokumentationsindex verlinken.

**Architecture:** Der Referenzlauf lebt isoliert unter `docs/reference-runs/2026-08-09-domain-migration/`. Die Haupt-README enthält nur einen kurzen Teaser; die vollständige Einordnung, Methodik, Metriken, Grenzen, Audit-Folgen und Reproduzierbarkeitsgrenzen stehen in der Case Study. Unveränderte textbasierte Exportartefakte werden unter `artifacts/` eingefroren und dienen als überprüfbare Primärquellen.

**Tech Stack:** Markdown, JSON, bestehende GitHub-Dokumentationsstruktur, Agora Report/Evidence-Export.

## Global Constraints

- Der Lauf demonstriert aktuelle End-to-End-Fähigkeiten, aber keine prädiktive Validität für reales menschliches Verhalten.
- Die Haupt-README bleibt deutsch und erhält nur einen kurzen Teaser.
- Die Case Study bleibt deutsch; etablierte technische Begriffe dürfen englisch bleiben.
- `33` erzeugte Agenten stammen aus dem Laufkontext; `total_agents: 24` ist der belegte Metrics-Snapshot. Diese Differenz wird nicht erfunden erklärt.
- Belegte Snapshot-Metriken: `total_interactions: 267`, `cluster_count: 3`, `echo_chamber_index: 0.4794`, Bridge Agents `[24, 15, 11, 18, 0]`, Clustergrößen `13`, `6`, `5`.
- Persona-Aussagen sind Simulationsereignisse, keine realen Stakeholder-Interviews.
- Audit-Finding, Laufbeobachtung und nachträgliche Remediation werden getrennt benannt.
- PR `#1147` darf als gemergte Remediation der kanonischen Evidence-Identität genannt werden; nicht als Lösung aller sichtbaren Probleme.
- Historische Rohartefakte werden inhaltlich nicht redaktionell umgeschrieben.
- Keine Änderungen an Report-Engine, Simulation oder Evidence-Gating-Logik in diesem PR.

---

### Task 1: Reference-Run-Index und eingefrorene Artefakte

**Files:**
- Create: `docs/reference-runs/README.md`
- Create: `docs/reference-runs/2026-08-09-domain-migration/artifacts/report.md`
- Create: `docs/reference-runs/2026-08-09-domain-migration/artifacts/evidence.json`

**Interfaces:**
- Consumes: Originalexporte `agora-report-report_41f7b1bcf1e4.md` und `agora-report-report_41f7b1bcf1e4-evidence.json`.
- Produces: stabile relative Pfade, auf die Case Study und README verweisen.

- [ ] **Step 1: Erzeuge den Reference-Run-Index**

Inhalt von `docs/reference-runs/README.md`:

```markdown
# Referenzläufe und Evaluationen

Referenzläufe dokumentieren reale Agora-End-to-End-Läufe einschließlich Eingaben, Simulationsmetriken, Reportausgaben, Evidenzgrenzen und bekannter Produktmängel.

Sie sind keine Nachweise prädiktiver Validität für reales menschliches Verhalten.

## Verfügbare Läufe

- [2026-08-09 · Domainmigration alexle135.de → alex-schneider.dev](./2026-08-09-domain-migration/README.md) — Social-Multi-Agenten-Simulation, Evidence Gating, Report, bekannte Grenzen und nachgelagerte Remediation.
```

- [ ] **Step 2: Kopiere den Markdown-Report byte-/textgleich in den Artifact-Pfad**

Quelle: angehängter Export `agora-report-report_41f7b1bcf1e4.md`.
Ziel: `docs/reference-runs/2026-08-09-domain-migration/artifacts/report.md`.

- [ ] **Step 3: Kopiere den Evidence-Export textgleich in den Artifact-Pfad**

Quelle: angehängter Export `agora-report-report_41f7b1bcf1e4-evidence.json`.
Ziel: `docs/reference-runs/2026-08-09-domain-migration/artifacts/evidence.json`.

- [ ] **Step 4: Validiere den JSON-Export**

Run lokal gegen die eingefrorene Datei:

```bash
python -m json.tool docs/reference-runs/2026-08-09-domain-migration/artifacts/evidence.json >/dev/null
```

Expected: Exit `0`.

- [ ] **Step 5: Verifiziere die zentralen IDs und Snapshot-Metriken**

```bash
python - <<'PY'
import json
from pathlib import Path
p = Path('docs/reference-runs/2026-08-09-domain-migration/artifacts/evidence.json')
data = json.loads(p.read_text())
assert data['report_id'] == 'report_41f7b1bcf1e4'
assert data['simulation_id'] == 'sim_1d96603073ae'
text = p.read_text()
for expected in [
    '"total_agents": 24',
    '"total_interactions": 267',
    '"cluster_count": 3',
    '"echo_chamber_index": 0.4794',
]:
    assert expected in text, expected
print('reference artifacts verified')
PY
```

Expected: `reference artifacts verified`.

- [ ] **Step 6: Commit**

```bash
git add docs/reference-runs/README.md docs/reference-runs/2026-08-09-domain-migration/artifacts/
git commit -m "docs: add domain migration reference artifacts"
```

---

### Task 2: Vollständige technische Case Study

**Files:**
- Create: `docs/reference-runs/2026-08-09-domain-migration/README.md`

**Interfaces:**
- Consumes: eingefrorene `artifacts/report.md`, `artifacts/evidence.json`, Audit-/Remediation-Plan und gemergte PR `#1147`.
- Produces: kanonische öffentliche Einordnung des Referenzlaufs.

- [ ] **Step 1: Schreibe Metadaten und Scope**

Die Case Study beginnt mit:

```markdown
# Referenzlauf: Domainmigration alexle135.de → alex-schneider.dev

> [!IMPORTANT]
> Dieser Lauf demonstriert Agoras End-to-End-Pipeline und Evidence-Gating-Verhalten in einem konkreten Szenario. Er validiert keine Vorhersage realen menschlichen Verhaltens und ersetzt keine empirische Nutzer- oder Stakeholderforschung.

| Feld | Wert |
|---|---|
| Datum | 9. August 2026 |
| Report | `report_41f7b1bcf1e4` |
| Simulation | `sim_1d96603073ae` |
| Szenario | Domainmigration `alexle135.de` → `alex-schneider.dev` |
| Umgebungen | Reddit-/Twitter-artige Social Simulation |
| Report-Artefakt | [`artifacts/report.md`](./artifacts/report.md) |
| Evidence-Artefakt | [`artifacts/evidence.json`](./artifacts/evidence.json) |
```

- [ ] **Step 2: Dokumentiere Eingabe und Ziel des Laufs**

Erkläre knapp, dass das Seed-Material reale Ausgangsdaten, Planungsannahmen, synthetische Stakeholder-Aussagen und bewusst eingebaute Widersprüche kombinierte. Nenne als Analyseziel die technische, kommunikative und markenstrategische Bewertung der Migration.

- [ ] **Step 3: Dokumentiere den Simulations-Snapshot**

Nutze exakt diese Tabelle:

```markdown
| Metrik | Exportierter Wert |
|---|---:|
| Aktive Agenten im Metrics-Snapshot | 24 |
| Social Interactions | 267 |
| Cluster | 3 |
| Echo-Chamber-Index | 0.4794 |
| Bridge Agents | 24, 15, 11, 18, 0 |
| Clustergrößen | 13 / 6 / 5 |
```

Direkt darunter:

```markdown
> [!WARNING]
> Im Laufkontext wurden 33 erzeugte Agenten angegeben, während der exportierte Metrics-Snapshot `total_agents: 24` ausweist. Aus den eingefrorenen Artefakten lässt sich nicht belastbar ableiten, ob dies aktive Agenten, ein Analysefenster oder eine Instrumentationslücke abbildet. Die Differenz bleibt daher ausdrücklich offen.
```

- [ ] **Step 4: Beschreibe die soziale Dynamik statt nur Persona-Interviews**

Zeige, dass der Evidence-Export `agent_action`-Ereignisse enthält, darunter `CREATE_POST` auf Reddit sowie weitere Social-Actions. Erkläre, dass der Report nur ausgewählte Persona-O-Töne vertieft, während die Simulation breiter ist.

- [ ] **Step 5: Fasse das Report-Ergebnis neutral zusammen**

Nenne Option B als Ergebnis des Reports, Identitätsinkonsistenz, Redirect-/SEO-/E-Mail-Risiken und `.dev`-Fehlwahrnehmung. Kennzeichne explizit, dass Recruiting- und SEO-Wirkung nicht empirisch belegt sind.

- [ ] **Step 6: Dokumentiere Evidence-Gating als Kernnachweis**

Beschreibe mit konkreten Kategorien:

```markdown
- `SUPPORTED`: Aussage hat geeignete gebundene Evidenz.
- `RELATED_ONLY`: Quelle ist thematisch verwandt, belegt den Claim aber nicht.
- `INSUFFICIENT`: Evidenz reicht für den Claim bzw. die numerische Aussage nicht aus.
- Hypothesis/Data Gap: Aussage bleibt sichtbar, wird aber nicht als validierter Claim persistiert.
- Confidence degradation: zu hoch angesetzte Confidence kann validatorseitig heruntergestuft werden.
```

Verweise auf das eingefrorene Evidence-JSON als Primärquelle.

- [ ] **Step 7: Schreibe sichtbar `Was funktioniert hat`**

Nur beobachtbare Punkte:

```markdown
- vollständiger Dokument→Graph→Persona→Social-Simulation→Evidence→Report-Pfad,
- Social-Agent-Aktivität in Reddit-/Twitter-artigen Umgebungen,
- Graph-/Interaktionsmetriken,
- strukturierter Entscheidungsreport,
- Hypothesen- und Data-Gap-Ausgabe,
- Entailment-/Evidence-Prüfung und Confidence-Degradation,
- exportierbare Markdown-/JSON-/HTML-/PDF-Artefakte.
```

- [ ] **Step 8: Schreibe sichtbar `Was nicht funktioniert hat oder unklar blieb`**

Mindestens diese sieben Punkte:

```markdown
1. 33 erzeugte Agenten im Laufkontext vs. 24 im Metrics-Snapshot sind nicht erklärt.
2. Der Report reduziert die breite Social Simulation stellenweise auf wenige vertiefend zitierte Personas.
3. Begriffe wie „Konsens“ sind stellenweise stärker als die gebundene Evidence.
4. Vorhandene Cluster-/Bridge-/Echo-Chamber-Metriken werden im finalen Report nur schwach ausgewertet.
5. Die damalige Legacy-Evidence-Identität war nicht kanonisch genug.
6. Mehrere Aussagen landen korrekt als `no_evidence_bound`, `RELATED_ONLY` oder unterhalb des Reviewer-Floors, zeigen aber zugleich eine niedrige belastbare Claim-Ausbeute.
7. Der historische Lauf besitzt noch keinen vollständigen RunManifest-/Replay-Nachweis.
```

- [ ] **Step 9: Trenne Laufbeobachtung, Audit und Remediation**

Nutze eine Tabelle mit den Spalten `Ebene`, `Befund`, `Status` und nenne dort insbesondere die Evidence-Identity-Lücke sowie PR `#1147` als gemergte Folgekorrektur. Sage ausdrücklich, dass andere Kritikpunkte offen bleiben.

- [ ] **Step 10: Schreibe `Was dieser Lauf zeigt` und `Was er nicht zeigt`**

Zulässig: End-to-End-Verarbeitung, Social-Agent-Interaktion, Graphmetriken, strukturierte Hypothesen/Risiken/Gaps, funktionierendes Evidence-Gating und Produktmängel als Ergebnis eines realen Runs.

Nicht zulässig: reale Vorhersagegüte, Repräsentativität, Recruiter-Präferenz für `.dev`, reale SEO-Wirkung, allgemeingültige Qualität aller Runs, vollständige Reproduzierbarkeit.

- [ ] **Step 11: Dokumentiere Reproduzierbarkeit**

Bezeichne den Lauf als `frozen historical reference run`, nicht als reproduzierbaren Benchmark. Verweise auf die geplante RunManifest-/Replay-Arbeit und darauf, dass ein späterer Replay-Lauf separat dokumentiert werden soll.

- [ ] **Step 12: Prüfe verbotene Übertreibungen**

```bash
rg -n "predicts people|beweist.*mensch|bewiesen.*Recruit|garantiert|wissenschaftlich validiert|repräsentativ" docs/reference-runs/2026-08-09-domain-migration/README.md
```

Expected: keine unqualifizierte positive Behauptung; Treffer dürfen nur in expliziten Negationen/Limitations stehen.

- [ ] **Step 13: Commit**

```bash
git add docs/reference-runs/2026-08-09-domain-migration/README.md
git commit -m "docs: document domain migration reference run"
```

---

### Task 3: README- und Dokumentations-Einstieg

**Files:**
- Modify: `README.md` direkt nach dem bestehenden Demo-Abschnitt.
- Modify: `docs/README.md` nach den bestehenden Einstiegspunkten bzw. vor den technischen Referenzblöcken.

**Interfaces:**
- Consumes: `docs/reference-runs/2026-08-09-domain-migration/README.md`.
- Produces: sichtbare Navigation zum Referenzlauf ohne README-Überladung.

- [ ] **Step 1: Ergänze die Haupt-README**

Füge einen kurzen Abschnitt `## Referenzlauf` ein. Er muss Szenario, Pipeline, die belegten Werte `267 Interaktionen`, `3 Cluster`, `0.4794` Echo-Chamber-Index und die Einschränkung der fehlenden prädiktiven Validität nennen. Die `24` wird als `aktive Agenten im exportierten Metrics-Snapshot` bezeichnet, nicht als Gesamtpopulation des Laufs. Verlinke die vollständige Case Study relativ.

- [ ] **Step 2: Ergänze `docs/README.md`**

Füge ein:

```markdown
## Referenzläufe und Evaluationen

- [Domainmigration alexle135.de → alex-schneider.dev](./reference-runs/2026-08-09-domain-migration/README.md) — realer End-to-End-Lauf mit Social Simulation, Evidence Gating, bekannten Grenzen und Remediation-Folgen.
```

- [ ] **Step 3: Prüfe die Navigationstexte**

```bash
rg -n "Referenzlauf|reference-runs/2026-08-09-domain-migration" README.md docs/README.md
```

Expected: je mindestens ein funktionaler Einstieg auf die Case Study.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/README.md
git commit -m "docs: surface real Agora reference run"
```

---

### Task 4: Endprüfung des Dokumentations-Slices

**Files:**
- Verify: `README.md`
- Verify: `docs/README.md`
- Verify: `docs/reference-runs/README.md`
- Verify: `docs/reference-runs/2026-08-09-domain-migration/README.md`
- Verify: `docs/reference-runs/2026-08-09-domain-migration/artifacts/report.md`
- Verify: `docs/reference-runs/2026-08-09-domain-migration/artifacts/evidence.json`

**Interfaces:**
- Consumes: alle vorherigen Tasks.
- Produces: reviewfähigen Dokumentations-Branch.

- [ ] **Step 1: Prüfe JSON und zentrale Metriken erneut**

```bash
python -m json.tool docs/reference-runs/2026-08-09-domain-migration/artifacts/evidence.json >/dev/null
rg -n 'total_agents|total_interactions|cluster_count|echo_chamber_index' docs/reference-runs/2026-08-09-domain-migration/artifacts/evidence.json | head -20
```

- [ ] **Step 2: Prüfe alle relativen Links der neuen Dokumente**

Manuell bzw. mit vorhandenem Repo-Linkchecker, falls vorhanden. Mindestens müssen diese Ziele existieren:

```text
docs/reference-runs/2026-08-09-domain-migration/README.md
docs/reference-runs/2026-08-09-domain-migration/artifacts/report.md
docs/reference-runs/2026-08-09-domain-migration/artifacts/evidence.json
```

- [ ] **Step 3: Vergleiche Branch gegen main**

```bash
git diff --check main...HEAD
git diff --stat main...HEAD
```

Expected: keine Whitespace-Fehler; nur Dokumentation, Spec, Plan und Referenzartefakte geändert.

- [ ] **Step 4: Inhaltsreview gegen die Design-Spec**

Prüfe explizit:

```text
[ ] keine empirische Vorhersagebehauptung
[ ] 33-vs-24 offen dokumentiert
[ ] 267 Interaktionen / 3 Cluster / 0.4794 korrekt
[ ] Social Simulation als Reddit/Twitter-artig beschrieben
[ ] Report-Ergebnis als Simulationsergebnis gekennzeichnet
[ ] Evidence-Gating sichtbar erklärt
[ ] Kritikpunkte prominent
[ ] PR #1147 korrekt als gemergte Teil-Remediation dargestellt
[ ] Reproduzierbarkeit nicht übertrieben
[ ] Rohartefakte unverändert
```

- [ ] **Step 5: Finalen Dokumentationsstand committen, nur falls Review-Korrekturen nötig waren**

```bash
git add README.md docs/README.md docs/reference-runs
git commit -m "docs: polish domain migration reference run"
```
