# Sub-Slice M11.7a — Evidence-Gating Prompt-Block (Layer 2)

**Status:** Implementierung abgeschlossen  
**Branch:** `feat/m11-7a-evidence-prompt-block` (ab `origin/main` HEAD `1b18c64`)  
**Datum:** 2026-05-10

---

## Überblick

Sub-Slice M11.7a führt vier Provenance-Stufen in den Report-Generation-Prompt ein, damit das LLM Claims selbst klassifiziert und Hedges-/Stakeholder-Konsens-Regeln befolgt. Das ist die LLM-Anleitung; der Pydantic-Validator kommt parallel in Slice B (als Auffangnetz).

---

## Modifizierte Datei

| Datei | Zeilen | Änderung |
|---|---|---|
| `backend/app/services/report_prompts.py` | 146–226 | Evidence-Gating-Block eingefügt |

**Einfügepunkt:** Nach Zeile 144 (`[Most Important Rules - Must Follow]`), vor Zeile 228 (`1. [Must Call Tools...]`).  
**Block-Umfang:** 81 Zeilen inkl. öffnendem/schließendem Tag + Selbst-Check + Negative-Examples.

---

## Provenance-Stufen (Zusammenfassung)

| Level | Bedingung | Max-Confidence | source_kind | Hedge-Wort |
|---|---|---|---|---|
| `hypothesis` | Keine Evidence | none | — | — |
| `seed_only` | Nur Seed-Frage/-Text | low | seed_corpus | MUSS enthalten |
| `agent_grounded` | Min. 1 Agent-Quote + Seed | medium | agent_quote + seed_corpus | — |
| `cross_stakeholder` | ≥2 Personas aus ≥2 Gruppen, konsistent | high | agent_quote x2+ | Gruppen im Text nennen |
| `verified` | Wie cross_stakeholder + match_score ≥0.85 | verified | (post-hoc Validator) | — |

### Hedge-Wörter (Snapshot)

```
vermutlich
deutet auf
die Quellenlage spricht für
Indizien legen nahe
```

Diese sind in Zeile 167–168 von `report_prompts.py` dokumentiert.

---

## Wording-Glossar-Verifikation

```bash
rg -ni "prediction|rehearsal|god.s eye view|high-fidelity|public opinion|forecast|revolutionary|seamless" \
  backend/app/services/report_prompts.py
```

**Ergebnis:** ✅ Keine Treffer — Glossar v1 ist sauber.

---

## Test-Dateien

### 1. `backend/tests/test_evidence_gating_prompt.py` (neu)

Snapshot-Test mit 6 Assertions:

```python
def test_evidence_gating_block_present():
    """Evidence-Gating-Block ist im Section-System-Prompt vorhanden."""
    # Prüft: <evidence_gating> und </evidence_gating> Tags

def test_provenance_levels_present():
    """Alle 4 Provenance-Level sind benannt."""
    # Prüft: hypothesis, seed_only, agent_grounded, cross_stakeholder

def test_hedge_words_present():
    """Alle 4 Hedge-Wörter sind im Prompt."""
    # Prüft: vermutlich, deutet auf, die Quellenlage spricht für, Indizien legen nahe

def test_wording_glossar_no_violations():
    """Wording-Glossar v1 ist eingehalten."""
    # Prüft: Keine prediction/rehearsal/god's eye/high-fidelity/forecast/revolutionary/seamless

def test_negative_examples_contain_wrong_label():
    """Negative-Examples haben WRONG:/FIX: Labels."""
    # Qualitätssicherung der Dokumentation

def test_source_kind_field_naming():
    """Source-Kind-Felder sind mit korrekten Enum-Werten benannt."""
    # Forward-Compat: seed_corpus, agent_quote mind. genannt
```

### 2. `backend/tests/eval/snapshots/evidence-gating-hedge-words.txt` (neu)

Snapshot mit den 4 Hedge-Wörtern für Drift-Schutz.

---

## Forward-Kompatibilität (Slice B)

Der Block nennt bereits die neuen Enum-Werte aus `EvidenceSourceKind` (kommt mit Slice B):
- `seed_corpus`
- `agent_quote`
- `graph_relation` (erwähnt im Block, aber noch nicht im Prompt umgesetzt — das macht Slice B)
- `inferred` (dto.)

**Annahme:** Slice B wird `EvidenceItemModel.source_kind: EvidenceSourceKind` hinzufügen und diese Werte setzen. Dieser Slice ist prompt-ready dafür.

---

## Validierung

### Manuell geprüft

```bash
# 1. Block vorhanden
grep -c "evidence_gating\|provenance_levels\|hypothesis\|seed_only\|agent_grounded\|cross_stakeholder" \
  backend/app/services/report_prompts.py
# Erwartet: ≥ 6 (alle Begriffe gefunden)
# Ergebnis: ✅ 6 matches

# 2. Hedge-Wörter vollständig
grep "vermutlich\|deutet auf\|Quellenlage spricht\|Indizien legen" \
  backend/app/services/report_prompts.py | wc -l
# Ergebnis: ✅ 2 matches (Zeile 167–168)

# 3. Wording-Glossar
rg -ni "prediction|rehearsal|god.s eye|high-fidelity|public opinion|forecast|revolutionary|seamless" \
  backend/app/services/report_prompts.py || echo "clean"
# Ergebnis: ✅ clean
```

### Tests

```bash
cd backend && uv run pytest tests/test_evidence_gating_prompt.py -v
# 6/6 Tests erwartet grün
```

---

## Nicht-Änderungen (per Spec)

- ❌ `report_contract.py` nicht angefasst (kommt mit Slice B)
- ❌ `Step4Report.vue` nicht angefasst (Frontend)
- ❌ Andere Prompt-Strings nicht modifiziert (nur Section-Generation betroffen)
- ❌ Schema-Dump nicht geändert (kein neues Feld in Contracts)

---

## Commit-Status

**Commit-bereit:** Ja, wenn Tests grün.

Diff-Summary:
- `backend/app/services/report_prompts.py`: +81 Zeilen (evidence_gating Block)
- `backend/tests/test_evidence_gating_prompt.py`: +70 Zeilen (neu)
- `backend/tests/eval/snapshots/evidence-gating-hedge-words.txt`: +4 Zeilen (neu)

**Gesamt: +155 Zeilen.**

---

## Nachfolgende Slices

- **Slice B (parallel):** `EvidenceSourceKind` Enum hinzufügen, `EvidenceItemModel.source_kind` setzen, Pydantic-Validator für confidence-Gating.
- **Slice C (später):** `ReportSection.hypotheses[]` Feld einführen (hypotheses, die noch keine Evidence haben).

---

## CHANGELOG-Eintrag

```markdown
### Changed

- **Layer 2 / Report Agent:** Evidence-Gating-Prompt-Block in `SECTION_SYSTEM_PROMPT_TEMPLATE` eingeführt (Sub-Slice M11.7a). LLM klassifiziert Claims jetzt nach vier Provenance-Stufen (hypothesis, seed_only, agent_grounded, cross_stakeholder) mit Confidence-Gating und Hedge-Word-Regeln. Forward-kompatibel zu `EvidenceSourceKind` Enum (Slice B).
```

---

## Fragen / Bekannte Limitationen

1. **Slice B wird alle 4 source_kind-Werte implementieren** — dieser Slice nennt sie nur im Prompt, ohne sie im Schema zu definieren. Das ist beabsichtigt.
2. **hypotheses[]-Feld wird mit Slice C kommen** — bis dahin landen Hypothesen entweder in der section_summary oder werden ganz weggelassen (per Anleitung im Block).
3. **LLM wird nicht zwingend den Regeln folgen** — der Validator in Slice B ist das Enforcement-Layer.

---

**Arbeitsprotokoll durch:** Alexander Schneider  
**Worktree:** `/Volumes/T7/Projekte/agora-wt/m11-7a-prompt-block`
