"""F3 library/structural undo: reorder, rename, delete, merge, split — each one
Ctrl+Z step restores the arrays AND the affected files/I.txt; redo re-applies."""
import os
import types
from unittest.mock import MagicMock

from line_ring import LineRing
from undo_manager import UndoManager
from helpers import make_ring_app


def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return [l.rstrip('\n') for l in f]


_METHODS = (
    '_f3_state', '_f3_undo_begin', '_f3_undo_file', '_f3_undo_commit',
    '_f3_restore', '_read_lines_or_none', '_undo_apply',
    '_save_library', '_atomic_write_lines', '_library_path',
    '_book_swap_entries', '_book_swap_up', '_book_swap_down', '_book_move_block',
    '_book_block_bounds', '_apply_book_order', '_book_try_rename',
    '_library_current_fname', '_book_send_to_zero', '_book_merge_prompt',
    '_book_cancel_merge', '_book_do_merge', '_split_chapter_at_slash',
)


def _f3_app(tmp_path, library, contents=None):
    from new_interface import FullscreenCircleApp
    contents = contents or {}
    app = make_ring_app(['.'])
    (tmp_path / 'I').mkdir(exist_ok=True)
    app.void_dir = str(tmp_path)
    app.f1_file = str(tmp_path / 'I' / '0.txt')
    open(app.f1_file, 'w').close()

    app._library_lines = list(library)
    ring = ['.' if x == '.' else os.path.splitext(x)[0] for x in library]
    app.book_ring = LineRing(ring)
    app._library_path_cache = {}
    for fn in library:
        if fn == '.':
            continue
        p = str(tmp_path / 'I' / fn)
        with open(p, 'w', encoding='utf-8') as f:
            f.write('\n'.join(contents.get(fn, [os.path.splitext(fn)[0]])) + '\n')
        app._library_path_cache[fn] = p

    app.current_file_path = app.f1_file
    app.current_view = 2
    app.config = {}
    app._ipc = MagicMock()
    app.book_view = MagicMock()
    app.book_view.editor.text.return_value = ''
    app._book_pending_new = False
    app._book_pending_merge = False
    app._undo = UndoManager()
    app._undo_last = {}
    app._undo_applying = False
    app._undo_txn = None
    app._f3_txn = None
    app._book_show_editor = MagicMock()
    app._book_refresh_editor = MagicMock()
    app._doc_show_editor = MagicMock()
    app.load_doc_lines = MagicMock()
    app._git_snapshot_void = MagicMock()
    app._book_is_portal = lambda: False
    for nm in _METHODS:
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app


def test_reorder_undo_redo(tmp_path):
    app = _f3_app(tmp_path, ['.', 'A.txt', 'B.txt'])
    app.book_ring.index = 1
    app.book_view.editor.text.return_value = 'A'      # no rename
    app._book_swap_down()
    assert app._library_lines == ['.', 'B.txt', 'A.txt']
    app._undo_apply()
    assert app._library_lines == ['.', 'A.txt', 'B.txt']
    app._undo_apply(redo=True)
    assert app._library_lines == ['.', 'B.txt', 'A.txt']


def test_delete_undo_restores_file_and_zero(tmp_path):
    app = _f3_app(tmp_path, ['.', 'A.txt', 'B.txt'],
                  {'A.txt': ['a1', 'a2'], 'B.txt': ['b1']})
    app.book_ring.index = 1                            # on A
    app._book_send_to_zero()
    assert 'A.txt' not in app._library_lines
    assert not os.path.exists(str(tmp_path / 'I' / 'A.txt'))
    assert _read(app.f1_file) != []                    # lines landed in 0.txt
    app._undo_apply()
    assert app._library_lines == ['.', 'A.txt', 'B.txt']
    assert _read(str(tmp_path / 'I' / 'A.txt')) == ['a1', 'a2']
    assert _read(app.f1_file) == []                    # 0.txt restored


def test_rename_undo(tmp_path):
    app = _f3_app(tmp_path, ['.', 'A.txt'], {'A.txt': ['a1']})
    app.book_ring.index = 1
    app.book_view.editor.text.return_value = 'C'
    app._book_try_rename()
    assert app._library_lines == ['.', 'C.txt']
    assert os.path.exists(str(tmp_path / 'I' / 'C.txt'))
    app._undo_apply()
    assert app._library_lines == ['.', 'A.txt']
    assert os.path.exists(str(tmp_path / 'I' / 'A.txt'))
    assert not os.path.exists(str(tmp_path / 'I' / 'C.txt'))


def test_merge_undo(tmp_path):
    app = _f3_app(tmp_path, ['.', 'A.txt', 'B.txt'],
                  {'A.txt': ['a1', 'a2'], 'B.txt': ['b1']})
    app.book_ring.index = 0                            # on the dot
    app._book_merge_prompt()
    app.book_view.editor.text.return_value = 'M'
    app._book_do_merge()
    assert app._library_lines == ['.', 'M.txt']
    app._undo_apply()
    assert app._library_lines == ['.', 'A.txt', 'B.txt']
    assert _read(str(tmp_path / 'I' / 'A.txt')) == ['a1', 'a2']
    assert not os.path.exists(str(tmp_path / 'I' / 'M.txt'))


def test_split_undo(tmp_path):
    app = _f3_app(tmp_path, ['.', 'MERGED.txt'],
                  {'MERGED.txt': ['a', '/X', 'b', '/Y']})
    app.current_file_path = app._library_path_cache['MERGED.txt']
    app.line_ring = LineRing(['a', '/X', 'b', '/Y'])
    app.book_ring.index = 1
    app._split_chapter_at_slash()
    assert 'X.txt' in app._library_lines and 'Y.txt' in app._library_lines
    assert not os.path.exists(str(tmp_path / 'I' / 'MERGED.txt'))
    app._undo_apply()
    assert app._library_lines == ['.', 'MERGED.txt']
    assert _read(str(tmp_path / 'I' / 'MERGED.txt')) == ['a', '/X', 'b', '/Y']
    assert not os.path.exists(str(tmp_path / 'I' / 'X.txt'))
