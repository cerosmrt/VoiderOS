"""Tests for F3 dot-separator display and delete behaviour."""
import types
import pytest
from unittest.mock import MagicMock, call

from line_ring import LineRing
from helpers import make_ring_app, _mock_circular_view


def _f3_app(ring_lines, lib_lines=None):
    """Build a minimal F3 app with book_ring wired up."""
    from new_interface import FullscreenCircleApp

    app = make_ring_app(['.'])
    app.book_ring = LineRing(ring_lines)
    app._library_lines = list(lib_lines or ring_lines)
    app.book_view = _mock_circular_view()
    app._save_library = MagicMock()
    app._book_pending_new = False
    app._tts_cut = MagicMock()

    for name in ('_book_show_editor', '_book_insert_separator',
                 '_book_backspace_on_dot', '_book_send_to_zero',
                 '_book_try_rename', '_book_is_portal',
                 '_library_current_fname'):
        setattr(app, name, types.MethodType(getattr(FullscreenCircleApp, name), app))

    return app


class TestSeparatorDisplay:

    def test_show_editor_on_dot_sets_single_dot(self):
        """_book_show_editor on a separator should setText('.'), not '· · ·'."""
        app = _f3_app(['.', 'chapter'])
        app.book_ring.index = 0  # on the dot
        app._book_show_editor()
        app.book_view.editor.setText.assert_called_with('.')

    def test_insert_separator_sets_single_dot(self):
        """_book_insert_separator should display the separator as '.'."""
        app = _f3_app(['chapter-a', 'chapter-b'])
        app.book_ring.index = 1  # not on a dot
        app._book_insert_separator()
        app.book_view.editor.setText.assert_called_with('.')



class TestSeparatorDelete:

    def test_ctrl_delete_on_dot_removes_only_separator(self):
        """Ctrl+Delete on a dot in F3 removes the dot, leaves chapters intact."""
        app = _f3_app(['.', 'chapter-a', 'chapter-b'])
        app.book_ring.index = 0  # on the dot
        app._book_send_to_zero()
        assert '.' not in app.book_ring.lines
        assert 'chapter-a' in app.book_ring.lines
        assert 'chapter-b' in app.book_ring.lines

    def test_ctrl_delete_on_dot_does_not_route_to_zero(self):
        """Deleting a separator must not append anything to 0.txt."""
        import builtins
        app = _f3_app(['.', 'chapter'])
        app.book_ring.index = 0
        opened_for_append = []
        real_open = builtins.open

        def _spy(path, mode='r', **kw):
            if 'a' in mode:
                opened_for_append.append(path)
            return real_open(path, mode, **kw)

        builtins.open = _spy
        try:
            app._book_send_to_zero()
        finally:
            builtins.open = real_open

        assert opened_for_append == [], "separator delete must not write to any file"
