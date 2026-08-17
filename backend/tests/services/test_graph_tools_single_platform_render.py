"""Issue #1320 — der Interview-Renderer erfindet keine stumme Plattform.

Empirischer Befund im Referenzlauf: 32 Interview-Traces in
``reddit_simulation.db``, 0 in ``twitter_simulation.db`` — und trotzdem trug
jedes der 42 Interview-Transkripte einen
``[Twitter Platform Response]``-Block mit ``(No response from this platform)``.

Ursache ist keine gescheiterte Twitter-Befragung, sondern eine, die nie
stattgefunden hat: der Direktpfad ist bewusst single-platform
(``interview_direct.interview_agents_batch_direct``), der Renderer war es nie.
Der Platzhalter sah für jeden Leser wie ein Fehler aus.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.sim import interview_direct

PERSISTED_PERSONAS = [
    {
        "user_id": 1,
        "username": "anna_m",
        "name": "Anna Musterfrau",
        "bio": "Konsumentin, interessiert an Nachhaltigkeit.",
        "profession": "Konsumentin",
    }
]


def _store_with_personas() -> MagicMock:
    store = MagicMock()
    store.read_json.side_effect = lambda simulation_id, name, default=None: (
        PERSISTED_PERSONAS if name == "reddit_profiles" else default
    )
    return store


def _make_service() -> object:
    from app.services.graph_tools import GraphToolsService

    svc = GraphToolsService.__new__(GraphToolsService)
    svc._llm_client = MagicMock()
    svc._llm_client.chat_json.return_value = {
        "selected_indices": [0],
        "reasoning": "Testauswahl",
        "questions": ["Wie bewerten Sie das neue Angebot?"],
    }
    svc._llm_client.chat.return_value = "Zusammenfassung der Interviews."
    svc._load_agent_profiles = MagicMock(
        return_value=[
            {
                "realname": "Anna Musterfrau",
                "username": "anna_m",
                "bio": "Konsumentin, interessiert an Nachhaltigkeit.",
                "profession": "Konsumentin",
            }
        ]
    )
    return svc


def _run_interview(api_result: dict) -> object:
    svc = _make_service()
    with patch(
        "app.services.simulation_runner.SimulationRunner.check_env_alive",
        return_value=False,
    ), patch(
        "app.services.sim.interview_client.check_env_alive",
        return_value=False,
    ), patch.object(
        interview_direct, "_store", return_value=_store_with_personas()
    ), patch(
        "app.services.simulation_runner.SimulationRunner.interview_agents_batch",
        return_value=api_result,
    ):
        return svc.interview_agents(
            simulation_id="sim_1320",
            interview_requirement="Wie bewerten Sie das neue Angebot?",
            simulation_requirement="Kontext",
            max_agents=5,
        )


REDDIT_ANSWER = "Der Preis ist fair, aber die Lieferzeit könnte kürzer sein."
TWITTER_ANSWER = "Ich finde das Angebot überzeugend und würde es weiterempfehlen."


def _api(results: dict) -> dict:
    return {
        "success": True,
        "interviews_count": len(results),
        "result": {"results": results},
        "timestamp": "2026-08-17T00:00:00Z",
    }


def test_single_platform_answer_renders_no_placeholder_block():
    result = _run_interview(_api({"reddit_0": {"response": REDDIT_ANSWER}}))

    assert result.interviews
    response = result.interviews[0].response
    assert "[Twitter Platform Response]" not in response, (
        "Die Twitter-Plattform hat nicht geantwortet — ein Block dafür behauptet "
        f"eine gescheiterte Befragung, die es nie gab:\n{response}"
    )
    assert "(No response from this platform)" not in response
    assert "[Reddit Platform Response]" in response
    assert REDDIT_ANSWER in response


def test_both_platforms_answering_keep_both_blocks():
    result = _run_interview(
        _api(
            {
                "twitter_0": {"response": TWITTER_ANSWER},
                "reddit_0": {"response": REDDIT_ANSWER},
            }
        )
    )

    response = result.interviews[0].response
    assert "[Twitter Platform Response]" in response
    assert "[Reddit Platform Response]" in response
    assert TWITTER_ANSWER in response
    assert REDDIT_ANSWER in response


def test_no_platform_answering_keeps_one_recognizable_placeholder():
    """Der Report-Agent verwirft daran das gescheiterte Interview als Evidence."""
    result = _run_interview(_api({"reddit_0": {"response": ""}}))

    response = result.interviews[0].response
    assert response.strip() == "(No response from this platform)"
