"""``chat_json`` darf abgeschnittene Antworten nicht als Erfolg ausgeben.

Meldet der Provider ``finish_reason="length"``, ist die Antwort am
Output-Cap gekappt. Syntaktisch laesst sie sich oft schliessen — semantisch
fehlen die restlichen Felder. Der Caller bekommt dann ein Objekt, das wie
ein Ergebnis aussieht, aber keins ist.

Erwartet: ein typisierter Fehler, auf den der Caller gezielt mit einem
kompakteren Retry reagieren kann.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from app.llm.client import LLMOutputTruncatedError


def _make_client(model: str = "MiniMax-M3") -> Any:
    from app.utils.llm_client import LLMClient

    with patch("app.llm.client.OpenAI"):
        return LLMClient(
            api_key="dummy-key",
            base_url="https://api.minimax.io/v1",
            model=model,
        )


def _make_response(content: str, finish_reason: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = finish_reason
    response = MagicMock()
    response.choices = [choice]
    response.usage = None
    return response


# Am Cap gekappte Persona: display_name ist vollstaendig, persona bricht ab.
TRUNCATED = '{"display_name": "Maya", "persona": "sehr langer abgeschnittener'


class TestChatJsonRejectsTruncatedOutput:
    def test_finish_reason_length_raises_typed_error(self):
        client = _make_client()
        response = _make_response(TRUNCATED, finish_reason="length")

        with patch.object(client, "_publish_model_active"):
            with patch("app.llm.client.llm_call_with_retry", return_value=response):
                with pytest.raises(LLMOutputTruncatedError):
                    client.chat_json([{"role": "user", "content": "persona bitte"}])

    def test_truncation_with_schema_is_not_mistaken_for_unsupported_schema(self):
        """Der Strict-Schema-Pfad faengt breit ``Exception``, um auf
        ``json_object`` zurueckzufallen, wenn der Provider kein
        ``json_schema`` kann. Eine Truncation ist kein solcher Fall — sie
        darf keinen zweiten, gleich teuren Call ausloesen.
        """

        class PersonaSchema(BaseModel):
            display_name: str
            persona: str

        client = _make_client()
        response = _make_response(TRUNCATED, finish_reason="length")

        with patch.object(client, "_publish_model_active"):
            with patch(
                "app.llm.client.llm_call_with_retry", return_value=response
            ) as call:
                with pytest.raises(LLMOutputTruncatedError):
                    client.chat_json(
                        [{"role": "user", "content": "persona bitte"}],
                        schema=PersonaSchema,
                    )

        assert call.call_count == 1, "Truncation darf keinen Fallback-Call ausloesen"

    def test_complete_response_still_parses(self):
        """Gegenprobe: ``finish_reason="stop"`` bleibt der normale Erfolgspfad."""
        client = _make_client()
        response = _make_response('{"display_name": "Maya"}', finish_reason="stop")

        with patch.object(client, "_publish_model_active"):
            with patch("app.llm.client.llm_call_with_retry", return_value=response):
                result = client.chat_json(
                    [{"role": "user", "content": "persona bitte"}]
                )

        assert result == {"display_name": "Maya"}
