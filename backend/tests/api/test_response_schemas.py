"""
Response-Schema-Validierungstests für die Kern-Domänen-Endpoints.

Spirit: Keine Live-Requests – pure Schema-Validation gegen realistische Sample-Payloads.
        Die Schemas pinnen die Pflicht-Felder (required) und lassen additive Felder offen
        (additionalProperties: true), damit Frontend-Mapper nie stillschweigend brechen.

Domänen: Project, Simulation, RunStatus, ReportStatus, GraphData,
          OntologyDefinition, Persona
"""

from __future__ import annotations

import pytest
from jsonschema import validate, ValidationError

# ============================================================
# Schema-Definitionen (JSON Schema Draft 2020-12)
# ============================================================

PROJECT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "project_id",
        "name",
        "status",
        "created_at",
        "updated_at",
        "files",
        "total_text_length",
    ],
    "additionalProperties": True,
    "properties": {
        "project_id": {"type": "string"},
        "name": {"type": "string"},
        "status": {
            "type": "string",
            "enum": [
                "created",
                "ontology_generated",
                "graph_building",
                "graph_completed",
                "failed",
            ],
        },
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["filename"],
                "additionalProperties": True,
                "properties": {
                    "filename": {"type": "string"},
                    "path": {"type": "string"},
                    "size": {"type": ["integer", "string", "null"]},
                },
            },
        },
        "total_text_length": {"type": "integer"},
        "ontology": {"type": ["object", "null"]},
        "analysis_summary": {"type": ["string", "null"]},
        "graph_id": {"type": ["string", "null"]},
        "graph_build_task_id": {"type": ["string", "null"]},
        "simulation_requirement": {"type": ["string", "null"]},
        "chunk_size": {"type": "integer"},
        "chunk_overlap": {"type": "integer"},
        "error": {"type": ["string", "null"]},
    },
}

SIMULATION_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "simulation_id",
        "project_id",
        "graph_id",
        "status",
        "entities_count",
        "profiles_count",
        "entity_types",
        "config_generated",
    ],
    "additionalProperties": True,
    "properties": {
        "simulation_id": {"type": "string"},
        "project_id": {"type": "string"},
        "graph_id": {"type": "string"},
        "enable_twitter": {"type": "boolean"},
        "enable_reddit": {"type": "boolean"},
        "status": {
            "type": "string",
            "enum": [
                "created",
                "preparing",
                "ready",
                "running",
                "paused",
                "stopped",
                "completed",
                "failed",
            ],
        },
        "entities_count": {"type": "integer"},
        "profiles_count": {"type": "integer"},
        "entity_types": {"type": "array", "items": {"type": "string"}},
        "config_generated": {"type": "boolean"},
        "config_reasoning": {"type": "string"},
        "current_round": {"type": "integer"},
        "twitter_status": {"type": "string"},
        "reddit_status": {"type": "string"},
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
        "error": {"type": ["string", "null"]},
        "source_simulation_id": {"type": ["string", "null"]},
        "root_simulation_id": {"type": ["string", "null"]},
        "branch_name": {"type": ["string", "null"]},
        "branch_depth": {"type": "integer"},
    },
}

RUN_STATUS_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "run_id",
        "run_type",
        "entity_id",
        "status",
        "progress",
        "message",
        "started_at",
        "updated_at",
        "artifacts",
        "linked_ids",
    ],
    "additionalProperties": True,
    "properties": {
        "run_id": {"type": "string"},
        "run_type": {"type": "string"},
        "entity_id": {"type": "string"},
        "parent_run_id": {"type": ["string", "null"]},
        "status": {
            "type": "string",
            "enum": ["pending", "processing", "completed", "failed", "paused", "stopped"],
        },
        "progress": {"type": "integer", "minimum": 0, "maximum": 100},
        "message": {"type": "string"},
        "error": {"type": ["string", "null"]},
        "started_at": {"type": "string"},
        "updated_at": {"type": "string"},
        "completed_at": {"type": ["string", "null"]},
        "artifacts": {"type": "object"},
        "resume_capability": {"type": "object"},
        "branch_label": {"type": ["string", "null"]},
        "metadata": {"type": "object"},
        "linked_ids": {"type": "object"},
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["timestamp", "type", "status"],
                "additionalProperties": True,
                "properties": {
                    "timestamp": {"type": "string"},
                    "type": {"type": "string"},
                    "status": {"type": "string"},
                    "progress": {"type": ["integer", "null"]},
                    "message": {"type": "string"},
                    "error": {"type": ["string", "null"]},
                    "details": {"type": "object"},
                },
            },
        },
    },
}

REPORT_STATUS_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "report_id",
        "simulation_id",
        "graph_id",
        "simulation_requirement",
        "status",
    ],
    "additionalProperties": True,
    "properties": {
        "report_id": {"type": "string"},
        "simulation_id": {"type": "string"},
        "graph_id": {"type": "string"},
        "simulation_requirement": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["pending", "planning", "generating", "completed", "failed"],
        },
        "outline": {
            "type": ["object", "null"],
            "properties": {
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["title"],
                        "additionalProperties": True,
                        "properties": {
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                        },
                    },
                },
            },
            "additionalProperties": True,
        },
        "markdown_content": {"type": "string"},
        "created_at": {"type": "string"},
        "completed_at": {"type": "string"},
        "error": {"type": ["string", "null"]},
        "has_evidence": {"type": "boolean"},
        "evidence_sections": {"type": "integer"},
    },
}

GRAPH_DATA_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["graph_id", "nodes", "edges", "node_count", "edge_count"],
    "additionalProperties": True,
    "properties": {
        "graph_id": {"type": "string"},
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["uuid", "name", "type"],
                "additionalProperties": True,
                "properties": {
                    "uuid": {"type": "string"},
                    "name": {"type": "string"},
                    "type": {"type": "string"},
                    "attributes": {"type": "object"},
                },
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["uuid", "source_uuid", "target_uuid", "name"],
                "additionalProperties": True,
                "properties": {
                    "uuid": {"type": "string"},
                    "source_uuid": {"type": "string"},
                    "target_uuid": {"type": "string"},
                    "name": {"type": "string"},
                    "fact_type": {"type": "string"},
                    "valid_from_round": {"type": ["integer", "null"]},
                    "valid_to_round": {"type": ["integer", "null"]},
                    "episode_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "node_count": {"type": "integer"},
        "edge_count": {"type": "integer"},
    },
}

ONTOLOGY_DEFINITION_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["entity_types", "edge_types"],
    "additionalProperties": True,
    "properties": {
        "entity_types": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "description"],
                "additionalProperties": True,
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "attributes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["name", "type"],
                            "additionalProperties": True,
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string"},
                                "description": {"type": "string"},
                            },
                        },
                    },
                    "examples": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "edge_types": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "description"],
                "additionalProperties": True,
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "source_targets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["source", "target"],
                            "additionalProperties": True,
                            "properties": {
                                "source": {"type": "string"},
                                "target": {"type": "string"},
                            },
                        },
                    },
                    "attributes": {"type": "array"},
                },
            },
        },
        "analysis_summary": {"type": "string"},
    },
}

PERSONA_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["user_id", "user_name", "name", "bio", "persona"],
    "additionalProperties": True,
    "properties": {
        "user_id": {"type": "integer"},
        "user_name": {"type": "string"},
        "name": {"type": "string"},
        "bio": {"type": "string"},
        "persona": {"type": "string"},
        "karma": {"type": "integer"},
        "friend_count": {"type": "integer"},
        "follower_count": {"type": "integer"},
        "statuses_count": {"type": "integer"},
        "age": {"type": ["integer", "null"]},
        "gender": {"type": ["string", "null"]},
        "mbti": {"type": ["string", "null"]},
        "country": {"type": ["string", "null"]},
        "profession": {"type": ["string", "null"]},
        "interested_topics": {"type": "array", "items": {"type": "string"}},
        "source_entity_uuid": {"type": ["string", "null"]},
        "source_entity_type": {"type": ["string", "null"]},
        "created_at": {"type": "string"},
    },
}

# ============================================================
# Sample-Payloads (repräsentative Beispiele aus Tests/Services)
# ============================================================

_PROJECT_SAMPLE = {
    "project_id": "proj_abc123",
    "name": "Demo-Projekt",
    "status": "graph_completed",
    "created_at": "2026-05-01T10:00:00",
    "updated_at": "2026-05-01T10:05:00",
    "files": [{"filename": "document.pdf", "path": "/uploads/doc.pdf", "size": 102400}],
    "total_text_length": 12345,
    "ontology": None,
    "analysis_summary": None,
    "graph_id": "abcdef0123456789abcdef0123456789",
    "graph_build_task_id": "task_xyz",
    "simulation_requirement": "Simuliere Twitter-Diskurs",
    "chunk_size": 500,
    "chunk_overlap": 50,
    "error": None,
}

_SIMULATION_SAMPLE = {
    "simulation_id": "sim_abc123",
    "project_id": "proj_abc123",
    "graph_id": "abcdef0123456789abcdef0123456789",
    "enable_twitter": True,
    "enable_reddit": False,
    "status": "ready",
    "entities_count": 10,
    "profiles_count": 10,
    "entity_types": ["Person", "Organization"],
    "config_generated": True,
    "config_reasoning": "Nutzer-Typen erkannt",
    "current_round": 0,
    "twitter_status": "not_started",
    "reddit_status": "not_started",
    "created_at": "2026-05-01T10:00:00",
    "updated_at": "2026-05-01T10:01:00",
    "error": None,
    "source_simulation_id": None,
    "root_simulation_id": None,
    "branch_name": None,
    "branch_depth": 0,
}

_RUN_STATUS_SAMPLE = {
    "run_id": "run_abcdef012345",
    "run_type": "graph_build",
    "entity_id": "proj_abc123",
    "parent_run_id": None,
    "status": "completed",
    "progress": 100,
    "message": "Graph build finished",
    "error": None,
    "started_at": "2026-05-01T10:00:00",
    "updated_at": "2026-05-01T10:02:00",
    "completed_at": "2026-05-01T10:02:00",
    "artifacts": {"graph_id": "abcdef0123456789abcdef0123456789"},
    "resume_capability": {},
    "branch_label": None,
    "metadata": {"project_id": "proj_abc123"},
    "linked_ids": {"project_id": "proj_abc123"},
    "events": [
        {
            "timestamp": "2026-05-01T10:00:00",
            "type": "created",
            "status": "pending",
            "progress": 0,
            "message": "graph_build created",
            "error": None,
            "details": {},
        }
    ],
}

_REPORT_STATUS_SAMPLE = {
    "report_id": "report_abc123",
    "simulation_id": "sim_abc123",
    "graph_id": "abcdef0123456789abcdef0123456789",
    "simulation_requirement": "Analyse sozialer Dynamiken",
    "status": "completed",
    "outline": {
        "title": "Simulationsbericht",
        "summary": "Kurzfassung der Ergebnisse",
        "sections": [
            {"title": "Einleitung", "content": "# Intro\n\nBeschreibung..."},
            {"title": "Ergebnisse", "content": "## Ergebnisse\n\n..."},
        ],
    },
    "markdown_content": "# Bericht\n\n...",
    "created_at": "2026-05-01T10:10:00",
    "completed_at": "2026-05-01T10:15:00",
    "error": None,
    "has_evidence": True,
    "evidence_sections": 3,
}

# GraphData-Sample direkt aus tests/test_graph_export.py::_graph_payload()
_GRAPH_DATA_SAMPLE = {
    "graph_id": "abcdef0123456789abcdef0123456789",
    "nodes": [
        {
            "uuid": "node-1",
            "name": "Alice",
            "type": "Person",
            "attributes": {"role": "lead"},
        },
        {
            "uuid": "node-2",
            "name": "Bob",
            "type": "Person",
        },
    ],
    "edges": [
        {
            "uuid": "edge-1",
            "source_uuid": "node-1",
            "target_uuid": "node-2",
            "name": "knows",
            "fact_type": "knows",
            "valid_from_round": 0,
            "valid_to_round": None,
            "episode_ids": ["ep-1", "ep-2"],
        }
    ],
    "node_count": 2,
    "edge_count": 1,
}

_ONTOLOGY_DEFINITION_SAMPLE = {
    "entity_types": [
        {
            "name": "Person",
            "description": "Any natural person",
            "attributes": [
                {"name": "role", "type": "text", "description": "Role in context"},
            ],
            "examples": ["Alice", "Bob"],
        },
        {
            "name": "Organization",
            "description": "Any organization or institution",
            "attributes": [],
            "examples": ["Acme Corp"],
        },
    ],
    "edge_types": [
        {
            "name": "KNOWS",
            "description": "Person knows another person",
            "source_targets": [{"source": "Person", "target": "Person"}],
            "attributes": [],
        }
    ],
    "analysis_summary": "Dokument beschreibt Personennetzwerk.",
}

# Persona-Sample basierend auf OasisAgentProfile.to_dict() und test_oasis_profile_format.py
_PERSONA_SAMPLE = {
    "user_id": 1,
    "user_name": "alice",
    "name": "Alice",
    "bio": "Softwareentwicklerin aus Berlin",
    "persona": "Alice ist eine technikaffine Person mit Interesse an Open-Source-Projekten.",
    "karma": 1500,
    "friend_count": 200,
    "follower_count": 350,
    "statuses_count": 800,
    "age": 32,
    "gender": "female",
    "mbti": "INTP",
    "country": "Deutschland",
    "profession": "Software Engineer",
    "interested_topics": ["Open Source", "AI", "Linux"],
    "source_entity_uuid": "uuid-123",
    "source_entity_type": "Person",
    "created_at": "2026-05-01",
}

# ============================================================
# Tests — Project
# ============================================================


def test_project_schema_valid_sample():
    validate(instance=_PROJECT_SAMPLE, schema=PROJECT_SCHEMA)


def test_project_schema_missing_required_field():
    bad = {k: v for k, v in _PROJECT_SAMPLE.items() if k != "project_id"}
    with pytest.raises(ValidationError, match="project_id"):
        validate(instance=bad, schema=PROJECT_SCHEMA)


def test_project_schema_invalid_status():
    bad = {**_PROJECT_SAMPLE, "status": "unknown_status"}
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=PROJECT_SCHEMA)


def test_project_schema_allows_extra_fields():
    extended = {**_PROJECT_SAMPLE, "new_field_from_future": "value"}
    validate(instance=extended, schema=PROJECT_SCHEMA)


# ============================================================
# Tests — Simulation
# ============================================================


def test_simulation_schema_valid_sample():
    validate(instance=_SIMULATION_SAMPLE, schema=SIMULATION_SCHEMA)


def test_simulation_schema_missing_required_field():
    bad = {k: v for k, v in _SIMULATION_SAMPLE.items() if k != "simulation_id"}
    with pytest.raises(ValidationError, match="simulation_id"):
        validate(instance=bad, schema=SIMULATION_SCHEMA)


def test_simulation_schema_invalid_status():
    bad = {**_SIMULATION_SAMPLE, "status": "bogus"}
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=SIMULATION_SCHEMA)


def test_simulation_schema_simple_dict_valid():
    """to_simple_dict() liefert Subset der Felder — muss auch gegen Schema passen."""
    simple = {
        "simulation_id": "sim_xyz",
        "project_id": "proj_xyz",
        "graph_id": "abcdef0123456789abcdef0123456789",
        "status": "ready",
        "entities_count": 5,
        "profiles_count": 5,
        "entity_types": ["Person"],
        "config_generated": False,
        "error": None,
        "source_simulation_id": None,
        "root_simulation_id": None,
        "branch_name": None,
        "branch_depth": 0,
    }
    validate(instance=simple, schema=SIMULATION_SCHEMA)


# ============================================================
# Tests — RunStatus
# ============================================================


def test_run_status_schema_valid_sample():
    validate(instance=_RUN_STATUS_SAMPLE, schema=RUN_STATUS_SCHEMA)


def test_run_status_schema_missing_run_id():
    bad = {k: v for k, v in _RUN_STATUS_SAMPLE.items() if k != "run_id"}
    with pytest.raises(ValidationError, match="run_id"):
        validate(instance=bad, schema=RUN_STATUS_SCHEMA)


def test_run_status_schema_invalid_status():
    bad = {**_RUN_STATUS_SAMPLE, "status": "invalid_state"}
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=RUN_STATUS_SCHEMA)


def test_run_status_schema_progress_out_of_range():
    bad = {**_RUN_STATUS_SAMPLE, "progress": 150}
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=RUN_STATUS_SCHEMA)


def test_run_status_schema_event_valid():
    run_with_events = {
        **_RUN_STATUS_SAMPLE,
        "events": [
            {
                "timestamp": "2026-05-01T10:00:00",
                "type": "updated",
                "status": "processing",
                "progress": 50,
                "message": "Halbzeit",
                "error": None,
                "details": {},
            }
        ],
    }
    validate(instance=run_with_events, schema=RUN_STATUS_SCHEMA)


# ============================================================
# Tests — ReportStatus
# ============================================================


def test_report_status_schema_valid_sample():
    validate(instance=_REPORT_STATUS_SAMPLE, schema=REPORT_STATUS_SCHEMA)


def test_report_status_schema_missing_required_field():
    bad = {k: v for k, v in _REPORT_STATUS_SAMPLE.items() if k != "report_id"}
    with pytest.raises(ValidationError, match="report_id"):
        validate(instance=bad, schema=REPORT_STATUS_SCHEMA)


def test_report_status_schema_pending_without_outline():
    pending = {
        "report_id": "report_xyz",
        "simulation_id": "sim_xyz",
        "graph_id": "abcdef0123456789abcdef0123456789",
        "simulation_requirement": "Test",
        "status": "pending",
        "outline": None,
        "markdown_content": "",
        "created_at": "2026-05-01T10:00:00",
        "completed_at": "",
        "error": None,
        "has_evidence": False,
        "evidence_sections": 0,
    }
    validate(instance=pending, schema=REPORT_STATUS_SCHEMA)


def test_report_status_schema_invalid_status():
    bad = {**_REPORT_STATUS_SAMPLE, "status": "unknown"}
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=REPORT_STATUS_SCHEMA)


# ============================================================
# Tests — GraphData
# ============================================================


def test_graph_data_schema_valid_sample():
    validate(instance=_GRAPH_DATA_SAMPLE, schema=GRAPH_DATA_SCHEMA)


def test_graph_data_schema_missing_required_field():
    bad = {k: v for k, v in _GRAPH_DATA_SAMPLE.items() if k != "graph_id"}
    with pytest.raises(ValidationError, match="graph_id"):
        validate(instance=bad, schema=GRAPH_DATA_SCHEMA)


def test_graph_data_schema_empty_graph():
    empty_graph = {
        "graph_id": "abcdef0123456789abcdef0123456789",
        "nodes": [],
        "edges": [],
        "node_count": 0,
        "edge_count": 0,
    }
    validate(instance=empty_graph, schema=GRAPH_DATA_SCHEMA)


def test_graph_data_schema_node_missing_uuid():
    bad_node = {
        "graph_id": "abcdef0123456789abcdef0123456789",
        "nodes": [{"name": "Alice", "type": "Person"}],  # uuid fehlt
        "edges": [],
        "node_count": 1,
        "edge_count": 0,
    }
    with pytest.raises(ValidationError, match="uuid"):
        validate(instance=bad_node, schema=GRAPH_DATA_SCHEMA)


def test_graph_data_schema_edge_missing_source():
    bad_edge = {
        **_GRAPH_DATA_SAMPLE,
        "edges": [
            {
                "uuid": "edge-1",
                # source_uuid fehlt
                "target_uuid": "node-2",
                "name": "knows",
            }
        ],
    }
    with pytest.raises(ValidationError, match="source_uuid"):
        validate(instance=bad_edge, schema=GRAPH_DATA_SCHEMA)


# ============================================================
# Tests — OntologyDefinition
# ============================================================


def test_ontology_definition_schema_valid_sample():
    validate(instance=_ONTOLOGY_DEFINITION_SAMPLE, schema=ONTOLOGY_DEFINITION_SCHEMA)


def test_ontology_definition_schema_missing_entity_types():
    bad = {k: v for k, v in _ONTOLOGY_DEFINITION_SAMPLE.items() if k != "entity_types"}
    with pytest.raises(ValidationError, match="entity_types"):
        validate(instance=bad, schema=ONTOLOGY_DEFINITION_SCHEMA)


def test_ontology_definition_schema_entity_missing_name():
    bad = {
        **_ONTOLOGY_DEFINITION_SAMPLE,
        "entity_types": [{"description": "kein Name"}],
    }
    with pytest.raises(ValidationError, match="name"):
        validate(instance=bad, schema=ONTOLOGY_DEFINITION_SCHEMA)


def test_ontology_definition_schema_empty_lists_valid():
    minimal = {"entity_types": [], "edge_types": []}
    validate(instance=minimal, schema=ONTOLOGY_DEFINITION_SCHEMA)


# ============================================================
# Tests — Persona
# ============================================================


def test_persona_schema_valid_sample():
    validate(instance=_PERSONA_SAMPLE, schema=PERSONA_SCHEMA)


def test_persona_schema_missing_required_field():
    bad = {k: v for k, v in _PERSONA_SAMPLE.items() if k != "user_id"}
    with pytest.raises(ValidationError, match="user_id"):
        validate(instance=bad, schema=PERSONA_SCHEMA)


def test_persona_schema_optional_fields_absent():
    """Minimalprofil ohne optionale Felder ist gültig."""
    minimal = {
        "user_id": 42,
        "user_name": "bob",
        "name": "Bob",
        "bio": "Just a person",
        "persona": "Bob is a simple guy.",
    }
    validate(instance=minimal, schema=PERSONA_SCHEMA)


def test_persona_schema_twitter_format_valid():
    """to_twitter_format() liefert username statt user_name — aber das Schema pinnt to_dict()."""
    twitter_fmt = {
        "user_id": 1,
        "user_name": "alice",
        "name": "Alice",
        "bio": "bio",
        "persona": "persona",
        "friend_count": 200,
        "follower_count": 350,
        "statuses_count": 800,
        "created_at": "2026-05-01",
        "source_entity_uuid": "uuid-123",
        "source_entity_type": "Person",
    }
    validate(instance=twitter_fmt, schema=PERSONA_SCHEMA)


def test_persona_schema_invalid_user_id_type():
    bad = {**_PERSONA_SAMPLE, "user_id": "not-an-int"}
    with pytest.raises(ValidationError):
        validate(instance=bad, schema=PERSONA_SCHEMA)
