"""F5 → '>' → F3 → Enter: MOVE the current paragraph out of the active file and
append it to the chosen chapter, then return to F5 on the next paragraph."""
import os
import types
from unittest.mock import MagicMock

from line_ring import LineRing
from undo_manager import UndoManager
from helpers import make_ring_app

_METHODS = (
    '_f5_begin_send', '_f5_cancel_send', '_f5_confirm_send', '_f5_collapse_dots',
    '_f5_tokens', '_f5_flatten', '_f5_para_positions', '_f5_para_count',
    '_f5_refresh', '_undo_begin', '_undo_commit', '_undo_capture',
    '_undo_trackable', '_atomic_write_lines', 'auto_save_circular',
    '_read_lines_or_none', '_rescue_on_large_shrink', '_library_current_fname',
)


def _read(p):
    with open(p, 'r', encoding='utf-8') as f:
        return [l.rstrip('\n') for l in f]


def _send_app(tmp_path, source_lines, library=('.', 'Dest.txt')):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(list(source_lines))
    (tmp_path / 'I').mkdir(exist_ok=True)
    app.void_dir = str(tmp_path)
    app.f1_file = str(tmp_path / 'I' / '0.txt'); open(app.f1_file, 'w').close()

    src = tmp_path / 'I' / 'src.txt'
    src.write_text('\n'.join(source_lines) + '\n', encoding='utf-8')
    app.current_file_path = str(src)
    app.line_ring = LineRing(list(source_lines))

    app._library_lines = list(library)
    app.book_ring = LineRing(['.' if x == '.' else x[:-4] for x in library])
    app._library_path_cache = {}
    for fn in library:
        if fn == '.':
            continue
        p = tmp_path / 'I' / fn
        if not p.exists():
            p.write_text('', encoding='utf-8')
        app._library_path_cache[fn] = str(p)

    app._ipc = MagicMock()
    app._undo = UndoManager(); app._undo_last = {}
    app._undo_applying = False; app._undo_txn = None; app._f3_txn = None
    app.reorder_view = None
    app.switched = []
    app.switch_to_view = lambda v: app.switched.append(v)
    app._git_snapshot_void = MagicMock()
    app._book_is_portal = lambda *a: False
    app._f5_send_mode = False
    app._f5_send_para = 0
    app._f5_send_source = app.current_file_path
    app._f5_para_idx = 0
    for nm in _METHODS:
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app, str(src)


def _target(app, fname):
    app.book_ring.index = app._library_lines.index(fname)


def test_send_moves_paragraph_to_target(tmp_path):
    app, src = _send_app(tmp_path, ['.', 'a', '.', 'b', '.', 'c'])
    app._f5_send_mode = True
    app._f5_send_para = 1                      # 'b'
    _target(app, 'Dest.txt')
    app._f5_confirm_send()

    assert _read(str(tmp_path / 'I' / 'Dest.txt')) == ['b']   # appended to target
    assert 'b' not in _read(src)                              # removed from source
    assert app._f5_para_idx == 1                              # now on 'c' (the next)
    assert app._f5_send_mode is False
    assert app.switched[-1] == 4                              # back to F5


def test_send_appends_after_existing_target_content(tmp_path):
    app, src = _send_app(tmp_path, ['.', 'a', '.', 'b'])
    with open(tmp_path / 'I' / 'Dest.txt', 'w', encoding='utf-8') as f:
        f.write('viejo\n')
    app._f5_send_mode = True
    app._f5_send_para = 0                       # 'a'
    _target(app, 'Dest.txt')
    app._f5_confirm_send()
    assert _read(str(tmp_path / 'I' / 'Dest.txt')) == ['viejo', '.', 'a']


def test_send_to_separator_is_ignored(tmp_path):
    app, src = _send_app(tmp_path, ['.', 'a', '.', 'b'], library=('.', 'Dest.txt'))
    app._f5_send_mode = True
    app._f5_send_para = 0
    app.book_ring.index = 0                      # on the '.' separator
    app._f5_confirm_send()
    assert _read(str(tmp_path / 'I' / 'Dest.txt')) == []      # untouched (empty)
    assert app._f5_send_mode is True             # still choosing


def test_send_to_same_file_ignored(tmp_path):
    app, src = _send_app(tmp_path, ['.', 'a', '.', 'b'], library=('.', 'src.txt'))
    app._f5_send_mode = True
    app._f5_send_para = 0
    _target(app, 'src.txt')                      # same as source
    app._f5_confirm_send()
    assert _read(src) == ['.', 'a', '.', 'b']    # unchanged
    assert app._f5_send_mode is True


def test_cancel_send_returns_without_moving(tmp_path):
    app, src = _send_app(tmp_path, ['.', 'a', '.', 'b'])
    app._f5_send_mode = True
    app._f5_cancel_send()
    assert app._f5_send_mode is False
    assert app.switched == [4]
    assert _read(src) == ['.', 'a', '.', 'b']
