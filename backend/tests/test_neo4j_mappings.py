"""Unit-Tests für storage/neo4j_mappings.py (Issue #50, EPIC-08-ST-01, Sub-Slice 1).

Sichern, dass die zentralisierten Storage-Helfer ``node_to_dict``,
``edge_to_dict`` und ``sanitize_label`` Wire-identisch zur vorherigen
Inline-Variante in ``Neo4jStorage`` liefern.
"""

from app.storage.neo4j_mappings import edge_to_dict, node_to_dict, sanitize_label


# ── node_to_dict ────────────────────────────────────────────────────


class TestNodeToDict:
    def test_minimal_node(self):
        node = {
            "uuid": "u1",
            "name": "Alice",
            "summary": "an entity",
            "attributes_json": "{}",
            "created_at": "2026-05-01T12:00:00Z",
        }
        result = node_to_dict(node, ["Entity", "Person"])
        assert result == {
            "uuid": "u1",
            "name": "Alice",
            "labels": ["Person"],  # Entity-Label wird gefiltert
            "summary": "an entity",
            "attributes": {},
            "created_at": "2026-05-01T12:00:00Z",
        }

    def test_attributes_json_is_parsed(self):
        node = {
            "uuid": "u1",
            "name": "Alice",
            "attributes_json": '{"role": "developer", "active": true}',
        }
        result = node_to_dict(node, [])
        assert result["attributes"] == {"role": "developer", "active": True}

    def test_invalid_attributes_json_falls_back_to_empty(self):
        """Defekter JSON darf den Mapper nicht crashen lassen."""
        node = {"uuid": "u1", "name": "X", "attributes_json": "{not json"}
        result = node_to_dict(node, [])
        assert result["attributes"] == {}

    def test_internal_fields_are_stripped(self):
        """``embedding`` und ``name_lower`` dürfen nicht im Wire-Output landen."""
        node = {
            "uuid": "u1",
            "name": "X",
            "embedding": [0.1, 0.2],
            "name_lower": "x",
        }
        result = node_to_dict(node, [])
        assert "embedding" not in result
        assert "name_lower" not in result
        assert "embedding" not in result.get("attributes", {})

    def test_empty_labels_list_yields_empty_label_array(self):
        result = node_to_dict({"uuid": "u1", "name": "X"}, [])
        assert result["labels"] == []

    def test_only_entity_label_drops_to_empty(self):
        result = node_to_dict({"uuid": "u1", "name": "X"}, ["Entity"])
        assert result["labels"] == []

    def test_missing_optional_props_default_correctly(self):
        result = node_to_dict({"uuid": "u1"}, ["Entity"])
        assert result["name"] == ""
        assert result["summary"] == ""
        assert result["attributes"] == {}
        assert result["created_at"] is None


# ── edge_to_dict ────────────────────────────────────────────────────


class TestEdgeToDict:
    def test_minimal_edge(self):
        rel = {
            "uuid": "r1",
            "name": "KNOWS",
            "fact": "Alice knows Bob.",
            "attributes_json": "{}",
            "created_at": "2026-05-01T12:00:00Z",
            "valid_from_round": 0,
            "valid_to_round": None,
            "reinforced_count": 1,
            "episode_ids": ["ep1"],
        }
        result = edge_to_dict(rel, source_uuid="ua", target_uuid="ub")
        assert result["uuid"] == "r1"
        assert result["name"] == "KNOWS"
        assert result["fact"] == "Alice knows Bob."
        assert result["source_node_uuid"] == "ua"
        assert result["target_node_uuid"] == "ub"
        assert result["valid_from_round"] == 0
        assert result["valid_to_round"] is None
        assert result["reinforced_count"] == 1
        assert result["episode_ids"] == ["ep1"]

    def test_fact_embedding_is_stripped(self):
        rel = {"uuid": "r1", "fact_embedding": [0.1] * 384}
        result = edge_to_dict(rel, "ua", "ub")
        assert "fact_embedding" not in result

    def test_episode_ids_scalar_is_wrapped_in_list(self):
        """Driver-Edge-Case: ``episode_ids`` als String statt Liste."""
        rel = {"uuid": "r1", "episode_ids": "ep_single"}
        result = edge_to_dict(rel, "ua", "ub")
        assert result["episode_ids"] == ["ep_single"]

    def test_missing_episode_ids_defaults_to_empty_list(self):
        rel = {"uuid": "r1"}
        result = edge_to_dict(rel, "ua", "ub")
        assert result["episode_ids"] == []

    def test_default_reinforced_count_is_1(self):
        rel = {"uuid": "r1"}
        result = edge_to_dict(rel, "ua", "ub")
        assert result["reinforced_count"] == 1

    def test_invalid_attributes_json_falls_back_to_empty(self):
        rel = {"uuid": "r1", "attributes_json": "{!"}
        result = edge_to_dict(rel, "ua", "ub")
        assert result["attributes"] == {}


# ── sanitize_label ──────────────────────────────────────────────────


class TestSanitizeLabel:
    def test_simple_ascii_label_passes(self):
        assert sanitize_label("Person") == "Person"

    def test_underscore_label_passes(self):
        assert sanitize_label("Internal_Group") == "Internal_Group"

    def test_whitespace_normalized_to_underscore(self):
        assert sanitize_label("Public Figure") == "Public_Figure"

    def test_umlauts_stripped(self):
        # Häufige LLM-Output-Verwüstung: Bürger → Brger (lesbar genug)
        assert sanitize_label("Bürger") == "Brger"

    def test_default_entity_label_rejected(self):
        assert sanitize_label("Entity") is None

    def test_empty_string_rejected(self):
        assert sanitize_label("") is None
        assert sanitize_label("   ") is None

    def test_non_string_rejected(self):
        assert sanitize_label(None) is None
        assert sanitize_label(42) is None
        assert sanitize_label(["Person"]) is None

    def test_starting_digit_rejected(self):
        assert sanitize_label("1stClass") is None

    def test_backtick_injection_attempt_stripped(self):
        """Cypher-Injection-Versuch wird durch Whitelist-Stripping
        in einen harmlosen Label umgewandelt — alle ``[^A-Za-z0-9_]``
        verschwinden, der Backtick kann das Quoting nicht mehr brechen."""
        cleaned = sanitize_label("Person`}; DROP DATABASE neo4j; //")
        # Backtick und Semikolons sind weg → kein Quoting-Escape mehr möglich
        assert cleaned is not None
        assert "`" not in cleaned
        assert ";" not in cleaned
        assert "/" not in cleaned

    def test_long_label_truncated_by_regex(self):
        """Whitelist erlaubt max 50 Zeichen — länger → reject."""
        assert sanitize_label("A" * 51) is None
        assert sanitize_label("A" * 50) == "A" * 50
