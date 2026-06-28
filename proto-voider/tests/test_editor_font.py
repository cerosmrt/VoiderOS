"""Inline editors must follow the configured app font, not a hardcoded 11pt.

Bug: the active line in F2 (and every CircularView editor) is a child QLineEdit
created with QFont("Consolas", 11). Changing the font size repainted the dimmed
lines but never the editor, so the line you were ON stayed at 11pt.
"""
import types
from unittest.mock import MagicMock

from PyQt6.QtGui import QFont

from helpers import make_ring_app


def _editor_view():
    v = MagicMock()
    v.editor = MagicMock()
    return v


def _settings_app():
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    app.config = {}
    app.circular_view = _editor_view()
    app.book_view = _editor_view()
    app.o_reader_view = None
    app.o_browser_view = None
    app.oracle_o_view = None
    app.metronome_view = None
    app.book_concat_view = None
    app.scratch_view = None
    app.entry = MagicMock()
    app.switch_to_view = MagicMock()
    app._prev_view = 0
    app._apply_settings = types.MethodType(FullscreenCircleApp._apply_settings, app)
    return app


def test_apply_settings_propagates_font_to_editors(monkeypatch):
    import new_interface
    monkeypatch.setattr(new_interface, '_save_config', lambda *a, **k: None)
    app = _settings_app()
    app._apply_settings({'font_family': 'Georgia', 'font_size': 22})
    for v in (app.circular_view, app.book_view):
        assert v.editor.setFont.called, "editor font was never updated"
        font_arg = v.editor.setFont.call_args[0][0]
        assert isinstance(font_arg, QFont)
        assert font_arg.pointSize() == 22
