"""Sprungkennungen an Belegen (Issue #1804, Etappe 5).

Abgeleitet wird nur, was der Beleg-Inhalt eindeutig hergibt: ``agent_action``
mit eigenem Beitrag und ``entity_summary`` mit Knoten-UUID. Alles andere bleibt
``None`` — keine Näherung über Zeitfenster, Autor oder Text.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.contracts.report_contract import EvidenceMapModel, EvidenceRecordModel
from app.services.evidence_identity import build_evidence_id, build_producer_key
from app.services.evidence_origin import derive_evidence_origin, with_evidence_origins

NODE_UUID = "3f2b9c1e-8a4d-4f6b-9c7e-1a2b3c4d5e6f"
TIMESTAMP = "2026-08-02T15:02:16.055352"


def _action_raw(
    action_type: str,
    args: dict[str, Any],
    *,
    platform: str = "twitter",
) -> dict[str, Any]:
    return {
        "round_num": 3,
        "timestamp": TIMESTAMP,
        "platform": platform,
        "agent_id": 7,
        "agent_name": "Anna",
        "action_type": action_type,
        "action_args": args,
        "result": None,
        "success": True,
    }


def _action_record(
    action_type: str,
    args: dict[str, Any],
    *,
    platform: str = "twitter",
    producer_key: str | None = None,
) -> EvidenceRecordModel:
    key = producer_key or f"simulation-action:{platform}:3:7:{action_type}:{TIMESTAMP}"
    return EvidenceRecordModel(
        evidence_id=build_evidence_id("report_x", "agent_action", key),
        producer_key=key,
        type="agent_action",
        source="simulation_actions",
        snippet="Anna: Beitrag",
        source_kind="agent_action",
        voice_key="agent:7",
        raw=_action_raw(action_type, args, platform=platform),
    )


def _entity_record(raw: Any, producer_key: str | None = None) -> EvidenceRecordModel:
    key = producer_key or f"graph-node:{NODE_UUID}"
    return EvidenceRecordModel(
        evidence_id=build_evidence_id("report_x", "graph_relation", key),
        producer_key=key,
        type="entity_summary",
        source="report_tool",
        snippet="Knoten",
        source_kind="graph_relation",
        raw=raw,
    )


class TestAgentActionOrigin:
    @pytest.mark.parametrize(
        ("action_type", "args", "expected"),
        [
            ("CREATE_POST", {"content": "x", "post_id": 12}, "twitter:12"),
            ("QUOTE_POST", {"quoted_id": 9, "new_post_id": 10, "quote_content": "x"}, "twitter:10"),
            ("REPOST", {"new_post_id": 46}, "twitter:46"),
            ("CREATE_COMMENT", {"content": "x", "comment_id": 5}, "twitter:comment:5"),
            ("CREATE_COMMENT", {"content": "x", "comment_id": "5"}, "twitter:comment:5"),
        ],
    )
    def test_own_contribution_gets_the_feed_format_id(self, action_type, args, expected) -> None:
        record = _action_record(action_type, args)
        assert derive_evidence_origin(record) == {"origin_post_id": expected}

    def test_reddit_prefix_follows_the_platform_of_the_action(self) -> None:
        record = _action_record("CREATE_COMMENT", {"comment_id": 4}, platform="reddit")
        assert derive_evidence_origin(record) == {"origin_post_id": "reddit:comment:4"}

    @pytest.mark.parametrize(
        ("action_type", "args"),
        [
            # Kennung des Ziels, kein eigener Beitrag.
            ("LIKE_POST", {"post_id": 8, "like_id": 1}),
            ("DISLIKE_POST", {"post_id": 8, "dislike_id": 1}),
            ("LIKE_COMMENT", {"comment_id": 3}),
            ("FOLLOW", {"follow_id": 1, "target_user_name": "x"}),
            ("SEARCH_POSTS", {"query": "x"}),
            ("DO_NOTHING", {}),
            # Beitrag ohne protokollierte Kennung (374 von 1391 CREATE_POST im Bestand).
            ("CREATE_POST", {"content": "x"}),
            # Unbrauchbare Kennungen.
            ("CREATE_POST", {"post_id": None}),
            ("CREATE_POST", {"post_id": True}),
            ("CREATE_POST", {"post_id": -3}),
            ("CREATE_POST", {"post_id": "abc"}),
            ("CREATE_POST", {"post_id": 1.5}),
        ],
    )
    def test_without_a_unique_own_id_the_field_stays_empty(self, action_type, args) -> None:
        assert derive_evidence_origin(_action_record(action_type, args)) == {}

    def test_unknown_platform_stays_empty(self) -> None:
        record = _action_record("CREATE_POST", {"post_id": 1}, platform="mastodon")
        assert derive_evidence_origin(record) == {}

    def test_producer_key_contradicting_the_raw_action_stays_empty(self) -> None:
        # producer_key sagt reddit, raw sagt twitter: nicht eindeutig zuzuordnen.
        record = _action_record(
            "CREATE_POST",
            {"post_id": 1},
            producer_key=f"simulation-action:reddit:3:7:CREATE_POST:{TIMESTAMP}",
        )
        assert derive_evidence_origin(record) == {}

    def test_hashed_legacy_producer_key_is_not_a_reason_to_refuse(self) -> None:
        record = _action_record(
            "CREATE_POST",
            {"post_id": 2},
            producer_key=build_producer_key("action", "twitter", "3", "7"),
        )
        assert derive_evidence_origin(record) == {"origin_post_id": "twitter:2"}

    @pytest.mark.parametrize("raw", [None, "Beitrag als Text", ["x"], {"action_type": "CREATE_POST"}])
    def test_raw_without_action_structure_stays_empty(self, raw) -> None:
        record = _action_record("CREATE_POST", {"post_id": 1})
        record = record.model_copy(update={"raw": raw})
        assert derive_evidence_origin(record) == {}

    def test_unhashable_platform_does_not_raise(self) -> None:
        record = _action_record("CREATE_POST", {"post_id": 1})
        raw = dict(record.raw)
        raw["platform"] = ["twitter"]
        assert derive_evidence_origin(record.model_copy(update={"raw": raw})) == {}


class TestEntitySummaryOrigin:
    def test_node_uuid_from_raw(self) -> None:
        record = _entity_record({"uuid": NODE_UUID, "name": "Stadt", "summary": "x"})
        assert derive_evidence_origin(record) == {"origin_node_uuids": [NODE_UUID]}

    def test_record_without_graph_node_key_still_uses_the_raw_uuid(self) -> None:
        record = _entity_record(
            {"uuid": NODE_UUID}, producer_key=build_producer_key("entity", "Stadt")
        )
        assert derive_evidence_origin(record) == {"origin_node_uuids": [NODE_UUID]}

    @pytest.mark.parametrize(
        "raw",
        [
            {"name": "ohne uuid"},
            {"uuid": "kein-uuid"},
            {"uuid": 123},
            "Text statt Entität",
            None,
        ],
    )
    def test_without_a_valid_uuid_the_field_stays_empty(self, raw) -> None:
        assert derive_evidence_origin(_entity_record(raw)) == {}

    def test_producer_key_contradicting_the_raw_uuid_stays_empty(self) -> None:
        other = "11111111-2222-4333-8444-555555555555"
        record = _entity_record({"uuid": NODE_UUID}, producer_key=f"graph-node:{other}")
        assert derive_evidence_origin(record) == {}


class TestOtherEvidenceTypes:
    @pytest.mark.parametrize("kind", ["graph_fact", "relationship_chain"])
    def test_graph_facts_carry_no_edge_or_node_id_in_raw(self, kind) -> None:
        # ``raw`` ist hier nur der Faktentext; selbst ein UUID-förmiger Text im
        # Fakt ist keine Kennung und wird nicht geraten.
        record = EvidenceRecordModel(
            evidence_id=build_evidence_id("report_x", "graph_relation", f"{kind}-1"),
            producer_key=f"{kind}-1",
            type=kind,
            source="report_tool",
            snippet=f"Fakt {NODE_UUID}",
            source_kind="graph_relation",
            raw=f"Fakt {NODE_UUID}",
        )
        assert derive_evidence_origin(record) == {}

    def test_interview_is_untouched_voice_key_already_identifies_the_persona(self) -> None:
        record = EvidenceRecordModel(
            evidence_id=build_evidence_id("report_x", "agent_quote", "interview-1"),
            producer_key="interview-1",
            type="agent_interview",
            source="report_tool",
            snippet="Antwort",
            quote="Antwort",
            persona_stakeholder_group="kunden",
            source_kind="agent_quote",
            voice_key="agent:7",
            raw={"agent_id": 7, "post_id": 3},
        )
        assert derive_evidence_origin(record) == {}


class TestWithEvidenceOrigins:
    def _map(self) -> EvidenceMapModel:
        post = _action_record("CREATE_POST", {"post_id": 12})
        like = _action_record("LIKE_POST", {"post_id": 8})
        node = _entity_record({"uuid": NODE_UUID})
        return EvidenceMapModel(
            report_id="report_x",
            simulation_id="sim_x",
            evidence_index={r.evidence_id: r for r in (post, like, node)},
        )

    def test_fills_only_derivable_records_and_leaves_the_input_untouched(self) -> None:
        source = self._map()
        before = source.model_dump(mode="json")

        result = with_evidence_origins(source)

        by_key = {r.producer_key: r for r in result.evidence_index.values()}
        post = by_key[f"simulation-action:twitter:3:7:CREATE_POST:{TIMESTAMP}"]
        like = by_key[f"simulation-action:twitter:3:7:LIKE_POST:{TIMESTAMP}"]
        node = by_key[f"graph-node:{NODE_UUID}"]
        assert post.origin_post_id == "twitter:12"
        assert like.origin_post_id is None
        assert node.origin_node_uuids == [NODE_UUID]
        assert source.model_dump(mode="json") == before

    def test_map_without_derivable_records_is_returned_as_is(self) -> None:
        source = EvidenceMapModel(
            report_id="report_x",
            simulation_id="sim_x",
            evidence_index={
                r.evidence_id: r for r in (_action_record("LIKE_POST", {"post_id": 8}),)
            },
        )
        assert with_evidence_origins(source) is source

    def test_derivation_is_idempotent(self) -> None:
        once = with_evidence_origins(self._map())
        twice = with_evidence_origins(once)
        assert once.model_dump(mode="json") == twice.model_dump(mode="json")


class TestOriginFieldsAreNeverPersisted:
    def test_unset_fields_are_absent_from_every_dump(self) -> None:
        # Der Schreibpfad dumpt EvidenceRecordModel ohne ``exclude_none``
        # (``register_evidence_record``). Ohne ``exclude_if`` stünden die neuen
        # Schlüssel als ``null`` in jeder persistierten Map und ein Rollback auf
        # eine ältere Fassung scheiterte an ``extra=forbid``.
        dumped = _action_record("CREATE_POST", {"post_id": 1}).model_dump(mode="json")
        assert "origin_post_id" not in dumped
        assert "origin_node_uuids" not in dumped

    def test_write_path_persists_a_record_without_origin_keys(self) -> None:
        from app.services.report_agent.action_search import build_action_evidence_item
        from app.services.report_agent.evidence import register_evidence_record

        item = build_action_evidence_item(
            {
                "round_num": 3,
                "timestamp": TIMESTAMP,
                "platform": "twitter",
                "agent_id": 7,
                "agent_name": "Anna",
                "action_type": "CREATE_POST",
                "action_args": {"content": "Hallo", "post_id": 12},
            }
        )
        evidence_map: dict[str, Any] = {}

        record = register_evidence_record(evidence_map, item, scope_id="report_x")

        assert record is not None
        stored = evidence_map["evidence_index"][record["evidence_id"]]
        assert "origin_post_id" not in stored
        assert "origin_node_uuids" not in stored

    def test_set_fields_appear_in_the_dump(self) -> None:
        record = _action_record("CREATE_POST", {"post_id": 1}).model_copy(
            update={"origin_post_id": "twitter:1"}
        )
        assert record.model_dump(mode="json")["origin_post_id"] == "twitter:1"

    @pytest.mark.parametrize("bad", ["twitter:", "mastodon:1", "twitter:comment:x", "1", "twitter:1 "])
    def test_origin_post_id_rejects_a_foreign_format(self, bad) -> None:
        data = _action_record("CREATE_POST", {"post_id": 1}).model_dump(mode="json")
        with pytest.raises(ValueError):
            EvidenceRecordModel.model_validate({**data, "origin_post_id": bad})

    @pytest.mark.parametrize("bad", [[], ["nope"], [NODE_UUID, "nope"]])
    def test_origin_node_uuids_reject_non_uuids_and_empty_lists(self, bad) -> None:
        data = _entity_record({"uuid": NODE_UUID}).model_dump(mode="json")
        with pytest.raises(ValueError):
            EvidenceRecordModel.model_validate({**data, "origin_node_uuids": bad})
