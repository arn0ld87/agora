# ADR-0012: Run-Budgets — Micros-Preise, Termination-Reason und ehrliche Unbekannt-Status

- Status: akzeptiert
- Datum: 2026-07-29
- Bezug: Issue #764 (Kosten-, Token- und Zeitbudgets für Runs)

## Kontext

Runs (Simulation, Report) verursachen Token-, Kosten- und Zeitaufwand, der vor,
während und nach dem Lauf transparent sein soll. Nutzer müssen weiche und harte
Limits setzen können; ein Budgetabbruch muss von technischem Fehler und
Nutzerabbruch unterscheidbar bleiben. Gleichzeitig liefern nicht alle Provider
Usage-Metadaten, und lokale Modelle haben keinen Geldpreis.

## Entscheidungen

### 1. Geldbeträge ausschließlich als Integer-Micros

Alle Kostenfelder heißen `*_cost_micros` (1 Einheit = 10⁻⁶ Währung, USD als
Default, Feld `currency` im Contract). Keine Floats für Geld — Float-Rundung
wäre über tausende LLM-Calls nicht auditierbar. Die Umrechnung in
Anzeigewährung ist reine Darstellung (Frontend `formatCostMicros` via
`Intl.NumberFormat`).

### 2. Unbekannt ist kein Wert, sondern ein Status

Fehlende Providerdaten werden niemals als `0` ausgegeben. Numerische Felder
sind nullable; der Messzustand wird über explizite Literale kommuniziert:

- `cost_status`: `measured | estimated | free | unknown`
- `tokens_status`: `measured | partial | unknown`
- `measurement_status` (RunUsage): `complete | partial | unknown`

Lokale Modelle ohne Geldpreis sind `free` (ehrliche 0), unbekannte Preise sind
`unknown` (null, niemals 0).

### 3. RunStatus bleibt unverändert — Abbruchgrund als eigenes Feld

Das kanonische `RunStatus`-Literal (`pending | processing | paused | completed |
failed | stopped`) wird nicht erweitert; Consumer (Dashboard, Resume, Polling)
hängen daran. Der Abbruchgrund steht in einem neuen optionalen Manifest-Feld
`termination_reason`: `completed | error | user_cancel | user_stop |
budget_tokens | budget_cost | budget_time | budget_calls`. Ein Budgetabbruch
ist `status=stopped` + `termination_reason=budget_*` — additiv, keine
Migration, Legacy-Manifeste bleiben lesbar.

### 4. Ein Enforcement-Level pro Budget

`RunBudgetConfig.enforcement` ist `soft | hard` und gilt für alle gesetzten
Dimensionen (Tokens, Kosten, Zeit, LLM-Aufrufe). Soft: Run läuft weiter,
auditierbare `BudgetWarning` im Run-Status und in der UI. Hard: planbare
Modellaufrufe werden deterministisch verhindert (`BudgetExceededError` vor dem
Call), Teilresultate bleiben erhalten, der Monitor beendet den Run mit
passender `termination_reason`.

### 5. Preise zentral und versioniert, nur für Schätzungen

Preise liegen in `backend/app/data/model_pricing.json` (statische Richtpreise,
Feld `version`, z. B. `2026-07`). Die `PricingRegistry` ist die einzige
Preislogik; das Frontend dupliziert keine Preise. Schätzungen tragen
`pricing_version` und `pricing_source` im Contract, damit spätere
Verbrauchswerte gegen dieselbe Preisbasis lesbar bleiben.

### 6. Harte Limits prüfen am Call, Zeitbudget im Monitor

Der `RunBudgetEnforcer` prüft Token-/Kosten-/Aufruflimits unmittelbar vor jedem
LLM-Call (`LLMClient.chat/chat_json`, Backend-Prozess) bzw. im
OASIS-Subprozess über den `SubprocessBudgetGuard` an Runden-Grenzen
(Datei-basiert: `budget_config.json` / `budget_abort.json` im Simulations-Dir,
first-writer-wins). Das Zeitbudget prüft der Simulations-Monitor
(backendseitig, monotone Zeit), weil es unabhängig von einzelnen Calls greifen
muss.

## Konsequenzen

- Verträge zuerst: `run_budget_contract.py` (Pydantic v2) → Schema-Dump
  (`run-budget-config`, `run-usage`, `run-budget-status`,
  `run-preflight-estimate`) → Zod-Spiegel `runBudgetContract.ts` mit
  Drift-Test. Keine parallelen handgeschriebenen Wahrheiten.
- Preflight-Schätzungen sind ehrlich gekennzeichnet (`is_estimate: true`,
  Bereiche statt Pseudopräzision, `data_quality`, Warnungen).
- Provider ohne Usage-Metadaten funktionieren weiter; ihr Verbrauch erscheint
  als `unknown`/`partial`.
- Export: `usage.json` + `budget.json` im Report-ZIP, secretsfrei
  (`serialize_for_manifest` lehnt Key-Material hart ab).
- Einschränkung: Hard-Limit-Granularität im OASIS-Subprozess ist die
  Runden-Grenze; ein einzelner laufender Call wird nicht abgebrochen.
