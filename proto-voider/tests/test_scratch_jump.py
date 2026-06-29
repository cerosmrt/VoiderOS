"""F1 /0: a single '0' scratch portal that moves above the current chapter."""
import os
import types
from unittest.mock import MagicMock

from line_ring import LineRing
from helpers import make_ring_app


def _app(tmp_path, library, current_name):
    """library: list of display names ('.' separators, '0' portals, else chapters)."""
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    void = tmp_path
    (void / 'I').mkdir(exist_ok=True)
    app.void_dir = str(void)
    app.f1_file = str(void / 'I' / '0.txt')
    open(app.f1_file, 'w').close()
    app._library_lines, ring = [], []
    app._library_path_cache = {}
    for name in library:
        if name == '.':
            app._library_lines.append('.'); ring.append('.'); continue
        if name == '0':
            app._library_lines.append('0.txt'); ring.append('0'); continue
        fn = name + '.txt'
        app._library_lines.append(fn); ring.append(name)
        p = str(void / 'I' / fn); open(p, 'w').close()
        app._library_path_cache[fn] = p
    app.book_ring = LineRing(ring)
    app.current_file_path = str(void / 'I' / current_name)
    if not os.path.exists(app.current_file_path):
        open(app.current_file_path, 'w').close()
    app._ipc = MagicMock()
    app.load_doc_lines = MagicMock()
    app._f1_show_current = MagicMock()
    for nm in ('_f1_scratch_jump', '_save_library', '_atomic_write_lines',
               '_library_path'):
        setattr(app, nm, types.MethodType(getattr(FullscreenCircleApp, nm), app))
    return app


def test_creates_portal_above_current_and_switches(tmp_path):
    app = _app(tmp_path, ['.', 'A', 'B'], current_name='B.txt')
    app._f1_scratch_jump()
    # one portal, directly above B
    bi = app._library_lines.index('B.txt')
    assert app._library_lines[bi - 1] == '0.txt'
    assert app._library_lines.count('0.txt') == 1
    assert app.current_file_path == app.f1_file          # switched to scratch
    assert app.book_ring.index == bi - 1                 # parked on the portal


def test_moves_existing_single_portal(tmp_path):
    # portal currently above A; jumping from C moves it above C
    app = _app(tmp_path, ['.', '0', 'A', 'B', 'C'], current_name='C.txt')
    app._f1_scratch_jump()
    assert app._library_lines.count('0.txt') == 1
    ci = app._library_lines.index('C.txt')
    assert app._library_lines[ci - 1] == '0.txt'


def test_consolidates_multiple_portals_to_one(tmp_path):
    app = _app(tmp_path, ['.', '0', 'A', '0', 'B'], current_name='B.txt')
    app._f1_scratch_jump()
    assert app._library_lines.count('0.txt') == 1
    bi = app._library_lines.index('B.txt')
    assert app._library_lines[bi - 1] == '0.txt'


def test_parallel_arrays_stay_aligned(tmp_path):
    app = _app(tmp_path, ['.', '0', 'A', 'B'], current_name='B.txt')
    app._f1_scratch_jump()
    assert len(app._library_lines) == len(app.book_ring.lines)
    # the portal entry/display agree
    pi = app._library_lines.index('0.txt')
    assert app.book_ring.lines[pi] == '0'


def test_noop_when_already_on_scratch(tmp_path):
    app = _app(tmp_path, ['.', 'A', 'B'], current_name='0.txt')
    before = list(app._library_lines)
    app._f1_scratch_jump()
    assert app._library_lines == before
    assert '0.txt' not in app._library_lines  # nothing created
