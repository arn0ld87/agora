"""Tests for resolve_default_event_bus() in event_bus.py (Issue #411).

Covers:
  (a) No Flask context → FilePollingEventBus is returned (safe fallback).
  (b) Flask not importable → FilePollingEventBus is returned.
  (c) Unexpected error while reading Flask extensions → logged, not swallowed;
      FilePollingEventBus is returned as fallback.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

from app.services.event_bus import FilePollingEventBus, resolve_default_event_bus


# ---------------------------------------------------------------------------
# (a) No Flask app context present → FilePollingEventBus
# ---------------------------------------------------------------------------


class TestResolveDefaultEventBusNoContext:
    def test_no_flask_context_returns_file_polling_bus(self):
        """Outside any Flask app context the fallback must be FilePollingEventBus.

        Flask IS importable but has_app_context() returns False, so the function
        must skip the container lookup and return FilePollingEventBus.
        """
        result = resolve_default_event_bus()
        assert isinstance(result, FilePollingEventBus)


# ---------------------------------------------------------------------------
# (b) Flask not importable → FilePollingEventBus, no exception leaks
# ---------------------------------------------------------------------------


class TestResolveDefaultEventBusFlaskMissing:
    def test_import_error_yields_fallback(self, monkeypatch):
        """If flask cannot be imported the function must still return the fallback."""
        # Temporarily make the flask import fail inside the function.
        original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

        def _block_flask(name, *args, **kwargs):
            if name == "flask":
                raise ImportError("flask is not installed")
            return original_import(name, *args, **kwargs)

        # Patch builtins.__import__ so the lazy `from flask import …` fails.
        import builtins
        monkeypatch.setattr(builtins, "__import__", _block_flask)

        # Remove cached flask module so the import actually runs.
        flask_modules = {k: v for k, v in sys.modules.items() if k == "flask" or k.startswith("flask.")}
        for k in flask_modules:
            monkeypatch.delitem(sys.modules, k, raising=False)

        result = resolve_default_event_bus()
        assert isinstance(result, FilePollingEventBus)


# ---------------------------------------------------------------------------
# (c) Unexpected error in Flask extensions → logged + FilePollingEventBus
# ---------------------------------------------------------------------------


class TestResolveDefaultEventBusUnexpectedError:
    def test_unexpected_error_is_logged_not_swallowed(self, monkeypatch):
        """An unexpected RuntimeError from extensions must be logged and fall back."""
        # Build a fake Flask environment where has_app_context() is True but
        # current_app.extensions.get() raises an unexpected error.
        fake_extensions = MagicMock()
        fake_extensions.get.side_effect = RuntimeError("broken DI container")

        fake_app = MagicMock()
        fake_app.extensions = fake_extensions

        fake_flask = types.ModuleType("flask")
        fake_flask.has_app_context = lambda: True  # type: ignore[attr-defined]
        fake_flask.current_app = fake_app  # type: ignore[attr-defined]

        # Replace the real flask in sys.modules for the duration of this test.
        monkeypatch.setitem(sys.modules, "flask", fake_flask)

        with patch("app.services.event_bus.logger") as mock_logger:
            result = resolve_default_event_bus()

        # Must fall back, not raise.
        assert isinstance(result, FilePollingEventBus)

        # The warning must have been emitted with exc_info=True.
        mock_logger.warning.assert_called_once()
        call_kwargs = mock_logger.warning.call_args
        assert call_kwargs.kwargs.get("exc_info") is True

    def test_unexpected_error_does_not_propagate(self, monkeypatch):
        """Callers must never see the internal RuntimeError."""
        fake_extensions = MagicMock()
        fake_extensions.get.side_effect = RuntimeError("container exploded")

        fake_app = MagicMock()
        fake_app.extensions = fake_extensions

        fake_flask = types.ModuleType("flask")
        fake_flask.has_app_context = lambda: True  # type: ignore[attr-defined]
        fake_flask.current_app = fake_app  # type: ignore[attr-defined]

        monkeypatch.setitem(sys.modules, "flask", fake_flask)

        with patch("app.services.event_bus.logger"):
            # Must not raise any exception.
            result = resolve_default_event_bus()

        assert isinstance(result, FilePollingEventBus)

    def test_container_event_bus_returned_when_present(self, monkeypatch):
        """Happy path: valid Flask context with DI container → container.event_bus."""
        fake_container = MagicMock()
        fake_container.event_bus = MagicMock(spec=["subscribe", "publish"])

        fake_extensions = MagicMock()
        fake_extensions.get.return_value = fake_container

        fake_app = MagicMock()
        fake_app.extensions = fake_extensions

        fake_flask = types.ModuleType("flask")
        fake_flask.has_app_context = lambda: True  # type: ignore[attr-defined]
        fake_flask.current_app = fake_app  # type: ignore[attr-defined]

        monkeypatch.setitem(sys.modules, "flask", fake_flask)

        result = resolve_default_event_bus()
        assert result is fake_container.event_bus
