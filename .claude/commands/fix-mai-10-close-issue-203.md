---
description: MAI-10 — Issue #203 (Step2/Step4 Hotspots) faktisch unter Schwelle, explizit schließen mit Befund-Kommentar.
allowed-tools: Read, Bash, Grep, Glob, Edit, Write
---

# /fix-mai-10-close-issue-203 — Issue #203 schließen

## Ziel

Issue #203 ist seit dem Phase-5-Refactor faktisch erledigt (Step2 -63 %, Step4 -38 % LOC, beide unter Schwelle). Explizit schließen mit Befund-Kommentar als Audit-Trail.

## Voraussetzungen

- Worktree: `/Volumes/T7/Projekte/agora-worktrees/mai-10/`.
- Branch: `chore/mai-10-close-203`.
- `gh` ist eingeloggt mit Schreibrechten.

## Schritt-für-Schritt

### Schritt 1: LOC-Check

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-10
echo "=== Aktuelle LOC ==="
wc -l frontend/src/components/Step2EnvSetup.vue \
       frontend/src/components/Step4Report.vue \
       frontend/src/components/Step3Simulation.vue
```

Erwartet (laut CLAUDE.md Stand 2026-05-11):

| File | LOC | Schwelle |
|---|---|---|
| Step2EnvSetup.vue | 667 | < 800 |
| Step4Report.vue | 797 | < 800 |

### Schritt 2: Issue-Status holen

```bash
gh issue view 203 --json state,title,body,labels,createdAt
```

### Schritt 3: Befund-Kommentar

```bash
gh issue comment 203 --body "$(cat <<'EOT'
## MAI-10 — Hotspot-Status 2026-05-14

Issue ist faktisch erledigt durch M11 Phase 5 + 5b und nachfolgende Schnitte:

| File | LOC vorher | LOC heute | Reduktion |
|---|---:|---:|---:|
| `Step2EnvSetup.vue` | 1804 | 667 | -63 % |
| `Step4Report.vue` | 1287 | 797 | -38 % |

Beide Files liegen unter der definierten 800-LOC-Schwelle. Weitere Schnitte
würden Composables erzeugen, die nur einmal verwendet werden — Kosten/Nutzen
negativ.

Schließe das Issue mit Verweis auf:

- `docu/2026-05-08-m11-phase5-arbeitsprotokoll.md` (simulation_runner.py)
- `docu/2026-05-08-m11-phase5b-arbeitsprotokoll.md` (graph_tools.py)
- analoge Frontend-Schnitte unter `frontend/src/composables/`

Falls die LOC durch zukünftige Features wieder über 800 wandert, wird ein
**neues** Issue mit klarem Wartungs-Treiber angelegt — nicht dieses
reaktiviert.
EOT
)"
```

### Schritt 4: Issue schließen

```bash
gh issue close 203
gh issue view 203 --json state --jq '.state'
# Erwartet: "CLOSED"
```

### Schritt 5: Worklog (rein dokumentarisch)

`docu/2026-05-14-mai-10-arbeitsprotokoll.md`:

```markdown
# MAI-10 · Issue #203 schließen — Arbeitsprotokoll

**Datum:** 2026-05-14
**Subagent:** agora-doc-worker (Haiku)
**Branch:** chore/mai-10-close-203

## Befund

Issue #203 (Step2/Step4 Hotspots) ist nach M11 Phase 5/5b faktisch erledigt.
Beide Komponenten liegen unter der 800-LOC-Schwelle.

## Aktion

Issue mit Audit-Kommentar geschlossen. Keine Code-Änderung.

## Akzeptanz erfüllt?

- [x] LOC < 800 in beiden Files (Schritt 1)
- [x] gh issue view 203 → state=CLOSED (Schritt 4)
- [x] Kommentar enthält Verweis auf Phase-5/5b-Worklogs

## Folge-Slices

- Keine. Falls LOC wieder steigt → neues Issue mit Wartungs-Treiber.
```

## Verifikation

```bash
# Issue ist geschlossen
gh issue view 203 --json state --jq '.state'
# Erwartet: CLOSED

# Audit-Kommentar ist sichtbar
gh issue view 203 --json comments --jq '.comments[-1].body' | head -5
```

## Warum?

Offene Issues, die in Wahrheit erledigt sind, verzerren das Backlog. Issue #203 war ein berechtigter LOC-Wartungs-Treiber, ist aber faktisch durch andere Slices gelöst worden — das gehört dokumentiert und geschlossen, sonst sucht beim nächsten Audit jemand vergeblich nach Resten.

## Nächste Schritte

1. CHANGELOG: `MAI-10 · Issue #203 (Step2/Step4 Hotspots) geschlossen — durch Phase-5/5b faktisch erledigt.`
2. Kein Push nötig (rein GitHub-API).
3. `/fix-mai-11-pr-smoke-rc-only` (Block D Start) ODER `/fix-mai-06-retire-v2-md` zuerst (Reihenfolge).
