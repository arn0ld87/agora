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


def test_set_status_idempotent():
    store = _store_with_profiles([{"username": "alice"}])
    service = PersonaReviewService(store)

    first = service.approve(SIM_ID, "alice")
    second = service.approve(SIM_ID, "alice")

    assert first["review_status"] == second["review_status"] == REVIEW_STATUS_APPROVED
