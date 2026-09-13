"""Vertragstests fuer den Interviewpfad (Befunde D und E).

Jeder Fall hier war vor dem Fix eine akzeptierte Eingabe, die erst weiter
unten im Interviewpfad als ``AttributeError``/``TypeError`` auffiel oder — noch
schlechter — still eine falsche Auswahl erzeugte.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.interview_contract import (
    DEFAULT_SELECTION_REASONING,
    InterviewAgentSelection,
    InterviewQuestions,
    PersistedAgentProfiles,
)


class TestPersistedAgentProfiles:
    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({"profiles": []}, id="wrapped-object"),
            pytest.param([None], id="null-element"),
            pytest.param(["invalid"], id="string-element"),
            pytest.param([123], id="int-element"),
            pytest.param("[]", id="string-root"),
            pytest.param([{"bio": 42}], id="non-string-bio"),
        ],
    )
    def test_invalid_payloads_are_rejected(self, payload) -> None:
        with pytest.raises(ValidationError):
            PersistedAgentProfiles.model_validate(payload)

    @pytest.mark.parametrize(
        "field", ["bio", "realname", "username", "name", "persona", "profession"]
    )
    def test_explicit_null_is_rejected_even_though_the_field_is_optional(
        self, field: str
    ) -> None:
        """Codex-Befund P2 auf PR #1498.

        Ein *fehlendes* Feld ist unproblematisch — die Fallbackkette des
        Interviewpfads faengt es ab. Ein ausdrueckliches ``null`` ist etwas
        anderes: ``profile.get("bio", "")[:200]`` liefert dann ``None[:200]``
        und wirft ``TypeError``, und zwar ausserhalb des ``try`` von
        ``select_agents_for_interview`` — der ganze Interviewlauf reisst ab.
        Der Vertrag muss solche Dateien in den CSV-/Leer-Fallback schicken,
        statt sie durchzulassen.
        """
        with pytest.raises(ValidationError):
            PersistedAgentProfiles.model_validate([{field: None}])

    def test_null_interested_topics_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PersistedAgentProfiles.model_validate([{"interested_topics": None}])

    def test_absent_fields_stay_valid(self) -> None:
        """Die Gegenprobe: nichts davon ist Pflicht."""
        assert PersistedAgentProfiles.model_validate([{"user_id": 3}]).root

    def test_empty_list_is_valid(self) -> None:
        assert PersistedAgentProfiles.model_validate([]).root == []

    def test_existing_reddit_profile_shape_stays_valid(self) -> None:
        """Rueckwaertskompatibilitaet: die real geschriebene Form aus
        ``OasisAgentProfile.to_reddit_format`` muss unveraendert durchgehen,
        inklusive der Zusatzfelder, die nicht im Vertrag stehen."""
        payload = [
            {
                "user_id": 0,
                "username": "maria_koch",
                "name": "Maria Koch",
                "bio": "Elternvertreterin",
                "persona": "Engagiert, skeptisch.",
                "karma": 12,
                "created_at": "2026-01-01",
                "age": "42",
                "gender": "female",
                "mbti": "INFJ",
                "profession": "Lehrerin",
                "interested_topics": ["Bildung"],
                "persona_kind": "individual",
                "voice_register": "neutral-de",
            },
            {
                "user_id": 1,
                "username": "schulamt",
                "name": "Schulamt",
                "bio": "Behoerde",
                "persona": "Kollektiv.",
                "karma": 3,
                "created_at": "2026-01-01",
                "age": "",
                "gender": "",
                "mbti": "",
                "persona_kind": "collective",
            },
        ]

        assert len(PersistedAgentProfiles.model_validate(payload).root) == 2


class TestInterviewAgentSelection:
    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({"selected_indices": [True]}, id="bool-is-not-int"),
            pytest.param({"selected_indices": [1, 1]}, id="duplicates"),
            pytest.param({"selected_indices": ["1"]}, id="string-index"),
            pytest.param({"selected_indices": [-1]}, id="negative-index"),
            pytest.param({"selected_indices": [1.5]}, id="float-index"),
            pytest.param({"selected_indices": "0,1"}, id="string-instead-of-list"),
        ],
    )
    def test_invalid_selections_are_rejected(self, payload) -> None:
        with pytest.raises(ValidationError):
            InterviewAgentSelection.model_validate(payload)

    def test_index_outside_profile_array_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            InterviewAgentSelection.model_validate(
                {"selected_indices": [0, 9]},
                context={"profile_count": 3, "max_agents": 5},
            )

    def test_more_than_max_agents_is_capped_not_rejected(self) -> None:
        """Codex-Befund (Review PR #1498): zu viele gueltige, eindeutige,
        in-range Indizes sind keine kaputte Antwort — nur eine, die das Cap
        ueberschreitet. Kappen auf die ersten ``max_agents`` erhaelt die
        inhaltliche LLM-Auswahl; ein ``ValueError`` haette den Aufrufer in
        seinen breiten ``except Exception`` und damit in den generischen
        "erste N Profile"-Fallback geschickt."""
        selection = InterviewAgentSelection.model_validate(
            {"selected_indices": [0, 1, 2], "reasoning": "Drei Perspektiven."},
            context={"profile_count": 10, "max_agents": 2},
        )

        assert selection.selected_indices == [0, 1]
        assert selection.reasoning == "Drei Perspektiven."

    def test_six_indices_at_max_agents_five_keeps_first_five(self) -> None:
        """Konkretes Beispiel aus dem Review: 6 statt 5 Indizes darf nicht auf
        den generischen Fallback fuehren, sondern muss die ersten 5 der
        LLM-Auswahl behalten."""
        selection = InterviewAgentSelection.model_validate(
            {"selected_indices": [3, 1, 4, 0, 2, 5]},
            context={"profile_count": 6, "max_agents": 5},
        )

        assert selection.selected_indices == [3, 1, 4, 0, 2]

    def test_valid_selection_passes(self) -> None:
        selection = InterviewAgentSelection.model_validate(
            {"selected_indices": [0, 2, 4], "reasoning": "Breite Perspektiven."},
            context={"profile_count": 5, "max_agents": 5},
        )

        assert selection.selected_indices == [0, 2, 4]
        assert selection.reasoning == "Breite Perspektiven."

    def test_missing_fields_fall_back_to_documented_defaults(self) -> None:
        selection = InterviewAgentSelection.model_validate({"ok": True, "stub": True})

        assert selection.selected_indices == []
        assert selection.reasoning == DEFAULT_SELECTION_REASONING

    def test_null_reasoning_uses_default_instead_of_discarding_selection(self) -> None:
        selection = InterviewAgentSelection.model_validate(
            {"selected_indices": [1], "reasoning": None}
        )

        assert selection.reasoning == DEFAULT_SELECTION_REASONING


class TestInterviewQuestions:
    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({"questions": None}, id="null"),
            pytest.param({"questions": "Warum?"}, id="bare-string"),
            pytest.param({"questions": [None]}, id="null-element"),
            pytest.param({"questions": ["   ", "b", "c"]}, id="blank-question"),
            pytest.param({"questions": ["a", "b"]}, id="too-few"),
            pytest.param({}, id="missing"),
        ],
    )
    def test_invalid_question_payloads_are_rejected(self, payload) -> None:
        with pytest.raises(ValidationError):
            InterviewQuestions.model_validate(payload)

    @pytest.mark.parametrize("count", [3, 4, 5])
    def test_three_to_five_questions_are_accepted(self, count: int) -> None:
        payload = {"questions": [f"Frage {i}?" for i in range(count)]}

        assert len(InterviewQuestions.model_validate(payload).questions) == count

    def test_six_questions_are_capped_to_five_not_rejected(self) -> None:
        """Codex-Befund (Review PR #1498): 6 gueltige, nichtleere Fragen sind
        keine kaputte Antwort. ``max_length`` wirkt weiterhin providerseitig
        im Strict-JSON-Schema (siehe ``schema=InterviewQuestions``); trotzdem
        ankommende Ueberschuesse werden gekappt statt in den generischen
        Default-Fragensatz (eine einzige Frage) zu fallen."""
        payload = {"questions": [f"Frage {i}?" for i in range(6)]}

        result = InterviewQuestions.model_validate(payload)

        assert result.questions == [f"Frage {i}?" for i in range(5)]

    def test_too_few_questions_stay_rejected_even_after_capping_logic(self) -> None:
        """Gegenprobe: das Kappen darf die Untergrenze nicht aufweichen — zu
        wenige Fragen bleiben eine kaputte Antwort, das behebt kein Kappen."""
        with pytest.raises(ValidationError):
            InterviewQuestions.model_validate({"questions": ["Nur eine?"]})
