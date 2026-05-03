"""Tests für DACH-Namens-Demographie-Quoten (Sub-Slice F, Issue #214).

Prüft:
- Summe der Quoten ≈ 1.0
- Grundlegende classify_name_origin-Regeln
- Optional (LLM-Marker): echte Verteilung bei generate_profiles_from_entities

CI: `pytest -m "not llm"` — schließt den @pytest.mark.llm-Test aus.
"""

from __future__ import annotations

import pytest

from app.services.persona_demographics import (
    DACH_NAME_ORIGIN_QUOTAS,
    classify_name_origin,
)


@pytest.mark.eval
def test_demographics_quota_sums_to_one():
    s = sum(q.share for q in DACH_NAME_ORIGIN_QUOTAS)
    assert abs(s - 1.0) < 0.01, f"Quoten-Summe {s:.4f} ≠ 1.0 (±0.01)"


@pytest.mark.eval
def test_all_buckets_have_names():
    for q in DACH_NAME_ORIGIN_QUOTAS:
        assert q.first_names, f"Bucket {q.bucket!r} hat keine first_names"
        assert q.last_names, f"Bucket {q.bucket!r} hat keine last_names"


@pytest.mark.eval
def test_classify_name_origin_basics():
    assert classify_name_origin("Yusuf Yılmaz") == "turkish", "Türkischer Name nicht erkannt"
    assert classify_name_origin("Ahmed Haddad") == "arabic_levant", "Arabischer Name nicht erkannt"
    assert classify_name_origin("Hans Müller") == "german_native", "Deutscher Name nicht erkannt"


@pytest.mark.eval
def test_classify_name_origin_extended():
    # Ex-YU via Zeichen
    assert classify_name_origin("Marko Petrović") == "ex_yu_balkan"
    # Polnisch via Zeichen
    assert classify_name_origin("Piotr Wiśniewski") == "polish_eastern"
    # Asiatisch via Lookup
    assert classify_name_origin("Minh Nguyen") == "asian"
    # Afrikanisch via Lookup
    assert classify_name_origin("Chidi Okafor") == "african_other"
    # Italienisch via Lookup
    assert classify_name_origin("Marco Rossi") == "italian"


@pytest.mark.eval
def test_classify_name_origin_fallback():
    # Unbekannter Name → german_native (konservativ)
    assert classify_name_origin("XyzUnbekannt Qqq") == "german_native"
    assert classify_name_origin("") == "german_native"


@pytest.mark.eval
def test_migration_share_in_quotas():
    """Migrationshintergrund-Anteil laut Destatis ~26 %."""
    migration_share = sum(q.share for q in DACH_NAME_ORIGIN_QUOTAS if q.bucket != "german_native")
    assert 0.24 <= migration_share <= 0.28, (
        f"Migrationsanteil {migration_share:.2%} außerhalb 24-28 % (Destatis-Schätzung)"
    )


# ---------------------------------------------------------------------------
# Optionaler LLM-Test — in CI per `-m "not llm"` ausgeschlossen
# ---------------------------------------------------------------------------

@pytest.mark.llm
def test_persona_name_distribution_matches_dach_demographics():
    """Prüft reale Namens-Verteilung nach LLM-Generierung (braucht laufendes Ollama)."""
    from app.services.oasis_profile_generator import OasisProfileGenerator
    from app.services.entity_reader import EntityNode

    # 50 generische Personen-Entitäten als Smoke-Batch
    entities = [
        EntityNode(
            uuid=f"test-{i}",
            name=f"TestPerson{i}",
            entity_type="individual",
            summary="Testpersona für demographische Verteilungsprüfung",
        )
        for i in range(50)
    ]

    gen = OasisProfileGenerator(language="de")
    profiles = gen.generate_profiles_from_entities(entities, use_llm=True)

    buckets: dict[str, int] = {}
    for p in profiles:
        b = classify_name_origin(p.name or "")
        buckets[b] = buckets.get(b, 0) + 1

    total = len(profiles)
    migration = sum(c for b, c in buckets.items() if b != "german_native")
    ratio = migration / total if total > 0 else 0.0

    assert 0.20 <= ratio <= 0.32, (
        f"Migrationsanteil {ratio:.2%} außerhalb 20-32 %. Buckets: {buckets}"
    )
