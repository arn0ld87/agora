from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError

from app.contracts.ai_provider_contract import AiRoute


@pytest.mark.parametrize("secret_ref", [None, ""])
def test_connection_only_route_requires_a_non_empty_secret_ref(
    secret_ref: str | None,
) -> None:
    """
    Verify that connection-only routes require a non-empty secret reference.
    
    Parameters:
        secret_ref (str | None): The secret reference value supplied to the route.
    """
    provider_options = {"connection_only": True}
    if secret_ref is not None:
        provider_options["secret_ref"] = secret_ref

    with pytest.raises(ValidationError, match="secret_ref"):
        AiRoute(
            provider_connection_id="connection-openai",
            model_id="gpt-4.1-mini",
            source="project",
            provider_options=provider_options,
        )


def test_ai_route_json_schema_requires_secret_ref_for_connection_only_route() -> None:
    """
    Verify that the generated JSON Schema requires a non-empty `secret_ref` for connection-only routes.
    """
    validator = Draft202012Validator(AiRoute.model_json_schema())
    base_route = {
        "provider_connection_id": "connection-openai",
        "model_id": "gpt-4.1-mini",
        "source": "project",
    }

    validator.validate(
        {
            **base_route,
            "provider_options": {
                "connection_only": True,
                "secret_ref": "connection-secret",
            },
        }
    )
    with pytest.raises(JsonSchemaValidationError):
        validator.validate(
            {
                **base_route,
                "provider_options": {"connection_only": True},
            }
        )

