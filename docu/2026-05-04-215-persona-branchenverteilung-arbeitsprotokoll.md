# Arbeitsprotokoll: Sub-Slice B — Issue #215 Persona-IT-Bias / Branchenverteilung

**Datum:** 2026-05-04  
**Issue:** #215 (P2, Backend Bug)  
**Branch:** `feat/task-215-persona-branchenverteilung`  
**Worker:** Agora-Backend-Refactor-Worker (Sonnet)

## Problem

**User-Befund 2026-05-03:** „Es werden auch fast nur Personas erzeugt mit starkem IT-Bezug, aber Agora soll nicht nur für die IT sein."

Ursache: Der `OasisProfileGenerator` erzeugte LLM-Prompts ohne Branchensteuerung. Das LLM defaultete systematisch auf IT-Personas (Softwareentwickler, DevOps-Ingenieure, IT-Admins), weil:

1. Kein Branchen-Soll-Block in den Prompts existierte.
2. Der `PersonaQuotaPlan`-Default (`None` in `prepare_service.py`) erzeugte keinen Branchen-Hinweis für den Generator.

## Lösung

### Neues Modul: `backend/app/services/persona_quota_defaults.py`

Enthält:
- `default_dach_industry_quota(total_personas: int) -> PersonaQuotaPlan` — erzeugt einen `PersonaQuotaPlan` mit Destatis-WZ-2008-Branchenverteilung.
- `build_industry_quota_prompt_block(quota_plan)` — deutschen Prompt-Block für LLM-Prompts.
- `build_industry_quota_prompt_block_en(quota_plan)` — englischer Prompt-Block.

### Default-Branchenverteilung (Destatis WZ 2008)

| Branche (WZ-Buchstabe) | Anteil | Personas (bei 100) |
|---|---|---|
| Verarbeitendes Gewerbe (C) | 17 % | 17 |
| Handel (G) | 14 % | 14 |
| Gesundheit und Sozialwesen (Q) | 13 % | 13 |
| Sonstige Dienstleistungen (M, N, R, S) | 12 % | 12 |
| **Information und Kommunikation (J)** | **12 %** (hard cap) | **12** |
| Öffentliche Verwaltung (O) | 7 % | 7 |
| Bildung (P) | 7 % | 7 |
| Bau (F) | 6 % | 6 |
| Verkehr und Lagerei (H) | 5 % | 5 |
| Gastgewerbe (I) | 4 % | 4 |
| Finanz- und Versicherungswesen (K) | 3 % | 3 |
| **Gesamt** | **100 %** | **100** |

### Quellen

- **Destatis WZ 2008:** Wirtschaftszweigklassifikation 2008, Statistisches Bundesamt. [https://www.destatis.de/DE/Methoden/Klassifikationen/Gueter-Wirtschaftsklassifikationen/klassifikation-wz-2008.html](https://www.destatis.de/DE/Methoden/Klassifikationen/Gueter-Wirtschaftsklassifikationen/klassifikation-wz-2008.html)
- **Bundesagentur für Arbeit:** Beschäftigtenstatistik nach Wirtschaftszweigen, Stand 2023. [https://statistik.arbeitsagentur.de](https://statistik.arbeitsagentur.de)
- **Statista:** Anteil der Erwerbstätigen nach Wirtschaftsbereichen in Deutschland 2022, veröffentlicht 2023.

Die Anteile sind explizite Konstanten (keine Laufzeit-Abfragen), damit Tests deterministisch bleiben.

### Algorithmus: Largest-Remainder-Methode + Clamp

1. Rohe Float-Werte: `share * total_personas`
2. Alle auf `int` flooren (math.floor).
3. Restpersonen mit Largest-Remainder auf die Branchen mit größten Dezimalresten verteilen → Summe == total garantiert.
4. Clamp: die 4 Hauptbranchen erhalten bei sehr kleinen Pools (total < 5) je mindestens 1 Persona (aus der Branche mit dem größten Pool abgezogen).
5. Branchen mit 0 Personas werden aus dem Plan-Dict entfernt.

**Hinweis zu kleinen Pools (total < 10):** Bei sehr kleinen Gesamt-Pools ist der IT-Cap von ≤ 12 % mathematisch nicht erzwingbar, da bereits 1 von 4 Personas = 25 % IT ergeben würde. Der Hard-Cap gilt für realistische Simulations-Pools (>= 10 Personas).

### Prompt-Einbindung (`oasis_profile_generator.py`)

- Import der neuen Hilfsfunktionen.
- `__init__` bekommt neuen optionalen Parameter `industry_quota_plan: Optional[PersonaQuotaPlan]`.
- Wenn kein Plan übergeben: `default_dach_industry_quota(100)` als Default.
- `_build_individual_persona_prompt` und `_build_group_persona_prompt` fügen je einen `{_industry_block_de/en}`-Block nach dem Namens-Quota-Block ein.

### Wiring in `prepare_service.py`

- Import von `default_dach_industry_quota`.
- In `_phase_generate_profiles`: `industry_plan = default_dach_industry_quota(max(total_entities, 1))` vor dem `OasisProfileGenerator`-Konstruktor.
- `industry_quota_plan=industry_plan` wird an den Konstruktor übergeben.

## Geänderte Dateien

| Datei | Art |
|---|---|
| `backend/app/services/persona_quota_defaults.py` | Neu |
| `backend/app/services/oasis_profile_generator.py` | Erweitert (Import, `__init__`, 4 Prompt-Blöcke) |
| `backend/app/services/prepare_service.py` | Erweitert (Import, industry_plan Wiring) |
| `backend/tests/services/test_persona_industry_distribution.py` | Neu |
| `docu/2026-05-04-215-persona-branchenverteilung-arbeitsprotokoll.md` | Neu |
| `CHANGELOG.md` | Erweitert (Fixed-Eintrag) |

## Test-Verifikation

Datei: `backend/tests/services/test_persona_industry_distribution.py`

```
31 passed in 2.08s
```

Assertions:
- `TestDefaultDachIndustryQuota100::test_it_share_at_most_12_percent` — IT-Anteil ≤ 12 % bei total=100
- `TestDefaultDachIndustryQuota100::test_at_least_7_branches` — mindestens 7 Branchen
- `TestDefaultDachIndustryQuota100::test_sum_equals_total` — Summe == total
- `TestDefaultDachIndustryQuota100::test_no_single_branch_above_25_percent` — keine Branche > 25 %
- `test_it_cap_never_exceeded[10..500]` — Cap für realistische Pools
- `test_sum_always_equals_total[1..500]` — Summen-Invariante
- `test_pydantic_plan_validates_correctly` — Pydantic-Validator grün

## IT-Quote im Default

Bei `total=100`:
- IT-Anteil: **12 %** (12 von 100 Personas)
- Branchen-Count: **11**
