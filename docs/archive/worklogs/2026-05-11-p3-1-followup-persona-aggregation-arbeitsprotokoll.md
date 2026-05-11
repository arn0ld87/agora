# Arbeitsprotokoll: P3.1-Followup — Echte Persona/Segment/FrictionPoint/TrustSignal-Aggregation

**Datum:** 2026-05-11
**Slice:** P3.1-Followup (Refs PLAN.md §4.1)
**Branch:** `claude/trusting-hopper-1bdec3`

## Was

`migrate_v2_to_v3` in `evidence_migrations.py` gab `personas`, `segments`, `friction_points`, `trust_signals` bisher als leere Listen zurück (mit DataGap-Marker für Personas). Dieser Followup-Slice implementiert echte Aggregation.

## Warum

PLAN.md §4.1 Zeile 34: P3.1-Followup-Notiz — "migrate_v2_to_v3 aggregiert Personas/Segmente/FrictionPoints/TrustSignals derzeit als leere Listen. Folge-Slice zieht echte Daten aus Persona-Storage + Segment-Aggregation."

## Implementierung

### Signatur-Änderung

Alt:
```python
def migrate_v2_to_v3(raw: dict, *, simulation_id: Optional[str] = None) -> dict
```

Neu:
```python
def migrate_v2_to_v3(
    raw: dict,
    *,
    simulation_id: Optional[str] = None,
    artifact_store: Optional[SimulationArtifactStore] = None,
) -> dict
```

Der neue `artifact_store`-Parameter ist optional (Default=None). Bestehende Aufrufer in `manager.py` (die keinen Store übergeben) bleiben vollständig kompatibel.

### Aggregations-Strategie

**Personas:**
- Quelle: `artifact_store.read_json(simulation_id, "reddit_profiles")`.
- Mapping: `age` → `alter_range` (String), `profession` → `beruf`, `country` → `region`, `voice_register` (Fallback auf `neutral-de` wenn ungültig), `interested_topics` → `needs`.
- Fallback: Wenn kein Store, kein simulation_id oder leere Profiles → DataGap-Marker `dg-migration-personas` wie bisher.

**Segments:**
- Aggregation per `segment`-Tag (aus `reddit_profiles`) oder `source_entity_type` als Fallback.
- Alle Persona-IDs mit gleichem Tag werden in ein Segment gruppiert.
- Nur wenn Personas vorhanden (kein Store → keine Segments).

**FrictionPoints:**
- Keyword-Matching auf `section_title` (case-insensitive): "reibungspunkt", "reibungs", "friction", "hindernis", "barriere".
- Claims aus Matching-Sections → `FrictionPoint` mit `severity` aus `confidence_label`.
- Nur Claims mit mind. 1 Evidence-Ref (analog zu Claims-Aggregation).

**TrustSignals:**
- Keyword-Matching auf `section_title`: "vertrauenssignal", "vertrauens", "trust", "cialdini".
- Claims aus Matching-Sections → `TrustSignal` mit `signal_type="authority"` (Default).
- Nur Claims mit mind. 1 Evidence-Ref.

### Hilfsfunktionen (neu in `evidence_migrations.py`)

- `_resolve_evidence_refs(claim, section_index, claim_id)` — dedupliziert aus claim-dict extrahierten Code.
- `_label_to_confidence(label)` — Normalisierung.
- `_section_title_matches(section_title, keywords)` — Keyword-Matching.
- `_load_personas_from_store(simulation_id, artifact_store)` — Lese-Adapter.
- `_map_profile_to_persona(profile, index)` — Mapping reddit_profiles → Persona-dict.
- `_aggregate_segments(personas, profiles)` — Gruppen-Aggregation.

## Tests

Neue Test-Datei: `backend/tests/services/test_evidence_migrations_aggregation.py`

**15 neue Tests in 3 Klassen:**

| Klasse | Anzahl | Was |
|--------|--------|-----|
| `TestVollAggregation` | 4 | Volle Aggregation mit InMemoryArtifactStore |
| `TestLeereAggregation` | 4 | Fallback ohne Store / leere Profiles → DataGap |
| `TestSectionBasierteExtraktion` | 7 | FP/TS aus Sections, Severity, Type, Nicht-FP-Sections |

Gesamtsuite: 1829 passed (war 1814 vor diesem Slice) — keine Regression.

## Risiken / Grenzen

- `build_report_v3` in `manager.py` übergibt keinen `artifact_store` an `migrate_v2_to_v3` (wird nicht verwendet). Der direkte Code-Pfad `save_report → build_report_v3` erzeugt weiterhin leere Personas — dies ist bewusst, da `build_report_v3` ein separates Pydantic-Objekt aufbaut. `migrate_v2_to_v3` ist der Migration-Pfad für Bestands-Reports.
- `signal_type` für TrustSignals ist immer `"authority"` — echtes Cialdini-Mapping erfordert LLM-Klassifikation (separater Slice).
- Persona ohne `voice_register`-Feld in Profiles bekommt `"neutral-de"` als Default.

## Migrationspfad für Bestehende Reports

Aufrufer, die `migrate_v2_to_v3` verwenden und Persona-Daten wollen, müssen `artifact_store` und `simulation_id` übergeben. Ohne diese Parameter verhält sich die Funktion wie bisher.

## Dateien

- `backend/app/services/evidence_migrations.py` — Implementierung (ca. +120 LOC)
- `backend/tests/services/test_evidence_migrations_aggregation.py` — Tests (neu, 15 Tests)
- `docs/2026-05-11-p3-1-followup-persona-aggregation-arbeitsprotokoll.md` — dieses Dokument
- `CHANGELOG.md` — [Unreleased]-Eintrag
- `PLAN.md` — P3.1-Followup als done markiert
