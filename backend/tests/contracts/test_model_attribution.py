"""Slice 8 (User-Bericht 2026-05-16): Modell-Provenance in ReportV3 + Evidence.

Why: User-Beschwerde, dass „nirgendwo hinterlegt wird, welches Modell für
welchen Teil der Erstellung zuständig war". Layer-0-Contract-Erweiterung
muss strikt validieren UND backward-compat zu existierenden Fixtures
bleiben (default = leere Liste bzw. None).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contracts.report_contract import (
    EvidenceItemModel,
    EvidenceSourceKind,
    EvidenceType,
)
from app.contracts.report_v3 import ModelAttribution, ReportV3


def _minimal_report(**overrides) -> dict:
    base = {
        "report_id": "rep_001",
        "generated_at": datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return base


def test_report_v3_backward_compat_without_model_attribution():
    """Alte Reports ohne model_attribution-Field laden weiterhin sauber."""
    report = ReportV3.model_validate(_minimal_report())
    assert report.model_attribution == []


def test_report_v3_with_model_attribution():
    attribution = [
        {
            "stage": "ontology",
            "provider": "ollama",
            "model_id": "qwen2.5:32b",
            "prompt_tokens": 1200,
            "completion_tokens": 340,
            "latency_ms": 2100.5,
            "started_at": "2026-05-16T12:00:00Z",
        },
        {
            "stage": "report_section",
            "provider": "openai",
            "model_id": "gpt-4o",
        },
    ]
    report = ReportV3.model_validate(_minimal_report(model_attribution=attribution))
    assert len(report.model_attribution) == 2
    assert report.model_attribution[0].stage == "ontology"
    assert report.model_attribution[0].prompt_tokens == 1200
    # Zweites Element nur mit Pflicht-Feldern
    assert report.model_attribution[1].latency_ms is None


def test_model_attribution_rejects_unknown_stage():
    """Stage ist Literal — Tippfehler oder freie Strings werden abgewiesen."""
    with pytest.raises(ValidationError):
        ModelAttribution.model_validate({
            "stage": "totally_made_up_stage",
            "provider": "ollama",
            "model_id": "qwen2.5:32b",
        })


def test_model_attribution_rejects_negative_latency():
    with pytest.raises(ValidationError):
        ModelAttribution.model_validate({
            "stage": "report_section",
            "provider": "ollama",
            "model_id": "qwen2.5:32b",
            "latency_ms": -1.0,
        })


def test_model_attribution_rejects_empty_model_id():
    with pytest.raises(ValidationError):
        ModelAttribution.model_validate({
            "stage": "report_section",
            "provider": "ollama",
            "model_id": "",
        })


def test_evidence_item_backward_compat_without_source_model():
    """Alte EvidenceItems ohne source_model laden weiterhin."""
    item = EvidenceItemModel.model_validate({
        "type": EvidenceType.web_fetch.value,
        "source": "https://example.com/article",
        "snippet": "Originaltext aus der Quelle, mind. 1 Zeichen lang.",
        "source_kind": EvidenceSourceKind.seed_corpus.value,
    })
    assert item.source_model is None


def test_evidence_item_with_source_model():
    item = EvidenceItemModel.model_validate({
        "type": EvidenceType.web_fetch.value,
        "source": "https://example.com/article",
        "snippet": "Originaltext aus der Quelle.",
        "source_kind": EvidenceSourceKind.seed_corpus.value,
        "source_model": "ollama/qwen2.5:32b",
    })
    assert item.source_model == "ollama/qwen2.5:32b"


def test_evidence_item_source_model_max_length():
    overlong = "a" * 201
    with pytest.raises(ValidationError):
        EvidenceItemModel.model_validate({
            "type": EvidenceType.web_fetch.value,
            "source": "https://example.com/article",
            "snippet": "Originaltext aus der Quelle.",
            "source_kind": EvidenceSourceKind.seed_corpus.value,
            "source_model": overlong,
        })
