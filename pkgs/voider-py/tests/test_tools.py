"""
Tests for tools.py:
  - clean_text
  - close_program
  - show_cursor
"""
import pytest
from unittest.mock import MagicMock, patch


class TestCleanText:
    """clean_text is currently a passthrough."""

    def test_returns_same_string(self):
        from tools import clean_text
        assert clean_text("hello") == "hello"

    def test_empty_string(self):
        from tools import clean_text
        assert clean_text("") == ""

    def test_whitespace_preserved(self):
        from tools import clean_text
        assert clean_text("  hello  ") == "  hello  "

    def test_unicode_preserved(self):
        from tools import clean_text
        assert clean_text("日本語 مرحبا") == "日本語 مرحبا"

    def test_dot_separator_preserved(self):
        from tools import clean_text
        assert clean_text(".") == "."

    def test_multiline_preserved(self):
        from tools import clean_text
        text = "line1\nline2\nline3"
        assert clean_text(text) == text

    def test_special_chars_preserved(self):
        from tools import clean_text
        text = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        assert clean_text(text) == text

    def test_none_passthrough(self):
        """clean_text returns whatever it receives — None passes through."""
        from tools import clean_text
        result = clean_text(None)
        assert result is None


class TestCloseProgram:
    def test_calls_app_close(self):
        from tools import close_program
        app = MagicMock()
        close_program(app)
        app.close.assert_called_once()

    def test_with_event_calls_close(self):
        from tools import close_program
        app = MagicMock()
        event = MagicMock()
        close_program(app, event=event)
        app.close.assert_called_once()

    def test_close_called_exactly_once(self):
        from tools import close_program
        app = MagicMock()
        close_program(app)
        assert app.close.call_count == 1


class TestShowCursor:
    def test_sets_cursor_visible(self):
        from tools import show_cursor
        app = MagicMock()
        show_cursor(app)
        app.entry.setCursorVisible.assert_called_once_with(True)

    def test_with_event_parameter(self):
        from tools import show_cursor
        app = MagicMock()
        event = MagicMock()
        show_cursor(app, event=event)
        app.entry.setCursorVisible.assert_called_once_with(True)

    def test_does_not_call_close(self):
        from tools import show_cursor
        app = MagicMock()
        show_cursor(app)
        app.close.assert_not_called()
