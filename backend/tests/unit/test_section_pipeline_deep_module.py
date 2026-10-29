"""Unit-Tests für das Deep Module SectionGenerationPipeline & SectionExecutionState (#1475)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.contracts.report_v3 import DEFAULT_REPORT_MODE
from app.services.report_agent.section_pipeline import (
    SectionContext,
    SectionEvidenceOutcome,
    SectionExecutionState,
    SectionGenerationPipeline,
    _persist_section_atomically,
    drop_unrepairable_section_entries,
    filter_structured_metadata_against_verified_section,
)


def _make_section(index: int = 1, title: str = "Marktreaktion") -> SimpleNamespace:
    return SimpleNamespace(
        index=index,
        title=title,
        content="",
        key_takeaways=[],
        TakeawayConfidence=[],
        claims=[],
        counterarguments=[],
        dissent_tracks=[],
        metadata={},
    )


def _make_ctx(**overrides) -> SectionContext:
    report_manager = MagicMock()
    report_manager.prepare_content_for_evidence.side_effect = lambda text: text
    defaults = dict(
        report_id="rep_deep_02",
        outline=SimpleNamespace(title="T", summary="S", sections=[]),
        total_sections=1,
        generate_section=lambda *_a, **_kw: (
            'Im Abschnitt sagt Anna: "Erstes Zitat aus der Simulation" [E001].'
        ),
        generate_metadata=lambda *_a, **_kw: {
            "key_takeaways": ["Kernaussage 1"],
            "claims": [{"statement": "Claim 1", "evidence_ids": ["E001"]}],
        },
        report_mode=DEFAULT_REPORT_MODE,
        persisted_section_contents={},
        report_manager=report_manager,
        validate_quotes=lambda *_a, **_kw: SimpleNamespace(
            is_valid=True, invalid_quotes=[], unbound_refs=[]
        ),
        verify_prose_fn=lambda text, *_a, **_kw: SimpleNamespace(
            changed=False, verified_text=text, demoted_hypotheses=[], unverified_statements=[]
        ),
    )
    defaults.update(overrides)
    return SectionContext(**defaults)


def test_section_execution_state_syncs_and_builds_result():
    agent = SimpleNamespace(
        _pending_unbound_evidence_refs={1: ["E999"]},
        _pending_quote_validation_failed={1: False},
        _pending_section_metadata={1: {"key_takeaways": ["Kernpunkt 1"]}},
        _pending_prose_hypotheses={1: [{"statement": "Hypothese 1"}]},
        _pending_unverified_statements={1: [{"statement": "Unbelegt"}]},
        evidence_map={"sections": []},
    )
    section = _make_section(1, "Abschnitt 1")
    state = SectionExecutionState.from_agent_pending(
        agent,
        section_index=1,
        title=section.title,
        content="Verifizierter Text [E001]",
    )

    assert state.unbound_evidence_refs == ["E999"]
    assert len(state.prose_hypotheses) == 1
    assert state.unverified_statements == [{"statement": "Unbelegt"}]
    assert state.raw_metadata == {"key_takeaways": ["Kernpunkt 1"]}

    result = state.to_section_result(agent, section)
    assert result.section_index == 1
    assert result.content == "Verifizierter Text [E001]"
    assert result.metadata["key_takeaways"] == ["Kernpunkt 1"]
    assert result.unbound_evidence_refs == ["E999"]


def test_persist_section_atomically_passes_explicit_section_state_when_supported():
    ctx = _make_ctx()
    section = _make_section(1, "Abschnitt 1")
    received_states: list[SectionExecutionState] = []
    call_order: list[str] = []

    def _save_with_state(
        report_id: str,
        section_index: int,
        section_title: str,
        content: str,
        *,
        section_state: SectionExecutionState | None = None,
    ) -> SectionEvidenceOutcome:
        call_order.append("evidence")
        if section_state is not None:
            received_states.append(section_state)
        return SectionEvidenceOutcome(
            claims=[{"claim_id": "c1", "statement": "Claim 1"}, {"claim_id": "c2", "statement": "Claim 2"}]
        )

    ctx.report_manager.save_section.side_effect = lambda *_a, **_kw: call_order.append("markdown")
    agent = SimpleNamespace(
        _save_evidence_section=_save_with_state,
        _pending_section_claims={},
        _pending_structured_metadata={},
        _pending_structured_attempt_counts={},
        _pending_unbound_evidence_refs={},
        _pending_quote_validation_failed={},
        _pending_section_metadata={},
        _pending_prose_hypotheses={},
        _pending_unverified_statements={},
    )
    state = SectionExecutionState(
        section_index=1,
        title="Abschnitt 1",
        content="Inhalt mit [E001]",
    )

    outcome = _persist_section_atomically(agent, section, ctx, state)
    assert call_order == ["evidence", "markdown"]
    assert len(outcome.claims) == 2
    assert len(received_states) == 1
    assert received_states[0] is state


def test_section_generation_pipeline_end_to_end_cleans_pending_state():
    ctx = _make_ctx()
    section = _make_section(1, "Abschnitt 1")

    agent = SimpleNamespace(
        evidence_map={"sections": []},
        _pending_section_claims={},
        _pending_structured_metadata={},
        _pending_structured_attempt_counts={},
        _pending_unbound_evidence_refs={},
        _pending_quote_validation_failed={},
        _pending_section_metadata={},
        _pending_prose_hypotheses={},
        _pending_unverified_statements={},
        _prose_evidence_pool=lambda: {},
        report_logger=None,
        llm=SimpleNamespace(),
        _record_section_metadata=lambda idx, meta: agent._pending_section_metadata.__setitem__(
            idx, dict(meta)
        ),
        generate_section_react=lambda *_a, **_kw: (
            'Im Abschnitt sagt Anna: "Erstes Zitat aus der Simulation" [E001].'
        ),
        generate_section_metadata=lambda *_a, **_kw: {
            "key_takeaways": ["Kernaussage 1"],
            "claims": [{"statement": "Claim 1", "evidence_ids": ["E001"]}],
        },
        _save_evidence_section=lambda *_a, **_kw: SectionEvidenceOutcome(
            claims=[{"claim_id": "c1", "statement": "Claim 1", "evidence_ids": ["E001"]}]
        ),
    )

    pipeline = SectionGenerationPipeline(ctx)
    result = pipeline.run(agent, section, section_index=1)

    assert result.section_index == 1
    assert not result.failed
    assert len(result.bound_claims) == 1
    assert 1 not in agent._pending_section_metadata
    assert 1 not in agent._pending_structured_metadata


def test_consolidated_step_helpers_exposed_on_section_pipeline():
    filtered = filter_structured_metadata_against_verified_section(
        {
            "key_takeaways": [
                {"takeaway": "Behalten", "claim_ids": ["c1"], "evidence_ids": ["E001"]}
            ],
        },
        verified_claims=[{"claim_id": "c1", "statement": "Behalten", "evidence_ids": ["E001"]}],
        persisted_content="Hier steht das Erste Zitat aus der Simulation [E001].",
    )
    assert len(filtered["key_takeaways"]) == 1

    sections = [
        {
            "section_index": 1,
            "section_title": "Sektion 1",
            "claims": [{"claim_id": "c_bad", "statement": ""}],
            "hypotheses": [],
        }
    ]
    fake_validation_error = SimpleNamespace(
        errors=lambda: [
            {
                "loc": ("sections", 0, "claims", 0, "statement"),
                "type": "string_too_short",
                "msg": "String should have at least 1 character",
            }
        ]
    )
    dropped = drop_unrepairable_section_entries(sections, fake_validation_error)  # type: ignore[arg-type]
    assert len(dropped) == 1
    assert dropped[0]["claim_id"] == "c_bad"
    assert sections[0]["claims"] == []
