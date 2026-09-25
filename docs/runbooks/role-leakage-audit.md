# Runbook: Role-Leakage-Audit

**Zweck:** Erkennt Stellen, an denen eine Persona in Simulationsaktionen aus einer
fremden Rolle schreibt (z. B. Agent „Kaufmännischer Geschäftsführer" schreibt
„Aus Sicht des Technischen Dienstes …").

Umgesetzt in Issue #1323, Slice 5.1 — Simulationstreue.

---

## Aufruf

```bash
# Einfache Ausgabe als Tabelle
cd backend
uv run python scripts/role_leakage_audit.py <sim_dir>

# Mit JSON-Export und mehr Beispielen
uv run python scripts/role_leakage_audit.py <sim_dir> --json out.json --max-examples 10
```

`<sim_dir>` ist das Verzeichnis einer abgeschlossenen Simulation, das
`twitter/actions.jsonl`, `reddit/actions.jsonl`, `twitter_profiles.csv`
und/oder `reddit_profiles.json` enthält.

---

## Ausgabe

```
Role-Leakage-Audit: /pfad/zur/sim
============================================================
Texttragende Aktionen gesamt: 154
Konflikte gesamt:             6 (3.9%)
Nach Kategorie:
  foreign_role                        3
  unmatched_self_reference            3

Pro Plattform:
  Plattform      Aktionen  Konflikte     Rate
  ------------------------------------------
  twitter              75          1     1.3%
  reddit               79          5     6.3%

Beispiele (max. 5):
  [1] 'Dozenten' (reddit, Runde 3, CREATE_COMMENT)
      Phrase: 'Betriebsratsmitglied war es mir wichtig'
      Grund:  foreign_role
      Treffer:'Stellvertretende Betriebsratsvorsitzende …'
```

### Konflikt-Kategorien

| Kategorie | Bedeutung |
|---|---|
| `foreign_role` | Selbstreferenz trifft die Rolle/den Namen einer anderen Persona im Lauf |
| `foreign_name_signature` | Namens-Signatur am Ende des Texts (z. B. `— Dr. Lisa Wagner`) gehört einer anderen Persona |
| `unmatched_self_reference` | Selbstreferenz-Phrase, die weder eigene noch fremde Rolle trifft — schwächere Kategorie |

---

## Grenzen (wichtig)

1. **Regelbasiert = Untergrenze.** Das Skript erkennt bekannte Muster
   (`Aus Sicht des/der …`, `Als <Nomen> …`, `Wir als/vom …`,
   Namens-Signaturen). Subtile Rollenvertauschungen ohne diese Marker
   werden nicht gefunden.

2. **Keine Schwelle, kein automatisches Gate.** Der Audit liefert
   Messzahlen. Eine akzeptable Konflikt-Rate muss vom Lead-Review definiert
   werden (Slice 5.2). Bis dahin ist der Audit ein Diagnosewerkzeug.

3. **Persona-Auflösung ist Index-first.** Fehlt ein Profil für eine
   `agent_id`, wird die Aktion trotzdem analysiert, aber nur `agent_name`
   als Identitätsmerkmal genutzt.

4. **Generische Phrasen sind ausgenommen.** „Als Unternehmen", „Als
   Beispiel", „Als nächstes", „Als jemand" u. a. lösen keinen Konflikt
   aus.

5. **Kein LLM, kein Netzwerk.** Der Audit ist vollständig offline.

---

## Baseline (Stand 2026-09-25)

### Lauf: `sim_54c1c2a6a875` (KI-Lernassistent, 2026-08-11)

Artefaktpfad (relativ zum Repo-Root): `agora-lauf-20260811-sim_54c1c2a6a875/sim_54c1c2a6a875/`

| Plattform | Texttragende Aktionen | Konflikte | Rate | foreign_role | unmatched_self_ref |
|---|---|---|---|---|---|
| twitter | 75 | 1 | 1,3 % | 0 | 1 |
| reddit | 79 | 5 | 6,3 % | 3 | 2 |
| **gesamt** | **154** | **6** | **3,9 %** | **3** | **3** |

#### Beispiele

**[1] foreign_role — Dozentin schreibt als Betriebsratsmitglied** (reddit, Runde 3 und 6)

> „Als Betriebsratsmitglied war es mir wichtig, …"

Agent 5 `Dozenten` (Profil: Dozentin für kaufmännische Umschulung). Die Rolle
gehört im Lauf der stellvertretenden Betriebsratsvorsitzenden.

**[2] unmatched_self_reference — IHK schreibt als Honorarkraft** (twitter
Runde 0, reddit Runde 0 und 1)

> „Als Honorarkraft werde ich nur für Unterrichtsstunden bezahlt."

Agent 1 `IHK` (Profil: Prüfungsreferentin bei der IHK). Keine Persona des
Laufs führt die Rolle „Honorarkraft" wörtlich; die Honorardozentin ist über
den Stamm nicht erreichbar. Inhaltlich ein klarer Rollenwechsel.

**[3] foreign_role — IHK als „Koordinatorin der Abschlussprüfungen"** (reddit,
Runde 5)

Grenzfall: trifft über „Koordinator" den Bildungscoach/Projektkoordinator.
Fachlich kann eine IHK-Prüfungsreferentin Prüfungen koordinieren — hier
zeigt sich die Grenze des Stammabgleichs.

#### Korrektur gegenüber dem ersten Stand (11 Konflikte, 7,1 %)

Der erste Stand zählte fünf eigene Rollen als Konflikt: Twitter-Profile
tragen keinen Beruf (`twitter_profiles.csv`), und der Abgleich verfehlte
Komposita („Fachdozent" ↔ „Dozent in der Umschulung", „Honorardozentin") und
Synonyme („Umschüler" ↔ „Teilnehmer"). Behoben durch Beruf-Ergänzung aus
`reddit_profiles.json` (nur bei gleichem Namen am gleichen Index),
Kopf-Nomen-Abgleich per Teilstring, kleine Synonymgruppen und gemeinsame
Bestimmungswörter („Betriebsrats-"). Alle fünf Fälle sind als Gegenprobe
getestet.

#### Einschränkungen dieser Baseline

- Nur ein Lauf mit Aktionslog und Profilen im Repo.
- Der Befund aus #1323 (≥ 23 von 234 Aktionen, AURORA-Lauf
  `sim_4245ff3d7b23`) ist hier nicht reproduzierbar, weil dessen
  `actions.jsonl` nicht im Repo liegt. Er ist mit
  `scripts/role_leakage_audit.py <sim_dir>` gegen das Datenverzeichnis des
  Laufs nachzumessen.
- Folge-Gate (Slice 5.2): Review der Baseline → Festlegung einer
  akzeptablen Schwelle → Markierung im `action_log_reader`-Pfad.

---

## Weitere Artefakte im Repo

Referenzläufe unter `docs/reference-runs/` enthalten keine
`actions.jsonl`-Dateien (nur Report-Artefakte). Eine Baseline über alle
Referenzläufe ist daher mit dem aktuellen Stand nicht möglich.
