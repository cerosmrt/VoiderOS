"""Tests for trash cascade: 0.txt deletes → trash.txt; trash.txt deletes → permanent."""
import os
import types
import tempfile

import pytest
from line_ring import LineRing
from helpers import make_ring_app


def _trash_app(lines, is_zero=False, is_trash=False, tmp=None):
    """Build a mock app viewing either 0.txt, trash.txt, or another file."""
    from new_interface import FullscreenCircleApp

    tmp = tmp or tempfile.mkdtemp()
    f0 = os.path.join(tmp, '0.txt')
    trash = os.path.join(tmp, 'I', 'trash.txt')
    other = os.path.join(tmp, 'other.txt')
    os.makedirs(os.path.join(tmp, 'I'), exist_ok=True)

    with open(f0, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    app = make_ring_app(list(lines), tmp_file=f0)
    app.line_ring = LineRing(list(lines))
    app.f1_file = f0
    app._trash_file = trash

    if is_zero:
        app.current_file_path = f0
    elif is_trash:
        # Simulate viewing trash.txt
        with open(trash, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        app.current_file_path = trash
    else:
        with open(other, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        app.current_file_path = other

    methods = ['_delete_line_to_zero']
    for name in methods:
        setattr(app, name, types.MethodType(getattr(FullscreenCircleApp, name), app))

    app.auto_save_circular = lambda: None
    app.circular_view._offset = 0.0
    app.circular_view.editor.setCursorPosition = lambda _: None

    return app, f0, trash


class TestTrashCascade:

    def test_delete_from_zero_goes_to_trash(self, tmp_path):
        """Deleting a line while on 0.txt appends it to trash.txt."""
        lines = ['Hello world.', '.', 'Keep this.']
        app, f0, trash = _trash_app(lines, is_zero=True, tmp=str(tmp_path))
        app.line_ring.index = 0  # on 'Hello world.'
        app._delete_line_to_zero()

        assert os.path.exists(trash)
        content = open(trash, encoding='utf-8').read()
        assert 'Hello world.' in content

    def test_delete_from_zero_removes_from_ring(self, tmp_path):
        """Deleting from 0.txt removes the line from the ring."""
        lines = ['Hello world.', '.', 'Keep this.']
        app, f0, trash = _trash_app(lines, is_zero=True, tmp=str(tmp_path))
        app.line_ring.index = 0
        app._delete_line_to_zero()

        assert 'Hello world.' not in app.line_ring.lines

    def test_delete_from_trash_is_permanent(self, tmp_path):
        """Deleting a line while viewing trash.txt removes it permanently.
        The line must leave the ring; it must not be re-appended to trash.txt."""
        lines = ['Trashed line.', '.', 'Another.']
        app, f0, trash = _trash_app(lines, is_trash=True, tmp=str(tmp_path))

        # Track appends to f1_file and trash to verify no double-write
        written_to = []
        real_open = open

        def _spy_open(path, mode='r', **kw):
            if 'a' in mode and os.path.abspath(path) == os.path.abspath(trash):
                written_to.append(path)
            return real_open(path, mode, **kw)

        import builtins
        builtins.open = _spy_open
        try:
            app.line_ring.index = 0
            app._delete_line_to_zero()
        finally:
            builtins.open = real_open

        # Line should be gone from the in-memory ring
        assert 'Trashed line.' not in app.line_ring.lines
        # The line must NOT have been re-appended to trash.txt
        assert written_to == [], "Expected no append-write to trash.txt during permanent delete"

    def test_delete_from_other_file_goes_to_zero(self, tmp_path):
        """Deleting a line from a non-0.txt file appends it to 0.txt (existing behavior)."""
        lines = ['From book.', '.', 'Stay.']
        app, f0, trash = _trash_app(lines, is_zero=False, tmp=str(tmp_path))
        app.line_ring.index = 0
        app._delete_line_to_zero()

        content = open(f0, encoding='utf-8').read()
        assert 'From book.' in content

    def test_delete_dot_line_from_zero_goes_to_trash(self, tmp_path):
        """Even paragraph separators deleted from 0.txt go to trash."""
        lines = ['.', 'Line.']
        app, f0, trash = _trash_app(lines, is_zero=True, tmp=str(tmp_path))
        app.line_ring.index = 0  # on the dot
        app._delete_line_to_zero()

        assert os.path.exists(trash)
        content = open(trash, encoding='utf-8').read()
        assert '.' in content
