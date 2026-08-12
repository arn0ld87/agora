"""Tests für ManifestCapture (Issue #763, Ticket 2)."""

import json
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.contracts.run_manifest_contract import RunManifest
from app.services.manifest_capture import ManifestCapture


class TestManifestCaptureDraft:
    """S1-S3: ManifestCapture.capture_draft() — Draft-Manifest schreiben."""

    @pytest.fixture
    def run_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield tmp

    def test_writes_draft_manifest(self, run_dir):
        """S1: capture_draft schreibt manifest.json mit status draft."""
        ManifestCapture.capture_draft(
            run_id="run_test123456",
            run_dir=run_dir,
            seed_document_hash="sha256:abc",
            seed_document_filename="test.md",
            simulation_config_hash="sha256:def",
            graph_id="graph_001",
            agora_version="0.9.5",
            schema_version="1.0.0",
            random_seed=42,
            simulation_id_seed="sim_test",
        )

        manifest_path = os.path.join(run_dir, "manifest.json")
        assert os.path.exists(manifest_path), "manifest.json wurde nicht geschrieben"

        with open(manifest_path) as f:
            data = json.load(f)

        assert data["status"] == "draft"
        assert data["run_id"] == "run_test123456"
        assert data["schema_version"] == 1

    def test_manifest_is_valid_pydantic(self, run_dir):
        """S2: Geschriebenes Manifest ist als RunManifest validierbar."""
        ManifestCapture.capture_draft(
            run_id="run_test123456",
            run_dir=run_dir,
            seed_document_hash="sha256:abc",
            seed_document_filename="test.md",
            simulation_config_hash="sha256:def",
            graph_id="graph_001",
            agora_version="0.9.5",
            schema_version="1.0.0",
            random_seed=42,
            simulation_id_seed="sim_test",
        )

        manifest_path = os.path.join(run_dir, "manifest.json")
        with open(manifest_path) as f:
            data = json.load(f)

        manifest = RunManifest(**data)
        assert manifest.status == "draft"
        assert manifest.run_id == "run_test123456"
        assert manifest.inputs.seed_document_hash == "sha256:abc"
        assert manifest.seeds.random_seed == 42

    def test_captured_at_is_utc_datetime(self, run_dir):
        """S2: captured_at ist ein UTC-Datetime-String."""
        ManifestCapture.capture_draft(
            run_id="run_test123456",
            run_dir=run_dir,
            seed_document_hash="sha256:abc",
            seed_document_filename="test.md",
            simulation_config_hash="sha256:def",
            graph_id="graph_001",
            agora_version="0.9.5",
            schema_version="1.0.0",
            random_seed=42,
            simulation_id_seed="sim_test",
        )

        manifest_path = os.path.join(run_dir, "manifest.json")
        with open(manifest_path) as f:
            data = json.load(f)

        captured_at = data["captured_at"]
        assert "T" in captured_at or "+" in captured_at or "Z" in captured_at

    def test_optional_fields_are_null_when_missing(self, run_dir):
        """S3: Optionale Felder sind null wenn nicht übergeben."""
        ManifestCapture.capture_draft(
            run_id="run_minimal123",
            run_dir=run_dir,
            seed_document_hash="sha256:abc",
            seed_document_filename="test.md",
            simulation_config_hash="sha256:def",
            graph_id="graph_001",
            agora_version="0.9.5",
            schema_version="1.0.0",
            random_seed=42,
            simulation_id_seed="sim_test",
        )

        manifest_path = os.path.join(run_dir, "manifest.json")
        with open(manifest_path) as f:
            data = json.load(f)

        assert data["replayed_from_run_id"] is None
        assert data["runtime"] is None
        assert data["inputs"]["graph_version"] is None
        assert data["inputs"]["embedding_version"] is None
