"""Contract-Tests für UserProfile + Onboarding-Vertrag (Onboarding Slice 2).

Testet ausschließlich den Vertrag (Pydantic v2-Validierung), keine
Implementierung. Siehe ``app.contracts.user_profile_contract``.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.user_profile_contract import (
    ONBOARDING_STEP_ORDER,
    REQUIRED_ONBOARDING_STEPS,
    OnboardingState,
    UserProfile,
    UserProfileUpdateRequest,
)


# ---------------------------------------------------------------------------
# UserProfile
# ---------------------------------------------------------------------------


class TestUserProfileDefaults:
    def test_defaults(self) -> None:
        profile = UserProfile(display_name="Alex")
        assert profile.language == "de"
        assert profile.theme == "system"
        assert profile.privacy_mode == "standard"
        assert profile.timezone == "Europe/Berlin"
        assert profile.report_language == "de"
        assert profile.avatar_ref is None
        assert profile.username is None

    def test_display_name_empty_string_raises(self) -> None:
        with pytest.raises(ValidationError, match="at least 1 character"):
            UserProfile(display_name="")

    def test_display_name_whitespace_only_raises(self) -> None:
        with pytest.raises(ValidationError, match="blank"):
            UserProfile(display_name="   ")

    def test_display_name_is_stripped(self) -> None:
        profile = UserProfile(display_name="  Alex Schneider  ")
        assert profile.display_name == "Alex Schneider"


class TestUserProfileTimezone:
    def test_invalid_timezone_raises(self) -> None:
        with pytest.raises(ValidationError, match="timezone"):
            UserProfile(display_name="Alex", timezone="Mars/Olympus")

    def test_valid_exotic_timezone_ok(self) -> None:
        profile = UserProfile(display_name="Alex", timezone="America/New_York")
        assert profile.timezone == "America/New_York"


class TestUserProfileUsername:
    def test_uppercase_username_raises(self) -> None:
        with pytest.raises(ValidationError, match="pattern"):
            UserProfile(display_name="Alex", username="ALEX")

    def test_single_char_username_raises(self) -> None:
        with pytest.raises(ValidationError, match="pattern"):
            UserProfile(display_name="Alex", username="a")

    def test_valid_username_ok(self) -> None:
        profile = UserProfile(display_name="Alex", username="alex.schneider")
        assert profile.username == "alex.schneider"


class TestUserProfileAvatarRef:
    def test_path_traversal_rejected(self) -> None:
        with pytest.raises(ValidationError, match="pattern"):
            UserProfile(display_name="Alex", avatar_ref="../../etc/passwd")

    def test_non_hex_ref_rejected(self) -> None:
        with pytest.raises(ValidationError, match="pattern"):
            UserProfile(display_name="Alex", avatar_ref="avatar-XYZ.png")

    def test_svg_extension_rejected(self) -> None:
        hex32 = "a" * 32
        with pytest.raises(ValidationError, match="pattern"):
            UserProfile(display_name="Alex", avatar_ref=f"avatar-{hex32}.svg")

    def test_valid_png_ref_ok(self) -> None:
        hex32 = "0123456789abcdef0123456789abcdef"[:32]
        profile = UserProfile(display_name="Alex", avatar_ref=f"avatar-{hex32}.png")
        assert profile.avatar_ref == f"avatar-{hex32}.png"


class TestUserProfileStrict:
    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="Extra inputs"):
            UserProfile(display_name="Alex", is_admin=True)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# UserProfileUpdateRequest
# ---------------------------------------------------------------------------


class TestUserProfileUpdateRequest:
    def test_empty_object_is_valid(self) -> None:
        request = UserProfileUpdateRequest()
        assert request.model_dump(exclude_unset=True) == {}

    def test_avatar_ref_field_is_rejected(self) -> None:
        hex32 = "a" * 32
        with pytest.raises(ValidationError, match="Extra inputs"):
            UserProfileUpdateRequest(avatar_ref=f"avatar-{hex32}.png")  # type: ignore[call-arg]

    def test_display_name_blank_raises(self) -> None:
        with pytest.raises(ValidationError, match="blank"):
            UserProfileUpdateRequest(display_name="   ")


# ---------------------------------------------------------------------------
# OnboardingState
# ---------------------------------------------------------------------------


class TestOnboardingStateDefaults:
    def test_defaults(self) -> None:
        state = OnboardingState()
        assert state.status == "not_started"
        assert state.current_step == "welcome"
        assert state.completed_steps == []
        assert state.operating_mode is None


class TestOnboardingStateCompletedSteps:
    def test_duplicate_completed_steps_raise(self) -> None:
        with pytest.raises(ValidationError, match="duplicates"):
            OnboardingState(completed_steps=["welcome", "welcome"])

    def test_unknown_step_raises(self) -> None:
        with pytest.raises(ValidationError):
            OnboardingState(completed_steps=["not-a-real-step"])  # type: ignore[list-item]

    def test_unknown_current_step_raises(self) -> None:
        with pytest.raises(ValidationError):
            OnboardingState(current_step="not-a-real-step")  # type: ignore[arg-type]


class TestOnboardingStateCompletion:
    def test_completed_without_required_steps_raises(self) -> None:
        with pytest.raises(ValidationError, match="completed onboarding requires steps"):
            OnboardingState(status="completed", completed_steps=["welcome"])

    def test_completed_with_required_steps_ok(self) -> None:
        state = OnboardingState(
            status="completed",
            completed_steps=["profile", "chat_model", "embeddings"],
        )
        assert state.status == "completed"

    def test_completed_with_all_steps_ok(self) -> None:
        state = OnboardingState(
            status="completed",
            completed_steps=list(ONBOARDING_STEP_ORDER),
        )
        assert state.status == "completed"


class TestOnboardingStateStrict:
    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="Extra inputs"):
            OnboardingState(nonsense_field=True)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# ONBOARDING_STEP_ORDER / REQUIRED_ONBOARDING_STEPS
# ---------------------------------------------------------------------------


class TestOnboardingStepOrder:
    def test_contains_all_seven_steps(self) -> None:
        assert len(ONBOARDING_STEP_ORDER) == 7
        assert set(ONBOARDING_STEP_ORDER) == {
            "welcome",
            "profile",
            "providers",
            "chat_model",
            "embeddings",
            "privacy",
            "summary",
        }

    def test_starts_with_welcome(self) -> None:
        assert ONBOARDING_STEP_ORDER[0] == "welcome"

    def test_ends_with_summary(self) -> None:
        assert ONBOARDING_STEP_ORDER[-1] == "summary"

    def test_no_duplicates_in_order(self) -> None:
        assert len(ONBOARDING_STEP_ORDER) == len(set(ONBOARDING_STEP_ORDER))

    def test_required_steps_are_subset_of_order(self) -> None:
        assert REQUIRED_ONBOARDING_STEPS.issubset(set(ONBOARDING_STEP_ORDER))
