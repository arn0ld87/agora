"""Regression #1663: ``schema_version`` für dateibasierte Verträge.

Regel aus #1657: PostgreSQL-Tabellen versioniert die Alembic-Revision, jedes
dateibasierte Artefakt trägt ein Feld ``schema_version``. Betroffen sind das
Dokument-Manifest (``extracted_documents.json``) und der Personasatz
(``reddit_profiles.json``, ``twitter_profiles.csv``).

Geprüft wird an drei Stellen:

- neuer Bestand trägt das Feld,
- Altbestand ohne das Feld wird als Version 1 gelesen,
- eine unbekannte Version wird abgelehnt und nicht still als Version 1
  weiterverarbeitet; der Leser, der degradieren darf, tut das sichtbar.
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts.document_manifest_contract import (
    DOCUMENT_MANIFEST_SCHEMA_VERSION,
    DocumentManifest,
    DocumentManifestEntry,
)
from app.contracts.interview_contract import PersistedAgentProfiles
from app.contracts.persona_contract import PERSONA_SCHEMA_VERSION, PersonaModel
from app.models.project import ProjectManager
from app.services.document_roles import load_document_roles
from app.services.oasis_profile_generator import OasisAgentProfile, OasisProfileGenerator

_LEGACY_MANIFEST = {
    "documents": [
        {
            "document_id": "report",
            "filename": "report.pdf",
            "start_offset": 30,
            "end_offset": 120,
            "document_role": "expected_result",
        }
    ]
}

_LEGACY_REDDIT_PROFILE = {
    "user_id": 1,
    "username": "betriebsrat",
    "name": "Betriebsrat",
    "bio": "Ein Gremium der Beschäftigten.",
    "persona": "Vertritt die Interessen der Belegschaft.",
    "karma": 1000,
    "age": 45,
    "gender": "other",
    "mbti": "ISTJ",
    "country": "DE",
    "persona_kind": "individual",
}


def test_current_versions_are_1():
    assert DOCUMENT_MANIFEST_SCHEMA_VERSION == 1
    assert PERSONA_SCHEMA_VERSION == 1


# --- Dokument-Manifest ------------------------------------------------------


@pytest.fixture
def project_id(tmp_path, monkeypatch) -> str:
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(tmp_path / "projects"))
    return ProjectManager.create_project(name="Schema-Version").project_id


def _manifest_path(project_id: str) -> Path:
    return Path(ProjectManager._get_project_documents_path(project_id))


def test_saved_manifest_carries_schema_version(project_id):
    manifest = DocumentManifest(
        documents=[
            DocumentManifestEntry(
                document_id="report", filename="report.pdf", start_offset=0, end_offset=10
            )
        ]
    )

    ProjectManager.save_document_manifest(project_id, manifest)

    raw = json.loads(_manifest_path(project_id).read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1


def test_legacy_manifest_without_schema_version_reads_as_v1(project_id):
    _manifest_path(project_id).write_text(json.dumps(_LEGACY_MANIFEST), encoding="utf-8")

    loaded = ProjectManager.get_document_manifest(project_id)

    assert loaded is not None
    assert loaded.schema_version == 1
    assert [entry.document_id for entry in loaded.documents] == ["report"]
    assert loaded.documents[0].document_role.value == "expected_result"


def test_manifest_with_unknown_schema_version_is_rejected(project_id):
    _manifest_path(project_id).write_text(
        json.dumps({**_LEGACY_MANIFEST, "schema_version": 2}), encoding="utf-8"
    )

    with pytest.raises(ValidationError, match="schema_version"):
        ProjectManager.get_document_manifest(project_id)


def test_document_roles_degrade_visibly_on_unknown_manifest_version(project_id, caplog):
    _manifest_path(project_id).write_text(
        json.dumps({**_LEGACY_MANIFEST, "schema_version": 2}), encoding="utf-8"
    )

    with caplog.at_level(logging.WARNING):
        roles = load_document_roles(project_id)

    assert roles == {}
    assert any(
        "Dokument-Manifest nicht lesbar" in record.getMessage() for record in caplog.records
    )


# --- Personasatz ------------------------------------------------------------


@pytest.fixture
def generator() -> OasisProfileGenerator:
    gen = OasisProfileGenerator.__new__(OasisProfileGenerator)
    gen.storage = None
    gen.graph_id = None
    return gen


def _agent_profile() -> OasisAgentProfile:
    return OasisAgentProfile(
        user_id=0,
        user_name="betriebsrat",
        name="Betriebsrat",
        bio="Ein Gremium der Beschäftigten.",
        persona="Vertritt die Interessen der Belegschaft gegenüber der Geschäftsführung.",
    )


def test_reddit_profile_file_carries_schema_version(generator, tmp_path):
    path = tmp_path / "reddit_profiles.json"

    generator._save_reddit_json([_agent_profile()], str(path))

    entries = json.loads(path.read_text(encoding="utf-8"))
    assert [entry["schema_version"] for entry in entries] == [1]


def test_twitter_profile_file_carries_schema_version(generator, tmp_path):
    path = tmp_path / "twitter_profiles.csv"

    generator._save_twitter_csv([_agent_profile()], str(path))

    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["schema_version"] for row in rows] == ["1"]
    # Die OASIS-Pflichtspalten bleiben unverändert.
    assert {"user_id", "name", "username", "user_char", "description"} <= set(rows[0])


def test_platform_formats_carry_schema_version():
    profile = _agent_profile()

    assert profile.to_reddit_format()["schema_version"] == 1
    assert profile.to_twitter_format()["schema_version"] == 1


def test_legacy_profile_file_without_schema_version_still_validates():
    profiles = PersistedAgentProfiles.model_validate([_LEGACY_REDDIT_PROFILE])

    assert profiles.root[0].schema_version == 1


def test_profile_file_with_unknown_schema_version_is_rejected():
    with pytest.raises(ValidationError, match="schema_version"):
        PersistedAgentProfiles.model_validate([{**_LEGACY_REDDIT_PROFILE, "schema_version": 2}])


def _persona_model_payload(**overrides) -> dict:
    payload = {
        "user_id": 1,
        "user_name": "betriebsrat",
        "name": "Betriebsrat",
        "bio": "Ein Gremium der Beschäftigten.",
        "persona": "Vertritt die Interessen der Belegschaft. " * 10,
    }
    payload.update(overrides)
    return payload


def test_persona_model_without_schema_version_reads_as_v1():
    assert PersonaModel.model_validate(_persona_model_payload()).schema_version == 1


def test_persona_model_rejects_unknown_schema_version():
    with pytest.raises(ValidationError, match="schema_version"):
        PersonaModel.model_validate(_persona_model_payload(schema_version=2))
