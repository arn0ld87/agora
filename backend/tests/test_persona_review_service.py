"""Service-level tests for the Slice 2.1 persona review foundation."""

from __future__ import annotations

import pytest

from app.services.artifact_store import InMemoryArtifactStore
from app.services.persona_review_service import (
    InvalidReviewStatusError,
    PersonaNotFoundError,
    PersonaReviewService,
    REVIEW_STATUS_APPROVED,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_REGENERATING,
    REVIEW_STATUS_REJECTED,
)

SIM_ID = "sim_abcdef012345"


def _store_with_profiles(profiles):
    store = InMemoryArtifactStore()
    store.write_json(SIM_ID, "reddit_profiles", profiles)
    return store


def test_list_profiles_normalizes_review_status_for_generated_personas():
    store = _store_with_profiles([
        {"username": "alice", "is_manual": False},
        {"username": "bob", "is_manual": True},
    ])
    service = PersonaReviewService(store)

    profiles = service.list_profiles(SIM_ID)

    assert {p["username"]: p["review_status"] for p in profiles} == {
        "alice": REVIEW_STATUS_PENDING,
        "bob": REVIEW_STATUS_APPROVED,
    }
    # Read does not mutate the on-disk artifact.
    raw = store.read_json(SIM_ID, "reddit_profiles")
    assert all("review_status" not in entry for entry in raw)


def test_list_profiles_handles_missing_artifact():
    service = PersonaReviewService(InMemoryArtifactStore())
    assert service.list_profiles(SIM_ID) == []


def test_list_profiles_skips_non_dict_entries():
    store = _store_with_profiles([{"username": "a"}, "garbage", None])
    service = PersonaReviewService(store)
    assert [p["username"] for p in service.list_profiles(SIM_ID)] == ["a"]


def test_approve_persists_status_and_timestamp():
    store = _store_with_profiles([{"username": "alice"}])
    service = PersonaReviewService(store)

    updated = service.approve(SIM_ID, "alice", notes="solid persona")

    assert updated["review_status"] == REVIEW_STATUS_APPROVED
    assert updated["review_notes"] == "solid persona"
    assert updated["reviewed_at"]
    persisted = store.read_json(SIM_ID, "reddit_profiles")
    assert persisted[0]["review_status"] == REVIEW_STATUS_APPROVED


def test_reject_persists_with_optional_notes():
    store = _store_with_profiles([{"username": "alice"}])
    service = PersonaReviewService(store)

    updated = service.reject(SIM_ID, "alice")

    assert updated["review_status"] == REVIEW_STATUS_REJECTED
    assert updated["review_notes"] is None


def test_set_status_rejects_unknown_status():
    store = _store_with_profiles([{"username": "alice"}])
    service = PersonaReviewService(store)

    with pytest.raises(InvalidReviewStatusError):
        service.set_status(SIM_ID, "alice", "maybe")


def test_unknown_username_raises_not_found():
    store = _store_with_profiles([{"username": "alice"}])
    service = PersonaReviewService(store)

    with pytest.raises(PersonaNotFoundError):
        service.approve(SIM_ID, "ghost")


def test_edit_invalidates_prior_approval():
    store = _store_with_profiles([
        {"username": "alice", "review_status": REVIEW_STATUS_APPROVED},
    ])
    service = PersonaReviewService(store)

    updated = service.edit(SIM_ID, "alice", {"bio": "rewritten"})

    assert updated["bio"] == "rewritten"
    assert updated["review_status"] == REVIEW_STATUS_PENDING
    assert updated["reviewed_at"] is None


def test_edit_ignores_unknown_fields_but_keeps_editable_ones():
    store = _store_with_profiles([{"username": "alice"}])
    service = PersonaReviewService(store)

    updated = service.edit(
        SIM_ID,
        "alice",
        {
            "bio": "ok",
            "user_id": 999,  # not editable, must be ignored
            "interested_topics": "ai, infra",
        },
    )

    assert updated["bio"] == "ok"
    assert updated["interested_topics"] == ["ai", "infra"]
    assert "user_id" not in updated  # not present in original, stays out


def test_edit_requires_at_least_one_editable_field():
    store = _store_with_profiles([{"username": "alice"}])
    service = PersonaReviewService(store)

    with pytest.raises(ValueError):
        service.edit(SIM_ID, "alice", {"user_id": 999})


def test_edit_can_explicitly_keep_review_status():
    store = _store_with_profiles([
        {"username": "alice", "review_status": REVIEW_STATUS_APPROVED},
    ])
    service = PersonaReviewService(store)

    updated = service.edit(
        SIM_ID,
        "alice",
        {"bio": "ok", "review_status": REVIEW_STATUS_APPROVED},
    )

    assert updated["review_status"] == REVIEW_STATUS_APPROVED


def test_start_gate_blocks_when_pending_or_rejected():
    store = _store_with_profiles([
        {"username": "alice", "review_status": REVIEW_STATUS_APPROVED},
        {"username": "bob"},  # defaults to pending
        {"username": "carol", "review_status": REVIEW_STATUS_REJECTED},
    ])
    service = PersonaReviewService(store)

    gate = service.evaluate_start_gate(SIM_ID)

    assert gate["allowed"] is False
    assert gate["pending"] == ["bob"]
    assert gate["rejected"] == ["carol"]
    assert gate["approved"] == ["alice"]
    assert gate["total"] == 3


def test_start_gate_allows_when_all_approved():
    store = _store_with_profiles([
        {"username": "alice", "review_status": REVIEW_STATUS_APPROVED},
        {"username": "bob", "is_manual": True},  # manual default = approved
    ])
    service = PersonaReviewService(store)

    gate = service.evaluate_start_gate(SIM_ID)

    assert gate["allowed"] is True
    assert set(gate["approved"]) == {"alice", "bob"}


def test_start_gate_blocks_empty_simulation():
    service = PersonaReviewService(InMemoryArtifactStore())
    gate = service.evaluate_start_gate(SIM_ID)
    # An empty simulation cannot start either — there is nothing to approve.
    assert gate["allowed"] is False
    assert gate["total"] == 0


def test_set_status_idempotent():
    store = _store_with_profiles([{"username": "alice"}])
    service = PersonaReviewService(store)

    first = service.approve(SIM_ID, "alice")
    second = service.approve(SIM_ID, "alice")

    assert first["review_status"] == second["review_status"] == REVIEW_STATUS_APPROVED


# ---------------------------------------------------------------------------
# Sub-Slice 31: regenerate() state-machine
# ---------------------------------------------------------------------------

def test_regenerate_from_pending_sets_regenerating():
    store = _store_with_profiles([{"username": "alice"}])
    service = PersonaReviewService(store)

    updated = service.regenerate(SIM_ID, "alice")

    assert updated["review_status"] == REVIEW_STATUS_REGENERATING
    assert updated["reviewed_at"] is not None
    persisted = store.read_json(SIM_ID, "reddit_profiles")
    assert persisted[0]["review_status"] == REVIEW_STATUS_REGENERATING


def test_regenerate_from_approved_sets_regenerating():
    store = _store_with_profiles([
        {"username": "alice", "review_status": REVIEW_STATUS_APPROVED},
    ])
    service = PersonaReviewService(store)

    updated = service.regenerate(SIM_ID, "alice")

    assert updated["review_status"] == REVIEW_STATUS_REGENERATING


def test_regenerate_from_rejected_sets_regenerating():
    store = _store_with_profiles([
        {"username": "alice", "review_status": REVIEW_STATUS_REJECTED},
    ])
    service = PersonaReviewService(store)

    updated = service.regenerate(SIM_ID, "alice")

    assert updated["review_status"] == REVIEW_STATUS_REGENERATING


def test_regenerate_from_regenerating_is_idempotent():
    """Re-requesting regeneration while already regenerating is allowed."""
    store = _store_with_profiles([
        {"username": "alice", "review_status": REVIEW_STATUS_REGENERATING},
    ])
    service = PersonaReviewService(store)

    updated = service.regenerate(SIM_ID, "alice", notes="second request")

    assert updated["review_status"] == REVIEW_STATUS_REGENERATING
    assert updated["review_notes"] == "second request"


def test_regenerate_unknown_username_raises_not_found():
    store = _store_with_profiles([{"username": "alice"}])
    service = PersonaReviewService(store)

    with pytest.raises(PersonaNotFoundError):
        service.regenerate(SIM_ID, "ghost")


def test_regenerate_sets_notes_and_requested_by():
    store = _store_with_profiles([{"username": "alice"}])
    service = PersonaReviewService(store)

    updated = service.regenerate(
        SIM_ID, "alice", notes="thin profile", requested_by="operator@example.com"
    )

    assert updated["review_notes"] == "thin profile"
    assert updated["review_requested_by"] == "operator@example.com"
    assert updated["review_status"] == REVIEW_STATUS_REGENERATING


def test_start_gate_blocks_when_any_persona_regenerating():
    store = _store_with_profiles([
        {"username": "alice", "review_status": REVIEW_STATUS_APPROVED},
        {"username": "bob", "review_status": REVIEW_STATUS_REGENERATING},
    ])
    service = PersonaReviewService(store)

    gate = service.evaluate_start_gate(SIM_ID)

    assert gate["allowed"] is False
    assert gate["regenerating"] == ["bob"]
    assert gate["approved"] == ["alice"]


def test_start_gate_allows_when_no_regenerating_pending_rejected():
    store = _store_with_profiles([
        {"username": "alice", "review_status": REVIEW_STATUS_APPROVED},
        {"username": "bob", "is_manual": True},  # manual default = approved
    ])
    service = PersonaReviewService(store)

    gate = service.evaluate_start_gate(SIM_ID)

    assert gate["allowed"] is True
    assert gate["regenerating"] == []
