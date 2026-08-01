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


def _retry_result(content: str, finish_reason: str) -> tuple:
    """Rueckgabeform von ``llm_call_with_retry`` im Client: ``(response, latency_ms)``.

    Ein blanker Response-Mock genuegt hier nicht: ``chat()`` entpackt das
    Ergebnis in zwei Werte. Ein MagicMock iteriert leer, das Entpacken schlug
    also mit ``ValueError`` fehl, bevor der Truncation-Guard ueberhaupt
    erreicht wurde — die drei betroffenen Tests haben lange nichts mehr
    geprueft, obwohl sie rot waren.
    """
    return _make_response(content, finish_reason), 12.5


# Am Cap gekappte Persona: display_name ist vollstaendig, persona bricht ab.
TRUNCATED = '{"display_name": "Maya", "persona": "sehr langer abgeschnittener'


class TestChatJsonRejectsTruncatedOutput:
    def test_finish_reason_length_raises_typed_error(self):
        client = _make_client()

        with patch.object(client, "_publish_model_active"):
            with patch(
                "app.llm.client.llm_call_with_retry",
                return_value=_retry_result(TRUNCATED, finish_reason="length"),
            ):
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

        with patch.object(client, "_publish_model_active"):
            with patch(
                "app.llm.client.llm_call_with_retry",
                return_value=_retry_result(TRUNCATED, finish_reason="length"),
            ) as call:
                with pytest.raises(LLMOutputTruncatedError):
                    client.chat_json(
                        [{"role": "user", "content": "persona bitte"}],
                        schema=PersonaSchema,
                    )

        assert call.call_count == 1, "Truncation darf keinen Fallback-Call ausloesen"

    def test_native_ollama_schema_call_rejects_truncated_output(self):
        """Der native Ollama-Pfad umgeht ``chat()`` — und damit dessen Guard.

        ``/api/chat`` meldet einen am ``num_predict``-Limit gekappten Lauf mit
        ``done_reason: "length"``. Ohne eigene Pruefung landet das Fragment in
        derselben Repair-Kette, die fuer den OpenAI-Pfad bereits geschlossen
        ist.
        """
        from app.llm.providers.ollama import chat_with_schema

        class PersonaSchema(BaseModel):
            display_name: str

        http_response = MagicMock()
        http_response.raise_for_status.return_value = None
        http_response.json.return_value = {
            "message": {"content": TRUNCATED},
            "done_reason": "length",
        }
        http_client = MagicMock()
        http_client.__enter__.return_value = http_client
        http_client.post.return_value = http_response

        with patch("httpx.Client", return_value=http_client):
            with pytest.raises(LLMOutputTruncatedError):
                chat_with_schema(
                    base_url="http://localhost:11434/v1",
                    model="llama3",
                    api_key="ollama",
                    think=False,
                    num_ctx=8192,
                    messages=[{"role": "user", "content": "persona bitte"}],
                    schema=PersonaSchema,
                    temperature=0.3,
                    max_tokens=4096,
                )

    def test_ollama_truncation_does_not_fall_back_to_openai_wrapper(self):
        """Der native Ollama-Pfad faellt bei Fehlern breit auf den
        OpenAI-Wrapper zurueck — gedacht fuer Netz- und 4xx-Fehler.

        Eine Truncation ist kein Transportfehler: derselbe Request ueber einen
        anderen Transport wird wieder gekappt, nur kostet er einen zweiten
        vollen Call. Der Abbruch muss deshalb durchschlagen.
        """

        class PersonaSchema(BaseModel):
            display_name: str

        client = _make_client()
        client.base_url = "http://localhost:11434/v1"

        http_response = MagicMock()
        http_response.raise_for_status.return_value = None
        http_response.json.return_value = {
            "message": {"content": TRUNCATED},
            "done_reason": "length",
        }
        http_client = MagicMock()
        http_client.__enter__.return_value = http_client
        http_client.post.return_value = http_response

        with patch.object(client, "_publish_model_active"):
            with patch("httpx.Client", return_value=http_client):
                with patch("app.llm.client.llm_call_with_retry") as openai_call:
                    with pytest.raises(LLMOutputTruncatedError):
                        client.chat_json(
                            [{"role": "user", "content": "persona bitte"}],
                            schema=PersonaSchema,
                        )

        assert openai_call.call_count == 0, (
            "Truncation darf keinen Fallback auf den OpenAI-Wrapper ausloesen"
        )

    def test_complete_response_still_parses(self):
        """Gegenprobe: ``finish_reason="stop"`` bleibt der normale Erfolgspfad."""
        client = _make_client()

        with patch.object(client, "_publish_model_active"):
            with patch(
                "app.llm.client.llm_call_with_retry",
                return_value=_retry_result('{"display_name": "Maya"}', finish_reason="stop"),
            ):
                result = client.chat_json(
                    [{"role": "user", "content": "persona bitte"}]
                )

        assert result == {"display_name": "Maya"}
