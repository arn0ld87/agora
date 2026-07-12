"""Service-Tests für OnboardingStateStore + compute_onboarding_requirements
(Onboarding Slice 2).

Instanzen werden direkt mit ``data_dir=tmp_path`` konstruiert. Für
``compute_onboarding_requirements`` (die intern den ``UserProfileStore``-
Singleton und ``get_settings`` verwendet) wird gezielt gepatcht statt echte
Settings zu konstruieren (vermeidet Kopplung an ADR-0003-Pflichtfelder wie
SECRET_KEY).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.contracts.user_profile_contract import (
    ONBOARDING_STEP_ORDER,
    OnboardingRequirements,
    OnboardingStepUpdateRequest,
    UserProfileUpdateRequest,
)
from app.services.onboarding_state_store import (
    OnboardingIncompleteError,
    OnboardingStateStore,
    compute_onboarding_requirements,
    get_onboarding_state_store,
    reset_onboarding_state_store_for_tests,
)
from app.services.user_profile_store import (
    get_user_profile_store,
    reset_user_profile_store_for_tests,
)


@pytest.fixture
def store(tmp_path) -> OnboardingStateStore:
    return OnboardingStateStore(data_dir=tmp_path)


class TestLoadDefault:
    def test_load_returns_not_started_default(self, store: OnboardingStateStore) -> None:
        state = store.load()
        assert state.status == "not_started"
        assert state.current_step == "welcome"
        assert state.completed_steps == []


class TestCompleteStepProgression:
    def test_first_step_advances_status_and_current_step(
        self, store: OnboardingStateStore
    ) -> None:
        state = store.complete_step(OnboardingStepUpdateRequest(step="welcome"))
        assert state.status == "in_progress"
        assert "welcome" in state.completed_steps
        assert state.current_step == ONBOARDING_STEP_ORDER[1]

    def test_full_progression_reaches_summary(self, store: OnboardingStateStore) -> None:
        state = None
        for step in ONBOARDING_STEP_ORDER:
            state = store.complete_step(OnboardingStepUpdateRequest(step=step))
        assert state is not None
        assert set(state.completed_steps) == set(ONBOARDING_STEP_ORDER)
        # Nach Abschluss aller Schritte bleibt current_step deterministisch
        # bei "summary" (letzter Fallback in _first_open_step).
        assert state.current_step == "summary"

    def test_idempotent_repeat_does_not_duplicate(
        self, store: OnboardingStateStore
    ) -> None:
        store.complete_step(OnboardingStepUpdateRequest(step="welcome"))
        state = store.complete_step(OnboardingStepUpdateRequest(step="welcome"))
        assert state.completed_steps.count("welcome") == 1


class TestOperatingMode:
    def test_operating_mode_is_persisted(self, store: OnboardingStateStore) -> None:
        state = store.complete_step(
            OnboardingStepUpdateRequest(step="welcome", operating_mode="local")
        )
        assert state.operating_mode == "local"

    def test_operating_mode_survives_later_steps_without_it(
        self, store: OnboardingStateStore
    ) -> None:
        store.complete_step(
            OnboardingStepUpdateRequest(step="welcome", operating_mode="hybrid")
        )
        state = store.complete_step(OnboardingStepUpdateRequest(step="profile"))
        assert state.operating_mode == "hybrid"


class TestResume:
    def test_second_instance_sees_state_from_first(self, tmp_path) -> None:
        first = OnboardingStateStore(data_dir=tmp_path)
        first.complete_step(OnboardingStepUpdateRequest(step="welcome"))
        first.complete_step(OnboardingStepUpdateRequest(step="profile"))

        second = OnboardingStateStore(data_dir=tmp_path)
        state = second.load()
        assert set(state.completed_steps) == {"welcome", "profile"}
        assert state.current_step == "providers"


class TestDismissReopen:
    def test_dismiss_from_not_started(self, store: OnboardingStateStore) -> None:
        state = store.dismiss()
        assert state.status == "dismissed"

    def test_dismiss_is_noop_when_already_completed(
        self, store: OnboardingStateStore
    ) -> None:
        for step in ONBOARDING_STEP_ORDER:
            store.complete_step(OnboardingStepUpdateRequest(step=step))
        store.complete(
            OnboardingRequirements(
                profile_valid=True,
                chat_model_configured=True,
                embedding_configured=True,
            )
        )
        state = store.dismiss()
        assert state.status == "completed"

    def test_reopen_restores_in_progress_and_keeps_completed_steps(
        self, store: OnboardingStateStore
    ) -> None:
        store.complete_step(OnboardingStepUpdateRequest(step="welcome"))
        store.dismiss()
        state = store.reopen()
        assert state.status == "in_progress"
        assert "welcome" in state.completed_steps
        assert state.current_step == "profile"


class TestComplete:
    def test_missing_requirement_raises_with_missing_list(
        self, store: OnboardingStateStore
    ) -> None:
        for step in ("profile", "chat_model", "embeddings"):
            store.complete_step(OnboardingStepUpdateRequest(step=step))
        with pytest.raises(OnboardingIncompleteError) as excinfo:
            store.complete(
                OnboardingRequirements(
                    profile_valid=False,
                    chat_model_configured=True,
                    embedding_configured=True,
                )
            )
        assert "profile_valid" in excinfo.value.missing

    def test_missing_required_step_raises_with_missing_list(
        self, store: OnboardingStateStore
    ) -> None:
        # Kein Schritt abgeschlossen — profile/chat_model/embeddings fehlen.
        with pytest.raises(OnboardingIncompleteError) as excinfo:
            store.complete(
                OnboardingRequirements(
                    profile_valid=True,
                    chat_model_configured=True,
                    embedding_configured=True,
                )
            )
        assert "profile" in excinfo.value.missing
        assert "chat_model" in excinfo.value.missing
        assert "embeddings" in excinfo.value.missing

    def test_happy_path_sets_completed(self, store: OnboardingStateStore) -> None:
        for step in ("profile", "chat_model", "embeddings"):
            store.complete_step(OnboardingStepUpdateRequest(step=step))
        state = store.complete(
            OnboardingRequirements(
                profile_valid=True,
                chat_model_configured=True,
                embedding_configured=True,
            )
        )
        assert state.status == "completed"


class TestSingleton:
    def test_get_and_reset_singleton(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
        reset_onboarding_state_store_for_tests()
        first = get_onboarding_state_store()
        second = get_onboarding_state_store()
        assert first is second
        reset_onboarding_state_store_for_tests()
        third = get_onboarding_state_store()
        assert third is not first


class TestComputeOnboardingRequirementsProfile:
    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
        reset_user_profile_store_for_tests()
        yield
        reset_user_profile_store_for_tests()

    def test_profile_valid_is_false_without_profile(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "app.services.onboarding_state_store.get_settings",
            lambda: SimpleNamespace(
                llm_model_name="test-chat-model",
                embedding_model="test-embed-model",
                vector_dim=768,
            ),
        )
        requirements = compute_onboarding_requirements()
        assert requirements.profile_valid is False

    def test_profile_valid_is_true_after_profile_created(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "app.services.onboarding_state_store.get_settings",
            lambda: SimpleNamespace(
                llm_model_name="test-chat-model",
                embedding_model="test-embed-model",
                vector_dim=768,
            ),
        )
        get_user_profile_store().update(
            UserProfileUpdateRequest(display_name="Alex Schneider")
        )
        requirements = compute_onboarding_requirements()
        assert requirements.profile_valid is True


class TestComputeOnboardingRequirementsSettings:
    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
        reset_user_profile_store_for_tests()
        yield
        reset_user_profile_store_for_tests()

    def test_chat_model_and_embedding_flip_with_blank_settings(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "app.services.onboarding_state_store.get_settings",
            lambda: SimpleNamespace(
                llm_model_name="", embedding_model="", vector_dim=0
            ),
        )
        requirements = compute_onboarding_requirements()
        assert requirements.chat_model_configured is False
        assert requirements.embedding_configured is False

    def test_chat_model_and_embedding_true_with_valid_settings(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "app.services.onboarding_state_store.get_settings",
            lambda: SimpleNamespace(
                llm_model_name="qwen2.5:32b",
                embedding_model="nomic-embed-text",
                vector_dim=768,
            ),
        )
        requirements = compute_onboarding_requirements()
        assert requirements.chat_model_configured is True
        assert requirements.embedding_configured is True

    def test_embedding_configured_false_when_vector_dim_zero(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "app.services.onboarding_state_store.get_settings",
            lambda: SimpleNamespace(
                llm_model_name="qwen2.5:32b",
                embedding_model="nomic-embed-text",
                vector_dim=0,
            ),
        )
        requirements = compute_onboarding_requirements()
        assert requirements.embedding_configured is False
