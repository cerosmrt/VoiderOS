"""F5 in-view chapter picker: Right opens a type-to-filter picker; Enter/→ MOVES
the current paragraph to the chosen (or newly created) chapter and stays in F5."""
import os
import types
from unittest.mock import MagicMock

from line_ring import LineRing
from undo_manager import UndoManager
from helpers import make_ring_app

_METHODS = (
    '_f5_move_current_to', '_f5_collapse_dots', '_f5_tokens', '_f5_flatten',
    '_f5_para_positions', '_f5_para_count', '_f5_refresh', '_f5_open_picker',
    '_f5_close_picker', '_f5_pick_matches', '_f5_pick_target', '_f5_pick_filter_add',
    '_f5_pick_filter_backspace', '_f5_pick_cycle', '_f5_pick_confirm',
    '_undo_begin', '_undo_commit', '_undo_capture', '_undo_trackable',
    '_atomic_write_lines', 'auto_save_circular', '_read_lines_or_none',
    '_rescue_on_large_shrink', '_save_library', '_library_path',
)


def _read(p):
    with open(p, 'r', encoding='utf-8') as f:
        return [l.rstrip('\n') for l in f]


def _app(tmp_path, source_lines, library=('.', 'Dest.txt', 'Other.txt')):
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
    app._git_snapshot_void = MagicMock()
    app._f5_para_idx = 0
    app._f5_picker_open = False
    app._f5_pick_filter = ''
    app._f5_pick_match_idx = 0
    for nm in _METHODS:
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app, str(src)


# ── move core ─────────────────────────────────────────────────────────────────

def test_move_current_to_moves_and_advances(tmp_path):
    app, src = _app(tmp_path, ['.', 'a', '.', 'b', '.', 'c'])
    app._f5_para_idx = 1                         # 'b'
    ok = app._f5_move_current_to(str(tmp_path / 'I' / 'Dest.txt'))
    assert ok is True
    assert _read(str(tmp_path / 'I' / 'Dest.txt')) == ['b']
    assert 'b' not in _read(src)
    assert app._f5_para_idx == 1                 # now on 'c' (the next)


def test_move_to_same_file_ignored(tmp_path):
    app, src = _app(tmp_path, ['.', 'a', '.', 'b'])
    assert app._f5_move_current_to(src) is False
    assert _read(src) == ['.', 'a', '.', 'b']


# ── picker filter / target ────────────────────────────────────────────────────

def test_pick_matches_filters_and_excludes(tmp_path):
    app, src = _app(tmp_path, ['.', 'a'],
                    library=('.', 'Dest.txt', 'Other.txt', '0.txt', 'src.txt'))
    app._f5_pick_filter = 'o'
    got = [d for _, d in app._f5_pick_matches()]
    assert got == ['Other']                      # 'o' matches Other; not 0/./src


def test_pick_target_create_new(tmp_path):
    app, src = _app(tmp_path, ['.', 'a'])
    app._f5_pick_filter = 'Nuevo Capitulo'
    t = app._f5_pick_target()
    assert t['is_new'] is True and t['fname'] == 'Nuevo Capitulo.txt'


# ── confirm from the picker ───────────────────────────────────────────────────

def test_confirm_sends_to_existing(tmp_path):
    app, src = _app(tmp_path, ['.', 'a', '.', 'b'])
    app._f5_open_picker()
    app._f5_pick_filter = 'Dest'
    app._f5_para_idx = 0                          # 'a'
    app._f5_pick_confirm()
    assert _read(str(tmp_path / 'I' / 'Dest.txt')) == ['a']
    assert app._f5_picker_open is False           # closed after send


def test_confirm_creates_new_chapter_and_sends(tmp_path):
    app, src = _app(tmp_path, ['.', 'a', '.', 'b'])
    app._f5_open_picker()
    app._f5_pick_filter = 'Fresh'
    app._f5_para_idx = 0
    app._f5_pick_confirm()
    assert os.path.exists(str(tmp_path / 'I' / 'Fresh.txt'))
    assert _read(str(tmp_path / 'I' / 'Fresh.txt')) == ['a']
    assert 'Fresh.txt' in app._library_lines      # new library entry
    assert app._f5_picker_open is False


def test_close_picker(tmp_path):
    app, src = _app(tmp_path, ['.', 'a', '.', 'b'])
    app._f5_open_picker()
    assert app._f5_picker_open is True
    app._f5_close_picker()
    assert app._f5_picker_open is False
    assert _read(src) == ['.', 'a', '.', 'b']     # nothing moved
