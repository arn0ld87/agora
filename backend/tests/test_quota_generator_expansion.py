"""Sub-Slice 20b — Generator-Erzwingung für PersonaQuotaPlan.

20a hat die API-Boundary geöffnet, 22 die Persistenz gefixt — aber der
Generator macht weiterhin „1 Persona pro Entity". Bei Quota=50 + nur 16
Entities im Pool failt der Run im post-generation _validate_persona_quota
(Sub-Slice 06) als Drift-Marker. 20b füllt aktiv auf bis zur Quote: pro
Segment werden so viele Personas erzeugt wie ``plan.targets[segment]``
vorgibt, indem der Entity-Pool des Segments per Round-Robin repliziert
wird.

Tests pinnen den Helper ``_expand_entities_for_quota``:
- Segment voll im Pool → unverändert auf Quote gekürzt
- Segment unterbesetzt → Round-Robin-Auffüllen
- Segment fehlt → ValueError (klare Diagnose, kein Synth-Entity)
- Plan kennt Segment, das User später entfernt hat → Pool wird gekürzt
- Pool-Reihenfolge wird stabil reproduzierbar (deterministischer Round-Robin)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.contracts import PersonaQuotaPlan


def _make_entity(uuid: str, entity_type: str, name: str = "Anon"):
    """Mock einer ``EntityNode`` mit minimaler API für den Expander."""
    e = MagicMock(name=f"Entity[{name}]")
    e.uuid = uuid
    e.name = name
    e.get_entity_type = MagicMock(return_value=entity_type)
    return e


def test_expand_entities_pool_groesser_als_quota_kuerzt(monkeypatch):
    """4 KMU-Entities, Quota verlangt 2 → nimmt erste 2."""
    from app.services.prepare_service import _expand_entities_for_quota

    pool = [_make_entity(f"u{i}", "kmu", f"KMU{i}") for i in range(4)]
    plan = PersonaQuotaPlan(targets={"kmu": 2}, total=2)

    expanded = _expand_entities_for_quota(pool, plan)
    assert len(expanded) == 2
    assert [e.uuid for e in expanded] == ["u0", "u1"]


def test_expand_entities_pool_kleiner_als_quota_round_robin():
    """2 KMU-Entities, Quota verlangt 5 → Round-Robin: e0, e1, e0, e1, e0."""
    from app.services.prepare_service import _expand_entities_for_quota

    pool = [
        _make_entity("u0", "kmu", "KMU0"),
        _make_entity("u1", "kmu", "KMU1"),
    ]
    plan = PersonaQuotaPlan(targets={"kmu": 5}, total=5)

    expanded = _expand_entities_for_quota(pool, plan)
    assert len(expanded) == 5
    assert [e.uuid for e in expanded] == ["u0", "u1", "u0", "u1", "u0"]


def test_expand_entities_fehlendes_segment_wirft_value_error():
    """Plan kennt Segment 'msp', Pool hat es nicht → klare Diagnose."""
    from app.services.prepare_service import _expand_entities_for_quota

    pool = [_make_entity("u0", "kmu", "KMU0")]
    plan = PersonaQuotaPlan(targets={"kmu": 1, "msp": 3}, total=4)

    with pytest.raises(ValueError) as excinfo:
        _expand_entities_for_quota(pool, plan)
    assert "msp" in str(excinfo.value)
    assert "entity_type" in str(excinfo.value).lower() or "segment" in str(excinfo.value).lower()


def test_expand_entities_mehrere_segmente_unabhaengig():
    """Plan: kmu=3, admin=2; Pool: 1 kmu, 4 admin → kmu round-robin auf 3,
    admin abgeschnitten auf 2."""
    from app.services.prepare_service import _expand_entities_for_quota

    pool = [
        _make_entity("k0", "kmu", "K0"),
        _make_entity("a0", "admin", "A0"),
        _make_entity("a1", "admin", "A1"),
        _make_entity("a2", "admin", "A2"),
        _make_entity("a3", "admin", "A3"),
    ]
    plan = PersonaQuotaPlan(targets={"kmu": 3, "admin": 2}, total=5)

    expanded = _expand_entities_for_quota(pool, plan)
    assert len(expanded) == 5

    by_seg = {}
    for e in expanded:
        by_seg.setdefault(e.get_entity_type(), []).append(e.uuid)

    assert by_seg["kmu"] == ["k0", "k0", "k0"]  # Round-robin auf 1-Pool
    assert by_seg["admin"] == ["a0", "a1"]


def test_expand_entities_dropt_pool_segmente_die_nicht_im_plan_sind():
    """Pool hat 'extra'-Segment, Plan nicht → diese Entities sind raus."""
    from app.services.prepare_service import _expand_entities_for_quota

    pool = [
        _make_entity("k0", "kmu", "K0"),
        _make_entity("x0", "extra", "X0"),
    ]
    plan = PersonaQuotaPlan(targets={"kmu": 1}, total=1)

    expanded = _expand_entities_for_quota(pool, plan)
    assert len(expanded) == 1
    assert expanded[0].uuid == "k0"


def test_expand_entities_no_plan_returns_pool_unveraendert():
    """Backwards-Compat: ``quota_plan=None`` → Pool unverändert (gleiche
    Liste, nicht zwingend Identität)."""
    from app.services.prepare_service import _expand_entities_for_quota

    pool = [_make_entity("u0", "kmu", "KMU0")]
    expanded = _expand_entities_for_quota(pool, None)
    assert expanded == pool


def test_expand_entities_empty_targets_returns_empty_list():
    """Sicherheits-Branch: ``targets`` mit nur unbesetzten Segmenten →
    PersonaQuotaPlan validiert das ohnehin nicht zu, aber falls je doch
    rausrutscht, soll der Helper deterministisch bleiben."""
    # PersonaQuotaPlan erzwingt min targets[v] >= 1, also kein realistischer
    # Pfad — wir testen aber trotzdem, dass Pool ohne Segment-Match nicht
    # crashed.
    from app.services.prepare_service import _expand_entities_for_quota

    pool = [_make_entity("k0", "kmu", "K0")]
    # Plan ohne den Pool-Segment, aber mit gültigem Target:
    plan = PersonaQuotaPlan(targets={"other": 1}, total=1)
    with pytest.raises(ValueError):
        _expand_entities_for_quota(pool, plan)


def test_apply_persona_floor_to_entities_round_robin_to_contract_minimum():
    """P1.2: Default-Pfad erzeugt mindestens 50 Profile aus kleinem Entity-Pool."""
    from app.services.prepare_service import _apply_persona_floor_to_entities
    from app.services.report_agent import MIN_PERSONA_TABLE_ROWS

    pool = [
        _make_entity("u0", "kmu", "KMU0"),
        _make_entity("u1", "kmu", "KMU1"),
    ]

    expanded = _apply_persona_floor_to_entities(pool)

    assert len(expanded) == MIN_PERSONA_TABLE_ROWS
    assert [entity.uuid for entity in expanded[:5]] == ["u0", "u1", "u0", "u1", "u0"]


def test_apply_persona_floor_to_quota_plan_preserves_total_and_segments():
    """P1.2: Kleine Quota-Pläne werden proportional auf 50 angehoben."""
    from app.services.prepare_service import _apply_persona_floor_to_quota_plan
    from app.services.report_agent import MIN_PERSONA_TABLE_ROWS

    plan = PersonaQuotaPlan(targets={"kmu": 2, "admin": 1}, total=3)

    adjusted = _apply_persona_floor_to_quota_plan(plan)

    assert adjusted is not None
    assert adjusted.total == MIN_PERSONA_TABLE_ROWS
    assert sum(adjusted.targets.values()) == MIN_PERSONA_TABLE_ROWS
    assert adjusted.targets == {"kmu": 33, "admin": 17}
