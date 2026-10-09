"""Ctrl+Z must leave the cursor where it was, not jump to the last-saved nav line
(which lags by one, so undo appeared to move the cursor up a line)."""
import json
import types
from unittest.mock import MagicMock

from undo_manager import UndoManager
from helpers import make_ring_app


def test_undo_preserves_cursor_line(tmp_path):
    from new_interface import FullscreenCircleApp
    p = tmp_path / 'chap.txt'
    p.write_text('.\na\nb\nc\nd\n', encoding='utf-8')

    app = make_ring_app(['.', 'a', 'b', 'c', 'd'], tmp_file=str(p))
    app.book_dir = str(tmp_path)
    app.current_view = 1
    app._ipc = MagicMock()
    app._doc_show_editor = MagicMock()
    app._undo = UndoManager()
    app._undo_last = {}
    app._undo_applying = False
    app._undo_txn = None
    app._f3_txn = None
    for nm in ('_undo_apply', '_undo_refresh', '_undo_cursor_line', 'load_doc_lines',
               '_restore_last_line', '_atomic_write_lines', '_undo_capture',
               '_read_lines_or_none', '_last_lines_path'):
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))

    # _last_lines.json lags by one line (saved 0 while the user is on line 3).
    (tmp_path / '_last_lines.json').write_text(json.dumps({'chap.txt': 0}))
    app.line_ring.index = 3

    # Something to undo: a line was added; undo restores the shorter version.
    app._undo.record(str(p), ['.', 'a', 'b', 'c', 'd'],
                     ['.', 'a', 'b', 'cc', 'd'])
    app._undo_apply()

    assert app.line_ring.index == 3      # stayed put, did NOT jump to 0


def _app(tmp_path, body):
    from new_interface import FullscreenCircleApp
    p = tmp_path / 'chap.txt'
    p.write_text('\n'.join(body) + '\n', encoding='utf-8')
    app = make_ring_app(list(body), tmp_file=str(p))
    app.book_dir = str(tmp_path)
    app.current_view = 1
    app._ipc = MagicMock()
    app._doc_show_editor = MagicMock()
    app._undo = UndoManager()
    app._undo_last = {}
    app._undo_applying = False
    app._undo_txn = None
    app._f3_txn = None
    for nm in ('_undo_apply', '_undo_refresh', 'load_doc_lines',
               '_restore_last_line', '_atomic_write_lines', '_undo_capture',
               '_read_lines_or_none', '_last_lines_path', '_undo_cursor_line'):
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app, p


def test_undo_and_redo_go_to_the_edited_line(tmp_path):
    before = ['.', 'a', 'b', 'c', 'd']
    after = ['.', 'a', 'b', 'cc', 'd']
    app, p = _app(tmp_path, before)
    app._undo.record(str(p), before, after)
    app.line_ring.index = 1                  # user wandered off to line 1
    app._undo_apply()
    assert app.line_ring.index == 3          # back on the line that changed
    app.line_ring.index = 1
    app._undo_apply(redo=True)
    assert app.line_ring.index == 3


def test_undo_of_appended_line_clamps_cursor_to_last_line(tmp_path):
    before = ['.', 'a', 'b']
    after = ['.', 'a', 'b', 'c']
    app, p = _app(tmp_path, before)
    app._undo.record(str(p), before, after)
    app.line_ring.index = 0
    app._undo_apply()
    assert app.line_ring.index == 2          # line 3 no longer exists
