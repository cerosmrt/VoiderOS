"""F3 cursor persistence: re-entering F3 (in-session or after reopen) lands on the
remembered chapter, never snapping to the top of the book."""
import types

from line_ring import LineRing
from helpers import make_ring_app


def _app(library, last_index=None, last_entry=None, f2_file='chap.txt'):
    from new_interface import FullscreenCircleApp
    app = make_ring_app(['.'])
    app._library_lines = list(library)
    app.book_ring = LineRing(['.' if x == '.' else x[:-4] for x in library])
    app.f2_file = '/void/I/' + f2_file
    app._book_last_index = last_index
    app._book_last_entry = last_entry
    app._resolve_f3_index = types.MethodType(
        FullscreenCircleApp._resolve_f3_index, app)
    return app


def test_exact_remembered_entry_wins_over_active():
    app = _app(['.', 'A.txt', 'B.txt'], last_index=2, last_entry='B.txt')
    assert app._resolve_f3_index('A.txt') == 2      # remembered B, not active A


def test_remembered_entry_found_by_name_after_reorder():
    app = _app(['.', 'B.txt', 'A.txt'], last_index=2, last_entry='B.txt')  # B now at 1
    assert app._resolve_f3_index('A.txt') == 1


def test_no_memory_falls_back_to_active_not_top():
    app = _app(['.', 'A.txt', 'B.txt'], last_index=None, last_entry=None)
    assert app._resolve_f3_index('B.txt') == 2      # the reopen bug: must NOT be 0


def test_dot_position_restored_by_exact_index():
    app = _app(['.', 'A.txt', '.', 'B.txt'], last_index=2, last_entry='.')
    assert app._resolve_f3_index('A.txt') == 2      # the second '.'


def test_unknown_active_and_no_memory_returns_top():
    app = _app(['.', 'A.txt'], last_index=None, last_entry=None, f2_file='gone.txt')
    assert app._resolve_f3_index('gone.txt') == 0
