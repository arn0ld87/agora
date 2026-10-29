"""Unit tests for app.llm._client_shim (get_client_attr)."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from app.llm._client_shim import _get_client_attr, get_client_attr


def test_get_client_attr_fallback_when_module_not_in_sys_modules():
    """Returns default when app.llm.client is absent from sys.modules."""
    with patch.dict(sys.modules, {"app.llm.client": None}, clear=False):
        # sys.modules.get("app.llm.client") returns None
        result = get_client_attr("nonexistent_symbol", default="my_fallback")
        assert result == "my_fallback"


def test_get_client_attr_fallback_when_attr_not_found():
    """Returns default when app.llm.client exists but attribute is missing."""
    mock_mod = MagicMock(spec=[])
    with patch.dict(sys.modules, {"app.llm.client": mock_mod}):
        result = get_client_attr("missing_attr", default=42)
        assert result == 42


def test_get_client_attr_returns_attr_when_present():
    """Returns attribute value when app.llm.client has the attribute."""
    mock_mod = MagicMock()
    mock_mod.custom_helper = "sentinel_value"
    with patch.dict(sys.modules, {"app.llm.client": mock_mod}):
        result = get_client_attr("custom_helper", default="default")
        assert result == "sentinel_value"


def test_get_client_attr_reflects_monkey_patch():
    """Reflects runtime patch on app.llm.client (e.g. via mock.patch)."""
    # Ensure app.llm.client is imported
    import app.llm.client as client_mod

    sentinel = MagicMock()
    with patch.object(client_mod, "OpenAI", sentinel):
        resolved = get_client_attr("OpenAI", default=None)
        assert resolved is sentinel


def test_get_client_attr_alias():
    """Ensures _get_client_attr alias is the same function."""
    assert _get_client_attr is get_client_attr


def test_mixins_import_shim():
    """Verifies that all 4 mixins expose _get_client_attr compatible with the shim."""
    from app.llm._client_chat import _get_client_attr as chat_shim
    from app.llm._client_route_factory import _get_client_attr as factory_shim
    from app.llm._client_routes import _get_client_attr as routes_shim
    from app.llm._client_transport import _get_client_attr as transport_shim

    assert chat_shim is get_client_attr
    assert factory_shim is get_client_attr
    assert routes_shim is get_client_attr
    assert transport_shim is get_client_attr
