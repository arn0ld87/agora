"""Issue #1759 (A5) — fragebezogene Hybrid-Auswahl beim ``max_agents``-Cap.

``_cap_entities_across_types`` verteilte die Plaetze reihum ueber die Typen,
ohne Bezug zur Simulationsfrage (Referenzlauf ``sim_3d3d8b2d8342``: fast exakt
zwei Sitze je Typ, genau eine Schwangere unter 30 Agenten). Die Hybrid-Auswahl
vergibt harte Mindestsitze fuer in der Frage genannte Gruppen, garantierte
Entscheider-Sitze und laesst ein Auswahl-LLM die Restplaetze ranken. Was ohne
Platz bleibt, ist eine sichtbare Degradation.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.contracts.entity_selection_contract import (
    EntityRelevanceItem,
    EntityRelevanceResponse,
)
from app.contracts.pipeline_degradation_contract import DegradationKind
from app.services import prepare_checkpoint, prepare_entities
from app.services.degradation_collector import DegradationCollector
from app.services.entity_reader import EntityNode, FilteredEntities
from app.services.prepare_checkpoint import checkpoint_is_resumable, new_checkpoint
from app.services.prepare_entities import (
    _apply_entity_cap,
    _cap_entities_across_types,
    _select_entities_for_requirement,
)
from app.services.prepare_requirement_selection import (
    plan_hard_seats,
    requirement_hash,
)
from app.services.prepare_service import compute_persona_target
from app.services.run_budget import BudgetExceededError

_QUESTION = (
    "Wie reagieren Beschäftigte und Schwangere auf die geplante Schließung der "
    "Geburtsstation?"
)


def _entity(name: str, entity_type: str = "Stakeholder", summary: str = "") -> EntityNode:
    return EntityNode(
        uuid=f"uuid-{name}-{entity_type}",
        name=name,
        labels=["Entity", entity_type],
        summary=summary,
        attributes={},
    )


def _pool() -> list[EntityNode]:
    """Zwei in der Frage genannte Gruppen, ein Entscheider, Randakteure."""
    pool = [
        _entity("Beschäftigte der Klinik", "EmployeeGroup"),
        _entity("Schwangere", "ExpectantMother"),
        _entity("Landrat Hollerau", "Official"),
    ]
    for i in range(6):
        pool.append(_entity(f"Lieferant {i}", "Supplier"))
    for i in range(6):
        pool.append(_entity(f"Verein {i}", "Association"))
    return pool


class _FakeClient:
    """Auswahl-LLM-Stub: bewertet nach Namensliste, protokolliert den Aufruf."""

    def __init__(self, relevant: dict[str, int] | None = None, error: Exception | None = None):
        self.relevant = relevant or {}
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def chat_json(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        user = kwargs["messages"][-1]["content"]
        items = []
        for line in user.splitlines():
            head, _, rest = line.partition(". ")
            if not head.isdigit():
                continue
            name = rest.split(" [Typ:")[0]
            items.append(
                {
                    "candidate_index": int(head),
                    "relevance": self.relevant.get(name, 1),
                    "reason": f"Bewertung fuer {name}",
                }
            )
        return {"items": items}


@pytest.fixture()
def fake_client(monkeypatch: pytest.MonkeyPatch) -> _FakeClient:
    client = _FakeClient({"Verein 3": 9, "Lieferant 2": 8})
    monkeypatch.setattr(prepare_entities, "_build_selection_client", lambda *a, **k: client)
    return client


def _select(
    pool: list[EntityNode],
    *,
    max_agents: int = 8,
    collector: DegradationCollector | None = None,
    requirement: str | None = _QUESTION,
    llm_runtime: Any = object(),
    use_llm_for_profiles: bool = True,
    has_quota_plan: bool = False,
):
    return _select_entities_for_requirement(
        pool,
        max_agents,
        simulation_requirement=requirement,
        llm_runtime=llm_runtime,
        llm_model="m",
        run_id="run-1",
        use_llm_for_profiles=use_llm_for_profiles,
        has_quota_plan=has_quota_plan,
        degradations=collector,
    )


def _names(selected: list[EntityNode]) -> list[str]:
    return [entity.name for entity in selected]


class TestMindestsitze:
    def test_in_der_frage_genannte_gruppen_sind_vertreten(self, fake_client: _FakeClient) -> None:
        selected, _, _ = _select(_pool())
        names = _names(selected)
        assert "Schwangere" in names
        assert "Beschäftigte der Klinik" in names

    def test_gruppen_entitaet_bekommt_mehrere_einzelplaetze(self, fake_client: _FakeClient) -> None:
        selected, _, decisions = _select(_pool())
        assert _names(selected).count("Beschäftigte der Klinik") == 2
        group = next(d for d in decisions if d.entity_name == "Beschäftigte der Klinik")
        assert group.basis == "named_group"
        assert group.seats == 2

    def test_zweiter_gruppensitz_ist_markierte_synthetische_ergaenzung(
        self, fake_client: _FakeClient
    ) -> None:
        """#1833: Der zweite Sitz traegt den Ergaenzungsmarker, sonst bekaemen zwei
        Profile denselben gesperrten Quellnamen. Der erste bleibt die Quellentitaet."""
        pool = _pool()
        pool[1] = _entity("Dr. Svenja Meyer", "Schwangere")
        selected, _, _ = _select(pool)
        seats = [e for e in selected if e.name == "Dr. Svenja Meyer"]
        assert len(seats) == 2
        assert seats[0] is pool[1]
        assert "identity_origin" not in pool[1].attributes
        assert seats[1] is not pool[1]
        assert seats[1].uuid == pool[1].uuid
        assert seats[1].attributes["identity_origin"] == "synthetic_supplement"

    def test_genau_max_agents_plaetze(self, fake_client: _FakeClient) -> None:
        selected, reserve, _ = _select(_pool(), max_agents=8)
        assert len(selected) == 8
        assert {e.uuid for e in reserve}.isdisjoint({e.uuid for e in selected})

    def test_hartes_budget_laesst_dem_llm_platz(self) -> None:
        pool = [_entity(f"Beratungsstelle{i}", "Office") for i in range(10)]
        question = "Beratungsstelle0 Beratungsstelle1 Beratungsstelle2 Beratungsstelle3"
        plans = plan_hard_seats(pool, question, 4)
        assert sum(plan.seats for plan in plans) <= 3

    def test_staerkster_treffer_gewinnt_bei_knappem_budget(self) -> None:
        pool = [
            _entity("Hebammenverband", "Association"),
            _entity("Hebammenverband Kreis Hollerau", "Association"),
        ]
        plans = plan_hard_seats(pool, "Hebammenverband Kreis Hollerau", 2)
        assert [plan.entity.name for plan in plans] == ["Hebammenverband Kreis Hollerau"]


class TestEntscheider:
    def test_entscheider_bekommt_sitz_trotz_null_relevanz(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _FakeClient({"Landrat Hollerau": 0})
        monkeypatch.setattr(prepare_entities, "_build_selection_client", lambda *a, **k: client)
        selected, _, decisions = _select(_pool())
        assert "Landrat Hollerau" in _names(selected)
        landrat = next(d for d in decisions if d.entity_name == "Landrat Hollerau")
        assert landrat.basis == "decision_maker"


class TestLlmAuswahl:
    def test_restplaetze_folgen_der_relevanz_mit_begruendung(self, fake_client: _FakeClient) -> None:
        selected, _, decisions = _select(_pool(), max_agents=8)
        names = _names(selected)
        assert "Verein 3" in names
        assert "Lieferant 2" in names
        llm = {d.entity_name: d for d in decisions if d.basis == "llm_relevance"}
        assert llm["Verein 3"].reason.startswith("Relevanz 9/10")
        assert all(d.reason for d in decisions)

    def test_prompt_enthaelt_frage_und_nutzt_chat_json_mit_schema(
        self, fake_client: _FakeClient
    ) -> None:
        _select(_pool())
        call = fake_client.calls[0]
        assert _QUESTION in call["messages"][-1]["content"]
        assert call["schema"] is EntityRelevanceResponse
        assert call["context"] == "persona"

    def test_unbewertete_kandidaten_zaehlen_als_null(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Partial(_FakeClient):
            def chat_json(self, **kwargs: Any) -> dict[str, Any]:
                result = super().chat_json(**kwargs)
                result["items"] = result["items"][:1]
                return result

        client = _Partial({"Verein 3": 9})
        monkeypatch.setattr(prepare_entities, "_build_selection_client", lambda *a, **k: client)
        selected, _, _ = _select(_pool())
        assert len(selected) == 8


class TestDegradation:
    def test_unvertretener_akteur_ist_sichtbar(self, fake_client: _FakeClient) -> None:
        collector = DegradationCollector()
        _, reserve, _ = _select(_pool(), collector=collector)
        events = [
            e
            for e in collector.report().events
            if e.kind is DegradationKind.ENTITY_SELECTION_ACTORS_OMITTED
        ]
        assert len(events) == 1
        event = events[0]
        assert event.context["omitted_count"] == len(reserve)
        assert event.context["selection_mode"] == "requirement_hybrid"
        assert reserve[0].name in event.detail

    def test_llm_ausfall_behaelt_harte_sitze_und_meldet_sichtbar(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _FakeClient(error=RuntimeError("provider down"))
        monkeypatch.setattr(prepare_entities, "_build_selection_client", lambda *a, **k: client)
        collector = DegradationCollector()
        selected, _, decisions = _select(_pool(), collector=collector)
        assert "Schwangere" in _names(selected)
        assert len(selected) == 8
        assert any(d.basis == "fallback_round_robin" for d in decisions)
        detail = collector.report().events[0].detail
        assert "Relevanz-Ranking ausgefallen" in detail
        assert "provider down" in detail

    def test_budgetfehler_wird_durchgereicht(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = _FakeClient(error=BudgetExceededError("llm_calls", 10, 10))
        monkeypatch.setattr(prepare_entities, "_build_selection_client", lambda *a, **k: client)
        with pytest.raises(BudgetExceededError):
            _select(_pool(), collector=DegradationCollector())


class TestFallbackPfade:
    @pytest.fixture(autouse=True)
    def _no_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(*_a: Any, **_k: Any) -> Any:
            raise AssertionError("Auswahl-LLM darf hier nicht gebaut werden")

        monkeypatch.setattr(prepare_entities, "_build_selection_client", _boom)

    @pytest.mark.parametrize(
        ("kwargs", "grund"),
        [
            ({"has_quota_plan": True}, "quota_plan"),
            ({"use_llm_for_profiles": False}, "use_llm_for_profiles=False"),
            ({"llm_runtime": None}, "keine LLM-Route"),
        ],
    )
    def test_bisheriger_cap_mit_sichtbarer_degradation(
        self, kwargs: dict[str, Any], grund: str
    ) -> None:
        collector = DegradationCollector()
        pool = _pool()
        selected, reserve, decisions = _select(pool, collector=collector, **kwargs)
        assert selected == _cap_entities_across_types(pool, 8)
        assert len(selected) + len(reserve) == len(pool)
        assert decisions == []
        event = collector.report().events[0]
        assert event.kind is DegradationKind.ENTITY_SELECTION_ACTORS_OMITTED
        assert event.context["selection_mode"] == "round_robin_fallback"
        assert grund in event.detail

    def test_ohne_frage_keine_degradation(self) -> None:
        collector = DegradationCollector()
        pool = _pool()
        selected, _, _ = _select(pool, collector=collector, requirement="  ")
        assert selected == _cap_entities_across_types(pool, 8)
        assert collector.report().events == []

    def test_ohne_sammler_kein_fehler(self) -> None:
        selected, _, _ = _select(_pool(), collector=None, use_llm_for_profiles=False)
        assert len(selected) == 8


class TestApplyEntityCap:
    def test_filtered_traegt_plaetze_reserve_und_begruendungen(
        self, fake_client: _FakeClient
    ) -> None:
        pool = _pool()
        filtered = FilteredEntities(
            entities=list(pool),
            entity_types={e.get_entity_type() or "Entity" for e in pool},
            total_count=len(pool),
            filtered_count=len(pool),
        )
        _apply_entity_cap(
            filtered,
            8,
            simulation_requirement=_QUESTION,
            llm_runtime=object(),
            llm_model="m",
            run_id="run-1",
            use_llm_for_profiles=True,
            has_quota_plan=False,
            degradations=None,
        )
        assert filtered.filtered_count == len(filtered.entities) == 8
        assert filtered.selection_decisions
        assert {e.uuid for e in filtered.reserve_entities}.isdisjoint(
            {e.uuid for e in filtered.entities}
        )

    def test_fortschritts_nenner_rechnet_wiederholungen_mit(
        self, fake_client: _FakeClient
    ) -> None:
        """Wiederholte Gruppen-Entitaeten sind Plaetze: der Nenner bleibt ``max_agents``."""
        pool = _pool()
        filtered = FilteredEntities(
            entities=list(pool),
            entity_types=set(),
            total_count=len(pool),
            filtered_count=len(pool),
        )
        _apply_entity_cap(
            filtered,
            8,
            simulation_requirement=_QUESTION,
            llm_runtime=object(),
            llm_model=None,
            run_id=None,
            use_llm_for_profiles=True,
            has_quota_plan=False,
            degradations=None,
        )
        assert len({e.uuid for e in filtered.entities}) < len(filtered.entities)
        target = compute_persona_target(len(filtered.entities), max_agents=8, floor=8)
        assert target.persona_target_count == 8
        # Vorschau (ohne LLM): min(Entitaeten, max_agents) == Plaetze nach dem Cap.
        assert min(len(pool), 8) == len(filtered.entities)


class TestResume:
    def _checkpoint(self, *, hash_: str | None) -> Any:
        checkpoint = new_checkpoint(
            simulation_id="sim-1",
            graph_id="graph-1",
            defined_entity_types=None,
            max_agents=4,
            persona_floor=4,
            use_llm_for_profiles=True,
            effective_quota_plan=None,
            primary_entity_uuids=["a"],
            reserve_entity_uuids=[],
            expanded_entity_uuids=["a"],
            entities_count=1,
            entity_types=["Stakeholder"],
            demographic_slots=[{}],
            requirement_hash=hash_,
        )
        return checkpoint.with_completed_profile(0, {"name": "x"})

    def _resumable(self, checkpoint: Any, hash_: str | None) -> bool:
        return checkpoint_is_resumable(
            checkpoint,
            simulation_id="sim-1",
            graph_id="graph-1",
            defined_entity_types=None,
            max_agents=4,
            persona_floor=4,
            use_llm_for_profiles=True,
            effective_quota_plan=None,
            requirement_hash=hash_,
        )

    def test_gleiche_frage_ist_resumable(self) -> None:
        h = requirement_hash(_QUESTION)
        assert self._resumable(self._checkpoint(hash_=h), h) is True

    def test_geaenderte_frage_ist_nicht_resumable(self) -> None:
        old = requirement_hash(_QUESTION)
        new = requirement_hash(_QUESTION + " Und die Hebammen?")
        assert old != new
        assert self._resumable(self._checkpoint(hash_=old), new) is False

    def test_altbestand_ohne_hash_bleibt_resumable(self) -> None:
        assert self._resumable(self._checkpoint(hash_=None), requirement_hash(_QUESTION)) is True

    def test_altes_checkpoint_json_ohne_neue_felder_ist_lesbar(self) -> None:
        raw = self._checkpoint(hash_="abc").model_dump(mode="json")
        raw.pop("requirement_hash")
        raw.pop("selection_reasons")
        loaded = prepare_checkpoint.PreparePersonaCheckpoint.model_validate(raw)
        assert loaded.requirement_hash is None
        assert loaded.selection_reasons == []

    def test_auswahlbegruendungen_ueberleben_den_roundtrip(self, fake_client: _FakeClient) -> None:
        _, _, decisions = _select(_pool())
        checkpoint = new_checkpoint(
            simulation_id="sim-1",
            graph_id="graph-1",
            defined_entity_types=None,
            max_agents=8,
            persona_floor=8,
            use_llm_for_profiles=True,
            effective_quota_plan=None,
            primary_entity_uuids=["a"],
            reserve_entity_uuids=[],
            expanded_entity_uuids=["a"],
            entities_count=1,
            entity_types=[],
            selection_reasons=decisions,
        )
        loaded = prepare_checkpoint.PreparePersonaCheckpoint.model_validate(
            checkpoint.model_dump(mode="json")
        )
        assert [d.entity_name for d in loaded.selection_reasons] == [
            d.entity_name for d in decisions
        ]

    def test_hash_normalisiert_whitespace_und_ignoriert_leere_frage(self) -> None:
        assert requirement_hash("Frage  eins\n") == requirement_hash("Frage eins")
        assert requirement_hash("   ") is None
        assert requirement_hash(None) is None


class TestRelevanceContract:
    def test_leere_begruendung_wird_abgelehnt(self) -> None:
        with pytest.raises(ValidationError):
            EntityRelevanceItem(candidate_index=1, relevance=5, reason="   ")

    def test_unbekannte_felder_werden_abgelehnt(self) -> None:
        with pytest.raises(ValidationError):
            EntityRelevanceItem(candidate_index=1, relevance=5, reason="ok", extra="x")  # type: ignore[call-arg]

    def test_relevanz_ist_auf_null_bis_zehn_begrenzt(self) -> None:
        with pytest.raises(ValidationError):
            EntityRelevanceItem(candidate_index=1, relevance=11, reason="ok")
